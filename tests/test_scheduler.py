from datetime import datetime

import pytest

from relay import store as st
from relay.scheduler import LAST_DAY, Schedule, ScheduleError, build, due_slot, next_slot, parse_numbers, tick
from relay.seed import VENDORS, seed

# Wednesday 21 October 2026
WEDNESDAY = datetime(2026, 10, 21)
START = datetime(2026, 10, 1, 6, 0)  # a Thursday


def weekdays_at_six(active: bool = True) -> Schedule:
    return Schedule(1, "weekly", START, days=(1, 2, 3, 4, 5), active=active)


def weekly_columns(days: str = "1,2,3,4,5") -> dict:
    return build("weekly", "2026-10-01", "06:00", days=days.split(","))


def test_numbers_are_cleaned_up():
    assert parse_numbers(["5", "1", "1", "9", "x"], 1, 7) == (1, 5)
    assert parse_numbers("1,15,32", 1, LAST_DAY) == (1, 15, 32)
    assert parse_numbers(None, 1, 7) == ()


def test_the_due_time_is_the_latest_one_that_arrived():
    schedule = weekdays_at_six()

    assert due_slot([schedule], WEDNESDAY.replace(hour=5, minute=59)) is None
    assert due_slot([schedule], WEDNESDAY.replace(hour=6)) == WEDNESDAY.replace(hour=6)
    # Missed while the computer was off: still runs within 30 minutes, not later
    assert due_slot([schedule], WEDNESDAY.replace(hour=6, minute=30)) == WEDNESDAY.replace(hour=6)
    assert due_slot([schedule], WEDNESDAY.replace(hour=6, minute=31)) is None


def test_only_the_chosen_days_and_active_schedules_count():
    saturday = datetime(2026, 10, 24, 6, 0)
    assert due_slot([weekdays_at_six()], saturday) is None
    assert due_slot([weekdays_at_six(active=False)], WEDNESDAY.replace(hour=6)) is None


def test_next_run_crosses_to_the_next_chosen_day():
    friday_night = datetime(2026, 10, 23, 20, 0)
    assert next_slot([weekdays_at_six()], friday_night) == datetime(2026, 10, 26, 6, 0)  # Monday
    assert next_slot([], friday_night) is None


def test_once_runs_only_on_its_date_and_time():
    once = Schedule(1, "once", datetime(2026, 10, 21, 9, 30))
    assert next_slot([once], datetime(2026, 10, 1)) == datetime(2026, 10, 21, 9, 30)
    assert next_slot([once], datetime(2026, 10, 21, 9, 30)) is None  # already past


def test_daily_every_n_days_counts_from_the_start():
    every_two = Schedule(1, "daily", START, every=2)  # 1, 3, 5... October
    assert next_slot([every_two], datetime(2026, 10, 1, 7)) == datetime(2026, 10, 3, 6)
    assert next_slot([every_two], datetime(2026, 9, 1)) == START  # nothing before the start


def test_weekly_every_n_weeks_skips_the_weeks_between():
    # Mondays every 2 weeks from the week of 1 October (Monday 28 September): 12 Oct, 26 Oct...
    schedule = Schedule(1, "weekly", START, every=2, days=(1,))
    assert next_slot([schedule], datetime(2026, 10, 2)) == datetime(2026, 10, 12, 6)
    assert next_slot([schedule], datetime(2026, 10, 13)) == datetime(2026, 10, 26, 6)


def test_monthly_on_chosen_days_and_the_last_day():
    schedule = Schedule(1, "monthly", START, months=(2, 11), month_days=(15, LAST_DAY))
    assert next_slot([schedule], datetime(2026, 10, 1)) == datetime(2026, 11, 15, 6)
    assert next_slot([schedule], datetime(2026, 11, 16)) == datetime(2026, 11, 30, 6)
    assert next_slot([schedule], datetime(2026, 12, 1)) == datetime(2027, 2, 15, 6)
    assert next_slot([schedule], datetime(2027, 2, 16)) == datetime(2027, 2, 28, 6)  # last day of February


def test_repetition_runs_every_few_minutes_for_the_duration():
    # Every 30 minutes for 1 hour from 23:30: 23:30 and 00:00 of the next day (like Windows)
    schedule = Schedule(1, "daily", START.replace(hour=23, minute=30), repeat_every=30, repeat_for=60)
    assert due_slot([schedule], datetime(2026, 10, 22, 0, 10)) == datetime(2026, 10, 22, 0, 0)
    assert next_slot([schedule], datetime(2026, 10, 22, 0, 0)) == datetime(2026, 10, 22, 23, 30)


