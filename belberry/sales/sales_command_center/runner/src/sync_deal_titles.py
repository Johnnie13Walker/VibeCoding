"""Синк названий сделок (TITLE) для встреч → deal_titles.

deals_snapshot хранит только ОТКРЫТЫЕ сделки, поэтому у встреч на закрытых сделках
название не резолвилось («Сделка #id»). Скрипт берёт все deal_id из таблицы
meetings и тянет их TITLE из Bitrix (включая закрытые), upsert в deal_titles.
Идемпотентно. Разовый прогон + в дневном пайплайне.

    python -m src.sync_deal_titles
    python -m src.sync_deal_titles --dry-run
"""

import sys
from typing import Any

from . import bx_client
from .collect import _fetch_all
from .db import connect, upsert


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_title_rows(deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for d in deals:
        did = _to_int(d.get("ID"))
        if did is None:
            continue
        rows.append({"deal_id": did, "title": d.get("TITLE")})
    return rows


def _meeting_deal_ids(conn) -> list[int]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT DISTINCT deal_id FROM meetings WHERE deal_id IS NOT NULL")
        return [r[0] for r in cursor.fetchall()]


def sync(conn=None, bx=None, dry_run: bool = False) -> dict[str, int]:
    if conn is None:
        return {"deal_ids": 0, "fetched": 0, "written": 0}
    ids = _meeting_deal_ids(conn)
    if not ids:
        return {"deal_ids": 0, "fetched": 0, "written": 0}
    deals = _fetch_all(
        bx,
        "crm.deal.list",
        {"filter": {"@ID": [str(i) for i in ids]}, "select": ["ID", "TITLE"]},
    )
    rows = build_title_rows(deals)
    written = 0
    if not dry_run and rows:
        written = upsert(conn, "deal_titles", rows, ["deal_id"], ["title"])
        conn.commit()
    return {"deal_ids": len(ids), "fetched": len(deals), "written": written}


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    bx_client.ensure_token_fresh()
    conn = connect()
    try:
        res = sync(conn=conn, dry_run=dry_run)
    finally:
        conn.close()
    print(f"[{'DRY-RUN' if dry_run else 'WRITTEN'}] deal_titles: {res}", flush=True)


if __name__ == "__main__":
    main()
