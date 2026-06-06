"""Точечный бэкафилл meetings.created_by (событийный слой ТМ).

Для диапазона рабочих дней тянет состоявшиеся встречи (SP1048, stageId=SUCCESS) и
проставляет ТОЛЬКО колонку created_by в существующих строках таблицы meetings.
НЕ пересобирает manager_activity / другие метрики / отчёты — нулевой blast radius
на /dashboard. Без LLM/Telegram. Идемпотентно (обновляет только NULL).

Запуск (на проде, DATABASE_URL в окружении):
    python -m src.backfill_meeting_creator 2025-11-01 2026-06-04
    python -m src.backfill_meeting_creator --dry-run 2026-05-01 2026-05-31
"""

import sys
from datetime import date, timedelta

from . import bx_client
from .collect import MEETING_HELD_STAGE, SEL_1048, _fetch_all, _range
from .db import connect


def _is_workday(d: date) -> bool:
    return d.weekday() < 5


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pairs_for_day(bx, day: date) -> list[tuple[int, int]]:
    """[(meeting_id, created_by), ...] для состоявшихся встреч этого дня."""
    d0, d1 = _range(day)
    held = _fetch_all(
        bx,
        "crm.item.list",
        {
            "entityTypeId": 1048,
            "filter": {">=ufCrm16_1751009238": d0, "<=ufCrm16_1751009238": d1, "stageId": MEETING_HELD_STAGE},
            "select": SEL_1048,
        },
        idfield="id",
    )
    out: list[tuple[int, int]] = []
    for it in held:
        mid = _to_int(it.get("id"))
        cb = _to_int(it.get("createdBy"))
        if mid is not None and cb is not None:
            out.append((mid, cb))
    return out


def backfill_range(start: date, end: date, conn=None, bx=None, dry_run: bool = False) -> dict[str, int]:
    totals = {"days": 0, "meetings_seen": 0, "rows_updated": 0}
    cur = start
    while cur <= end:
        if _is_workday(cur):
            pairs = _pairs_for_day(bx, cur)
            updated = 0
            if not dry_run and conn is not None and pairs:
                with conn.cursor() as cursor:
                    # Только NULL — не перетираем уже проставленное; по meeting_id.
                    cursor.executemany(
                        "UPDATE meetings SET created_by = %s WHERE meeting_id = %s AND created_by IS NULL",
                        [(cb, mid) for mid, cb in pairs],
                    )
                    updated = cursor.rowcount
                conn.commit()
            print(f"{cur} held={len(pairs)} updated={updated}", flush=True)
            totals["days"] += 1
            totals["meetings_seen"] += len(pairs)
            totals["rows_updated"] += updated
        cur += timedelta(days=1)
    return totals


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    positional = [a for a in argv if not a.startswith("--")]
    start = date.fromisoformat(positional[0])
    end = date.fromisoformat(positional[1]) if len(positional) > 1 else start

    conn = None
    bx_client.ensure_token_fresh()
    if not dry_run:
        conn = connect()
    try:
        totals = backfill_range(start, end, conn=conn, dry_run=dry_run)
    finally:
        if conn is not None:
            conn.close()
    mode = "DRY-RUN" if dry_run else "WRITTEN"
    print(f"\n[{mode}] {start}..{end}: {totals}", flush=True)


if __name__ == "__main__":
    main()
