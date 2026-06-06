"""Синк фактических приходов (оплат) из «Приходы 2026», вкладка «Продажи» → payments.

Источник правды по деньгам (не Bitrix-won). Полная перезапись таблицы (DELETE+INSERT)
— зеркало вкладки. «Оплата» на дашборде = КД без НДС, Отдел=Продажи, по месяцу/году.

Env:
    GOOGLE_SERVICE_ACCOUNT_JSON — путь к ключу finance-SA (default /etc/scc/finance-sa.json)
    SCC_PAYMENTS_SHEET_ID       — id таблицы (default «Приходы 2026»)
    SCC_PAYMENTS_TAB            — вкладка (default «Продажи»)

    python -m src.sync_payments
    python -m src.sync_payments --dry-run
"""

import os
import sys

from .db import connect

DEFAULT_SHEET_ID = "17SBisFgKrf3hRP_zjVPC2e4wMzlq8j8HDC2bvkyS74Y"
DEFAULT_TAB = "Продажи"
DEFAULT_KEY = "/etc/scc/finance-sa.json"

_MONTHS = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}


def _num(s):
    t = str(s or "").replace("\xa0", "").replace(" ", "").replace(",", ".").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _month_num(s):
    return _MONTHS.get(str(s or "").strip().lower())


def _to_int(s):
    try:
        return int(str(s).strip())
    except (TypeError, ValueError):
        return None


def fetch_rows() -> list[list[str]]:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", DEFAULT_KEY)
    sid = os.environ.get("SCC_PAYMENTS_SHEET_ID", DEFAULT_SHEET_ID)
    tab = os.environ.get("SCC_PAYMENTS_TAB", DEFAULT_TAB)
    creds = Credentials.from_service_account_file(
        key, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    sh = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()
    return sh.values().get(spreadsheetId=sid, range=f"'{tab}'!A2:O").execute().get("values", [])


def build_payment_rows(raw_rows: list[list[str]]) -> list[dict]:
    rows = []
    for r in raw_rows:
        r = (list(r) + [""] * 15)[:15]
        project = (r[0] or "").strip()
        if not project:
            continue
        rows.append(
            {
                "project": project,
                "source": (r[1] or "").strip() or None,
                "dept": (r[2] or "").strip() or None,
                "manager": (r[3] or "").strip() or None,
                "service": (r[4] or "").strip() or None,
                "kd_with_vat": _num(r[5]),
                "kd_no_vat": _num(r[6]),
                "dd_with_vat": _num(r[7]),
                "dd_no_vat": _num(r[8]),
                "pay_date": (r[9] or "").strip() or None,
                "pay_form": (r[10] or "").strip() or None,
                "counterparty": (r[11] or "").strip() or None,
                "brand": (r[12] or "").strip() or None,
                "pay_month": _month_num(r[13]),
                "pay_year": _to_int(r[14]),
            }
        )
    return rows


_COLS = [
    "project", "source", "dept", "manager", "service",
    "kd_with_vat", "kd_no_vat", "dd_with_vat", "dd_no_vat",
    "pay_date", "pay_form", "counterparty", "brand", "pay_month", "pay_year",
]


def sync(conn=None, dry_run: bool = False) -> dict[str, int]:
    rows = build_payment_rows(fetch_rows())
    if not dry_run and conn is not None:
        placeholders = ", ".join(["%s"] * len(_COLS))
        sql = f"INSERT INTO payments ({', '.join(_COLS)}) VALUES ({placeholders})"
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM payments")
            cursor.executemany(sql, [tuple(r[c] for c in _COLS) for r in rows])
        conn.commit()
    return {"rows": len(rows)}


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    conn = None if dry_run else connect()
    try:
        res = sync(conn=conn, dry_run=dry_run)
    finally:
        if conn is not None:
            conn.close()
    print(f"[{'DRY-RUN' if dry_run else 'WRITTEN'}] payments: {res}", flush=True)


if __name__ == "__main__":
    main()
