"""Разовый backfill meeting_type для исторических встреч.

До марта 2026 встречи назывались доменом клиента, без слова «Брифинг/Защита», и
движок относил их к «другое» — на дашборде «Первых встреч/Презентаций» за янв-фев
были дыры. Скрипт собирает все состоявшиеся встречи (SP 1048, SUCCESS), размечает
тип через assign_meeting_types (название → позиция в сделке) и обновляет
meetings.meeting_type. Идемпотентно. Сам анализ/данные не трогает.

Запуск:
    python -m src.backfill_meeting_type           # dry-run
    python -m src.backfill_meeting_type --apply    # запись
"""

from __future__ import annotations

import argparse
from collections import Counter

from . import bx_client
from .collect import MEETING_HELD_STAGE, _fetch_all
from .db import connect
from .transform import assign_meeting_types


def run(dry_run: bool = True, bx=None, conn=None) -> dict[str, int]:
    bx_client.ensure_token_fresh()
    items = _fetch_all(
        bx or bx_client,
        "crm.item.list",
        {
            "entityTypeId": 1048,
            "filter": {"stageId": MEETING_HELD_STAGE},
            "select": ["id", "title", "parentId2", "ufCrm16_1751009238"],
        },
        idfield="id",
    )
    print(f"held meetings: {len(items)}", flush=True)
    types = assign_meeting_types(items)
    print(f"classified: {dict(Counter(types.values()))}", flush=True)

    own_conn = conn is None
    conn = conn or connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT meeting_id, meeting_type FROM meetings")
            current = {int(mid): mt for mid, mt in cur.fetchall()}

        changed = 0
        for mid, new_type in types.items():
            if mid not in current:
                continue  # встреча не в нашей БД (вне собранных дней)
            if current[mid] == new_type:
                continue
            if dry_run:
                changed += 1
                continue
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE meetings SET meeting_type = %s WHERE meeting_id = %s",
                    (new_type, mid),
                )
                changed += cur.rowcount
        if not dry_run:
            conn.commit()
    finally:
        if own_conn:
            conn.close()

    stats = {"held": len(items), "in_db": len(current), "changed": changed, "dry_run": int(dry_run)}
    print(f"RESULT {stats}", flush=True)
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill meeting_type (briefing/defense by name→position)")
    parser.add_argument("--apply", action="store_true", help="записать в БД (по умолчанию dry-run)")
    args = parser.parse_args()
    run(dry_run=not args.apply)
