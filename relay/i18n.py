"""Screen texts in Spanish (default), English and Japanese.

t("key", name=value) returns safe HTML: the texts below are trusted and every
value passed in is escaped unless it is already Markup.
"""

import re
from collections.abc import Callable

from markupsafe import Markup

DEFAULT = "es"
LANGUAGES = {"es": "Español", "en": "English", "ja": "日本語"}
DATE_FORMATS = {"es": "%d/%m/%Y %H:%M", "en": "%Y-%m-%d %H:%M", "ja": "%Y/%m/%d %H:%M"}

TEXTS: dict[str, dict[str, str]] = {
    # General
    "language": {"es": "Idioma", "en": "Language", "ja": "言語"},
    "change_language": {"es": "Cambiar", "en": "Change", "ja": "変更"},
    "theme_tip": {"es": "Cambiar a modo claro u oscuro", "en": "Switch between light and dark mode", "ja": "ライト／ダークモードを切り替え"},
    "close": {"es": "Cerrar", "en": "Close", "ja": "閉じる"},
    "close_tip": {"es": "Cerrar notificación", "en": "Close notification", "ja": "通知を閉じる"},
    "skip_to_content": {"es": "Saltar al contenido", "en": "Skip to content", "ja": "本文へスキップ"},
    "sign_out": {"es": "Salir", "en": "Sign out", "ja": "ログアウト"},
    "sign_out_tip": {"es": "Cerrar sesión", "en": "Sign out of Supply Relay", "ja": "Supply Relay からログアウト"},

    # Login
    "login_title": {"es": "Iniciar sesión", "en": "Sign in", "ja": "ログイン"},
    "login_subtitle": {"es": "Infor LX → Portal de proveedores", "en": "Infor LX → Supplier portal", "ja": "Infor LX → サプライヤーポータル"},
    "username": {"es": "Usuario", "en": "Username", "ja": "ユーザー名"},
    "password": {"es": "Contraseña", "en": "Password", "ja": "パスワード"},
    "sign_in": {"es": "Entrar", "en": "Sign in", "ja": "ログイン"},
    "sign_in_tip": {"es": "Entrar a Supply Relay", "en": "Sign in to Supply Relay", "ja": "Supply Relay にログイン"},

    # Vendors
    "vendors": {"es": "Proveedores", "en": "Vendors", "ja": "仕入先"},
    "vendor_number": {"es": "Número de vendor", "en": "Vendor number", "ja": "仕入先番号"},
    "vendor_placeholder": {"es": "Número de vendor, ej. 400191", "en": "Vendor number, e.g. 400191", "ja": "仕入先番号（例：400191）"},
    "add": {"es": "Agregar", "en": "Add", "ja": "追加"},
    "add_tip": {"es": "Agregar el vendor a la lista de sincronización", "en": "Add the vendor to the sync list", "ja": "仕入先を同期リストに追加"},
    "syncing": {"es": "Sincronizando", "en": "Syncing", "ja": "同期中"},
    "sync_all": {"es": "Sincronizar todo", "en": "Sync all", "ja": "すべて同期"},
    "sync_all_tip": {"es": "Enviar al portal todos los vendors activos y el calendario", "en": "Send every active vendor and the calendar to the portal", "ja": "有効なすべての仕入先とカレンダーをポータルへ送信"},
    "col_vendor": {"es": "Proveedor", "en": "Vendor", "ja": "仕入先"},
    "col_rows": {"es": "Filas", "en": "Rows", "ja": "行数"},
    "col_status": {"es": "Estado", "en": "Status", "ja": "状態"},
    "col_last": {"es": "Último envío", "en": "Last sent", "ja": "最終送信"},
    "col_actions": {"es": "Acciones", "en": "Actions", "ja": "操作"},
    "not_synced": {"es": "Aún no sincronizado", "en": "Not synced yet", "ja": "未同期"},
    "active": {"es": "Activo", "en": "Active", "ja": "有効"},
    "paused": {"es": "Pausado", "en": "Paused", "ja": "一時停止"},
    "sync_tip": {"es": "Sincronizar este vendor ahora", "en": "Sync this vendor now", "ja": "この仕入先を今すぐ同期"},
    "pause_tip": {"es": "Pausar: no se enviará hasta activarlo", "en": "Pause: it won't be sent until you activate it", "ja": "一時停止：再開するまで送信されません"},
    "activate_tip": {"es": "Activar: se volverá a enviar", "en": "Activate: it will be sent again", "ja": "再開：再び送信されます"},
    "remove_tip": {"es": "Quitar de la lista", "en": "Remove from the list", "ja": "リストから削除"},
    "confirm_remove": {
        "es": "El proveedor {number} se quitará de la lista y ya no se sincronizará. El portal conservará sus últimos datos.",
        "en": "Vendor {number} will be removed from the list and no longer synced. The portal will keep its last data.",
        "ja": "仕入先 {number} はリストから削除され、今後は同期されません。ポータルには最後のデータが残ります。",
    },
    "confirm_title": {"es": "¿Eliminar proveedor?", "en": "Remove vendor?", "ja": "仕入先を削除しますか？"},
    "confirm_yes": {"es": "Sí, eliminar", "en": "Yes, remove", "ja": "削除する"},
    "confirm_yes_tip": {"es": "Quitar el vendor de la lista", "en": "Remove the vendor from the list", "ja": "仕入先をリストから削除"},
    "cancel": {"es": "Cancelar", "en": "Cancel", "ja": "キャンセル"},
    "cancel_tip": {"es": "Cerrar sin eliminar", "en": "Close without removing", "ja": "削除せずに閉じる"},
    "empty_title": {"es": "Todavía no hay proveedores", "en": "No vendors yet", "ja": "仕入先はまだありません"},
    "empty_text": {
        "es": "Agrega el número de vendor de Infor de cada proveedor que usará el portal.",
        "en": "Add the Infor vendor number of each supplier that will use the portal.",
        "ja": "ポータルを利用する各仕入先の Infor 仕入先番号を追加してください。",
    },

    # History
    "history": {"es": "Historial", "en": "History", "ja": "履歴"},
    "filter_history": {"es": "Filtrar historial", "en": "Filter history", "ja": "履歴を絞り込み"},
    "search_placeholder": {"es": "Buscar por número", "en": "Search by number", "ja": "番号で検索"},
    "from": {"es": "Desde", "en": "From", "ja": "開始日"},
    "to": {"es": "Hasta", "en": "To", "ja": "終了日"},
    "filter": {"es": "Filtrar", "en": "Filter", "ja": "絞り込み"},
    "filter_tip": {"es": "Aplicar los filtros al historial", "en": "Apply the filters to the history", "ja": "条件で履歴を絞り込む"},
    "clear": {"es": "Limpiar", "en": "Clear", "ja": "クリア"},
    "clear_tip": {"es": "Quitar los filtros", "en": "Remove the filters", "ja": "条件を解除"},
    "download_excel": {"es": "Descargar Excel", "en": "Download Excel", "ja": "Excel をダウンロード"},
    "download_excel_tip": {
        "es": "Descargar en Excel el historial con los filtros aplicados",
        "en": "Download the history with the current filters as Excel",
        "ja": "絞り込んだ履歴を Excel でダウンロード",
    },
    "event_added": {"es": "Proveedor {vendor} agregado", "en": "Vendor {vendor} added", "ja": "仕入先 {vendor} を追加"},
    "event_paused": {"es": "Proveedor {vendor} pausado", "en": "Vendor {vendor} paused", "ja": "仕入先 {vendor} を一時停止"},
    "event_activated": {"es": "Proveedor {vendor} activado", "en": "Vendor {vendor} activated", "ja": "仕入先 {vendor} を再開"},
    "event_removed": {"es": "Proveedor {vendor} eliminado", "en": "Vendor {vendor} removed", "ja": "仕入先 {vendor} を削除"},
    "title_added": {"es": "Proveedor agregado", "en": "Vendor added", "ja": "仕入先を追加"},
    "title_paused": {"es": "Proveedor pausado", "en": "Vendor paused", "ja": "仕入先を一時停止"},
    "title_activated": {"es": "Proveedor activado", "en": "Vendor activated", "ja": "仕入先を再開"},
    "title_removed": {"es": "Proveedor eliminado", "en": "Vendor removed", "ja": "仕入先を削除"},
    "sync_ok": {"es": "Sincronización completa", "en": "Sync completed", "ja": "同期完了"},
    "sync_partial": {"es": "Sincronización con errores", "en": "Sync with errors", "ja": "一部エラーのある同期"},
    "sync_error": {"es": "Sincronización fallida", "en": "Sync failed", "ja": "同期失敗"},
    "sync_running": {"es": "Sincronización en curso", "en": "Sync running", "ja": "同期実行中"},
    "trigger_manual": {"es": "Manual", "en": "Manual", "ja": "手動"},
    "trigger_scheduled": {"es": "Programada", "en": "Scheduled", "ja": "スケジュール"},
    "show_error": {"es": "Ver error", "en": "Show error", "ja": "エラーを表示"},
    "show_errors": {"es": "Ver {count} errores", "en": "Show {count} errors", "ja": "エラー {count} 件を表示"},
    "pagination": {"es": "Páginas del historial", "en": "History pages", "ja": "履歴のページ"},
    "previous": {"es": "Anterior", "en": "Previous", "ja": "前へ"},
    "previous_tip": {"es": "Página anterior", "en": "Previous page", "ja": "前のページ"},
    "next": {"es": "Siguiente", "en": "Next", "ja": "次へ"},
    "next_tip": {"es": "Página siguiente", "en": "Next page", "ja": "次のページ"},
    "page_tip": {"es": "Ir a la página {number}", "en": "Go to page {number}", "ja": "{number} ページへ"},
    "showing": {"es": "{first}–{last} de {total}", "en": "{first}–{last} of {total}", "ja": "全 {total} 件中 {first}–{last} 件"},
    "no_events": {"es": "Sin movimientos todavía.", "en": "No events yet.", "ja": "履歴はまだありません。"},
    "no_events_filtered": {"es": "No hay movimientos con estos filtros.", "en": "No events match these filters.", "ja": "条件に一致する履歴はありません。"},

    # Menu
    "menu": {"es": "Menú", "en": "Menu", "ja": "メニュー"},
    "nav_vendors": {"es": "Proveedores", "en": "Vendors", "ja": "仕入先"},
    "nav_schedule": {"es": "Programación", "en": "Schedule", "ja": "スケジュール"},
    "nav_history": {"es": "Historial", "en": "History", "ja": "履歴"},
    "next_sync": {"es": "Próxima sincronización: {when}", "en": "Next sync: {when}", "ja": "次回の同期：{when}"},
    "no_schedule": {"es": "Sin sincronización programada", "en": "No scheduled sync", "ja": "予定された同期はありません"},

    # Schedule
    "schedule_title": {"es": "Programación", "en": "Schedule", "ja": "スケジュール"},
    "schedule_intro": {
        "es": "Como en el Programador de tareas de Windows: cuándo se envían automáticamente al portal todos los proveedores activos y el calendario.",
        "en": "Like Windows Task Scheduler: when every active vendor and the calendar are sent to the portal automatically.",
        "ja": "Windows タスク スケジューラと同じように、有効なすべての仕入先とカレンダーを自動でポータルへ送信するタイミングを設定します。",
    },
    "next_run": {"es": "Próxima ejecución", "en": "Next run", "ja": "次回の実行"},
    "scheduler": {"es": "Programador", "en": "Scheduler", "ja": "スケジューラー"},
    "scheduler_ok": {"es": "En marcha · revisó {when}", "en": "Running · checked {when}", "ja": "稼働中・最終確認 {when}"},
    "scheduler_off": {"es": "Detenido", "en": "Stopped", "ja": "停止中"},
    "scheduler_off_help": {
        "es": "No ha revisado la programación en los últimos minutos, así que no se ejecutará. En el servidor debe existir la tarea de Windows que ejecuta «python -m relay.scheduler» cada minuto; en tu computadora, deja corriendo «python -m relay.scheduler --work».",
        "en": "It has not checked the schedule in the last minutes, so nothing will run. On the server, the Windows task that runs “python -m relay.scheduler” every minute must exist; on your computer, keep “python -m relay.scheduler --work” running.",
        "ja": "ここ数分スケジュールを確認していないため、同期は実行されません。サーバーでは「python -m relay.scheduler」を毎分実行する Windows タスクが必要です。お使いのパソコンでは「python -m relay.scheduler --work」を実行したままにしてください。",
    },
    "new_schedule": {"es": "Nueva programación", "en": "New schedule", "ja": "新しいスケジュール"},
    "days": {"es": "Días", "en": "Days", "ja": "曜日"},
    "schedule_name": {"es": "Nombre", "en": "Name", "ja": "名前"},
    "hint_name": {"es": "Opcional. Para reconocerla en la lista y el historial.", "en": "Optional. To recognize it in the list and the history.", "ja": "任意。一覧と履歴で見分けるための名前です。"},
    "hint_trigger": {"es": "Con qué frecuencia se sincroniza.", "en": "How often it syncs.", "ja": "同期する頻度です。"},
    "hint_start": {"es": "Desde cuándo y a qué hora.", "en": "From when and at what time.", "ja": "開始する日付と時刻です。"},
    "recurrence": {"es": "Recurrencia", "en": "Recurrence", "ja": "繰り返し"},
    "hint_recur": {"es": "Qué días se ejecuta.", "en": "Which days it runs.", "ja": "実行する日です。"},
    "hint_once": {"es": "Se ejecuta una sola vez, en la fecha y hora de inicio.", "en": "It runs only once, on the start date and time.", "ja": "開始日時に 1 回だけ実行されます。"},
    "hint_advanced": {"es": "Repetir durante el día o dejar de ejecutarse en una fecha.", "en": "Repeat during the day or stop running on a date.", "ja": "1 日の中で繰り返す、または指定日で終了します。"},
    "schedule_name_placeholder": {"es": "Ej. Turno de la mañana", "en": "E.g. Morning shift", "ja": "例：朝のシフト"},
    "trigger": {"es": "Desencadenador", "en": "Trigger", "ja": "トリガー"},
    "kind_once": {"es": "Una vez", "en": "One time", "ja": "1 回"},
    "kind_daily": {"es": "Diario", "en": "Daily", "ja": "毎日"},
    "kind_weekly": {"es": "Semanal", "en": "Weekly", "ja": "毎週"},
    "kind_monthly": {"es": "Mensual", "en": "Monthly", "ja": "毎月"},
    "start": {"es": "Iniciar", "en": "Start", "ja": "開始"},
    "start_date": {"es": "Fecha de inicio", "en": "Start date", "ja": "開始日"},
    "start_time": {"es": "Hora de inicio", "en": "Start time", "ja": "開始時刻"},
    "repeat_every_label": {"es": "Repetir cada", "en": "Recur every", "ja": "間隔"},
    "unit_days": {"es": "días", "en": "days", "ja": "日ごと"},
    "unit_weeks": {"es": "semanas, el:", "en": "weeks on:", "ja": "週ごと（曜日）："},
    "months": {"es": "Meses", "en": "Months", "ja": "月"},
    "month_days": {"es": "Días del mes", "en": "Days of the month", "ja": "日付"},
    "last_day": {"es": "Último", "en": "Last", "ja": "最終日"},
    "advanced": {"es": "Configuración avanzada", "en": "Advanced settings", "ja": "詳細設定"},
    "repeat_task": {"es": "Repetir la tarea cada", "en": "Repeat task every", "ja": "繰り返し間隔"},
    "for_duration": {"es": "durante", "en": "for a duration of", "ja": "継続時間"},
    "expire": {"es": "Caduca", "en": "Expire", "ja": "有効期限"},
    "n_minutes": {"es": "{n} minutos", "en": "{n} minutes", "ja": "{n} 分"},
    "n_hours": {"es": "{n} h", "en": "{n} h", "ja": "{n} 時間"},
    "n_days": {"es": "{n} día(s)", "en": "{n} day(s)", "ja": "{n} 日"},
    "desc_once": {"es": "Una vez, el {when}", "en": "Once, on {when}", "ja": "1 回：{when}"},
    "desc_daily": {"es": "Todos los días a las {time}", "en": "Every day at {time}", "ja": "毎日 {time}"},
    "desc_daily_n": {"es": "Cada {n} días a las {time}", "en": "Every {n} days at {time}", "ja": "{n} 日ごと {time}"},
    "desc_weekly": {"es": "{days} a las {time}", "en": "{days} at {time}", "ja": "{days} {time}"},
    "desc_weekly_n": {"es": "Cada {n} semanas: {days} a las {time}", "en": "Every {n} weeks: {days} at {time}", "ja": "{n} 週ごと：{days} {time}"},
    "desc_monthly": {"es": "Día {days} de {months} a las {time}", "en": "Day {days} of {months} at {time}", "ja": "{months} の {days} 日 {time}"},
    "every_month": {"es": "todos los meses", "en": "every month", "ja": "毎月"},
    "desc_repeat": {"es": "cada {every} durante {duration}", "en": "every {every} for {duration}", "ja": "{every} ごと（{duration}）"},
    "desc_expires": {"es": "caduca el {when}", "en": "expires {when}", "ja": "{when} に期限切れ"},
    "col_schedule": {"es": "Programación", "en": "Schedule", "ja": "スケジュール"},
    "expired": {"es": "Sin más ejecuciones", "en": "No more runs", "ja": "今後の実行なし"},
    "save": {"es": "Guardar", "en": "Save", "ja": "保存"},
    "save_schedule_tip": {"es": "Guardar la programación", "en": "Save the schedule", "ja": "スケジュールを保存"},
    "every_day": {"es": "Todos los días", "en": "Every day", "ja": "毎日"},
    "weekdays": {"es": "Lunes a viernes", "en": "Monday to Friday", "ja": "月曜〜金曜"},
    "mon_sat": {"es": "Lunes a sábado", "en": "Monday to Saturday", "ja": "月曜〜土曜"},
    "pause_schedule_tip": {"es": "Pausar: no se ejecutará hasta activarla", "en": "Pause: it won't run until you activate it", "ja": "一時停止：再開するまで実行されません"},
    "activate_schedule_tip": {"es": "Activar: se volverá a ejecutar", "en": "Activate: it will run again", "ja": "再開：再び実行されます"},
    "remove_schedule_tip": {"es": "Eliminar esta programación", "en": "Remove this schedule", "ja": "このスケジュールを削除"},
    "confirm_schedule_title": {"es": "¿Eliminar programación?", "en": "Remove schedule?", "ja": "スケジュールを削除しますか？"},
    "confirm_remove_schedule": {
        "es": "La sincronización de «{schedule}» dejará de ejecutarse.",
        "en": "The sync of “{schedule}” will stop running.",
        "ja": "「{schedule}」の同期は実行されなくなります。",
    },
    "empty_schedule_title": {"es": "Todavía no hay programación", "en": "No schedule yet", "ja": "スケジュールはまだありません"},
    "empty_schedule_text": {
        "es": "Crea una arriba: elige el desencadenador, la fecha y la hora de inicio.",
        "en": "Create one above: choose the trigger and the start date and time.",
        "ja": "上で作成してください。トリガーと開始日時を選びます。",
    },
    "schedule_saved": {"es": "Programación guardada.", "en": "Schedule saved.", "ja": "スケジュールを保存しました。"},
    "schedule_no_days": {"es": "Elige al menos un día.", "en": "Choose at least one day.", "ja": "曜日を 1 つ以上選んでください。"},
    "schedule_bad_kind": {"es": "Elige un desencadenador.", "en": "Choose a trigger.", "ja": "トリガーを選んでください。"},
    "schedule_bad_start": {"es": "Elige una fecha y hora de inicio válidas.", "en": "Choose a valid start date and time.", "ja": "有効な開始日時を選んでください。"},
    "schedule_past": {"es": "Esa fecha y hora ya pasaron.", "en": "That date and time have already passed.", "ja": "その日時はすでに過ぎています。"},
    "schedule_bad_every": {"es": "El intervalo de repetición no es válido.", "en": "The recurrence interval is not valid.", "ja": "間隔が正しくありません。"},
    "schedule_no_months": {"es": "Elige al menos un mes.", "en": "Choose at least one month.", "ja": "月を 1 つ以上選んでください。"},
    "schedule_no_month_days": {"es": "Elige al menos un día del mes.", "en": "Choose at least one day of the month.", "ja": "日付を 1 つ以上選んでください。"},
    "schedule_bad_repeat": {"es": "Elige cada cuánto y durante cuánto repetir.", "en": "Choose how often and for how long to repeat.", "ja": "繰り返しの間隔と継続時間を選んでください。"},
    "schedule_bad_expiry": {"es": "La caducidad debe ser posterior al inicio.", "en": "The expiry must be after the start.", "ja": "有効期限は開始より後にしてください。"},
    "schedule_paused_msg": {"es": "Programación pausada.", "en": "Schedule paused.", "ja": "スケジュールを一時停止しました。"},
    "schedule_activated_msg": {"es": "Programación activada.", "en": "Schedule activated.", "ja": "スケジュールを再開しました。"},
    "schedule_removed_msg": {"es": "Programación eliminada.", "en": "Schedule removed.", "ja": "スケジュールを削除しました。"},
    "event_schedule_added": {"es": "Programación agregada", "en": "Schedule added", "ja": "スケジュールを追加"},
    "event_schedule_paused": {"es": "Programación pausada", "en": "Schedule paused", "ja": "スケジュールを一時停止"},
    "event_schedule_activated": {"es": "Programación activada", "en": "Schedule activated", "ja": "スケジュールを再開"},
    "event_schedule_removed": {"es": "Programación eliminada", "en": "Schedule removed", "ja": "スケジュールを削除"},
    "title_schedule_added": {"es": "Programación agregada", "en": "Schedule added", "ja": "スケジュールを追加"},
    "title_schedule_paused": {"es": "Programación pausada", "en": "Schedule paused", "ja": "スケジュールを一時停止"},
    "title_schedule_activated": {"es": "Programación activada", "en": "Schedule activated", "ja": "スケジュールを再開"},
    "title_schedule_removed": {"es": "Programación eliminada", "en": "Schedule removed", "ja": "スケジュールを削除"},
    "actor_seed": {"es": "Carga inicial", "en": "Initial load", "ja": "初期登録"},

    # Status of a send
    "status_ok": {"es": "Correcto", "en": "OK", "ja": "成功"},
    "status_error": {"es": "Error", "en": "Error", "ja": "エラー"},
    "status_partial": {"es": "Con errores", "en": "With errors", "ja": "一部エラー"},
    "status_running": {"es": "En curso", "en": "Running", "ja": "実行中"},

    # Excel
    "xl_sheet": {"es": "Historial", "en": "History", "ja": "履歴"},
    "xl_file": {"es": "historial", "en": "history", "ja": "history"},
    "xl_date": {"es": "Fecha", "en": "Date", "ja": "日時"},
    "xl_event": {"es": "Evento", "en": "Event", "ja": "イベント"},
    "xl_vendor": {"es": "Proveedor", "en": "Vendor", "ja": "仕入先"},
    "xl_status": {"es": "Estado", "en": "Status", "ja": "状態"},
    "xl_origin": {"es": "Usuario / origen", "en": "User / source", "ja": "ユーザー／実行元"},
    "xl_detail": {"es": "Detalle", "en": "Detail", "ja": "詳細"},

    # Notifications
    "too_many_attempts": {
        "es": "Demasiados intentos. Espera 15 minutos e inténtalo de nuevo.",
        "en": "Too many attempts. Wait 15 minutes and try again.",
        "ja": "試行回数が多すぎます。15 分後にもう一度お試しください。",
    },
    "wrong_login": {"es": "Usuario o contraseña incorrectos.", "en": "Wrong username or password.", "ja": "ユーザー名またはパスワードが違います。"},
    "invalid_vendor": {
        "es": "Escribe un número de proveedor válido (solo dígitos, hasta 8).",
        "en": "Enter a valid vendor number (digits only, up to 8).",
        "ja": "有効な仕入先番号を入力してください（数字のみ、8 桁まで）。",
    },
    "vendor_added": {
        "es": "Proveedor {number} agregado. Se enviará en la próxima sincronización.",
        "en": "Vendor {number} added. It will be sent in the next sync.",
        "ja": "仕入先 {number} を追加しました。次回の同期で送信されます。",
    },
    "vendor_exists": {"es": "El proveedor {number} ya está en la lista.", "en": "Vendor {number} is already in the list.", "ja": "仕入先 {number} はすでにリストにあります。"},
    "vendor_paused": {"es": "Proveedor {number} pausado.", "en": "Vendor {number} paused.", "ja": "仕入先 {number} を一時停止しました。"},
    "vendor_activated": {"es": "Proveedor {number} activado.", "en": "Vendor {number} activated.", "ja": "仕入先 {number} を再開しました。"},
    "vendor_removed": {
        "es": "Proveedor {number} eliminado de la lista. El portal conserva sus últimos datos.",
        "en": "Vendor {number} removed from the list. The portal keeps its last data.",
        "ja": "仕入先 {number} をリストから削除しました。ポータルには最後のデータが残ります。",
    },
    "syncing_vendor": {"es": "Sincronizando el proveedor {number}…", "en": "Syncing vendor {number}…", "ja": "仕入先 {number} を同期しています…"},
    "sync_busy": {"es": "Ya hay una sincronización en curso.", "en": "A sync is already running.", "ja": "同期はすでに実行中です。"},
    "sync_started": {
        "es": "Sincronización iniciada. La página se actualiza sola mientras corre.",
        "en": "Sync started. The page refreshes by itself while it runs.",
        "ja": "同期を開始しました。実行中はページが自動で更新されます。",
    },
}

