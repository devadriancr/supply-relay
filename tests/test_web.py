import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from relay.scheduler import build
from relay.web import create_app

from .conftest import PASSWORD


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), follow_redirects=False) as client:
        yield client


def csrf(client, path="/"):
    page = client.get(path).text
    return re.search(r'name="csrf" value="([^"]+)"', page).group(1)


def login(client, password=PASSWORD):
    return client.post("/login", data={"username": "admin", "password": password, "csrf": csrf(client, "/login")})


def test_pages_require_login(client):
    assert client.get("/").headers["location"] == "/login"
    assert client.post("/sync").headers["location"] == "/login"


def test_login_and_dashboard(client):
    assert login(client, "wrong").headers["location"] == "/login"
    assert "incorrectos" in client.get("/login").text

    assert login(client).headers["location"] == "/"
    page = client.get("/")
    assert page.status_code == 200
    assert "Número de vendor" in page.text
    assert "portal.test" in page.text


def test_login_is_blocked_after_repeated_failures(client):
    for _ in range(5):
        login(client, "wrong")

    login(client)  # right password, but blocked

    assert client.get("/").headers["location"] == "/login"
    assert "Demasiados intentos" in client.get("/login").text


def test_vendors_are_added_paused_and_removed(client, store):
    login(client)
    token = csrf(client)

    client.post("/vendors", data={"number": "400191", "csrf": token})
    client.post("/vendors", data={"number": "abc", "csrf": token})
    assert [row["number"] for row in store.vendors()] == [400191]
    assert "número de proveedor válido" in client.get("/").text

    client.post("/vendors/400191/toggle", data={"csrf": token})
    assert store.vendor(400191)["active"] == 0

    client.post("/vendors/400191/delete", data={"csrf": token})
    assert store.vendors() == []


def test_forms_without_csrf_token_are_rejected(client, store):
    login(client)

    response = client.post("/vendors", data={"number": "400191", "csrf": "forged"})

    assert response.status_code == 303
    assert store.vendors() == []


def test_security_headers_and_no_api_docs(client):
    response = client.get("/login")

    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_history_shows_vendor_changes_and_sync_errors(client, store):
    login(client)
    token = csrf(client)
    client.post("/vendors", data={"number": "400191", "csrf": token})
    client.post("/vendors/400191/toggle", data={"csrf": token})
    client.post("/vendors/400191/toggle", data={"csrf": token})
    client.post("/vendors/400191/delete", data={"csrf": token})
    run = store.start_run("scheduled")
    store.finish_run(run, "partial", "410020: No existe | 500: Infor timeout")

    assert [event["kind"] for event in store.recent_events()] == ["sync", "removed", "activated", "paused", "added"]
    assert store.recent_events()[-1]["actor"] == "admin"

    page = client.get("/historial").text
    assert "Sincronización con errores" in page
    assert "Ver 2 errores" in page
    assert "500: Infor timeout" in page
    for word in ("agregado", "pausado", "activado", "eliminado"):
        assert word in page


def test_history_filters_by_vendor_and_dates(client, store):
    login(client)
    store.log_event("added", 400191, actor="admin")
    store.log_event("added", 200000, actor="admin")
    run = store.start_run("scheduled")
    store.finish_run(run, "partial", "400191: Infor timeout")

    page = client.get("/historial", params={"vendor": "400191"}).text
    assert "Proveedor <span class=\"strong\">400191</span> agregado" in page
    assert "200000</span> agregado" not in page
    assert "Sincronización con errores" in page  # its error mentions the vendor

    assert "No hay movimientos con estos filtros." in client.get("/historial", params={"hasta": "2000-01-01"}).text
    assert "200000</span> agregado" in client.get("/historial", params={"desde": "2000-01-01", "vendor": "x"}).text


