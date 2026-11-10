"""Reads Infor LX (read only) and builds what the portal receives.

The queries are the ones the portal used to run itself (YPU202B labels and
YPU204B1/B2 delivery instruction). Only the fields printed on those documents
leave the company: no prices, costs, bank data or capacities.
"""

from collections.abc import Iterable, Sequence
from datetime import date, datetime

import pyodbc

from relay.config import Settings

ITEM_TYPES = "('G', 'P', 'Q', 'R')"
CHUNK_SIZE = 200
NO_UPPER_LIMIT = 99999999


# Value helpers. The ODBC driver returns fixed-width CHAR values and packed numbers.

def text(value) -> str | None:
    """Right-trimmed text; empty becomes None."""
    if value is None:
        return None
    value = str(value).rstrip()
    return value or None


def number(value) -> int:
    return int(round(float(value or 0)))


def quantity(value) -> float:
    return round(float(value or 0), 3)


def to_date(value) -> str | None:
    """Infor date (YYYYMMDD or CYYMMDD) as YYYY-MM-DD; None when empty or invalid."""
    value = number(value)
    if value <= 0:
        return None
    if value < 19000000:
        value += 19000000
    try:
        return datetime.strptime(str(value), "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def shift(order_control: str | None) -> str | None:
    """Delivery shift: 5th character of the PO control number (POCNO)."""
    return text((order_control or "").ljust(5)[4])


def chunks(items: Sequence, size: int = CHUNK_SIZE) -> Iterable[Sequence]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


# Payload builders (no database access, easy to test)

def vendor_fields(row: dict) -> dict:
    return {
        "name": text(row["VNDNAM"]) or "",
        "short_name": text(row["VNALPH"]),
        "street": text(row["VNDAD1"]),
        "locality": text(row["VNDAD2"]),
        "region": text(row["VNDAD3"]),
        "state": text(row["VSTATE"]),
        "postal_code": text(row["VPOST"]),
        "country": text(row["VCOUN"]),
        "tax_id": text(row["VMFSCD"]),
        "phone": text(row["VPHONE"]),
        "contact_name": text(row["VCON"]),
        "email": text(row["VMDATN"]),
    }


def part_fields(row: dict, next_process: str | None) -> dict:
    return {
        "number": text(row["IPROD"]),
        "description": text(row["IDESC"]),
        "project": text(row["IREF04"]),
        "standard_pack": text(row["IMSPKT"]),
        "standard_pack_quantity": max(0, number(row["IMBOXQ"])),
        "side": text(row["IUFD14"]),
        "next_process": next_process,
    }


def purchase_order_line(row: dict) -> dict | None:
    due_date = to_date(row["PDDTE"])
    if due_date is None:
        return None
    return {
        "part_number": text(row["PPROD"]),
        "number": number(row["PORD"]),
        "line": number(row["PLINE"]),
        "quantity": quantity(row["PQORD"]),
        # Already received in the plant: the portal shows how much is still missing
        "received_quantity": max(0.0, quantity(row.get("PQREC"))),
        "due_date": due_date,
        "shift": shift(row["POCNO"]),
        "warehouse": text(row["PWHSE"]),
    }


def delivery_row(row: dict) -> dict | None:
    due_date = to_date(row["DDTE"])
    if due_date is None:
        return None
    order = number(row["ORD"])
    return {
        "part_number": text(row["PROD"]),
        "origin": text(row["ORIGIN"]) or "",
        "number": order or None,
        "line": number(row["LINE"]) if order else None,
        "quantity": quantity(row["QTY"]),
        "due_date": due_date,
    }


def build_snapshot(vendor_row: dict, line_rows: list[dict], delivery_rows: list[dict],
                   part_rows: list[dict], next_processes: dict[str, str]) -> dict:
    lines = [line for line in map(purchase_order_line, line_rows) if line]
    deliveries = [row for row in map(delivery_row, delivery_rows) if row]
    used = {row["part_number"] for row in lines + deliveries}
    parts = [
        part_fields(row, next_processes.get(text(row["IPROD"])))
        for row in part_rows
        if text(row["IPROD"]) in used
    ]
    return {
        "vendor": vendor_fields(vendor_row),
        "part_numbers": list({part["number"]: part for part in parts}.values()),
        "purchase_order_lines": lines,
        "delivery_rows": deliveries,
    }


class InforReader:
    """Read-only connection to Infor LX. Use it as a context manager."""

    def __init__(self, settings: Settings, connect=pyodbc.connect):
        self.settings = settings
        self.lib = settings.infor_library
        self.custom = settings.infor_custom_library
        self._connect = connect
        self._connection = None

    def __enter__(self) -> "InforReader":
        # Braces keep a ; or } inside the credentials from changing the connection string
        def braced(value: str) -> str:
            return "{" + value.replace("}", "}}") + "}"

        dsn = self.settings.infor_dsn.rstrip(";") + ";"
        connection_string = (
            f"{dsn}Uid={braced(self.settings.infor_username)};"
            f"Pwd={braced(self.settings.infor_password.get_secret_value())};"
        )
        self._connection = self._connect(connection_string, readonly=True, autocommit=True, timeout=30)
        return self

    def __exit__(self, *exc) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def select(self, sql: str, params: Sequence = ()) -> list[dict]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(sql, list(params))
            columns = [column[0].upper() for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    # What the portal needs for one vendor

    def vendor_snapshot(self, vendor: int, since: date) -> dict | None:
        """Everything due from `since` on; None when the vendor is not active in AVM."""
        vendor_rows = self.select(
            f"""SELECT VNDNAM, VNALPH, VNDAD1, VNDAD2, VNDAD3, VSTATE, VPOST, VCOUN, VMFSCD, VPHONE, VCON, VMDATN
                FROM {self.lib}.AVM
                WHERE VENDOR = ? AND VMID = 'VM' AND VNSTAT = 'A'""",
            [vendor],
        )
        if not vendor_rows:
            return None

        from8 = int(since.strftime("%Y%m%d"))
        line_rows = self.label_lines(vendor, from8)
        delivery_rows = self.delivery_rows(vendor, from8)

        part_numbers = sorted({text(row["PPROD"]) for row in line_rows} | {text(row["PROD"]) for row in delivery_rows})
        part_rows = self.parts(part_numbers)
        next_processes = self.next_processes(vendor, part_numbers)

        return build_snapshot(vendor_rows[0], line_rows, delivery_rows, part_rows, next_processes)

    def label_lines(self, vendor: int, from8: int) -> list[dict]:
        """Open PO lines of the vendor (YPU202B selection)."""
        return self.select(
            f"""SELECT P.PORD, P.PLINE, P.PPROD, P.PQORD, P.PQREC, P.PDDTE, P.PWHSE, P.POCNO
                FROM {self.lib}.HPO AS P
                         INNER JOIN {self.lib}.IIM AS I ON I.IPROD = P.PPROD
                WHERE P.PVEND = ?
                  AND P.PQORD <> 0
                  AND I.IITYP IN {ITEM_TYPES}
                  AND P.PDDTE BETWEEN ? AND ?
                ORDER BY P.PDDTE, P.PPROD, P.PORD, P.PLINE""",
            [vendor, from8, NO_UPPER_LIMIT],
        )

    def delivery_rows(self, vendor: int, from8: int) -> list[dict]:
        """DI rows (YPU204B1/B2): PO lines, firm planned orders and forecasts.
        Columns: ORIGIN, ORD, LINE, PROD, QTY, DDTE."""
        item = f"I.IMPLC = ' ' AND I.IITYP IN {ITEM_TYPES}"

        # Forecast files share the same layout with a different prefix
        def forecast(file: str, p: str) -> str:
            return f"""
                SELECT 'FR', 0, 0, F.{p}PATN, SUM(F.{p}QUAN), F.{p}DATE
                FROM {self.custom}.{file} AS F
                         INNER JOIN {self.lib}.IIM AS I ON I.IPROD = F.{p}PATN
                WHERE I.IVEND = ? AND {item}
                  AND F.{p}DATE BETWEEN ? AND ? AND F.{p}QUAN <> 0
                GROUP BY F.{p}PATN, F.{p}DATE"""

        sql = f"""
            SELECT P.PID AS ORIGIN, P.PORD AS ORD, P.PLINE AS LINE, P.PPROD AS PROD, P.PQORD AS QTY, P.PDDTE AS DDTE
            FROM {self.lib}.HPO AS P
                     INNER JOIN {self.lib}.IIM AS I ON I.IPROD = P.PPROD
            WHERE P.PVEND = ? AND P.PQORD <> 0 AND {item}
              AND P.PDDTE BETWEEN ? AND ?

            UNION ALL
            SELECT 'FP', 0, 0, K.FPROD, K.FQTY, K.FRDTE
            FROM {self.lib}.KFP AS K
                     INNER JOIN {self.lib}.IIM AS I ON I.IPROD = K.FPROD
            WHERE I.IVEND = ? AND K.FTYPE = 'F' AND {item}
              AND K.FRDTE BETWEEN ? AND ?

            UNION ALL {forecast('YKRE4', 'K4')}
            UNION ALL {forecast('YM200', 'M0')}
            UNION ALL {forecast('YM202', 'M2')}
            UNION ALL {forecast('TM200', 'T2')}"""

        return self.select(sql, [vendor, from8, NO_UPPER_LIMIT] * 6)

    def parts(self, part_numbers: list[str]) -> list[dict]:
        """Item master data of the parts. IIU is limited to its first record."""
        rows = []
        for chunk in chunks(part_numbers):
            marks = ",".join("?" * len(chunk))
            rows += self.select(
                f"""SELECT I.IPROD, I.IDESC, I.IMBOXQ, I.IMSPKT, I.IREF04, U.IUFD14
                    FROM {self.lib}.IIM AS I
                             LEFT JOIN {self.lib}.IIU AS U ON U.IUPROD = I.IPROD AND U.IUSEQN = 1
                    WHERE I.IPROD IN ({marks})""",
                chunk,
            )
        return rows

    def next_processes(self, vendor: int, part_numbers: list[str]) -> dict[str, str]:
        """Next process per part (YPU202B @GLIN): routing (FRT) with the vendor as
        work center, then the description of the work center in ROPDS2 (LWK)."""
        work_centers: dict[str, int] = {}
        for chunk in chunks(part_numbers):
            marks = ",".join("?" * len(chunk))
            rows = self.select(
                f"SELECT RPROD, ROPDS2 FROM {self.lib}.FRT WHERE RWRKC = ? AND RPROD IN ({marks})",
                [vendor, *chunk],
            )
            for row in rows:
                part, code = text(row["RPROD"]), (text(row["ROPDS2"]) or "").strip()
                if part not in work_centers and code.isdigit():
                    work_centers[part] = int(code)

        names: dict[int, str] = {}
        for chunk in chunks(sorted(set(work_centers.values()))):
            marks = ",".join("?" * len(chunk))
            for row in self.select(f"SELECT WWRKC, WDESC FROM {self.lib}.LWK WHERE WWRKC IN ({marks})", chunk):
                names[number(row["WWRKC"])] = text(row["WDESC"]) or ""

        return {part: names[code] for part, code in work_centers.items() if names.get(code)}

    # Work calendar

    def work_calendars(self, facility: str, work_center: int, years: list[int]) -> list[dict]:
        marks = ",".join("?" * len(years))
        rows = self.select(
            f"""SELECT SCFAC, SCRKC, SCYEAR, SCTYPE
                FROM {self.lib}.FSC
                WHERE SCID = 'SC' AND SCFAC = ? AND SCRKC = ? AND SCYEAR IN ({marks})""",
            [facility, work_center, *years],
        )
        return [
            {
                "facility": text(row["SCFAC"]),
                "work_center": number(row["SCRKC"]),
                "year": number(row["SCYEAR"]),
                # Not trimmed: a space is a working day, also at the start of the year
                "days": str(row["SCTYPE"] or "").ljust(366)[:366],
            }
            for row in rows
            # A year that is all blanks is not loaded in Infor yet (no weekends, no holidays):
            # sending it would show every day as a working day
            if str(row["SCTYPE"] or "").strip()
        ]
