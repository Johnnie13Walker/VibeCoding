"""Health-check и alerting для утренней рассылки Sales Copilot."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.lev_petrovich.legacy_sales_agent.report_contract import SALES_DISPATCH_SEQUENCE
from apps.lev_petrovich.telegram_route import describe_lev_petrovich_route, resolve_lev_petrovich_bot_token
from apps.lev_petrovich.legacy_sales_agent.sales_formatter import SALES_REPORT_FORMAT_VERSION, report_format_metadata, report_required_markers
from cloudbot.business_day import MOSCOW_TZ

DEFAULT_REQUIRED_REPORTS = SALES_DISPATCH_SEQUENCE
DEFAULT_JOB_NAME = "morning_sales_dispatch"


def sales_log_path(path: str | None = None) -> Path:
    raw = str(path or os.environ.get("SALES_LOG_FILE") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(__file__).resolve().parents[2] / "logs" / "sales_agent.log"


def append_sales_dispatch_event(event: str, **payload: Any) -> None:
    log_path = sales_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts_msk": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
        "event": event,
        **payload,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str))
        handle.write("\n")


def _load_events(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for raw_line in log_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _parse_ts_msk(raw_value: Any) -> datetime | None:
    raw = str(raw_value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=MOSCOW_TZ)
    return parsed.astimezone(MOSCOW_TZ)


def _report_label(report_type: str) -> str:
    mapping = {
        "sales": "Sales Copilot",
        "risks": "Риски по продажам",
        "focus": "Фокус РОПа",
        "followup": "Sales Follow-up",
        "weekly": "Weekly Sales Review",
    }
    return mapping.get(report_type, report_type)


def evaluate_morning_dispatch(
    *,
    now: datetime | None = None,
    log_path: str | Path | None = None,
    job_name: str = DEFAULT_JOB_NAME,
    required_reports: Iterable[str] = DEFAULT_REQUIRED_REPORTS,
    expected_format_version: str = SALES_REPORT_FORMAT_VERSION,
) -> dict[str, Any]:
    current = (now or datetime.now(MOSCOW_TZ)).astimezone(MOSCOW_TZ)
    dispatch_date = current.date()
    required = [str(item).strip().lower() for item in required_reports if str(item).strip()]
    expected_templates = {
        report_type: report_format_metadata(report_type).get("template_id", "")
        for report_type in required
    }
    expected_markers = {
        report_type: report_required_markers(report_type)
        for report_type in required
    }
    morning_start = datetime.combine(dispatch_date, time(9, 30), tzinfo=MOSCOW_TZ)

    path = sales_log_path(str(log_path) if log_path else None)
    raw_events = _load_events(path)

    relevant_events: list[dict[str, Any]] = []
    for event in raw_events:
        ts = _parse_ts_msk(event.get("ts_msk"))
        if ts is None or ts.date() != dispatch_date or ts < morning_start:
            continue
        if str(event.get("job_name") or "") != job_name:
            continue
        relevant_events.append({**event, "_ts": ts})

    started = any(item.get("event") == "sales_dispatch_start" for item in relevant_events)
    sent_by_report: dict[str, dict[str, Any]] = {}
    sent_sequence: list[str] = []
    errors_by_report: dict[str, list[str]] = {}
    format_issues_by_report: dict[str, list[str]] = {}
    for item in relevant_events:
        report_type = str(item.get("report_type") or "").strip().lower()
        if not report_type:
            continue
        if item.get("event") == "sales_report_sent":
            sent_by_report[report_type] = item
            sent_sequence.append(report_type)
        elif item.get("event") == "sales_report_error":
            errors_by_report.setdefault(report_type, []).append(str(item.get("error") or "unknown error"))

    missing_reports = [report for report in required if report not in sent_by_report]
    expected_sent_sequence = [report for report in required if report in sent_by_report]
    sequence_ok = sent_sequence[: len(expected_sent_sequence)] == expected_sent_sequence
    for report in required:
        sent_event = sent_by_report.get(report) or {}
        if not sent_event:
            continue
        actual_version = str(sent_event.get("format_version") or "").strip()
        expected_template = expected_templates.get(report) or ""
        actual_template = str(sent_event.get("template_id") or "").strip()
        actual_markers = [str(item) for item in (sent_event.get("format_markers") or []) if str(item)]
        if actual_version != expected_format_version:
            format_issues_by_report.setdefault(report, []).append(
                f"format_version={actual_version or '-'} вместо {expected_format_version}"
            )
        if expected_template and actual_template != expected_template:
            format_issues_by_report.setdefault(report, []).append(
                f"template_id={actual_template or '-'} вместо {expected_template}"
            )
        missing_markers = [marker for marker in expected_markers.get(report, []) if marker not in actual_markers]
        if missing_markers:
            format_issues_by_report.setdefault(report, []).append(
                "missing_markers=" + ", ".join(missing_markers)
            )
    ok = (
        started
        and not missing_reports
        and sequence_ok
        and not any(errors_by_report.get(report) for report in required)
        and not any(format_issues_by_report.get(report) for report in required)
    )

    return {
        "ok": ok,
        "log_path": str(path),
        "job_name": job_name,
        "dispatch_date": dispatch_date.isoformat(),
        "started": started,
        "required_reports": required,
        "missing_reports": missing_reports,
        "expected_sent_sequence": expected_sent_sequence,
        "sent_sequence": sent_sequence,
        "sequence_ok": sequence_ok,
        "sent_reports": sorted(sent_by_report.keys()),
        "errors_by_report": errors_by_report,
        "expected_format_version": expected_format_version,
        "expected_templates": expected_templates,
        "expected_markers": expected_markers,
        "format_issues_by_report": format_issues_by_report,
    }


def format_morning_dispatch_status(result: Mapping[str, Any]) -> str:
    dispatch_date = str(result.get("dispatch_date") or "")
    if result.get("ok"):
        sent_reports = [
            _report_label(report_type)
            for report_type in result.get("sent_reports") or []
            if report_type in (result.get("required_reports") or [])
        ]
        reports_text = ", ".join(sent_reports) or "все обязательные отчёты"
        return f"OK: утренняя рассылка {dispatch_date} доставила {reports_text}."

    lines = [f"⚠️ Утренняя рассылка sales за {dispatch_date} неполная."]
    if not result.get("started"):
        lines.append("- Не найден старт morning job `09:30 Europe/Moscow`.")
    missing = result.get("missing_reports") or []
    if missing:
        lines.append(
            "- Не доставлены: " + ", ".join(_report_label(report_type) for report_type in missing) + "."
        )
    if not result.get("sequence_ok", True):
        actual_sequence = ", ".join(_report_label(report_type) for report_type in (result.get("sent_sequence") or []))
        expected_sequence = ", ".join(
            _report_label(report_type) for report_type in (result.get("expected_sent_sequence") or [])
        )
        lines.append(
            f"- Нарушен порядок доставки: ожидалось `{expected_sequence}`, получено `{actual_sequence or '-'}`."
        )
    for report_type, errors in sorted((result.get("errors_by_report") or {}).items()):
        if not errors:
            continue
        last_error = str(errors[-1] or "unknown error")
        lines.append(f"- Ошибка { _report_label(report_type) }: {last_error}")
    for report_type, issues in sorted((result.get("format_issues_by_report") or {}).items()):
        if not issues:
            continue
        lines.append(f"- Формат { _report_label(report_type) } неактуален: {'; '.join(issues)}")
    return "\n".join(lines)


def _mask_value(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    if len(raw) <= 4:
        return "***"
    return f"{raw[:2]}***{raw[-2:]}"


def _normalize_chat_id(value: str | None) -> str:
    raw = str(value or "").strip()
    if raw.startswith("telegram:"):
        raw = raw.split(":", 1)[1].strip()
    return raw


def _resolve_alert_target(env: Mapping[str, str]) -> tuple[str, str, str]:
    bot_token = resolve_lev_petrovich_bot_token(env, allow_shared_fallback=True)
    chat_id = _normalize_chat_id(
        env.get("SALES_ALERT_TELEGRAM_CHAT_ID")
        or env.get("SALES_TELEGRAM_CHAT_ID")
        or env.get("SALES_DAILY_TELEGRAM_CHAT_ID")
        or env.get("SALES_TELEGRAM_OWNER_ID")
        or env.get("TELEGRAM_CHAT_ID")
        or env.get("TELEGRAM_OWNER_ID")
        or ""
    )
    api_base = str(
        env.get("SALES_TELEGRAM_API_BASE_URL")
        or env.get("TELEGRAM_API_BASE_URL")
        or "https://api.telegram.org"
    ).strip()
    if not bot_token or not chat_id:
        raise RuntimeError("Для alert не заданы Telegram token/chat_id контура Льва Петровича.")
    return bot_token, chat_id, api_base


def send_alert_to_telegram(text: str, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    env_data = {str(key): str(value) for key, value in (env or os.environ).items()}
    bot_token, chat_id, api_base = _resolve_alert_target(env_data)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    request = Request(
        f"{api_base.rstrip('/')}/bot{bot_token}/sendMessage",
        method="POST",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram alert failed: {detail}") from None
    except URLError as error:
        raise RuntimeError(f"Telegram alert failed: {error.reason or error}") from None

    response_payload = json.loads(raw or "{}")
    if response_payload.get("ok") is not True:
        raise RuntimeError(f"Telegram alert failed: {response_payload.get('description') or 'unknown error'}")
    result = response_payload.get("result") or {}
    return {
        "chat_id_masked": _mask_value(chat_id),
        "message_id": str(result.get("message_id") or ""),
    }


def _positive_flag(raw_value: str | None) -> bool:
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Health-check утренней рассылки sales-отчётов.")
    parser.add_argument("--log-file", default="")
    parser.add_argument("--job-name", default=DEFAULT_JOB_NAME)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--send-alert", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    result = evaluate_morning_dispatch(
        log_path=args.log_file or None,
        job_name=args.job_name,
    )
    status_text = format_morning_dispatch_status(result)
    if args.json:
        print(json.dumps({**result, "status_text": status_text}, ensure_ascii=False))
    else:
        print(status_text)

    should_send_alert = bool(args.send_alert) or _positive_flag(os.environ.get("SALES_MORNING_ALERT"))
    if not result["ok"] and should_send_alert:
        delivery = send_alert_to_telegram(status_text)
        route_meta = describe_lev_petrovich_route()
        append_sales_dispatch_event(
            "sales_morning_alert_sent",
            job_name=args.job_name,
            chat_id=delivery["chat_id_masked"],
            message_id=delivery["message_id"],
            dispatch_date=result["dispatch_date"],
            route_key=route_meta["route_key"],
            display_name=route_meta["display_name"],
            bot_username=route_meta["bot_username"],
        )

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
