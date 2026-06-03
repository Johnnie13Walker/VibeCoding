import argparse
import json
from datetime import date

from src import bx_client
from src import analyze_llm
from src import notify
from src.config import load_config
from src.db import connect
from src.deltas import compute_deltas
from src.lock import AlreadyRunning, single_instance
from src.promises import compute_promises_loop
from src.collect import collect_day
from src.enrich import enrich_meetings
from src.render import extract_rejections, render_report, _load_css
from src.report_author import author_report, build_payload, substitute_photos, wrap_document
from src.transform import build_db_rows, compute_stale_deals, resolve_target_date
from src.timeutil import now_msk
from src.writer import write_day


def build_extras(raw: dict, now) -> dict:
    return {
        "raw": raw,
        "report_date": raw.get("report_date"),
        "stale": compute_stale_deals(raw.get("deals_open", []), now, raw.get("wazzup")),
        "users": raw.get("users", {}),
        "photos": raw.get("photos", {}),
        "rejections": extract_rejections(raw, raw.get("users", {})),
    }


def _user_directory_rows(raw: dict) -> list[dict]:
    """Справочник для веб-витрины: id → имя → должность (WORK_POSITION → dept).
    Email — плейсхолдер (auth матчит живой Bitrix, не это поле); writer на
    конфликте обновляет только name+dept, не трогая auth-поля."""
    names = raw.get("users") or {}
    roles = raw.get("user_roles") or {}
    out: list[dict] = []
    for uid, name in names.items():
        suid = str(uid)
        if not suid.isdigit():
            continue
        out.append(
            {
                "bitrix_id": int(suid),
                "email": f"{suid}@belberrycrm.local",
                "name": str(name or suid).strip() or suid,
                "dept": str(roles.get(uid) or roles.get(suid) or "").strip(),
                "is_active": True,
            }
        )
    return out


def already_done(conn, target: date) -> bool:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT status FROM reports WHERE report_date = %s",
            (target.isoformat(),),
        )
        row = cursor.fetchone()
    return bool(row and row[0] == "done")


def run_llm_phase(raw, rows, extras, *, client_factory=None, bx=None) -> dict:
    enriched = enrich_meetings(raw, bx=bx, refresh=True)
    meetings_meta = {int(item["id"]): item for item in raw.get("meet_day", [])}
    for row in rows.get("meetings", []):
        meeting_id = int(row["meeting_id"])
        transcript = enriched.get(meeting_id, {})
        row["transcript_url"] = transcript.get("url")
        row["transcript_text"] = transcript.get("text")
        row["transcript_ok"] = transcript.get("transcript_status") == "ok"
    client = (client_factory or analyze_llm.get_client)()
    analyses = analyze_llm.analyze_day(enriched, meetings_meta, client=client, wazzup=raw.get("wazzup"))
    for row in rows.get("meetings", []):
        meeting_id = int(row["meeting_id"])
        analysis = analyses.get(meeting_id)
        if analysis:
            row["analysis_json"] = json.dumps(analysis, ensure_ascii=False)
            row["analysis_status"] = "done" if analysis.get("analysis_available", True) else "skipped_no_transcript"
    narrative = analyze_llm.analyze_day_narrative(rows, extras, analyses, client=client)
    return {"analyses": analyses, "narrative": narrative}


def run(
    target: date | None = None,
    *,
    force: bool = False,
    bx=None,
    connect_fn=connect,
    now_fn=now_msk,
    llm_client_factory=None,
):
    load_config(["DATABASE_URL"])
    target = target or resolve_target_date(None)
    conn = connect_fn()
    try:
        if not force and already_done(conn, target):
            return {"status": "skipped", "report_date": target.isoformat()}

        bx_client.ensure_token_fresh()
        now = now_fn()
        raw = collect_day(target, bx=bx)
        raw.setdefault("report_date", target.isoformat())
        rows = build_db_rows(raw, target, now)
        rows["_users"] = _user_directory_rows(raw)
        extras = build_extras(raw, now)
        extras["deltas"] = compute_deltas(conn, target, rows)
        extras["promises_loop"] = compute_promises_loop(conn, target, rows)
        llm_status = "done"
        try:
            llm_result = run_llm_phase(raw, rows, extras, client_factory=llm_client_factory, bx=bx)
            extras["analyses"] = llm_result["analyses"]
            extras["narrative"] = llm_result["narrative"]
        except Exception as exc:
            llm_status = "partial_llm_failure"
            extras["analyses"] = {}
            extras["narrative"] = {}
            extras["llm_error"] = _mask(str(exc))

        # Архитектура B: финальный отчёт авторит LLM по данным дня (report.css —
        # дизайн-контракт). render_report остаётся fallback-скелетом на сбой.
        html = None
        if llm_status == "done":
            try:
                client = (llm_client_factory or analyze_llm.get_client)()
                body = author_report(build_payload(rows, extras), client=client)
                if body:
                    body = substitute_photos(body, extras.get("photos") or {}, extras.get("users") or {})
                    html = wrap_document(body, _load_css(), target.isoformat())
            except Exception as exc:
                extras["llm_error"] = _mask(str(exc))
        if html is None:
            if llm_status == "done":
                llm_status = "partial_llm_failure"
            html = render_report(rows, extras)
        summary = {
            "generated_at": now.isoformat(),
            "report_date": target.isoformat(),
            "counts": {key: len(value) for key, value in rows.items()},
            "llm_status": llm_status,
            "llm_error": extras.get("llm_error"),
        }
        counts = write_day(conn, target, rows, html, summary, status=llm_status)
        conn.commit()
        return {
            "status": "done",
            "report_date": target.isoformat(),
            "counts": counts,
            "llm_status": llm_status,
        }
    finally:
        conn.close()


