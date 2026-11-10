"""History filters and the text of each event, shared by the screen and the Excel export."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from relay import store as st

SYNC_TITLES = {st.OK: "sync_ok", st.PARTIAL: "sync_partial", st.ERROR: "sync_error", st.RUNNING: "sync_running"}
STATUS_LABELS = {st.OK: "status_ok", st.PARTIAL: "status_partial", st.ERROR: "status_error", st.RUNNING: "status_running"}


@dataclass
class HistoryFilter:
    vendor: str = ""
    start: date | None = None
    end: date | None = None

    @classmethod
    def from_query(cls, vendor: str | None, start: str | None, end: str | None) -> "HistoryFilter":
        def parse(value: str | None) -> date | None:
            try:
                return date.fromisoformat(value) if value else None
            except ValueError:
                return None

        digits = "".join(ch for ch in (vendor or "") if ch.isdigit())[:8]
        return cls(digits, parse(start), parse(end))

    @property
    def active(self) -> bool:
        return bool(self.vendor or self.start or self.end)

    def _bounds(self) -> tuple[str | None, datetime | None, datetime | None]:
        # Dates are days of this computer's clock: from 00:00 of `start` to the end of `end`
        local = datetime.now().astimezone().tzinfo
        start = datetime.combine(self.start, time.min, local) if self.start else None
        end = datetime.combine(self.end + timedelta(days=1), time.min, local) if self.end else None
        return self.vendor or None, start, end

    def search(self, store: st.Store, limit: int | None = None) -> list:
        return store.search_events(*self._bounds(), limit=limit)

    def page(self, store: st.Store, number: int, size: int) -> "Page":
        total = store.count_events(*self._bounds())
        pages = max(1, -(-total // size))
        number = min(max(1, number), pages)  # an out-of-range page shows the closest one
        items = store.search_events(*self._bounds(), limit=size, offset=(number - 1) * size)
        return Page(items, number, pages, total, size)

    def query(self) -> dict[str, str]:
        params = {"vendor": self.vendor, "desde": self.start, "hasta": self.end}
        return {key: str(value) for key, value in params.items() if value}


@dataclass
class Page:
    items: list
    number: int
    pages: int
    total: int
    size: int

    @property
    def first(self) -> int:
        return (self.number - 1) * self.size + 1 if self.total else 0

    @property
    def last(self) -> int:
        return min(self.number * self.size, self.total)

    def numbers(self) -> list[int | None]:
        """Page links to show: first, last and two around the current one; None is a gap (…)."""
        wanted = {1, self.pages, *range(self.number - 2, self.number + 3)}
        shown = sorted(n for n in wanted if 1 <= n <= self.pages)
        result: list[int | None] = []
        for n in shown:
            if result and n - result[-1] > 1:
                result.append(None)
            result.append(n)
        return result


def title_key(event) -> str:
    """Translation key of the event title, without the vendor number."""
    if event["kind"] == st.SYNC:
        return SYNC_TITLES.get(event["status"], "sync_running")
    return f"title_{event['kind']}"


def origin_key(event) -> str | None:
    """Translation key of who started a sync; None for a user name."""
    if event["kind"] == st.SYNC:
        return "trigger_manual" if event["actor"] == "manual" else "trigger_scheduled"
    return None
