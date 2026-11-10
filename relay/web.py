"""Admin screen: vendors to sync (with a "sync now" button), the schedules
of the automatic sync, and the history of everything that happened.

Run (IIS starts it through web.config):
    .venv\\Scripts\\python.exe -m uvicorn relay.web:create_app --factory --port 8000
"""

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from relay import store as st
from relay.auth import LoginThrottle, csrf_token, valid_csrf, verify_password
from relay.config import Settings, get_settings
from relay.history import STATUS_LABELS, SYNC_TITLES, HistoryFilter, origin_key, title_key
from relay.i18n import DATE_FORMATS, DAY_NAMES, LANGUAGES, MONTH_NAMES, describe_days, language, saved_message, translator
from relay.logs import setup_logging
from relay import scheduler as sch
from relay.scheduler import LAST_CHECK, Schedule, ScheduleError, next_slot, parse_numbers, parse_times
from relay.sync import run_sync
from relay.xlsx import workbook

HERE = Path(__file__).resolve().parent
SESSION_HOURS = 8
MAX_VENDOR = 99_999_999  # VENDOR is 8 digits in Infor
HISTORY_PAGE_SIZE = 5  # history events per page (the Excel has all of them)
LANG_COOKIE = "lang"
SYNC_WAIT_SECONDS = 60  # how long to wait for a sync started from the screen to begin
SCHEDULER_ALIVE = timedelta(minutes=3)  # the scheduler checks every minute; older than this, it is stopped

log = logging.getLogger("relay.web")

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class LoginRequired(Exception):
    pass


def local_time(value: str | None, lang: str = "es") -> str:
    if not value:
        return "—"
    return datetime.fromisoformat(value).astimezone().strftime(DATE_FORMATS[lang])


def slot_time(value: datetime, lang: str = "es") -> str:
    """A scheduled time (local, without time zone): "Jue 23/10/2026 06:00"."""
    return f"{DAY_NAMES[lang][value.isoweekday() - 1]} {value.strftime(DATE_FORMATS[lang])}"


