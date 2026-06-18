"""Синк интейк-когорты воронки Продажи [10] в таблицу funnel_cohort.

Когорта = сделки cat10, созданные с начала года. Для каждой считаем самую дальнюю
достигнутую стадию (из stagehistory + текущая стадия), чтобы дашборд честно
показывал «из созданных за месяц сколько ДОШЛО до этапа X» — по ОДНИМ И ТЕМ ЖЕ
сделкам, а не по разрозненным событиям (старый гибрид: база=созданные, КП/защита=
distinct-события могли быть по другим сделкам).

Почему furthest-stage, а не текущая стадия: сделка, дошедшая до «Защиты» и затем
отвалившаяся, сейчас стоит на C10:LOSE — по текущей стадии она бы недосчиталась в
середине воронки. История стадий ловит максимум достигнутого.

Идемпотентно (upsert по deal_id). Один прогон с начала года = бэкафилл + поддержка
свежести на cron. НЕ трогает дневной пайплайн отчёта.

    python -m src.sync_funnel_cohort
    python -m src.sync_funnel_cohort --dry-run
    python -m src.sync_funnel_cohort --since 2026-01-01
"""

import sys
from datetime import date
from typing import Any

from . import bx_client
from .collect import _fetch_all
from .db import connect, upsert
from .funnel_stages import LOST_STAGES_10, WON_STAGE_10, furthest_order, stage_order
from .transform import parse_dt

SALES_CATEGORY = 10


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


def fetch_cohort_deals(bx, since: str) -> list[dict[str, Any]]:
    """cat10-сделки, созданные с since (включая закрытые/выигранные/отвал)."""
    return _fetch_all(
        bx,
        "crm.deal.list",
        {
            "filter": {"CATEGORY_ID": SALES_CATEGORY, ">=DATE_CREATE": f"{since}T00:00:00"},
            "select": ["ID", "ASSIGNED_BY_ID", "DATE_CREATE", "STAGE_ID", "OPPORTUNITY", "CATEGORY_ID"],
        },
    )


def fetch_stage_history(bx, since: str) -> dict[int, set[str]]:
    """Из stagehistory: множество стадий, которые сделка КОГДА-ЛИБО проходила (cat10)."""
    rows = _fetch_all(
        bx,
        "crm.stagehistory.list",
        {
            "entityTypeId": 2,
            "filter": {"CATEGORY_ID": SALES_CATEGORY, ">=CREATED_TIME": f"{since}T00:00:00"},
            "select": ["OWNER_ID", "STAGE_ID", "CREATED_TIME", "CATEGORY_ID"],
        },
    )
    hist: dict[int, set[str]] = {}
    for h in rows:
        did = _to_int(h.get("OWNER_ID"))
        st = h.get("STAGE_ID")
        if did is None or not st:
            continue
        hist.setdefault(did, set()).add(st)
    return hist


def build_cohort_rows(
    deals: list[dict[str, Any]], history: dict[int, set[str]]
) -> list[dict[str, Any]]:
    """Сырьё crm.deal.list + история стадий → строки funnel_cohort. Чистая функция."""
    rows: list[dict[str, Any]] = []
    for d in deals:
        did = _to_int(d.get("ID"))
        if did is None:
            continue
        current = d.get("STAGE_ID")
        stages: set[str] = set(history.get(did, set()))
        if current:
            stages.add(current)
        order = furthest_order(stages)
        # Текстовая «самая дальняя стадия» — ключ с максимальным порядком.
        fstage = next((s for s in stages if stage_order(s) == order), None) if order else None
        created = parse_dt(d.get("DATE_CREATE"))
        rows.append(
            {
                "deal_id": did,
                "category_id": SALES_CATEGORY,
                "cohort_date": created.date() if created else None,
                "manager_id": _to_int(d.get("ASSIGNED_BY_ID")),
                "current_stage": current,
                "furthest_stage": fstage,
                "furthest_order": order,
                "is_won": WON_STAGE_10 in stages,
                "is_lost": current in LOST_STAGES_10,
                "opportunity": _to_float(d.get("OPPORTUNITY")),
            }
        )
    return rows


def sync(conn=None, bx=None, dry_run: bool = False, since: str | None = None) -> dict[str, int]:
    since = since or f"{date.today().year}-01-01"
    deals = fetch_cohort_deals(bx, since)
    history = fetch_stage_history(bx, since)
    rows = build_cohort_rows(deals, history)

    written = 0
    if not dry_run and conn is not None and rows:
        update_cols = [c for c in rows[0] if c != "deal_id"]
        written = upsert(conn, "funnel_cohort", rows, ["deal_id"], update_cols)
        conn.commit()
    return {
        "deals": len(deals),
        "history_deals": len(history),
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
    print(f"[{'DRY-RUN' if dry_run else 'WRITTEN'}] funnel_cohort: {res}", flush=True)


if __name__ == "__main__":
    main()
