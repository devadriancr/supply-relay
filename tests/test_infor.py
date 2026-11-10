from relay.infor import InforReader, build_snapshot, shift, to_date


def test_dates_accept_both_infor_formats():
    assert to_date(20261020) == "2026-10-20"
    assert to_date(1261020) == "2026-10-20"  # CYYMMDD
    assert to_date(0) is None
    assert to_date(20261340) is None


def test_shift_is_the_fifth_character_of_the_control_number():
    assert shift("1234A") == "A"
    assert shift("1234 ") is None
    assert shift(None) is None


def test_snapshot_keeps_only_the_printed_fields():
    vendor = {
        "VNDNAM": "YOROZU AUTOMOTIVE   ", "VNALPH": "YOROZU", "VNDAD1": "AVENIDA AMISTAD 102", "VNDAD2": "",
        "VNDAD3": "GUANAJUATO", "VSTATE": "GTO", "VPOST": "38160", "VCOUN": "MEX", "VMFSCD": "YAG120309888",
        "VPHONE": "4131586400", "VCON": "CHRISTIAN MEJIA", "VMDATN": "christian@example.com",
    }
    lines = [
        {"PORD": 12345, "PLINE": 1, "PPROD": "BDTS28911A    ", "PQORD": 25.0, "PQREC": 10.0, "PDDTE": 20261020, "PWHSE": "YK1", "POCNO": "0000A"},
        {"PORD": 12345, "PLINE": 2, "PPROD": "BDTS28911A", "PQORD": 5.0, "PDDTE": 0, "PWHSE": "YK1", "POCNO": ""},
    ]
    deliveries = [
        {"ORIGIN": "FR", "ORD": 0, "LINE": 0, "PROD": "XX99", "QTY": 40.5, "DDTE": 20261022},
    ]
    parts = [
        {"IPROD": "BDTS28911A", "IDESC": "BRACKET", "IMBOXQ": 10, "IMSPKT": "BOX", "IREF04": "J59", "IUFD14": "R"},
        {"IPROD": "XX99", "IDESC": "COVER", "IMBOXQ": 0, "IMSPKT": None, "IREF04": "8", "IUFD14": None},
        {"IPROD": "NOT-USED", "IDESC": "", "IMBOXQ": 1, "IMSPKT": "", "IREF04": "", "IUFD14": ""},
    ]

    snapshot = build_snapshot(vendor, lines, deliveries, parts, {"BDTS28911A": "WELDING"})

    assert snapshot["vendor"]["name"] == "YOROZU AUTOMOTIVE"
    assert snapshot["vendor"]["locality"] is None
    assert snapshot["purchase_order_lines"] == [{
        "part_number": "BDTS28911A", "number": 12345, "line": 1, "quantity": 25.0, "received_quantity": 10.0,
        "due_date": "2026-10-20", "shift": "A", "warehouse": "YK1",
    }]  # the line without date is left out
    assert snapshot["delivery_rows"] == [{
        "part_number": "XX99", "origin": "FR", "number": None, "line": None, "quantity": 40.5, "due_date": "2026-10-22",
    }]
    assert [part["number"] for part in snapshot["part_numbers"]] == ["BDTS28911A", "XX99"]
    assert snapshot["part_numbers"][0]["next_process"] == "WELDING"
    assert snapshot["part_numbers"][0]["side"] == "R"


def test_credentials_cannot_change_the_connection_string(settings):
    seen = {}

    def connect(connection_string, **options):
        seen["dsn"], seen["options"] = connection_string, options
        return type("Connection", (), {"close": lambda self: None})()

    settings.infor_password = type(settings.infor_password)("pa;ss}word")
    with InforReader(settings, connect=connect):
        pass

    assert seen["dsn"].endswith("Uid={reader};Pwd={pa;ss}}word};")
    assert seen["options"]["readonly"] is True


def test_years_not_loaded_in_infor_are_not_sent(settings):
    reader = InforReader(settings)
    reader.select = lambda sql, params: [
        {"SCFAC": "YK1", "SCRKC": 0, "SCYEAR": 2026, "SCTYPE": "HHWW" + " " * 362},
        {"SCFAC": "YK1", "SCRKC": 0, "SCYEAR": 2027, "SCTYPE": " " * 366},
    ]

    calendars = reader.work_calendars("YK1", 0, [2026, 2027])

    assert [calendar["year"] for calendar in calendars] == [2026]
    assert calendars[0]["days"].startswith("HHWW") and len(calendars[0]["days"]) == 366