def duration_text(minutes: int, lang: str = "es") -> str:
    """"30 minutos", "12 h", "1 día(s)"."""
    t = translator(lang)
    if minutes % 1440 == 0:
        return str(t("n_days", n=minutes // 1440))
    if minutes % 60 == 0:
        return str(t("n_hours", n=minutes // 60))
    return str(t("n_minutes", n=minutes))


def describe_schedule(schedule: Schedule, lang: str = "es") -> str:
    """"Lunes a viernes a las 06:00 · cada 30 minutos durante 8 h" in the language of the page."""
    t = translator(lang)
    at = schedule.start.strftime("%H:%M")
    if schedule.kind == sch.ONCE:
        text = t("desc_once", when=schedule.start.strftime(DATE_FORMATS[lang]))
    elif schedule.kind == sch.DAILY:
        text = t("desc_daily", time=at) if schedule.every == 1 else t("desc_daily_n", n=schedule.every, time=at)
    elif schedule.kind == sch.WEEKLY:
        days = describe_days(schedule.days, lang)
        text = (t("desc_weekly", days=days, time=at) if schedule.every == 1
                else t("desc_weekly_n", n=schedule.every, days=days, time=at))
    else:
        days = ", ".join(str(t("last_day")) if day == sch.LAST_DAY else str(day) for day in schedule.month_days)
        months = (t("every_month") if len(schedule.months) == 12
                  else ", ".join(MONTH_NAMES[lang][month - 1] for month in schedule.months))
        text = t("desc_monthly", days=days, months=months, time=at)

    parts = [str(text)]
    if schedule.repeat_every:
        parts.append(str(t("desc_repeat", every=duration_text(schedule.repeat_every, lang),
                           duration=duration_text(schedule.repeat_for, lang))))
    if schedule.expires:
        parts.append(str(t("desc_expires", when=schedule.expires.strftime(DATE_FORMATS[lang]))))
    return " · ".join(parts)


def schedule_label(schedule: Schedule, lang: str = "es") -> str:
    """Its name and what it does, for the history and the buttons of the list."""
    text = describe_schedule(schedule, lang)
    return f"{schedule.name} ({text})" if schedule.name else text


def schedule_message(row) -> str:
    """What the history keeps of a schedule: its columns, described later in the reader's language."""
    return json.dumps({name: row[name] for name in st.SCHEDULE_COLUMNS})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings)
    store = st.Store(settings.database_path)
    throttle = LoginThrottle()

    app = FastAPI(title="Supply Relay", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
        session_cookie="relay_session",
        max_age=SESSION_HOURS * 3600,
        same_site="strict",
        https_only=settings.secure_cookies,
    )
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    templates = Jinja2Templates(directory=HERE / "templates")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    @app.exception_handler(LoginRequired)
    async def to_login(request: Request, exc: LoginRequired):
        return RedirectResponse("/login", status_code=303)

    # Helpers

    def lang_of(request: Request) -> str:
        return language(request.cookies.get(LANG_COOKIE))

    def require_user(request: Request) -> str:
        user = request.session.get("user")
        if not user:
            raise LoginRequired()
        return user

    def require_post(request: Request, token: str | None) -> None:
        require_user(request)
        if not valid_csrf(request.session, token):
            raise LoginRequired()

    def flash(request: Request, key: str, kind: str = "ok", **values) -> None:
        # Saved as a text key, so it shows in the language of the page that displays it.
        # Reassigned (not appended) so the session notices the change and saves it.
        request.session["flash"] = [*request.session.get("flash", []), {"kind": kind, "key": key, "values": values}]

    def back(path: str = "/") -> RedirectResponse:
        return RedirectResponse(path, status_code=303)

    def render(request: Request, template: str, **context) -> HTMLResponse:
        lang = lang_of(request)
        t = translator(lang)
        flashes = [
            {"kind": item["kind"], "message": t(item["key"], **item.get("values", {}))}
            for item in request.session.pop("flash", [])
        ]
        return templates.TemplateResponse(
            request,
            template,
            {
                "csrf": csrf_token(request.session),
                "flashes": flashes,
                "t": t,
                "lang": lang,
                "languages": LANGUAGES,
                "fmt_time": lambda value: local_time(value, lang),
                "fmt_slot": lambda value: slot_time(value, lang),
                "saved_message": lambda text: saved_message(text, lang),
                "user": request.session.get("user"),
                "portal_host": urlsplit(settings.portal_base).netloc,
                "here": request.url.path + (f"?{request.url.query}" if request.url.query else ""),
                **context,
            },
        )

    def start_sync(request: Request, background: BackgroundTasks, vendors: list[int] | None) -> bool:
        if store.is_locked():
            return False
        # Remember where the history was, to announce the result when the run ends
        latest = store.recent_events(limit=1)
        request.session["watch_sync"] = {"after": latest[0]["id"] if latest else 0, "since": time.time()}
        background.add_task(run_sync, settings, store, "manual", vendors)
        return True

    def watching_sync(request: Request) -> bool:
        """Turns the end of a sync started from this screen into a notification.
        True while that sync has not finished (the page keeps refreshing)."""
        watch = request.session.get("watch_sync")
        if not watch:
            return False
        if store.is_locked():
            return True
        finished = [e for e in store.recent_events(limit=10) if e["id"] > watch["after"] and e["kind"] == st.SYNC]
        if finished:
            status = finished[0]["status"]
            flash(request, SYNC_TITLES.get(status, "sync_ok"), "ok" if status == st.OK else "error")
        elif time.time() - watch["since"] < SYNC_WAIT_SECONDS:
            return True  # started in the background but not running yet
        request.session.pop("watch_sync", None)
        return False

    # Pages

    @app.get("/health", include_in_schema=False)
    def health():
        return JSONResponse({"status": "ok"})

    @app.get("/idioma")
    def set_language(lang: str = "", next: str = "/"):
        # Only paths of this site, so the link cannot send anyone elsewhere
        target = next if next.startswith("/") and not next.startswith("//") and "\\" not in next else "/"
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(LANG_COOKIE, language(lang), max_age=365 * 24 * 3600, samesite="lax",
                            httponly=True, secure=settings.secure_cookies)
        return response

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        if request.session.get("user"):
            return back()
        return render(request, "login.html")

    @app.post("/login")
    def login(request: Request, username: str = Form(""), password: str = Form(""), csrf: str = Form("")):
        address = request.client.host if request.client else "unknown"
        if not valid_csrf(request.session, csrf):
            return RedirectResponse("/login", status_code=303)
        if throttle.blocked(address):
            flash(request, "too_many_attempts", "error")
            return RedirectResponse("/login", status_code=303)

        # Both checks always run, so the response time does not reveal the user name
        valid_user = username == settings.admin_username
        valid_password = verify_password(password, settings.admin_password_hash)
        if not (valid_user and valid_password):
            throttle.fail(address)
            log.warning("Failed login from %s", address)
            flash(request, "wrong_login", "error")
            return RedirectResponse("/login", status_code=303)

        throttle.reset(address)
        request.session.clear()  # new session after login
        request.session["user"] = username
        log.info("Login from %s", address)
        return back()

    @app.post("/logout")
    def logout(request: Request, csrf: str = Form("")):
        if valid_csrf(request.session, csrf):
            request.session.clear()
        return RedirectResponse("/login", status_code=303)

    def schedules() -> list[Schedule]:
        return [Schedule.from_row(row) for row in store.schedules()]

    def schedule_text(message: str | None, lang: str) -> str:
        """History events of schedules keep their columns (schedule_message); older ones
        kept "days|times" (e.g. "1,2,3,4,5|06:00,14:00")."""
        if message and message.startswith("{"):
            return schedule_label(Schedule.from_row({"id": 0, "active": 1, **json.loads(message)}), lang)
        days, _, times = (message or "").partition("|")
        return f"{describe_days(parse_numbers(days, 1, 7), lang)} · {', '.join(t.strftime('%H:%M') for t in parse_times(times))}"

    @app.get("/", response_class=HTMLResponse)
    def vendors_page(request: Request):
        require_user(request)
        waiting = watching_sync(request)
        vendors = store.vendors()
        return render(
            request,
            "vendors.html",
            tab="vendors",
            vendors=vendors,
            active=sum(1 for vendor in vendors if vendor["active"]),
            next_run=next_slot(schedules(), datetime.now()),
            running=waiting or store.is_locked(),
        )

    @app.get("/historial", response_class=HTMLResponse)
    def history_page(request: Request, vendor: str = "", desde: str = "", hasta: str = "", pagina: str = "1"):
        require_user(request)
        waiting = watching_sync(request)
        lang = lang_of(request)
        history = HistoryFilter.from_query(vendor, desde, hasta)
        page = history.page(store, int(pagina) if pagina.isdigit() else 1, HISTORY_PAGE_SIZE)
        return render(
            request,
            "history.html",
            tab="history",
            events=page.items,
            page=page,
            page_url=lambda number: "/historial?" + urlencode({**history.query(), "pagina": number}),
            history=history,
            export_query=urlencode(history.query()),
            describe_schedule=lambda message: schedule_text(message, lang),
            running=waiting or store.is_locked(),
        )

    @app.get("/programacion", response_class=HTMLResponse)
    def schedule_page(request: Request):
        require_user(request)
        lang = lang_of(request)
        items = schedules()
        now = datetime.now()
        checked_at = store.get_meta(LAST_CHECK)
        alive = bool(checked_at) and datetime.now(UTC) - datetime.fromisoformat(checked_at) < SCHEDULER_ALIVE
        return render(
            request,
            "schedule.html",
            tab="schedule",
            schedules=items,
            next_run=next_slot(items, now),
            next_run_of=lambda schedule: next_slot([schedule], now),
            scheduler_alive=alive,
            scheduler_checked_at=checked_at,
            today=now.date().isoformat(),
            kinds=sch.KINDS,
            day_names=DAY_NAMES[lang],
            month_names=MONTH_NAMES[lang],
            last_day=sch.LAST_DAY,
            repeat_every=sch.REPEAT_EVERY,
            repeat_for=sch.REPEAT_FOR,
            max_name=sch.MAX_NAME,
            duration=lambda minutes: duration_text(minutes, lang),
            describe=lambda schedule: describe_schedule(schedule, lang),
            label=lambda schedule: schedule_label(schedule, lang),
        )

    @app.post("/programacion")
    def add_schedule(
        request: Request,
        kind: str = Form(""), name: str = Form(""), start_date: str = Form(""), start_time: str = Form(""),
        every_days: str = Form("1"), every_weeks: str = Form("1"),
        days: list[str] = Form([]), months: list[str] = Form([]), month_days: list[str] = Form([]),
        repeat: str = Form(""), repeat_every: str = Form(""), repeat_for: str = Form(""),
        expires: str = Form(""), expires_date: str = Form(""), expires_time: str = Form(""),
        csrf: str = Form(""),
    ):
        require_post(request, csrf)
        try:
            columns = sch.build(
                kind, start_date, start_time, name=name,
                every=every_weeks if kind == sch.WEEKLY else every_days,
                days=days, months=months, month_days=month_days,
                repeat=bool(repeat), repeat_every=repeat_every, repeat_for=repeat_for,
                expires=bool(expires), expires_date=expires_date, expires_time=expires_time,
            )
        except ScheduleError as error:
            flash(request, error.key, "error")
            return back("/programacion")
        store.add_schedule(columns)
        store.log_event(st.SCHEDULE_ADDED, message=schedule_message(columns), actor=request.session["user"])
        flash(request, "schedule_saved")
        return back("/programacion")

    @app.post("/programacion/{schedule_id}/toggle")
    def toggle_schedule(request: Request, schedule_id: int, csrf: str = Form("")):
        require_post(request, csrf)
        row = store.schedule(schedule_id)
        if row:
            store.set_schedule_active(schedule_id, not row["active"])
            store.log_event(st.SCHEDULE_PAUSED if row["active"] else st.SCHEDULE_ACTIVATED,
                            message=schedule_message(row), actor=request.session["user"])
            flash(request, "schedule_paused_msg" if row["active"] else "schedule_activated_msg")
        return back("/programacion")

    @app.post("/programacion/{schedule_id}/delete")
    def delete_schedule(request: Request, schedule_id: int, csrf: str = Form("")):
        require_post(request, csrf)
        row = store.schedule(schedule_id)
        if row:
            store.remove_schedule(schedule_id)
            store.log_event(st.SCHEDULE_REMOVED, message=schedule_message(row), actor=request.session["user"])
            flash(request, "schedule_removed_msg")
        return back("/programacion")

    @app.get("/historial.xlsx")
    def export_history(request: Request, vendor: str = "", desde: str = "", hasta: str = ""):
        require_user(request)
        lang = lang_of(request)
        t = translator(lang)
        history = HistoryFilter.from_query(vendor, desde, hasta)
        def detail(event) -> str:
            if event["kind"].startswith("schedule_"):
                return schedule_text(event["message"], lang)
            return saved_message(event["message"], lang)

        def origin(event) -> str:
            if origin_key(event):
                return str(t(origin_key(event)))
            return str(t("actor_seed")) if event["actor"] == "seed" else (event["actor"] or "")

        rows = [
            [
                local_time(event["at"], lang),
                str(t(title_key(event))),
                event["vendor"] if event["vendor"] is not None else "",
                str(t(STATUS_LABELS[event["status"]])) if event["status"] in STATUS_LABELS else "",
                origin(event),
                detail(event),
            ]
            for event in history.search(store, limit=None)
        ]
        headers = [str(t(key)) for key in ("xl_date", "xl_event", "xl_vendor", "xl_status", "xl_origin", "xl_detail")]
        content = workbook(str(t("xl_sheet")), headers, rows, widths=[18, 28, 12, 14, 18, 90])
        filename = f"{t('xl_file')}_supply_relay_{datetime.now():%Y%m%d_%H%M}.xlsx"
        return Response(
            content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/vendors")
    def add_vendor(request: Request, number: str = Form(""), csrf: str = Form("")):
        require_post(request, csrf)
        number = number.strip()
        if not number.isdigit() or not 0 < int(number) <= MAX_VENDOR:
            flash(request, "invalid_vendor", "error")
        elif store.add_vendor(int(number)):
            store.log_event(st.ADDED, int(number), actor=request.session["user"])
            flash(request, "vendor_added", number=int(number))
        else:
            flash(request, "vendor_exists", "error", number=int(number))
        return back()

    @app.post("/vendors/{number}/toggle")
    def toggle_vendor(request: Request, number: int, csrf: str = Form("")):
        require_post(request, csrf)
        vendor = store.vendor(number)
        if vendor:
            store.set_active(number, not vendor["active"])
            store.log_event(st.PAUSED if vendor["active"] else st.ACTIVATED, number, actor=request.session["user"])
            flash(request, "vendor_paused" if vendor["active"] else "vendor_activated", number=number)
        return back()

    @app.post("/vendors/{number}/delete")
    def delete_vendor(request: Request, number: int, csrf: str = Form("")):
        require_post(request, csrf)
        if store.vendor(number):
            store.remove_vendor(number)
            store.log_event(st.REMOVED, number, actor=request.session["user"])
            flash(request, "vendor_removed", number=number)
        return back()

    @app.post("/vendors/{number}/sync")
    def sync_vendor(request: Request, number: int, background: BackgroundTasks, csrf: str = Form("")):
        require_post(request, csrf)
        if not store.vendor(number):
            return back()
        if start_sync(request, background, [number]):
            flash(request, "syncing_vendor", number=number)
        else:
            flash(request, "sync_busy", "error")
        return back()

    @app.post("/sync")
    def sync_all(request: Request, background: BackgroundTasks, csrf: str = Form("")):
        require_post(request, csrf)
        if start_sync(request, background, None):
            flash(request, "sync_started")
        else:
            flash(request, "sync_busy", "error")
        return back()

    return app
