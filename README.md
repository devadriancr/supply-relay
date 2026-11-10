# Supply Relay

Servicio interno que copia la información de proveedores de **Infor LX** al **portal de proveedores** (Laravel, proyecto `YSP`).

```
RED INTERNA                                        PORTAL (expuesto)
┌──────────┐   lectura   ┌──────────────┐  HTTPS firmado  ┌──────────────────┐
│ Infor LX │ ──────────► │ Supply Relay │ ──────────────► │ /api/sync/...    │
│  (ODBC)  │   (ODBC)    │  (este repo) │   solo salida   │ Laravel + BD     │
└──────────┘             └──────────────┘                 └──────────────────┘
```

- El portal **nunca** se conecta a Infor. Solo recibe lo que este servicio le envía.
- Solo salen de Infor los datos que se imprimen en las etiquetas y el DI, y solo de los proveedores dados de alta en la pantalla de administración. Nunca salen precios, costos, datos bancarios ni capacidades de planta.
- Cada envío va firmado con una llave compartida (`SYNC_KEY`). El portal rechaza cualquier petición que no esté firmada con esa llave, que se haya modificado en el camino, que tenga más de 5 minutos o que ya se haya usado antes.

## Qué envía

| Al portal | Desde Infor | Cuándo |
|---|---|---|
| Proveedor | AVM (`VMID = 'VM'`, `VNSTAT = 'A'`) | Cada corrida |
| Números de parte | IIM + IIU, siguiente proceso con FRT + LWK | Cada corrida |
| Líneas de orden de compra (etiquetas) | HPO | Desde el día 1 del mes anterior en adelante |
| Filas del DI | HPO + KFP + YKRE4, YM200, YM202, TM200 | Desde el día 1 del mes anterior en adelante |
| Calendario laboral | FSC (`SCID = 'SC'`) | Año del mes anterior, el actual y el siguiente, en la corrida completa |

Cada proveedor se reemplaza completo en el portal dentro de una transacción. Si algo falla, el proveedor sigue viendo los datos anteriores.

## Instalación (Windows Server + IIS)

> El manual completo de los dos proyectos, en local y en IIS, está en el portal: `YSP\docs\INSTALACION.md`.

Requisitos: Python 3.12, el controlador ODBC de IBM i Access (64 bits) y el módulo [HttpPlatformHandler](https://www.iis.net/downloads/microsoft/httpplatformhandler) de IIS.

```powershell
cd C:\inetpub\supply-relay
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Llena el `.env`:

1. **`INFOR_USERNAME` / `INFOR_PASSWORD`**: un usuario de Infor **de solo lectura**.
2. **`PORTAL_URL`**: la dirección del portal, con `https://`.
3. **`SYNC_KEY`**: genera una llave y pon **la misma** en el `.env` del portal:
   ```powershell
   .venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
   ```
4. **`SECRET_KEY`**: otra llave distinta, generada igual. Firma la sesión de la pantalla de administración.
5. **`ADMIN_PASSWORD_HASH`**: genera el hash de la contraseña del administrador:
   ```powershell
   .venv\Scripts\python.exe -m relay.passwd
   ```
6. **`CALENDAR_WORK_CENTER`**: el centro de trabajo (`SCRKC`) del calendario de planta en FSC. Ver la sección siguiente.

### Pantalla de administración en IIS

1. Crea un sitio (o aplicación) en IIS que apunte a esta carpeta, con un certificado HTTPS.
2. En `web.config` cambia `C:\inetpub\supply-relay` por la ruta real.
3. Da permisos de escritura a la identidad del Application Pool sobre las carpetas `data` y `logs`.
4. Publica el sitio **solo en la red interna**. Esta pantalla no debe ser accesible desde internet.

### Proveedores iniciales

Carga la lista de proveedores del portal, como un *seeder* de Laravel. Si se vuelve a ejecutar, solo agrega los que falten:

```powershell
.venv\Scripts\python.exe -m relay.seed
```

La lista está en `relay/seed.py`.

### Sincronización automática (pestaña Programación)

Cuándo sincronizar se elige en la pestaña **Programación**, como un desencadenador del Programador de tareas de Windows: **una vez**, **diario** (cada N días), **semanal** (cada N semanas, en ciertos días) o **mensual** (ciertos días del mes, incluido el último, en ciertos meses), desde una fecha y hora de inicio. En la configuración avanzada se puede **repetir cada 5–60 minutos durante** 15 min a 1 día, y poner una fecha de **caducidad**. Se pueden tener varias programaciones, cada una con un nombre opcional. Las programaciones del formato anterior (días + horas) se borran al actualizar. Quien las ejecuta es el **programador** (`relay.scheduler`), que funciona como el `schedule:run` de Laravel: se ejecuta cada minuto, revisa si a esa hora toca sincronizar y, si toca, corre la sincronización.

IIS detiene los procesos inactivos, así que el programador corre aparte con **una sola** tarea del Programador de tareas de Windows, que no cambia aunque cambien los horarios:

- **Programa:** `C:\inetpub\supply-relay\.venv\Scripts\python.exe`
- **Argumentos:** `-m relay.scheduler`
- **Iniciar en:** `C:\inetpub\supply-relay`
- **Desencadenador:** diario, a las 00:00, repetir cada **1 minuto** durante 1 día.
- Ejecutar aunque el usuario no haya iniciado sesión.

En tu computadora, en lugar de la tarea, deja corriendo en otra ventana (como `schedule:work` de Laravel):

```powershell
.venv\Scripts\python.exe -m relay.scheduler --work
```

- La pestaña **Programación** indica si el programador está **en marcha** (revisó en los últimos 3 minutos) o **detenido**.
- Las horas son las del reloj de la computadora donde corre el relay.
- Cada hora programada corre una sola vez. Si la computadora estaba apagada a esa hora, todavía corre si el programador revisa dentro de los 30 minutos siguientes.
- El botón **Sincronizar** y el programador nunca corren al mismo tiempo; si a la hora programada hay una sincronización manual en curso, el programador lo vuelve a intentar al minuto siguiente.
- `python -m relay.sync` sigue sirviendo para lanzar una sincronización completa a mano desde la consola.

## Centro de trabajo del calendario

El calendario de FSC depende de la planta (`SCFAC = 'YK1'`) y del centro de trabajo (`SCRKC`). Para saber cuál es el de la planta, compara en Infor:

```sql
SELECT SCRKC, SCYEAR, SUBSTR(SCTYPE, 1, 40)
FROM LX834F01.FSC
WHERE SCID = 'SC' AND SCFAC = 'YK1' AND SCYEAR = 2026
```

El registro correcto empieza igual que el calendario que mostraba el portal (`HHWW      W      W...`). Pon su `SCRKC` en `CALENDAR_WORK_CENTER` aquí y en `PORTAL_CALENDAR_WORK_CENTER` en el portal.

## Desarrollo

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m uvicorn relay.web:create_app --factory --reload   # con SECURE_COOKIES=false
```

| Archivo | Qué hace |
|---|---|
| `relay/infor.py` | Consultas a Infor y armado de lo que se envía |
| `relay/portal.py` | Envío firmado al portal |
| `relay/sync.py` | Una corrida completa (el "job") |
| `relay/scheduler.py` | Programador: decide cuándo toca sincronizar según la pestaña Programación |
| `relay/seed.py` | Proveedores iniciales |
| `relay/web.py` | Pantalla de administración: Proveedores, Programación e Historial |
| `relay/store.py` | Base local SQLite: proveedores, programación, historial y candado |
| `relay/auth.py` | Contraseña (scrypt), bloqueo por intentos fallidos y CSRF |
