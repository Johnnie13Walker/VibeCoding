"""Синк отвалов/отказов в deal_rejections (событийный слой).

Полный апсерт всех закрытых-проигранных сделок двух воронок:
- ТМ [50]: C50:APOLOGY (отвал), C50:LOSE (отложено), причина UF_CRM_1771324790;
- Продажи [10]: C10:LOSE (отказ), причина UF_CRM_1771495464.
С причиной, суммой (OPPORTUNITY), тем кто закрыл (MODIFY_BY_ID), владельцем
(ASSIGNED_BY_ID) и датой закрытия (DATE_MODIFY). Идемпотентно (upsert по deal_id).
Так как фильтр только по стадии (без даты) — один прогон наполняет всю историю
(бэкафилл) и поддерживает свежесть на cron. НЕ трогает дневной пайплайн отчёта.

    python -m src.sync_rejections
    python -m src.sync_rejections --dry-run
"""

import sys
from typing import Any

from . import bx_client
from .collect import _fetch_all
from .db import connect, upsert
from .transform import parse_dt

# Воронка ТМ [50] и воронка Продажи [10] используют РАЗНЫЕ поля причины отказа.
REJECTION_STAGES_50 = ["C50:APOLOGY", "C50:LOSE"]
REASON_FIELD_50 = "UF_CRM_1771324790"
REJECTION_STAGES_10 = ["C10:LOSE"]
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


def build_rejection_rows(deals: list[dict[str, Any]], reason_field: str) -> list[dict[str, Any]]:
    """Сырьё crm.deal.list → строки deal_rejections. Чистая функция."""
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
        {
            "filter": {"@STAGE_ID": stages},
            "select": [*_SELECT_BASE, reason_field],
        },
    )


def sync(conn=None, bx=None, dry_run: bool = False) -> dict[str, int]:
    deals_50 = _fetch_stage(bx, REJECTION_STAGES_50, REASON_FIELD_50)
    deals_10 = _fetch_stage(bx, REJECTION_STAGES_10, REASON_FIELD_10)
    rows = build_rejection_rows(deals_50, REASON_FIELD_50) + build_rejection_rows(
        deals_10, REASON_FIELD_10
    )
    written = 0
    if not dry_run and conn is not None and rows:
        update_cols = [c for c in rows[0] if c != "deal_id"]
        written = upsert(conn, "deal_rejections", rows, ["deal_id"], update_cols)
        conn.commit()
    return {
        "fetched_50": len(deals_50),
        "fetched_10": len(deals_10),
        "rows": len(rows),
        "written": written,
    }


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    bx_client.ensure_token_fresh()
    conn = None if dry_run else connect()
    try:
        res = sync(conn=conn, dry_run=dry_run)
    finally:
        if conn is not None:
            conn.close()
    print(f"[{'DRY-RUN' if dry_run else 'WRITTEN'}] rejections: {res}", flush=True)


if __name__ == "__main__":
    main()
