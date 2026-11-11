from relay import store as st
from relay.sync import run_sync

SNAPSHOT = {
    "vendor": {"name": "YOROZU"},
    "part_numbers": [{"number": "A"}],
    "purchase_order_lines": [{}, {}],
    "delivery_rows": [{}],
}


class FakeInfor:
    def __init__(self, settings):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def work_calendars(self, facility, work_center, years):
        return [{"facility": facility, "work_center": work_center, "year": year, "days": " " * 366} for year in years]

    def vendor_snapshot(self, vendor, since):
        if vendor == 999:
            return None  # not active in AVM
        if vendor == 500:
            raise RuntimeError("Infor timeout")
        return SNAPSHOT


class FakePortal:
    sent = []

    def __init__(self, settings):
        FakePortal.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def send_work_calendars(self, calendars):
        FakePortal.sent.append(("calendars", len(calendars)))

    def send_vendor(self, vendor, snapshot):
        FakePortal.sent.append(("vendor", vendor))


def sync(settings, store, vendors=None):
    return run_sync(settings, store, "manual", vendors, reader_factory=FakeInfor, portal_factory=FakePortal)


def test_sends_the_calendar_and_every_active_vendor(settings, store):
    store.add_vendor(400191)
    store.add_vendor(200000)
    store.add_vendor(101004)
    store.set_active(101004, False)

    assert sync(settings, store) == st.OK
    # Last year, this one and the next: unreceived lines go back one year
    assert FakePortal.sent == [("calendars", 3), ("vendor", 200000), ("vendor", 400191)]

    vendor = store.vendor(400191)
    assert (vendor["name"], vendor["last_status"], vendor["last_rows"]) == ("YOROZU", st.OK, 4)
    assert store.vendor(101004)["last_status"] is None
    assert store.recent_runs()[0]["status"] == st.OK
    assert not store.is_locked()


def test_one_failing_vendor_does_not_stop_the_others(settings, store):
    for number in (999, 500, 400191):
        store.add_vendor(number)

    assert sync(settings, store) == st.PARTIAL
    assert ("vendor", 400191) in FakePortal.sent
    assert "inactivo" in store.vendor(999)["last_message"]
    assert "Infor timeout" in store.vendor(500)["last_message"]


def test_a_single_vendor_run_skips_the_calendar(settings, store):
    store.add_vendor(400191)

    sync(settings, store, vendors=[400191])

    assert FakePortal.sent == [("vendor", 400191)]


def test_only_one_run_at_a_time(settings, store):
    store.add_vendor(400191)
    assert store.acquire_lock("other-process")
    FakePortal.sent = []

    assert sync(settings, store) == "busy"
    assert FakePortal.sent == []


def test_each_run_is_kept_in_the_history(settings, store):
    store.add_vendor(999)

    sync(settings, store)

    event = store.recent_events()[0]
    assert (event["kind"], event["status"], event["actor"]) == ("sync", st.PARTIAL, "manual")  # the calendar was sent, the vendor failed
    assert "inactivo" in event["message"]


def test_data_is_sent_from_the_first_day_of_the_previous_month():
    from datetime import date

    from relay.sync import first_day_of_previous_month

    assert first_day_of_previous_month(date(2026, 10, 15)) == date(2026, 9, 1)
    assert first_day_of_previous_month(date(2027, 1, 3)) == date(2026, 12, 1)
    assert first_day_of_previous_month(date(2026, 3, 31)) == date(2026, 2, 1)
