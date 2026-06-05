#!/usr/bin/env python3
"""Создание задач Bitrix из следующих шагов разбора встреч за день.

Тестовый/ручной запуск. По умолчанию DRY-RUN (только печать полей, без записи).

    python scripts/create_meeting_tasks.py --date 2026-06-04 --meeting 2212        # dry-run одной встречи
    python scripts/create_meeting_tasks.py --date 2026-06-04 --meeting 2212 --live  # реально создать

Идемпотентность Phase-1 простая: перед созданием проверяем, нет ли уже задачи в
сделке с таким же TITLE (UF_CRM_TASK=D_<deal>). Полноценное хранение id — Phase-2.
"""
import argparse
import json
import sys
from datetime import date

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from src import bx_client as bx  # noqa: E402
from src import tasks as T  # noqa: E402
from src.db import connect  # noqa: E402


def _load_meetings(conn, target: date, meeting_id: int | None):
    q = (
        "SELECT m.meeting_id, m.deal_id, m.manager_id, m.analysis_json, d.title "
        "FROM meetings m LEFT JOIN deals_snapshot d "
        "ON d.report_date=m.report_date AND d.deal_id=m.deal_id "
        "WHERE m.report_date=%s AND m.analysis_json IS NOT NULL"
    )
    params: list = [target.isoformat()]
    if meeting_id:
        q += " AND m.meeting_id=%s"
        params.append(meeting_id)
    with conn.cursor() as cur:
        cur.execute(q, tuple(params))
        return cur.fetchall()


def _steps(analysis: dict) -> list[dict]:
    """Phase-1: один next_step → один шаг. (Phase-2: next_steps[] от LLM.)"""
    steps = analysis.get("next_steps")
    if isinstance(steps, list) and steps:
        return [s for s in steps if isinstance(s, dict) and (s.get("what") or "").strip()]
    ns = analysis.get("next_step")
    if isinstance(ns, dict) and (ns.get("what") or "").strip():
        return [ns]
    return []


def _existing_titles(deal_id: int) -> set[str]:
    """Заголовки уже существующих задач сделки — простая защита от дублей."""
    r = bx.call("tasks.task.list", {
        "filter": {"UF_CRM_TASK": f"D_{deal_id}"},
        "select": ["ID", "TITLE"],
    }) or {}
    items = (r.get("result", {}) or {}).get("tasks", []) or []
    return {str(t.get("title") or t.get("TITLE") or "").strip() for t in items}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--meeting", type=int, default=None)
    p.add_argument("--live", action="store_true", help="реально создавать задачи (иначе dry-run)")
    p.add_argument("--creator", type=int, default=T.DEFAULT_CREATOR_ID)
    args = p.parse_args()
    target = date.fromisoformat(args.date)

    conn = connect()
    rows = _load_meetings(conn, target, args.meeting)
    conn.close()
    if not rows:
        print("нет встреч с разбором за дату/ID")
        return

    created, skipped, planned = [], [], 0
    for meeting_id, deal_id, manager_id, analysis_json, deal_title in rows:
        analysis = analysis_json if isinstance(analysis_json, dict) else json.loads(analysis_json or "{}")
        steps = _steps(analysis)
        if not steps or not deal_id or not manager_id:
            continue
        existing = _existing_titles(deal_id) if args.live else set()
        for step in steps:
            fields = T.build_task_fields(
                deal_id=deal_id, deal_title=deal_title, responsible_id=manager_id,
                step=step, analysis=analysis, base_date=target, creator_id=args.creator,
            )
            planned += 1
            print("=" * 70)
            print(f"встреча {meeting_id} · сделка {deal_id} ({deal_title})")
            print(f"  TITLE: {fields['TITLE']}")
            print(f"  RESPONSIBLE_ID: {fields['RESPONSIBLE_ID']}  CREATED_BY: {fields['CREATED_BY']}")
            print(f"  DEADLINE: {fields['DEADLINE']}  TASK_CONTROL: {fields['TASK_CONTROL']}  UF_CRM_TASK: {fields['UF_CRM_TASK']}")
            print("  DESCRIPTION:")
            for ln in fields["DESCRIPTION"].splitlines():
                print(f"    {ln}")
            if args.live:
                if fields["TITLE"] in existing:
                    print("  → ПРОПУСК: задача с таким заголовком в сделке уже есть")
                    skipped.append(fields["TITLE"])
                    continue
                tid = T.create_task(bx, fields)
                print(f"  → СОЗДАНА задача id={tid}  {T.task_url(tid)}")
                created.append(tid)
    print("=" * 70)
    print(f"запланировано: {planned} · создано: {len(created)} · пропущено(дубль): {len(skipped)} · режим: {'LIVE' if args.live else 'DRY-RUN'}")
    if created:
        print("task ids:", created)


if __name__ == "__main__":
    main()
