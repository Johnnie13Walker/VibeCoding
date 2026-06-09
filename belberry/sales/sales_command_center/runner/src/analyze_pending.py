"""Инкрементальный LLM-разбор: ТОЛЬКО непроанализированные встречи (analysis_status
!= 'done') за последние N дней. Уже разобранные не трогает (не тратит LLM заново).
Автоматически ловит поздние транскрипты. Без отчёта/Telegram. Для часового cron.

    python -m src.analyze_pending            # последние 3 дня
    python -m src.analyze_pending --days 7
"""

import json
import os
import sys
from datetime import date, datetime, timedelta

from . import analyze_llm, bx_client
from . import tasks as bx_tasks
from .db import connect, upsert
from .enrich import enrich_meetings
from .reanalyze import collect_meetings_raw
from .timeutil import MSK
from .transform import build_post_meeting_comms


def _pending(conn, since: date) -> dict[str, set[int]]:
    """{report_date_iso: {meeting_id,...}} непроанализированных SUCCESS-встреч."""
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT report_date, meeting_id FROM meetings "
            "WHERE status = 'DT1048_24:SUCCESS' AND report_date >= %s "
            "AND coalesce(analysis_status, '') <> 'done'",
            (since.isoformat(),),
        )
        out: dict[str, set[int]] = {}
        for rd, mid in cursor.fetchall():
            key = rd.isoformat() if hasattr(rd, "isoformat") else str(rd)
            out.setdefault(key, set()).add(int(mid))
        return out


def analyze_day_pending(target: date, pending_ids: set[int], conn, bx=None) -> int:
    raw = collect_meetings_raw(target, bx)
    raw["meet_day"] = [m for m in raw["meet_day"] if int(m.get("id") or 0) in pending_ids]
    if not raw["meet_day"]:
        print(f"{target}: pending={len(pending_ids)} в Bitrix нет (нет SUCCESS-встречи/транскрипта) разобрано=0", flush=True)
        return 0

    enriched = enrich_meetings(raw, bx=bx, refresh=True)
    meetings_meta = {int(item["id"]): item for item in raw["meet_day"]}
    post_comms = build_post_meeting_comms(raw["meet_day"], raw.get("wazzup"), raw.get("activities"))
    client = analyze_llm.get_client()
    analyses = analyze_llm.analyze_day(enriched, meetings_meta, client=client, wazzup=post_comms)

    rows = []
    analyzed = 0
    for mid in pending_ids:
        a = analyses.get(mid)
        if not a:
            continue
        tr = enriched.get(mid, {})
        available = a.get("analysis_available", True)
        rows.append(
            {
                "report_date": target.isoformat(),
                "meeting_id": mid,
                "analysis_json": json.dumps(a, ensure_ascii=False),
                "analysis_status": "done" if available else "skipped_no_transcript",
                "transcript_url": tr.get("url"),
                "transcript_text": tr.get("text"),
                "transcript_ok": tr.get("transcript_status") == "ok",
            }
        )
        if available:
            analyzed += 1

    if rows and conn is not None:
        cols = [c for c in rows[0] if c not in ("report_date", "meeting_id")]
        upsert(conn, "meetings", rows, ["report_date", "meeting_id"], cols)
        conn.commit()
    print(f"{target}: pending={len(pending_ids)} разобрано={analyzed}", flush=True)
    return analyzed


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    days = 3
    if "--days" in argv:
        days = int(argv[argv.index("--days") + 1])
    bx_client.ensure_token_fresh()
    conn = connect()
    since = datetime.now(MSK).date() - timedelta(days=days)
    total = 0
    create_tasks = os.environ.get("SCC_CREATE_TASKS") == "1"
    today = datetime.now(MSK).date()
    try:
        pending = _pending(conn, since)
        for rd, ids in sorted(pending.items()):
            total += analyze_day_pending(date.fromisoformat(rd), ids, conn=conn)
        # Задачи ставим СРАЗУ после разбора встречи (а не утренним batch'ем
        # следующего дня): на каждый день окна создаём задачи по уже разобранным
        # встречам. Идемпотентно по meeting_tasks — ловит встречи, разобранные
        # этим прогоном И ранее без задач; дублей с дневным прогоном нет.
        if create_tasks:
            # Умный проход постановки: планировщик (≤2 рычажных задачи) + дедуп.
            # client включает планировщик; без него — старая логика next_steps.
            task_client = analyze_llm.get_client()
            day = since
            while day <= today:
                try:
                    res = bx_tasks.create_tasks_for_day(conn, bx_client, day, client=task_client)
                    created = sum(1 for r in res if r.get("status") == "created")
                    if created:
                        print(f"[tasks] {day.isoformat()}: создано {created}", flush=True)
                except Exception as exc:  # noqa: BLE001
                    print(f"[tasks] {day.isoformat()} создание не удалось: {str(exc)[:200]}", flush=True)
                day = date.fromordinal(day.toordinal() + 1)
    finally:
        conn.close()
    print(f"[ANALYZE_PENDING] since {since}: разобрано={total}", flush=True)


if __name__ == "__main__":
    main()
