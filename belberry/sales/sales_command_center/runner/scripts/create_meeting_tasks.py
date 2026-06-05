#!/usr/bin/env python3
"""Создание задач Bitrix из следующих шагов разбора встреч за день.

Тестовый/ручной запуск. По умолчанию DRY-RUN (только печать плана, без записи).
Идемпотентность — через таблицу meeting_tasks (повторный запуск не дублирует).

    python scripts/create_meeting_tasks.py --date 2026-06-04 --meeting 2212        # dry-run
    python scripts/create_meeting_tasks.py --date 2026-06-04 --meeting 2212 --live  # создать
    python scripts/create_meeting_tasks.py --date 2026-06-04 --live                 # все встречи дня
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import bx_client  # noqa: E402
from src import tasks as T  # noqa: E402
from src.db import connect  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--meeting", type=int, default=None)
    p.add_argument("--live", action="store_true", help="реально создавать (иначе dry-run)")
    p.add_argument("--creator", type=int, default=T.DEFAULT_CREATOR_ID)
    args = p.parse_args()
    target = date.fromisoformat(args.date)

    conn = connect()
    try:
        res = T.create_tasks_for_day(
            conn, bx_client, target,
            creator_id=args.creator, meeting_id=args.meeting, dry_run=not args.live,
        )
    finally:
        conn.close()

    for e in res:
        print("=" * 70)
        print(f"встреча {e['meeting_id']} · сделка {e['deal_id']} · {e['status']}")
        print(f"  ЧТО: {e.get('what')}")
        f = e.get("fields")
        if f:
            print(f"  TITLE: {f['TITLE']}")
            print(f"  RESPONSIBLE_ID: {f['RESPONSIBLE_ID']}  CREATED_BY: {f['CREATED_BY']}  DEADLINE: {f['DEADLINE']}  UF_CRM_TASK: {f['UF_CRM_TASK']}")
        if e.get("task_id"):
            print(f"  → задача id={e['task_id']}  {T.task_url(e['task_id'])}")
    created = [e for e in res if e.get("status") == "created"]
    planned = [e for e in res if e.get("status") == "planned"]
    skipped = [e for e in res if e.get("status") == "skip_exists"]
    print("=" * 70)
    print(f"план: {len(planned)} · создано: {len(created)} · пропущено(уже есть): {len(skipped)} · режим: {'LIVE' if args.live else 'DRY-RUN'}")
    if created:
        print("task ids:", [e["task_id"] for e in created])


if __name__ == "__main__":
    main()