def test_nothing_runs_once_it_expires():
    schedule = Schedule(1, "daily", START, repeat_every=60, repeat_for=720, expires=datetime(2026, 10, 21, 9, 0))
    assert due_slot([schedule], WEDNESDAY.replace(hour=8, minute=10)) == WEDNESDAY.replace(hour=8)
    assert due_slot([schedule], WEDNESDAY.replace(hour=9, minute=10)) is None
    assert next_slot([schedule], WEDNESDAY.replace(hour=8)) is None


def test_build_checks_the_form():
    now = datetime(2026, 10, 21, 12, 0)
    cases = [
        (("hourly", "2026-10-21", "06:00"), {}, "schedule_bad_kind"),
        (("daily", "2026-13-01", "06:00"), {}, "schedule_bad_start"),
        (("once", "2026-10-21", "11:59"), {}, "schedule_past"),
        (("daily", "2026-10-21", "06:00"), {"every": "0"}, "schedule_bad_every"),
        (("weekly", "2026-10-21", "06:00"), {}, "schedule_no_days"),
        (("monthly", "2026-10-21", "06:00"), {"month_days": ["1"]}, "schedule_no_months"),
        (("monthly", "2026-10-21", "06:00"), {"months": ["1"]}, "schedule_no_month_days"),
        (("daily", "2026-10-21", "06:00"), {"repeat": True, "repeat_every": "7", "repeat_for": "60"}, "schedule_bad_repeat"),
        (("daily", "2026-10-21", "06:00"), {"expires": True, "expires_date": "2026-10-20"}, "schedule_bad_expiry"),
    ]
    for args, options, key in cases:
        with pytest.raises(ScheduleError) as error:
            build(*args, now=now, **options)
        assert error.value.key == key

    columns = build("monthly", "2026-10-21", "06:00", name="  Cierre  ", months=["12", "1", "13"], month_days=["32", "1"],
                    repeat=True, repeat_every="15", repeat_for="60", expires=True, expires_date="2027-01-31", now=now)
    assert columns == {"name": "Cierre", "kind": "monthly", "start_at": "2026-10-21T06:00", "every": 1, "days": "",
                       "months": "1,12", "month_days": "1,32", "repeat_every": 15, "repeat_for": 60,
                       "expires_at": "2027-01-31T23:59"}


def test_each_time_runs_once(settings, store):
    store.add_schedule(weekly_columns())
    calls = []
    runner = lambda *args: calls.append(args) or st.OK  # noqa: E731

    assert tick(settings, store, WEDNESDAY.replace(hour=6), runner) == st.OK
    assert tick(settings, store, WEDNESDAY.replace(hour=6, minute=1), runner) is None  # same time, already ran
    assert tick(settings, store, WEDNESDAY.replace(hour=9), runner) is None  # nothing due
    assert len(calls) == 1 and calls[0][2] == "scheduled"
    assert store.get_meta("scheduler_checked_at")  # the screen can tell it is running


def test_a_time_is_retried_while_a_manual_sync_is_running(settings, store):
    store.add_schedule(weekly_columns("3"))
    answers = iter(["busy", st.OK])
    runner = lambda *args: next(answers)  # noqa: E731

    assert tick(settings, store, WEDNESDAY.replace(hour=6), runner) == "busy"
    assert tick(settings, store, WEDNESDAY.replace(hour=6, minute=1), runner) == st.OK


def test_paused_schedules_do_not_run(settings, store):
    schedule_id = store.add_schedule(weekly_columns("3"))
    store.set_schedule_active(schedule_id, False)

    assert tick(settings, store, WEDNESDAY.replace(hour=6), lambda *args: st.OK) is None


def test_old_schedules_of_days_and_times_are_dropped(tmp_path):
    import sqlite3
    from contextlib import closing

    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE schedules (id INTEGER PRIMARY KEY, days TEXT, times TEXT, active INTEGER, created_at TEXT)")
        db.execute("INSERT INTO schedules VALUES (1, '1,2,3', '06:00', 1, 'x')")

    store = st.Store(path)
    assert store.schedules() == []
    assert store.add_schedule(weekly_columns()) == 1


def test_seed_loads_the_vendors_once(store):
    assert seed(store) == list(VENDORS)
    assert store.vendor(410010)["name"] == "HIRUTA MEXICO SA DE CV MXN"
    assert seed(store) == []  # running it again adds nothing
    assert len(store.vendors()) == len(VENDORS)