# Messages saved by the sync (always in Spanish in the database), shown in the chosen language
SAVED_MESSAGES = [
    (re.compile(r"No existe o está inactivo en Infor \(AVM\)\."),
     {"en": "Does not exist or is inactive in Infor (AVM).", "ja": "Infor（AVM）に存在しないか、無効です。"}),
    (re.compile(r"(\d+) proveedor\(es\) enviados\."),
     {"en": r"\1 vendor(s) sent.", "ja": r"仕入先 \1 件を送信しました。"}),
    (re.compile(r"Calendario:"), {"en": "Calendar:", "ja": "カレンダー:"}),
    (re.compile(r"El portal respondió"), {"en": "The portal answered", "ja": "ポータルの応答"}),
]


def language(value: str | None) -> str:
    return value if value in LANGUAGES else DEFAULT


def translator(lang: str) -> Callable[..., Markup]:
    def t(key: str, **values) -> Markup:
        text = TEXTS[key].get(lang) or TEXTS[key][DEFAULT]
        return Markup(text).format(**values) if values else Markup(text)

    return t


# Short day names, Monday first (1 = Monday ... 7 = Sunday)
DAY_NAMES = {
    "es": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "ja": ["月", "火", "水", "木", "金", "土", "日"],
}


MONTH_NAMES = {
    "es": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "ja": ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"],
}


def describe_days(days, lang: str) -> str:
    """"Lunes a viernes", "Todos los días" or "Lun, Mié, Vie"."""
    days = tuple(days)
    named = {(1, 2, 3, 4, 5, 6, 7): "every_day", (1, 2, 3, 4, 5): "weekdays", (1, 2, 3, 4, 5, 6): "mon_sat"}
    if days in named:
        return str(translator(lang)(named[days]))
    return ", ".join(DAY_NAMES[lang][day - 1] for day in days)


def saved_message(text: str | None, lang: str) -> str:
    if not text or lang == DEFAULT:
        return text or ""
    for pattern, translations in SAVED_MESSAGES:
        text = pattern.sub(translations[lang], text)
    return text
