"""Синк отвалов ТМ-воронки [50] в deal_rejections (событийный слой).

Полный апсерт всех закрытых cat50-сделок (C50:APOLOGY=отвал, C50:LOSE=отложено)
с причиной (UF_CRM_1771324790), тем кто закрыл (MODIFY_BY_ID), владельцем и датой
закрытия. Идемпотентно (upsert по deal_id). Разовый бэкафилл + можно на cron для
свежести. НЕ трогает дневной пайплайн отчёта.

    python -m src.sync_rejections
    python -m src.sync_rejections --dry-run
"""

import sys
from typing import Any

from . import bx_client
from .collect import _fetch_all
from .db import connect, upsert
from .transform import parse_dt

REJECTION_STAGES_50 = ["C50:APOLOGY", "C50:LOSE"]
REASON_FIELD = "UF_CRM_1771324790"


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_rejection_rows(deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                "reason_id": _to_int(d.get(REASON_FIELD)),
                "modified_by": _to_int(d.get("MODIFY_BY_ID")),
                "assigned_by": _to_int(d.get("ASSIGNED_BY_ID")),
                "rejected_at": parse_dt(d.get("DATE_MODIFY")),
                "title": d.get("TITLE"),
            }
        )
    return rows


def sync(conn=None, bx=None, dry_run: bool = False) -> dict[str, int]:
    deals = _fetch_all(
        bx,
        "crm.deal.list",
        {
            "filter": {"@STAGE_ID": REJECTION_STAGES_50},
            "select": [
                "ID",
                "CATEGORY_ID",
                "STAGE_ID",
                REASON_FIELD,
                "MODIFY_BY_ID",
                "ASSIGNED_BY_ID",
                "DATE_MODIFY",
                "TITLE",
            ],
        },
    )
    rows = build_rejection_rows(deals)
    written = 0
    if not dry_run and conn is not None and rows:
        update_cols = [c for c in rows[0] if c != "deal_id"]
        written = upsert(conn, "deal_rejections", rows, ["deal_id"], update_cols)
        conn.commit()
    return {"fetched": len(deals), "rows": len(rows), "written": written}


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