def run_llm_only(target: date, *, connect_fn=connect, llm_client_factory=None):
    conn = connect_fn()
    rows = _read_meetings_from_db(conn, target)
    pending = {}
    all_analyses = {}
    meetings_meta = {}
    for row in rows["meetings"]:
        mid = int(row["meeting_id"])
        meetings_meta[mid] = row
        if row.get("analysis_json"):
            all_analyses[mid] = _json_load(row["analysis_json"])
            continue
        pending[mid] = {
            "text": row.get("transcript_text") or "",
            "url": row.get("transcript_url"),
            "transcript_status": "ok" if row.get("transcript_ok") else "missing",
            "meeting_title": f"Встреча {mid}",
        }
    client = (llm_client_factory or analyze_llm.get_client)()
    new_analyses = analyze_llm.analyze_day(pending, meetings_meta, client=client) if pending else {}
    all_analyses.update(new_analyses)
    for row in rows["meetings"]:
        mid = int(row["meeting_id"])
        analysis = all_analyses.get(mid)
        if analysis:
            row["analysis_json"] = json.dumps(analysis, ensure_ascii=False)
            row["analysis_status"] = "done" if analysis.get("analysis_available", True) else "skipped_no_transcript"
    extras = {"raw": {"meet_day": []}, "report_date": target.isoformat(), "stale": {}, "users": {}, "photos": {}, "rejections": [], "analyses": all_analyses}
    extras["narrative"] = analyze_llm.analyze_day_narrative(rows, extras, all_analyses, client=client)
    html = render_report(rows, extras)
    summary = {"generated_at": now_msk().isoformat(), "report_date": target.isoformat(), "llm_status": "done"}
    counts = write_day(conn, target, rows, html, summary, status="done")
    conn.commit()
    return {"status": "done", "report_date": target.isoformat(), "counts": counts}


def _read_meetings_from_db(conn, target: date) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT meeting_id, deal_id, meeting_type, status, manager_id, scheduled_at,
                   transcript_url, transcript_text, transcript_ok, analysis_json
            FROM meetings WHERE report_date = %s
            """,
            (target.isoformat(),),
        )
        db_rows = cursor.fetchall()
    meetings = []
    for row in db_rows:
        if isinstance(row, dict):
            meetings.append({**row, "report_date": target.isoformat()})
        else:
            (
                meeting_id,
                deal_id,
                meeting_type,
                status,
                manager_id,
                scheduled_at,
                transcript_url,
                transcript_text,
                transcript_ok,
                analysis_json,
            ) = row
            meetings.append(
                {
                    "report_date": target.isoformat(),
                    "meeting_id": meeting_id,
                    "deal_id": deal_id,
                    "meeting_type": meeting_type,
                    "status": status,
                    "manager_id": manager_id,
                    "scheduled_at": scheduled_at,
                    "analysis_json": analysis_json,
                    "transcript_url": transcript_url,
                    "transcript_text": transcript_text,
                    "transcript_ok": transcript_ok,
                    "analysis_status": "done" if analysis_json else "pending",
                }
            )
    return {"deals_snapshot": [], "meetings": meetings, "manager_activity": [], "kp_briefs": []}


def _json_load(value):
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


def _mask(text: str) -> str:
    return text.replace("ANTHROPIC_API_KEY", "***")


def cron_entry(
    target: date | None = None,
    *,
    force: bool = False,
    run_fn=run,
    lock_ctx=single_instance,
    notify_link=notify.send_report_link,
    notify_alert=notify.send_alert,
) -> int:
    try:
        with lock_ctx():
            try:
                result = run_fn(target, force=force)
            except Exception as exc:
                report_date = target.isoformat() if isinstance(target, date) else None
                notify_alert(_mask(str(exc)), report_date=report_date)
                return 1
    except AlreadyRunning:
        print("daily_runner уже выполняется, пропуск")
        return 0

    if result.get("status") == "skipped":
        return 0

    report_date = result.get("report_date")
    if result.get("status") == "done" and result.get("llm_status") == "partial_llm_failure":
        notify_alert("Отчёт сформирован частично: LLM-разбор недоступен", report_date=report_date)
        return 0

    if result.get("status") == "done" and report_date:
        notify_link(report_date)

    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Дата отчёта YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Перегенерировать готовый день")
    parser.add_argument("--phase", choices=["all", "llm"], default="all")
    args = parser.parse_args()
    target = resolve_target_date(args.date)
    if args.phase == "llm":
        result = run_llm_only(target)
        print(result)
        return

    raise SystemExit(cron_entry(target, force=args.force))


if __name__ == "__main__":
    main()
