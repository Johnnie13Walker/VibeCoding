"""Бэкафилл: дозачёт «итоги встречи отправлены клиенту» по пост-встречной переписке.

Разбор встречи идемпотентен и происходит в день встречи, а итоги/резюме менеджер
часто шлёт клиенту через день-два — в исходном разборе они не засчитывались (+ был
баг сбора Wazzup: order ASC + одна страница → свежие сообщения терялись, см.
collect._collect_wazzup). Этот проход перепроверяет ПО ИСПРАВЛЕННОЙ пост-переписке
(Wazzup ПОСЛЕ времени встречи) признак summary_sent и, если итоги найдены:
  • ставит analysis_json.summary_sent = true,
  • ставит флаг analysis_json.summary_sent_backfilled = true (для прозрачности),
  • повышает балл на +1 (не выше 10).
Метод определения — ИИ по пост-переписке (как в основном разборе), не эвристика.

    python -m src.backfill_meeting_summaries --days 60          # dry-run (без записи)
    python -m src.backfill_meeting_summaries --days 60 --live   # запись в БД
"""

import argparse
import json
import sys
from datetime import datetime, timedelta

from . import analyze_llm, bx_client
from .collect import _collect_wazzup
from .db import connect
from .timeutil import MSK
from .transform import parse_dt

JUDGE_SYSTEM = (
    "Ты проверяешь по переписке/письмам ПОСЛЕ встречи, отправил ли менеджер клиенту "
    "ИТОГИ/РЕЗЮМЕ встречи или следующие шаги. В тексте исходящие сообщения менеджера и "
    "входящие клиента. Верни строго JSON {\"sent\": true|false, \"evidence\": \"...\"}. "
    "sent=true ТОЛЬКО если менеджер отправил резюме/итоги/договорённости/следующие шаги "
    "(не просто «спасибо»/«перезвоню»/пустая вежливость). evidence — короткая цитата "
    "исходящего сообщения с итогами (или пусто). Если итогов нет — sent=false."
)


def _post_meeting_text(scheduled_at, wazzup_for_deal) -> str:
    """Wazzup-сообщения по сделке, отправленные ПОСЛЕ времени встречи (как в
    transform.build_post_meeting_comms, но из БД-времени встречи)."""
    mt = parse_dt(scheduled_at)
    parts: list[str] = []
    for c in wazzup_for_deal or []:
        created = parse_dt(c.get("CREATED") or c.get("created"))
        if mt and created and created <= mt:
            continue
        body = str(c.get("COMMENT") or "").strip()
        if body:
            parts.append(f"[Wazzup {c.get('CREATED')}] {body}")
    return "\n".join(parts)[:4000]


def _judge_summary_sent(text: str, client) -> dict:
    """ИИ: отправлены ли итоги. {sent: bool, evidence: str}."""
    response = analyze_llm._call_with_retry(
        client,
        model=analyze_llm.MODEL,
        max_tokens=300,
        temperature=0,
        system=analyze_llm._system(JUDGE_SYSTEM),
        messages=[{"role": "user", "content": f"Переписка после встречи:\n{text}"}],
    )
    parsed = analyze_llm._parse_llm_json(analyze_llm._response_text(response))
    if not isinstance(parsed, dict):
        return {"sent": False, "evidence": ""}
    return {"sent": bool(parsed.get("sent")), "evidence": str(parsed.get("evidence") or "")[:200]}


def _candidates(conn, since_iso: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT report_date, meeting_id, deal_id, scheduled_at, analysis_json "
            "FROM meetings WHERE report_date >= %s AND analysis_json IS NOT NULL "
            "AND coalesce(analysis_json->>'summary_sent','') <> 'true' "
            "ORDER BY report_date",
            (since_iso,),
        )
        return cur.fetchall()


def run(days: int, live: bool) -> dict:
    bx_client.ensure_token_fresh()
    conn = connect()
    since = (datetime.now(MSK).date() - timedelta(days=days)).isoformat()
    client = analyze_llm.get_client()
    stats = {"candidates": 0, "no_post_comms": 0, "judged": 0, "flipped": 0, "errors": 0}
    flips = []
    try:
        rows = _candidates(conn, since)
        stats["candidates"] = len(rows)
        for report_date, meeting_id, deal_id, scheduled_at, analysis_json in rows:
            if not deal_id:
                continue
            analysis = analysis_json if isinstance(analysis_json, dict) else json.loads(analysis_json or "{}")
            try:
                wz = _collect_wazzup({deal_id})
                text = _post_meeting_text(scheduled_at, wz.get(str(deal_id)) or [])
                if not text.strip():
                    stats["no_post_comms"] += 1
                    continue
                stats["judged"] += 1
                verdict = _judge_summary_sent(text, client)
            except Exception as exc:  # noqa: BLE001
                stats["errors"] += 1
                print(f"  #{meeting_id} (deal {deal_id}) ошибка: {str(exc)[:120]}", flush=True)
                continue
            if not verdict["sent"]:
                continue
            # Итоги найдены → отмечаем + балл +1 (потолок 10).
            old_score = analysis.get("score")
            new_score = old_score
            if isinstance(old_score, int):
                new_score = min(10, old_score + 1)
            analysis["summary_sent"] = True
            analysis["summary_sent_backfilled"] = True
            if isinstance(new_score, int):
                analysis["score"] = new_score
            flips.append((report_date, meeting_id, deal_id, old_score, new_score, verdict["evidence"]))
            stats["flipped"] += 1
            if live:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE meetings SET analysis_json=%s WHERE report_date=%s AND meeting_id=%s",
                        (json.dumps(analysis, ensure_ascii=False), report_date, meeting_id),
                    )
                conn.commit()
        return {"stats": stats, "flips": flips}
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--live", action="store_true", help="записать изменения в БД (иначе dry-run)")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    result = run(args.days, args.live)
    mode = "LIVE" if args.live else "DRY-RUN"
    print(f"\n=== Бэкафилл итогов встреч [{mode}], окно {args.days} дн. ===")
    for rd, mid, deal, old, new, ev in result["flips"]:
        print(f"  {rd} встреча #{mid} (сделка {deal}): балл {old} → {new} | итоги: «{ev[:90]}»")
    s = result["stats"]
    print(
        f"\nКандидатов: {s['candidates']} | без пост-переписки: {s['no_post_comms']} | "
        f"проверено ИИ: {s['judged']} | дозачтено итогов: {s['flipped']} | ошибок: {s['errors']}"
    )
    if not args.live and result["flips"]:
        print("Это dry-run. Для записи в БД повторить с --live.")


if __name__ == "__main__":
    main()
