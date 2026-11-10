"""Runs the sync when the schedules of the "Programación" screen say so.

Like Laravel's scheduler: something calls it every minute and it decides whether
a sync is due (the sync itself is relay.sync.run_sync, the "job").

    .venv\\Scripts\\python.exe -m relay.scheduler          one check, for Windows Task Scheduler every minute
    .venv\\Scripts\\python.exe -m relay.scheduler --work   keeps checking every minute (on your computer)

Each schedule works like a trigger of Windows Task Scheduler: once, daily, weekly
or monthly from a start date and time, optionally repeated every few minutes for
a while, until it expires. Times are this computer's local time. A time that was
missed because the computer was off still runs if the scheduler checks in within
30 minutes.
"""

import argparse
import logging
import sys
import time as clock
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from relay import store as st
from relay.config import Settings, get_settings
from relay.logs import setup_logging
from relay.sync import run_sync

log = logging.getLogger("relay.scheduler")

GRACE = timedelta(minutes=30)  # how late a missed time can still run
LAST_CHECK = "scheduler_checked_at"
HORIZON = timedelta(days=400)  # how far ahead the next run is looked for (a monthly one can be a year away)

ONCE, DAILY, WEEKLY, MONTHLY = "once", "daily", "weekly", "monthly"
KINDS = (ONCE, DAILY, WEEKLY, MONTHLY)
LAST_DAY = 32  # in month_days: the last day of the month, whatever its number
REPEAT_EVERY = (5, 10, 15, 30, 60)  # minutes, the choices of Windows Task Scheduler
REPEAT_FOR = (15, 30, 60, 720, 1440)
MAX_EVERY = {DAILY: 365, WEEKLY: 52}
MAX_NAME = 60


class ScheduleError(ValueError):
    """A form that can't be saved; `key` is the message to show (relay.i18n)."""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


@dataclass(frozen=True)
class Schedule:
    id: int
    kind: str
    start: datetime
    every: int = 1  # every N days (daily) or weeks (weekly)
    days: tuple[int, ...] = ()  # weekly: 1 = Monday ... 7 = Sunday
    months: tuple[int, ...] = ()  # monthly: 1 = January ... 12 = December
    month_days: tuple[int, ...] = ()  # monthly: 1 ... 31, LAST_DAY
    repeat_every: int = 0  # minutes; 0 = runs once at the start time
    repeat_for: int = 0  # minutes, from the start time
    expires: datetime | None = None
    active: bool = True
    name: str = ""

    @classmethod
    def from_row(cls, row) -> "Schedule":
        return cls(
            id=row["id"],
            kind=row["kind"],
            start=datetime.fromisoformat(row["start_at"]),
            every=row["every"] or 1,
            days=parse_numbers(row["days"], 1, 7),
            months=parse_numbers(row["months"], 1, 12),
            month_days=parse_numbers(row["month_days"], 1, LAST_DAY),
            repeat_every=row["repeat_every"] or 0,
            repeat_for=row["repeat_for"] or 0,
            expires=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            active=bool(row["active"]),
            name=row["name"] or "",
        )

    def occurs_on(self, day: date) -> bool:
        """Whether it starts on this day."""
        first = self.start.date()
        if day < first:
            return False
        if self.kind == ONCE:
            return day == first
        if self.kind == DAILY:
            return (day - first).days % self.every == 0
        if self.kind == WEEKLY:
            weeks = ((day - timedelta(days=day.weekday())) - (first - timedelta(days=first.weekday()))).days // 7
            return day.isoweekday() in self.days and weeks % self.every == 0
        last = (day + timedelta(days=1)).month != day.month
        return day.month in self.months and (day.day in self.month_days or (last and LAST_DAY in self.month_days))

    def runs_from(self, day: date) -> Iterator[datetime]:
        """Its runs that start on this day; repetitions can go past midnight."""
        if not self.occurs_on(day):
            return
        first = datetime.combine(day, self.start.time())
        # Like Windows: "every 30 minutes for 1 hour" runs at :00 and :30
        for offset in range(0, self.repeat_for, self.repeat_every) if self.repeat_every else (0,):
            moment = first + timedelta(minutes=offset)
            if self.expires and moment >= self.expires:
                return
            yield moment


def parse_numbers(text: str | Iterable | None, low: int, high: int) -> tuple[int, ...]:
    """"5,1,1,x,9" -> (1, 5) for 1..7: the numbers in range, sorted, without repeats."""
    values = (text or "").split(",") if isinstance(text, str) or text is None else text
    return tuple(sorted({int(v) for v in values if str(v).strip().isdigit() and low <= int(v) <= high}))


def parse_times(text: str | Iterable) -> tuple[time, ...]:
    """Times of the schedules saved before triggers existed ("06:00,14:00"), still in the history."""
    values = text.split(",") if isinstance(text, str) else text
    times = set()
    for value in values:
        try:
            times.add(time.fromisoformat(str(value).strip()[:5]).replace(second=0, microsecond=0))
        except ValueError:
            continue
    return tuple(sorted(times))


def format_numbers(numbers: Iterable[int]) -> str:
    return ",".join(str(n) for n in numbers)