def test_history_downloads_as_excel(client, store):
    import io
    import zipfile

    login(client)
    store.log_event("added", 400191, actor="admin")
    store.log_event("removed", 200000, actor="admin")

    response = client.get("/historial.xlsx", params={"vendor": "400191"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "attachment" in response.headers["content-disposition"]
    sheet = zipfile.ZipFile(io.BytesIO(response.content)).read("xl/worksheets/sheet1.xml").decode()
    assert "Proveedor agregado" in sheet and "400191" in sheet
    assert "Proveedor eliminado" not in sheet


def test_excel_requires_login(client):
    assert client.get("/historial.xlsx").headers["location"] == "/login"


def test_page_can_be_switched_to_english_and_japanese(client):
    login(client)
    assert "Proveedores" in client.get("/").text  # Spanish by default

    response = client.get("/idioma", params={"lang": "en", "next": "/"})
    assert response.headers["location"] == "/"
    page = client.get("/").text
    assert '<html lang="en">' in page and "Sync all" in page
    assert "Download Excel" in client.get("/historial").text

    client.get("/idioma", params={"lang": "ja"})
    page = client.get("/").text
    assert "すべて同期" in page and "履歴" in page


def test_language_switch_only_redirects_inside_the_site(client):
    for target in ("https://evil.test/", "//evil.test", r"/\evil.test"):
        assert client.get("/idioma", params={"lang": "en", "next": target}).headers["location"] == "/"
    assert client.get("/idioma", params={"lang": "xx"}).cookies.get("lang") == "es"


def test_notifications_follow_the_language(client):
    login(client)
    client.get("/idioma", params={"lang": "en"})
    client.post("/vendors", data={"number": "abc", "csrf": csrf(client)})

    assert "Enter a valid vendor number" in client.get("/").text


def test_saved_sync_messages_are_translated(client, store):
    login(client)
    run = store.start_run("manual")
    store.finish_run(run, "partial", "410020: No existe o está inactivo en Infor (AVM).")
    client.get("/idioma", params={"lang": "en"})

    page = client.get("/historial").text
    assert "Sync with errors" in page and "Does not exist or is inactive in Infor (AVM)." in page


def test_excel_follows_the_language(client, store):
    import io
    import zipfile

    login(client)
    store.log_event("added", 400191, actor="admin")
    client.get("/idioma", params={"lang": "en"})

    response = client.get("/historial.xlsx")
    sheet = zipfile.ZipFile(io.BytesIO(response.content)).read("xl/worksheets/sheet1.xml").decode()
    assert "Vendor added" in sheet and ">Date<" in sheet
    assert 'filename="history_supply_relay_' in response.headers["content-disposition"]


def test_the_end_of_a_sync_started_here_is_announced(client, store, monkeypatch):
    import relay.web

    calls = []
    monkeypatch.setattr(relay.web, "run_sync", lambda *args: calls.append(args))
    login(client)
    store.add_vendor(400191)
    client.post("/sync", data={"csrf": csrf(client)})
    assert calls  # started in the background

    page = client.get("/").text
    assert "Sincronización iniciada" in page
    assert 'http-equiv="refresh"' in page  # keeps refreshing until it ends
    assert "data-auto-refresh" in page and 'href="#content"' in page

    run = store.start_run("manual")
    store.finish_run(run, "ok", "1 proveedor(es) enviados.")
    page = client.get("/").text
    assert 'toast toast-ok' in page and "Sincronización completa" in page
    assert 'http-equiv="refresh"' not in client.get("/").text


def test_history_is_paginated_five_at_a_time(client, store):
    login(client)
    for number in range(100001, 100013):  # 12 events, newest last
        store.log_event("added", number, actor="admin")

    page = client.get("/historial").text
    assert "1–5 de 12" in page
    assert "100012</span> agregado" in page and "100007</span>" not in page
    assert 'aria-current="page">1<' in page and "pagina=2" in page

    last = client.get("/historial", params={"pagina": 3}).text
    assert "11–12 de 12" in last and "100001</span> agregado" in last

    assert "11–12 de 12" in client.get("/historial", params={"pagina": 99}).text  # closest page
    assert "1–5 de 12" in client.get("/historial", params={"pagina": "abc"}).text


def test_pages_keep_the_filters(client, store):
    login(client)
    for number in range(400100, 400107):
        store.log_event("added", number, actor="admin")
    store.log_event("added", 200000, actor="admin")

    page = client.get("/historial", params={"vendor": "4001"}).text
    assert "1–5 de 7" in page
    assert "vendor=4001&amp;pagina=2" in page


def test_removing_asks_in_a_modal(client, store):
    login(client)
    store.add_vendor(400191)

    page = client.get("/").text
    assert "data-confirm-dialog" in page and "¿Eliminar proveedor?" in page
    assert 'data-confirm="El proveedor 400191 se quitará de la lista' in page


def test_the_menu_has_vendors_schedule_and_history(client):
    login(client)
    page = client.get("/").text
    assert 'href="/programacion"' in page and 'href="/historial"' in page
    assert 'class="menu-item menu-item-active"' in page and 'aria-current="page"' in page

    assert client.get("/programacion").status_code == 200
    assert client.get("/historial").status_code == 200
    assert client.get("/programacion").headers.get("location") is None


def test_schedules_are_added_paused_and_removed(client, store):
    login(client)
    token = csrf(client, "/programacion")

    client.post("/programacion", data={
        "kind": "weekly", "name": "Turno A", "start_date": "2026-10-01", "start_time": "06:00",
        "every_weeks": "1", "every_days": "9", "days": ["1", "2", "3", "4", "5"], "months": ["1"],
        "repeat": "1", "repeat_every": "30", "repeat_for": "720", "csrf": token,
    })
    [row] = store.schedules()
    # Only the fields of the chosen trigger count
    assert (row["kind"], row["name"], row["days"], row["every"], row["months"], row["repeat_every"], row["active"]) == (
        "weekly", "Turno A", "1,2,3,4,5", 1, "", 30, 1)

    page = client.get("/programacion").text
    assert "Programación guardada." in page
    assert "Lunes a viernes a las 06:00 · cada 30 minutos durante 12 h" in page and "Turno A" in page

    client.post(f"/programacion/{row['id']}/toggle", data={"csrf": token})
    assert store.schedule(row["id"])["active"] == 0

    client.post(f"/programacion/{row['id']}/delete", data={"csrf": token})
    assert store.schedules() == []

    history = client.get("/historial").text
    for text in ("Programación agregada", "Programación pausada", "Programación eliminada"):
        assert text in history
    assert "Turno A (Lunes a viernes a las 06:00 · cada 30 minutos durante 12 h)" in history


def test_history_still_reads_schedules_of_days_and_times(client, store):
    login(client)
    store.log_event("schedule_added", message="1,2,3,4,5|06:00,14:00", actor="admin")
    assert "Lunes a viernes · 06:00, 14:00" in client.get("/historial").text


def test_a_schedule_form_with_mistakes_is_not_saved(client, store):
    login(client)
    token = csrf(client, "/programacion")

    client.post("/programacion", data={"kind": "weekly", "start_date": "2026-10-01", "start_time": "06:00", "csrf": token})
    assert "Elige al menos un día." in client.get("/programacion").text

    client.post("/programacion", data={"kind": "once", "start_date": "2020-01-01", "start_time": "06:00", "csrf": token})
    assert "Esa fecha y hora ya pasaron." in client.get("/programacion").text
    assert store.schedules() == []


def test_schedule_page_says_whether_the_scheduler_runs(client, store):
    from datetime import UTC, datetime

    login(client)
    assert "Detenido" in client.get("/programacion").text

    store.set_meta("scheduler_checked_at", datetime.now(UTC).isoformat(timespec="seconds"))
    assert "En marcha" in client.get("/programacion").text


def test_vendors_page_shows_the_next_scheduled_sync(client, store):
    login(client)
    assert "Sin sincronización programada" in client.get("/").text

    store.add_schedule(build("daily", "2026-10-01", "06:00"))
    assert "Próxima sincronización:" in client.get("/").text


def test_schedule_page_follows_the_language(client, store):
    login(client)
    store.add_schedule(build("weekly", "2026-10-01", "06:00", days=["1", "3", "5"]))
    client.get("/idioma", params={"lang": "ja"})

    page = client.get("/programacion").text
    assert "スケジュール" in page and "月, 水, 金 06:00" in page and "毎週" in page


def test_schedule_page_shows_every_kind_of_trigger_and_its_next_run(client, store):
    login(client)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    store.add_schedule(build("once", tomorrow, "09:30"))
    store.add_schedule(build("daily", "2026-10-01", "06:00", every="2"))
    store.add_schedule(build("monthly", "2026-10-01", "06:00", months=["2", "11"], month_days=["15", "32"],
                             expires=True, expires_date="2030-12-31"))
    store.add_schedule(build("daily", "2026-10-01", "06:00", expires=True, expires_date="2026-10-02"))

    page = client.get("/programacion").text
    assert "Una vez, el " in page and "Cada 2 días a las 06:00" in page
    assert "Día 15, Último de Feb, Nov a las 06:00 · caduca el 31/12/2030 23:59" in page
    assert "Sin más ejecuciones" in page  # the expired one
