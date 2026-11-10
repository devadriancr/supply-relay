"""Local SQLite database: vendors to sync, the result of each run, the sync
schedules and a lock so a scheduled run and the "sync now" button never run at
the same time."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS vendors (
    number        INTEGER PRIMARY KEY,
    name          TEXT,
    active        INTEGER NOT NULL DEFAULT 1,
    added_at      TEXT NOT NULL,
    last_sync_at  TEXT,
    last_status   TEXT,
    last_message  TEXT,
    last_rows     INTEGER
);

CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger      TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL,
    message      TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    at       TEXT NOT NULL,
    kind     TEXT NOT NULL,
    vendor   INTEGER,
    status   TEXT,
    message  TEXT,
    actor    TEXT
);

CREATE TABLE IF NOT EXISTS lock (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    owner        TEXT NOT NULL,
    acquired_at  TEXT NOT NULL
);

-- When to sync, like a trigger of Windows Task Scheduler (relay.scheduler.Schedule)
CREATE TABLE IF NOT EXISTS schedules (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL DEFAULT '',
    kind          TEXT NOT NULL,              -- once | daily | weekly | monthly
    start_at      TEXT NOT NULL,              -- local "2026-11-02T06:00"
    every         INTEGER NOT NULL DEFAULT 1, -- every N days (daily) or weeks (weekly)
    days          TEXT NOT NULL DEFAULT '',   -- weekly: "1,2,3,4,5" (1 = Monday)
    months        TEXT NOT NULL DEFAULT '',   -- monthly: "1,...,12"
    month_days    TEXT NOT NULL DEFAULT '',   -- monthly: "1,15,32" (32 = last day)
    repeat_every  INTEGER NOT NULL DEFAULT 0, -- minutes, 0 = no repetition
    repeat_for    INTEGER NOT NULL DEFAULT 0, -- minutes
    expires_at    TEXT,                       -- local, or NULL
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

-- Scheduled times already taken ("2026-10-21T06:00"), so each one runs only once
CREATE TABLE IF NOT EXISTS schedule_slots (
    slot        TEXT PRIMARY KEY,
    claimed_at  TEXT NOT NULL
);

-- Small values, like the last time the scheduler checked in
CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""

RUNNING = "running"
OK = "ok"
ERROR = "error"
PARTIAL = "partial"

# History events
ADDED = "added"
PAUSED = "paused"
ACTIVATED = "activated"
REMOVED = "removed"
SYNC = "sync"
SCHEDULE_ADDED = "schedule_added"
SCHEDULE_PAUSED = "schedule_paused"
SCHEDULE_ACTIVATED = "schedule_activated"
SCHEDULE_REMOVED = "schedule_removed"

SCHEDULE_COLUMNS = ("name", "kind", "start_at", "every", "days", "months", "month_days",
                    "repeat_every", "repeat_for", "expires_at")


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            # Schedules of days + times (before triggers) are dropped, not converted
            if "times" in {column[1] for column in db.execute("PRAGMA table_info(schedules)")}:
                db.execute("DROP TABLE schedules")
            db.executescript(SCHEMA)
            # Runs saved before the history existed are copied into it once
            if not db.execute("SELECT 1 FROM events LIMIT 1").fetchone():
                db.execute(
                    """INSERT INTO events (at, kind, status, message, actor)
                       SELECT finished_at, 'sync', status, message, trigger FROM runs
                       WHERE finished_at IS NOT NULL ORDER BY id"""
                )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def _execute(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with closing(self._connect()) as db, db:
            return db.execute(sql, params).fetchall()

    # Vendors

    def vendors(self, only_active: bool = False) -> list[sqlite3.Row]:
        where = "WHERE active = 1" if only_active else ""
        return self._execute(f"SELECT * FROM vendors {where} ORDER BY number")

    def vendor(self, number: int) -> sqlite3.Row | None:
        rows = self._execute("SELECT * FROM vendors WHERE number = ?", (number,))
        return rows[0] if rows else None

    def add_vendor(self, number: int, name: str | None = None) -> bool:
        """False when the vendor was already in the list."""
        try:
            self._execute("INSERT INTO vendors (number, name, added_at) VALUES (?, ?, ?)", (number, name, now()))
        except sqlite3.IntegrityError:
            return False
        return True

    def remove_vendor(self, number: int) -> None:
        self._execute("DELETE FROM vendors WHERE number = ?", (number,))

    def set_active(self, number: int, active: bool) -> None:
        self._execute("UPDATE vendors SET active = ? WHERE number = ?", (int(active), number))

    def record_vendor_result(self, number: int, status: str, message: str | None = None,
                             rows: int | None = None, name: str | None = None) -> None:
        self._execute(
            """UPDATE vendors
               SET last_sync_at = ?, last_status = ?, last_message = ?, last_rows = ?, name = COALESCE(?, name)
               WHERE number = ?""",
            (now(), status, message, rows, name, number),
        )

    # Runs

    def start_run(self, trigger: str) -> int:
        with closing(self._connect()) as db, db:
            cursor = db.execute(
                "INSERT INTO runs (trigger, started_at, status) VALUES (?, ?, ?)", (trigger, now(), RUNNING)
            )
            return cursor.lastrowid

    def finish_run(self, run_id: int, status: str, message: str | None = None) -> None:
        self._execute(
            "UPDATE runs SET finished_at = ?, status = ?, message = ? WHERE id = ?", (now(), status, message, run_id)
        )
        trigger = self._execute("SELECT trigger FROM runs WHERE id = ?", (run_id,))[0]["trigger"]
        self.log_event(SYNC, status=status, message=message, actor=trigger)

    # History

    def log_event(self, kind: str, vendor: int | None = None, status: str | None = None,
                  message: str | None = None, actor: str | None = None) -> None:
        self._execute(
            "INSERT INTO events (at, kind, vendor, status, message, actor) VALUES (?, ?, ?, ?, ?, ?)",
            (now(), kind, vendor, status, message, actor),
        )

    def recent_events(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.search_events(limit=limit)

    @staticmethod
    def _event_filters(vendor: str | None, start: datetime | None, end: datetime | None) -> tuple[str, list]:
        where, params = [], []
        if vendor:
            where.append("(CAST(vendor AS TEXT) LIKE ? OR message LIKE ?)")
            params += [f"{vendor}%", f"%{vendor}%"]
        if start:
            where.append("at >= ?")
            params.append(start.astimezone(UTC).isoformat(timespec="seconds"))
        if end:
            where.append("at < ?")
            params.append(end.astimezone(UTC).isoformat(timespec="seconds"))
        return (" WHERE " + " AND ".join(where) if where else ""), params

    def search_events(self, vendor: str | None = None, start: datetime | None = None, end: datetime | None = None,
                      limit: int | None = None, offset: int = 0) -> list[sqlite3.Row]:
        """Newest first. `vendor` also matches sync runs whose errors mention it;
        `start` (inclusive) and `end` (exclusive) are timezone-aware."""
        where, params = self._event_filters(vendor, start, end)
        sql = f"SELECT * FROM events{where} ORDER BY id DESC"
        if limit:
            sql += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        return self._execute(sql, tuple(params))

    def count_events(self, vendor: str | None = None, start: datetime | None = None, end: datetime | None = None) -> int:
        where, params = self._event_filters(vendor, start, end)
        return self._execute(f"SELECT COUNT(*) FROM events{where}", tuple(params))[0][0]

    def recent_runs(self, limit: int = 10) -> list[sqlite3.Row]:
        return self._execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))

    # Schedules

    def schedules(self, only_active: bool = False) -> list[sqlite3.Row]:
        where = "WHERE active = 1" if only_active else ""
        return self._execute(f"SELECT * FROM schedules {where} ORDER BY id")

    def schedule(self, schedule_id: int) -> sqlite3.Row | None:
        rows = self._execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        return rows[0] if rows else None

    def add_schedule(self, columns: dict) -> int:
        """`columns` as relay.scheduler.build returns them."""
        with closing(self._connect()) as db, db:
            cursor = db.execute(
                f"INSERT INTO schedules ({', '.join(SCHEDULE_COLUMNS)}, created_at) "
                f"VALUES ({', '.join('?' * len(SCHEDULE_COLUMNS))}, ?)",
                (*(columns[name] for name in SCHEDULE_COLUMNS), now()),
            )
            return cursor.lastrowid

    def set_schedule_active(self, schedule_id: int, active: bool) -> None:
        self._execute("UPDATE schedules SET active = ? WHERE id = ?", (int(active), schedule_id))

    def remove_schedule(self, schedule_id: int) -> None:
        self._execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))

    def claim_slot(self, slot: str) -> bool:
        """Takes a scheduled time; False when it was already taken (it ran, or is running)."""
        with closing(self._connect()) as db, db:
            # Times a week older than this one are not needed any more
            week_before = (datetime.fromisoformat(slot) - timedelta(days=7)).isoformat(timespec="minutes")
            db.execute("DELETE FROM schedule_slots WHERE slot < ?", (week_before,))
            try:
                db.execute("INSERT INTO schedule_slots (slot, claimed_at) VALUES (?, ?)", (slot, now()))
            except sqlite3.IntegrityError:
                return False
        return True

    def release_slot(self, slot: str) -> None:
        self._execute("DELETE FROM schedule_slots WHERE slot = ?", (slot,))

    # Small values

    def set_meta(self, key: str, value: str) -> None:
        self._execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    def get_meta(self, key: str) -> str | None:
        rows = self._execute("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    # Lock

    def acquire_lock(self, owner: str, stale_after: timedelta = timedelta(hours=1)) -> bool:
        """Takes the lock unless another run holds it; a lock older than
        stale_after is considered abandoned (process killed) and taken over."""
        stale = (datetime.now(UTC) - stale_after).isoformat(timespec="seconds")
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM lock WHERE acquired_at < ?", (stale,))
            try:
                db.execute("INSERT INTO lock (id, owner, acquired_at) VALUES (1, ?, ?)", (owner, now()))
            except sqlite3.IntegrityError:
                return False
        return True

    def release_lock(self, owner: str) -> None:
        self._execute("DELETE FROM lock WHERE owner = ?", (owner,))

    def is_locked(self) -> bool:
        return bool(self._execute("SELECT 1 FROM lock"))
