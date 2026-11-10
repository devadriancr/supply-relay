"""One sync run: reads each active vendor (and the work calendar) from Infor
and sends it to the portal.

Scheduled task (Windows Task Scheduler):  .venv\\Scripts\\python.exe -m relay.sync
"""

import logging
import os
import sys
import uuid
from datetime import date, timedelta

from relay import store as st
from relay.config import Settings, get_settings
from relay.infor import InforReader
from relay.logs import setup_logging
from relay.portal import PortalClient

log = logging.getLogger("relay.sync")


def first_day_of_previous_month(today: date) -> date:
    """The portal shows one month back, so data is sent from that month's first day."""
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)


def short_error(error: Exception) -> str:
    # Enough to know what failed without filling the screen (never includes the key)
    return f"{type(error).__name__}: {error}"[:300]


def run_sync(settings: Settings, store: st.Store, trigger: str, vendors: list[int] | None = None,
             reader_factory=InforReader, portal_factory=PortalClient) -> str:
    """Runs a sync and returns its status. `vendors` limits it to some vendors
    (the work calendar is only sent on a full run). Returns "busy" when another
    run is in progress."""
    owner = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
    if not store.acquire_lock(owner):
        log.info("Sync skipped: another run is in progress")
        return "busy"

    run_id = store.start_run(trigger)
    numbers = vendors if vendors is not None else [row["number"] for row in store.vendors(only_active=True)]
    since = first_day_of_previous_month(date.today())
    failures = []
    sent = 0

    try:
        with reader_factory(settings) as infor, portal_factory(settings) as portal:
            if vendors is None:
                try:
                    # The year of the previous month too: in January the portal shows December
                    year = date.today().year
                    years = sorted({since.year, year, year + 1})
                    calendars = infor.work_calendars(settings.calendar_facility, settings.calendar_work_center, years)
                    portal.send_work_calendars(calendars)
                    sent += 1
                    log.info("Work calendar sent: %s year(s)", len(calendars))
                except Exception as error:
                    log.exception("Work calendar failed")
                    failures.append(f"Calendario: {short_error(error)}")

            for number in numbers:
                try:
                    snapshot = infor.vendor_snapshot(number, since)
                    if snapshot is None:
                        message = "No existe o está inactivo en Infor (AVM)."
                        store.record_vendor_result(number, st.ERROR, message)
                        failures.append(f"{number}: {message}")
                        continue

                    portal.send_vendor(number, snapshot)
                    rows = sum(len(snapshot[key]) for key in ("part_numbers", "purchase_order_lines", "delivery_rows"))
                    store.record_vendor_result(number, st.OK, rows=rows, name=snapshot["vendor"]["name"])
                    sent += 1
                    log.info("Vendor %s sent: %s rows", number, rows)
                except Exception as error:
                    log.exception("Vendor %s failed", number)
                    store.record_vendor_result(number, st.ERROR, short_error(error))
                    failures.append(f"{number}: {short_error(error)}")
    except Exception as error:
        # Infor or the portal could not be reached at all
        log.exception("Sync failed")
        store.finish_run(run_id, st.ERROR, short_error(error))
        return st.ERROR
    finally:
        store.release_lock(owner)

    if not failures:
        status, message = st.OK, f"{len(numbers)} proveedor(es) enviados."
    else:
        status = st.PARTIAL if sent else st.ERROR
        message = " | ".join(failures)[:1000]

    store.finish_run(run_id, status, message)
    return status


def main() -> int:
    settings = get_settings()
    setup_logging(settings)
    status = run_sync(settings, st.Store(settings.database_path), trigger="scheduled")
    return 0 if status in (st.OK, "busy") else 1


if __name__ == "__main__":
    sys.exit(main())
