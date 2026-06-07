"""Хирургический ПЕРЕАНАЛИЗ встреч за период: подтянуть транскрипт + LLM-разбор и
записать ТОЛЬКО в таблицу meetings (analysis_json + поля транскрипта). Без снимка
воронки, без manager_activity, без отчёта/Telegram. Используется для восстановления
разбора за дни, где он был затёрт, и для наполнения страницы «Анализ встреч».

Запуск (на проде, DATABASE_URL + LLM-ключ в окружении):
    python -m src.reanalyze 2026-05-29 2026-06-04
    python -m src.reanalyze --dry-run 2026-06-02     # без записи в БД (LLM всё равно вызывается)
"""

import json
import sys
from datetime import date, datetime, timedelta

from . import analyze_llm, bx_client
from .collect import MEETING_HELD_STAGE, SEL_1048, _collect_wazzup, _fetch_all, _range
from .db import connect, upsert
from .enrich import enrich_meetings
from .timeutil import MSK
from .transform import build_db_rows, build_post_meeting_comms

_EMPTY_RAW_KEYS = {
    "deals_open": [], "deals_created": [], "stagehistory": [], "won_deals": [],
    "entered_deals": [], "meet_created_day": [], "meet_today": [], "briefs": [],
    "kp": [], "activities": [], "calls": [], "messenger_dialogs": {},
}


def collect_meetings_raw(target: date, bx=None) -> dict:
    d0, d1 = _range(target)
    meet_day = _fetch_all(
        bx,
        "crm.item.list",
        {"entityTypeId": 1048, "filter": {">=ufCrm16_1751009238": d0, "<=ufCrm16_1751009238": d1, "stageId": MEETING_HELD_STAGE}, "select": SEL_1048},
        idfield="id",
    )
    deal_ids = {item.get("parentId2") for item in meet_day if item.get("parentId2")}
    wazzup = _collect_wazzup(deal_ids, bx) if deal_ids else {}
    # Исходящие письма по сделкам встреч — для детекта «итоги отправлены».
    activities: list = []
    if deal_ids:
        activities = _fetch_all(
            bx,
            "crm.activity.list",
            {
                "filter": {"OWNER_TYPE_ID": 2, "@OWNER_ID": [str(i) for i in deal_ids], "PROVIDER_ID": "CRM_EMAIL"},
                "select": ["ID", "OWNER_ID", "OWNER_TYPE_ID", "PROVIDER_ID", "SUBJECT", "DIRECTION", "CREATED"],
            },
        )
    raw = {"report_date": target.isoformat(), "meet_day": meet_day, "wazzup": wazzup, **_EMPTY_RAW_KEYS}
    raw["activities"] = activities
    return raw


def reanalyze_day(target: date, conn=None, bx=None, dry_run: bool = False) -> dict[str, int]:
    raw = collect_meetings_raw(target, bx)
    rows = build_db_rows(raw, target, datetime.now(MSK))
    meetings_rows = rows.get("meetings", [])
    if not meetings_rows:
        print(f"{target}: встреч нет", flush=True)
        return {"meetings": 0, "transcripts": 0, "analyzed": 0}

    enriched = enrich_meetings(raw, bx=bx, refresh=True)
    meetings_meta = {int(item["id"]): item for item in raw["meet_day"]}
    for row in meetings_rows:
        mid = int(row["meeting_id"])
        tr = enriched.get(mid, {})
        row["transcript_url"] = tr.get("url")
        row["transcript_text"] = tr.get("text")
        row["transcript_ok"] = tr.get("transcript_status") == "ok"

    post_comms = build_post_meeting_comms(raw["meet_day"], raw.get("wazzup"), raw.get("activities"))
    client = analyze_llm.get_client()
    analyses = analyze_llm.analyze_day(enriched, meetings_meta, client=client, wazzup=post_comms)
    analyzed = 0
    for row in meetings_rows:
        mid = int(row["meeting_id"])
        a = analyses.get(mid)
        if a:
            row["analysis_json"] = json.dumps(a, ensure_ascii=False)
            available = a.get("analysis_available", True)
            row["analysis_status"] = "done" if available else "skipped_no_transcript"
            if available:
                analyzed += 1

    with_tr = sum(1 for r in meetings_rows if r.get("transcript_ok"))
    print(f"{target}: встреч={len(meetings_rows)} с_транскриптом={with_tr} разобрано={analyzed}", flush=True)

    if not dry_run and conn is not None:
        update_cols = [c for c in meetings_rows[0] if c not in ("report_date", "meeting_id")]
        upsert(conn, "meetings", meetings_rows, ["report_date", "meeting_id"], update_cols)
        conn.commit()
    return {"meetings": len(meetings_rows), "transcripts": with_tr, "analyzed": analyzed}


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv
    pos = [a for a in argv if not a.startswith("--")]
    start = date.fromisoformat(pos[0])
    end = date.fromisoformat(pos[1]) if len(pos) > 1 else start

    conn = None
    if not dry_run:
        bx_client.ensure_token_fresh()
        conn = connect()
    totals = {"meetings": 0, "transcripts": 0, "analyzed": 0}
    cur = start
    try:
        while cur <= end:
            if cur.weekday() < 5:
                r = reanalyze_day(cur, conn=conn, bx=None, dry_run=dry_run)
                for k in totals:
                    totals[k] += r[k]
            cur += timedelta(days=1)
    finally:
        if conn is not None:
            conn.close()
    print(f"\n[{'DRY-RUN' if dry_run else 'DONE'}] {start}..{end}: {totals}", flush=True)


if __name__ == "__main__":
    main()
