"""Синк отвалов/отказов в deal_rejections (событийный слой).

Две воронки, РАЗНЫЕ источники (под изменившийся процесс):
- ТМ [50]: по ТЕКУЩЕЙ стадии — C50:APOLOGY (отвал), C50:LOSE (отложено),
  причина UF_CRM_1771324790. Отвал ТМ терминален → снимок стадии корректен.
- Продажи [10]: по СОБЫТИЯМ перехода в C10:LOSE (отвал) из stagehistory,
  причина UF_CRM_1771495464. Отказная сделка Продаж может уезжать в воронку
  Телемаркетинг на возврат → из стадии C10:LOSE она пропадает, поэтому снимок
  стадии недосчитывает. Берём ВСЕ переходы в C10:LOSE с начала года (реальная
  дата отказа = CREATED_TIME перехода), дедуп по сделке (последний переход),
  и обогащаем текущими полями сделки (причина/сумма/владелец).

Идемпотентно (upsert по deal_id). Один прогон с начала года = бэкафилл +
поддержка свежести на cron. НЕ трогает дневной пайплайн отчёта.

    python -m src.sync_rejections
    python -m src.sync_rejections --dry-run
    python -m src.sync_rejections --since 2026-01-01
"""

import sys
from datetime import date
from typing import Any

from . import bx_client
from .collect import _fetch_all
from .db import connect, upsert
from .transform import parse_dt

# Воронка ТМ [50] — по текущей стадии.
REJECTION_STAGES_50 = ["C50:APOLOGY", "C50:LOSE"]
REASON_FIELD_50 = "UF_CRM_1771324790"

# Воронка Продажи [10] — по событиям перехода в отвал.
SALES_CATEGORY = 10
SALES_LOSE_STAGE = "C10:LOSE"
REASON_FIELD_10 = "UF_CRM_1771495464"

_SELECT_BASE = [
    "ID",
    "CATEGORY_ID",
    "STAGE_ID",
    "MODIFY_BY_ID",
    "ASSIGNED_BY_ID",
    "DATE_MODIFY",
    "TITLE",
    "OPPORTUNITY",
]


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(value):
    """Поле причины может прийти списком (enumeration) — берём первый код."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


# ── ТМ [50]: по текущей стадии ────────────────────────────────────────────────


def build_rejection_rows(deals: list[dict[str, Any]], reason_field: str) -> list[dict[str, Any]]:
    """Сырьё crm.deal.list → строки deal_rejections (стадия/категория из сделки). Чистая."""
    rows: list[dict[str, Any]] = []
    for d in deals:
        did = _to_int(d.get("ID"))
        if did is None:
            continue
        rows.append(
            {
                "deal_id": did,
                "category_id": _to_int(d.get("CATEGORY_ID")),
                "stage_id": d.get("STAGE_ID"),
                "reason_id": _to_int(_first(d.get(reason_field))),
                "modified_by": _to_int(d.get("MODIFY_BY_ID")),
                "assigned_by": _to_int(d.get("ASSIGNED_BY_ID")),
                "rejected_at": parse_dt(d.get("DATE_MODIFY")),
                "title": d.get("TITLE"),
                "opportunity": _to_float(d.get("OPPORTUNITY")),
            }
        )
    return rows


def _fetch_stage(bx, stages: list[str], reason_field: str) -> list[dict[str, Any]]:
    return _fetch_all(
        bx,
        "crm.deal.list",
        {"filter": {"@STAGE_ID": stages}, "select": [*_SELECT_BASE, reason_field]},
    )


# ── Продажи [10]: по событиям перехода в C10:LOSE ─────────────────────────────


def fetch_sales_lose_dates(bx, since: str) -> dict[int, str]:
    """Из stagehistory: последний переход сделки в C10:LOSE с даты since.
    Возвращает {deal_id: CREATED_TIME (реальная дата отказа)}."""
    rows = _fetch_all(
        bx,
        "crm.stagehistory.list",
        {
            "entityTypeId": 2,
            "filter": {
                "CATEGORY_ID": SALES_CATEGORY,
                "STAGE_ID": SALES_LOSE_STAGE,
                ">=CREATED_TIME": f"{since}T00:00:00",
            },
            "select": ["ID", "OWNER_ID", "CREATED_TIME", "STAGE_ID", "CATEGORY_ID"],
        },
    )
    latest: dict[int, str] = {}
    for h in rows:
        did = _to_int(h.get("OWNER_ID"))
        created = h.get("CREATED_TIME")
        if did is None or not created:
            continue
        if did not in latest or created > latest[did]:
            latest[did] = created
    return latest


def _fetch_deals_by_ids(bx, ids: list[int], reason_field: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for chunk in _chunks(list(ids), 50):
        out += _fetch_all(
            bx,
            "crm.deal.list",
            {"filter": {"@ID": chunk}, "select": [*_SELECT_BASE, reason_field]},
        )
    return out


def build_sales_rejection_rows(
    deals: list[dict[str, Any]], lose_dates: dict[int, str], reason_field: str
) -> list[dict[str, Any]]:
    """cat10: фиксируем отказ Продажи (даже если сделка уже уехала в ТМ) — стадию
    и категорию ставим как у отказа, дату берём из stagehistory. Чистая функция."""
    rows: list[dict[str, Any]] = []
    for d in deals:
        did = _to_int(d.get("ID"))
        if did is None:
            continue
        rows.append(
            {
                "deal_id": did,
                "category_id": SALES_CATEGORY,
                "stage_id": SALES_LOSE_STAGE,
                "reason_id": _to_int(_first(d.get(reason_field))),
                "modified_by": _to_int(d.get("MODIFY_BY_ID")),
                "assigned_by": _to_int(d.get("ASSIGNED_BY_ID")),
                "rejected_at": parse_dt(lose_dates.get(did)),
                "title": d.get("TITLE"),
                "opportunity": _to_float(d.get("OPPORTUNITY")),
            }
        )
    return rows


def sync(conn=None, bx=None, dry_run: bool = False, since: str | None = None) -> dict[str, int]:
    since = since or f"{date.today().year}-01-01"

    # ТМ [50] — по текущей стадии.
    deals_50 = _fetch_stage(bx, REJECTION_STAGES_50, REASON_FIELD_50)
    rows = build_rejection_rows(deals_50, REASON_FIELD_50)

    # Продажи [10] — по событиям перехода в C10:LOSE с начала года.
    lose_dates = fetch_sales_lose_dates(bx, since)
    deals_10 = _fetch_deals_by_ids(bx, list(lose_dates.keys()), REASON_FIELD_10) if lose_dates else []
    rows += build_sales_rejection_rows(deals_10, lose_dates, REASON_FIELD_10)

    written = 0
    if not dry_run and conn is not None and rows:
        update_cols = [c for c in rows[0] if c != "deal_id"]
        written = upsert(conn, "deal_rejections", rows, ["deal_id"], update_cols)
        conn.commit()
    return {
        "fetched_50": len(deals_50),
        "lose10_events": len(lose_dates),
        "fetched_10": len(deals_10),
        "rows": len(rows),
        "written": written,
    }


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    since = None
    if "--since" in argv:
        idx = argv.index("--since")
        if idx + 1 < len(argv):
            since = argv[idx + 1]
    bx_client.ensure_token_fresh()
    conn = None if dry_run else connect()
    try:
        res = sync(conn=conn, dry_run=dry_run, since=since)
    finally:
        if conn is not None:
            conn.close()
    print(f"[{'DRY-RUN' if dry_run else 'WRITTEN'}] rejections: {res}", flush=True)


if __name__ == "__main__":
    main()
