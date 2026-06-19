"""Синк выигрышей Продажи [10] в deal_wins (событийный слой).

По СОБЫТИЯМ перехода в C10:WON из stagehistory (выигранная сделка уходит из
открытого снимка → текущую стадию не поймать; payments к deal_id не привязан).
Берём ВСЕ переходы в C10:WON с начала года (дата выигрыша = CREATED_TIME, дедуп
по сделке — последний переход), обогащаем суммой/владельцем из crm.deal.list.

Зеркало Продажи-ветки sync_rejections. Идемпотентно (upsert по deal_id). Один
прогон с начала года = бэкафилл; на cron — поддержка свежести. Дневной пайплайн
отчёта не трогает. Нужен для окупаемости ТМ (встречи → выигрыши/сумма).

    python -m src.sync_wins
    python -m src.sync_wins --dry-run
    python -m src.sync_wins --since 2026-01-01
"""

import sys
from datetime import date
from typing import Any

from . import bx_client
from .collect import _fetch_all
from .db import connect, upsert
from .sync_rejections import _chunks, _to_float, _to_int, resolve_owners
from .transform import parse_dt

SALES_CATEGORY = 10
SALES_WON_STAGE = "C10:WON"

_SELECT = ["ID", "ASSIGNED_BY_ID", "TITLE", "OPPORTUNITY"]


def fetch_won_dates(bx, since: str) -> dict[int, str]:
    """Из stagehistory: последний переход сделки в C10:WON с даты since.
    Возвращает {deal_id: CREATED_TIME (дата выигрыша)}."""
    rows = _fetch_all(
        bx,
        "crm.stagehistory.list",
        {
            "entityTypeId": 2,
            "filter": {
                "CATEGORY_ID": SALES_CATEGORY,
                "STAGE_ID": SALES_WON_STAGE,
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


def _fetch_deals_by_ids(bx, ids: list[int]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for chunk in _chunks(list(ids), 50):
        out += _fetch_all(bx, "crm.deal.list", {"filter": {"@ID": chunk}, "select": _SELECT})
    return out


def build_win_rows(
    deals: list[dict[str, Any]],
    won_dates: dict[int, str],
    owners: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """crm.deal.list + даты выигрыша → строки deal_wins (владельца денормализуем,
    вкл. уволенных). Чистая функция."""
    owners = owners or {}
    rows: list[dict[str, Any]] = []
    for d in deals:
        did = _to_int(d.get("ID"))
        if did is None:
            continue
        owner_id = _to_int(d.get("ASSIGNED_BY_ID"))
        o = owners.get(owner_id) if owner_id is not None else None
        won_dt = parse_dt(won_dates.get(did))
        rows.append(
            {
                "deal_id": did,
                "won_date": won_dt.date() if won_dt else None,
                "opportunity": _to_float(d.get("OPPORTUNITY")),
                "owner_id": owner_id,
                "owner_name": o.get("name") if o else None,
                "owner_dept": o.get("dept") if o else None,
                "owner_active": o.get("active") if o else None,
            }
        )
    return rows


def sync(conn=None, bx=None, dry_run: bool = False, since: str | None = None) -> dict[str, int]:
    since = since or f"{date.today().year}-01-01"
    won_dates = fetch_won_dates(bx, since)
    deals = _fetch_deals_by_ids(bx, list(won_dates.keys())) if won_dates else []
    owner_ids = [_to_int(d.get("ASSIGNED_BY_ID")) for d in deals]
    owners = resolve_owners([i for i in owner_ids if i is not None], bx)
    rows = build_win_rows(deals, won_dates, owners)

    written = 0
    if not dry_run and conn is not None and rows:
        update_cols = [c for c in rows[0] if c != "deal_id"]
        written = upsert(conn, "deal_wins", rows, ["deal_id"], update_cols)
        conn.commit()
    return {"won_events": len(won_dates), "fetched": len(deals), "rows": len(rows), "written": written}


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    since = None
    if "--since" in argv:
        since = argv[argv.index("--since") + 1]

    conn = None
    if not dry_run:
        bx_client.ensure_token_fresh()
        conn = connect()
    try:
        totals = sync(conn=conn, bx=bx_client, dry_run=dry_run, since=since)
    finally:
        if conn is not None:
            conn.close()
    print(f"[{'DRY-RUN' if dry_run else 'WRITTEN'}] {totals}", flush=True)


if __name__ == "__main__":
    main()