def build(kind: str, start_date: str, start_time: str, *, name: str = "", every: str = "1",
          days: Iterable = (), months: Iterable = (), month_days: Iterable = (),
          repeat: bool = False, repeat_every: str = "", repeat_for: str = "",
          expires: bool = False, expires_date: str = "", expires_time: str = "",
          now: datetime | None = None) -> dict:
    """The columns of a new schedule from the form, or ScheduleError with what is wrong."""
    if kind not in KINDS:
        raise ScheduleError("schedule_bad_kind")
    try:
        start = datetime.combine(date.fromisoformat(start_date), time.fromisoformat(start_time[:5]))
    except ValueError:
        raise ScheduleError("schedule_bad_start") from None
    if kind == ONCE and start < (now or datetime.now()).replace(second=0, microsecond=0):
        raise ScheduleError("schedule_past")

    columns = {"name": name.strip()[:MAX_NAME], "kind": kind, "start_at": start.isoformat(timespec="minutes"),
               "every": 1, "days": "", "months": "", "month_days": "", "repeat_every": 0, "repeat_for": 0,
               "expires_at": None}

    if kind in MAX_EVERY:
        if not every.strip().isdigit() or not 1 <= int(every) <= MAX_EVERY[kind]:
            raise ScheduleError("schedule_bad_every")
        columns["every"] = int(every)
    if kind == WEEKLY:
        columns["days"] = format_numbers(parse_numbers(days, 1, 7))
        if not columns["days"]:
            raise ScheduleError("schedule_no_days")
    if kind == MONTHLY:
        columns["months"] = format_numbers(parse_numbers(months, 1, 12))
        columns["month_days"] = format_numbers(parse_numbers(month_days, 1, LAST_DAY))
        if not columns["months"]:
            raise ScheduleError("schedule_no_months")
        if not columns["month_days"]:
            raise ScheduleError("schedule_no_month_days")

    if repeat:
        if not (repeat_every.isdigit() and int(repeat_every) in REPEAT_EVERY
                and repeat_for.isdigit() and int(repeat_for) in REPEAT_FOR):
            raise ScheduleError("schedule_bad_repeat")
        columns["repeat_every"], columns["repeat_for"] = int(repeat_every), int(repeat_for)

    if expires:
        try:
            end = datetime.combine(date.fromisoformat(expires_date), time.fromisoformat((expires_time or "23:59")[:5]))
        except ValueError:
            raise ScheduleError("schedule_bad_expiry") from None
        if end <= start:
            raise ScheduleError("schedule_bad_expiry")
        columns["expires_at"] = end.isoformat(timespec="minutes")

    return columns


def slots(schedules: Iterable[Schedule], start: datetime, end: datetime) -> Iterator[datetime]:
    """Every scheduled time from `start` to `end` (both included), oldest first, a day at a time."""
    schedules = [schedule for schedule in schedules if schedule.active]
    day = start.date()
    while day <= end.date():
        # Repetitions started the day before can still be running after midnight
        found = {
            moment
            for schedule in schedules
            for started in (day - timedelta(days=1), day)
            for moment in schedule.runs_from(started)
            if moment.date() == day and start <= moment <= end
        }
        yield from sorted(found)
        day += timedelta(days=1)


def due_slot(schedules: Iterable[Schedule], now: datetime, grace: timedelta = GRACE) -> datetime | None:
    """The latest scheduled time that has arrived, if it is not older than `grace`."""
    due = list(slots(schedules, now - grace, now))
    return due[-1] if due else None


def next_slot(schedules: Iterable[Schedule], now: datetime) -> datetime | None:
    """The next scheduled time after `now`."""
    return next(slots(schedules, now + timedelta(minutes=1), now + HORIZON), None)


def tick(settings: Settings, store: st.Store, now: datetime | None = None, runner=run_sync) -> str | None:
    """One check: runs the sync when a scheduled time is due. Returns the status
    of the run, or None when nothing was due."""
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    store.set_meta(LAST_CHECK, datetime.now(UTC).isoformat(timespec="seconds"))

    schedules = [Schedule.from_row(row) for row in store.schedules(only_active=True)]
    slot = due_slot(schedules, now)
    if slot is None:
        return None

    key = slot.isoformat(timespec="minutes")
    if not store.claim_slot(key):
        return None  # this time already ran (or another check is running it)

    log.info("Scheduled sync for %s", key)
    status = runner(settings, store, "scheduled")
    if status == "busy":
        # A sync started by hand is running: try this time again on the next check
        store.release_slot(key)
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m relay.scheduler", description=__doc__.splitlines()[0])
    parser.add_argument("--work", action="store_true", help="keep checking every minute until stopped (Ctrl+C)")
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging(settings)
    store = st.Store(settings.database_path)

    if not args.work:
        status = tick(settings, store)
        return 0 if status in (None, st.OK, "busy") else 1

    print("Supply Relay: revisando la programación cada minuto. Ctrl+C para detener.")
    try:
        while True:
            try:
                tick(settings, store)
            except Exception:
                log.exception("Scheduler check failed")
            # Wake up at the start of the next minute
            clock.sleep(60 - datetime.now().second + 0.5)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
