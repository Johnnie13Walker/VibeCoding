import argparse
import json
import os
from datetime import date

from src import bx_client
from src import analyze_llm
from src import notify
from src import tasks as bx_tasks
from src.config import load_config
from src.db import connect
from src.deltas import compute_deltas
from src.lock import AlreadyRunning, single_instance
from src.promises import compute_promises_loop
from src.collect import collect_day
from src.enrich import enrich_meetings
from src.feed import build_day_feed, extract_rejections
from src.transform import build_db_rows, build_post_meeting_comms, compute_stale_deals, resolve_target_date
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


def _analysis_is_empty(obj) -> bool:
    """Разбор считается пустым/пропущенным (нет содержательной части)."""
    if not isinstance(obj, dict):
        return True
    return not obj.get("checklist") and not obj.get("verdict") and not obj.get("systemic_conclusion")


def _preserve_prior_analysis(conn, target, rows, extras) -> None:
    """Если у встречи свежий разбор пуст (skipped_no_transcript), а в БД есть прежний
    непустой — восстанавливаем прежний (analysis_json + транскрипт + extras.analyses)."""
    meetings = rows.get("meetings") or []
    empty = [m for m in meetings if _analysis_is_empty(_json_load(m.get("analysis_json")))]
    ids = [int(m["meeting_id"]) for m in empty if m.get("meeting_id")]
    if not ids:
        return
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT meeting_id, analysis_json, transcript_ok, transcript_url, transcript_text "
            "FROM meetings WHERE report_date = %s AND meeting_id = ANY(%s) AND analysis_json IS NOT NULL",
            (target.isoformat(), ids),
        )
        prior = {row[0]: row for row in cursor.fetchall()}
    analyses = extras.setdefault("analyses", {})
    for m in empty:
        rec = prior.get(int(m.get("meeting_id") or 0))
        if not rec:
            continue
        prior_obj = _json_load(rec[1])
        if _analysis_is_empty(prior_obj):
            continue
        m["analysis_json"] = json.dumps(prior_obj, ensure_ascii=False)
        m["analysis_status"] = "done"
        m["transcript_ok"] = rec[2]
        if rec[3]:
            m["transcript_url"] = rec[3]
        if rec[4]:
            m["transcript_text"] = rec[4]
        analyses[int(m["meeting_id"])] = prior_obj
        print(f"[preserve] встреча {m['meeting_id']}: восстановлен прежний разбор (транскрипт не скачался)", flush=True)


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
    post_comms = build_post_meeting_comms(raw.get("meet_day"), raw.get("wazzup"), raw.get("activities"))
    analyses = analyze_llm.analyze_day(enriched, meetings_meta, client=client, wazzup=post_comms)
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

        # Защита от транзиентного сбоя транскрипта: если свежий разбор встречи пуст
        # (транскрипт не скачался), а в БД есть прежний непустой — оставляем прежний.
        # Иначе теряются разбор и автозадачи по встрече при разовом сбое скачивания.
        _preserve_prior_analysis(conn, target, rows, extras)

        # Дневной отчёт отключён (атавизм): HTML-отчёт больше не генерируем.
        # Пишем только строку-якорь дня + данные дашбордов + разбор встреч.
        html = ""
        summary = {
            "generated_at": now.isoformat(),
            "report_date": target.isoformat(),
            "counts": {key: len(value) for key, value in rows.items()},
            "llm_status": llm_status,
            "llm_error": extras.get("llm_error"),
            "feed": build_day_feed(raw),  # лента дня — для архивного /today
        }
        counts = write_day(conn, target, rows, html, summary, status=llm_status)
        conn.commit()
        return {
            "status": "done",
            "report_date": target.isoformat(),
            "counts": counts,
            "llm_status": llm_status,
            "html": html,
            "digest": None,
        }
    finally:
        conn.close()


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
        notify_alert("LLM-разбор встреч недоступен (данные собраны)", report_date=report_date)
        return 0

    if result.get("status") == "done" and report_date:
        # Дневной отчёт отключён — в Telegram больше не шлём. Остаются автозадачи.
        # Автозадачи из разбора встреч — только в боевом утреннем прогоне (SCC_CREATE_TASKS=1),
        # чтобы ручные --force/бэкафилл не создавали задачи. Идемпотентно (meeting_tasks).
        if os.environ.get("SCC_CREATE_TASKS") == "1":
            try:
                conn = connect()
                try:
                    res = bx_tasks.create_tasks_for_day(conn, bx_client, date.fromisoformat(report_date))
                    print(f"[tasks] создано {sum(1 for r in res if r.get('status') == 'created')} задач за {report_date}", flush=True)
                finally:
                    conn.close()
            except Exception as exc:  # noqa: BLE001
                print(f"[tasks] create failed: {_mask(str(exc))[:200]}", flush=True)

    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Дата сбора YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Перегенерировать готовый день")
    args = parser.parse_args()
    target = resolve_target_date(args.date)
    raise SystemExit(cron_entry(target, force=args.force))


if __name__ == "__main__":
    main()
