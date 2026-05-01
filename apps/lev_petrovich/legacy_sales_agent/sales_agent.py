"""Sales Copilot agent: Bitrix CRM -> анализ -> Telegram-отчет."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.request import Request, urlopen

from cloudbot.business_day import (
    current_business_week,
    current_business_week_window,
    previous_business_day,
    previous_business_week_window,
)
from cloudbot.devops.sales_dispatch_health import append_sales_dispatch_event
from cloudbot.providers.bitrix.bitrix_sales_adapter import BitrixSalesAdapter
from cloudbot.providers.bitrix_provider import BitrixProvider
from cloudbot.skills.bitrix_sales_data import get_sales_snapshot
from shared.contracts.telegram_routing_contract import normalize_chat_id

from apps.lev_petrovich.telegram_route import describe_lev_petrovich_route, resolve_lev_petrovich_bot_token

from .communications_metrics import (
    get_communications_summary_for_window,
    get_yesterday_communications_summary,
    resolve_sales_team_filter,
)
from .pipeline_analyzer import MOSCOW_TZ, analyze_pipeline
from .report_contract import SALES_RUNTIME_REPORT_TYPES, sales_followup_report_types
from .risk_detector import detect_risks
from .sales_formatter import (
    format_focus_sales_report,
    format_followup_report,
    format_pipeline_report,
    format_risks_report,
    format_sales_brief,
    format_weekly_review,
    report_marker_status,
    report_format_metadata,
)

REPORT_TYPES = set(SALES_RUNTIME_REPORT_TYPES)
TELEGRAM_PARSE_MODE = "HTML"
ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SALES_DAILY_HISTORY_FILE = ROOT_DIR / "logs" / "sales_daily_history.json"
DEFAULT_FIXTURE_SALES_LOG_FILE = ROOT_DIR / "tmp" / "sales_agent_fixture.log"


class SalesAgentError(RuntimeError):
    """Ошибка подготовки sales-отчета."""


def _mask_value(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    if len(raw) <= 4:
        return "***"
    return f"{raw[:2]}***{raw[-2:]}"


def _env_dict(env: Mapping[str, str] | None = None) -> dict[str, str]:
    if env is None:
        return {str(key): str(value) for key, value in os.environ.items()}
    return {str(key): str(value) for key, value in env.items()}


def _append_sales_log(event: str, **payload: Any) -> None:
    append_sales_dispatch_event(event, **payload)


def _resolve_now(env_data: Mapping[str, str]) -> datetime:
    raw_ts = str(env_data.get("SALES_AGENT_NOW_TS") or "").strip()
    if raw_ts:
        return datetime.fromtimestamp(int(raw_ts), tz=timezone.utc).astimezone(MOSCOW_TZ)
    return datetime.now(MOSCOW_TZ)


def _optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _parse_report_date(raw_value: str | None, *, option_name: str) -> date | None:
    raw = str(raw_value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as error:
        raise SalesAgentError(f"Неверная дата {option_name}: {raw}. Ожидается формат YYYY-MM-DD.") from error


def _resolve_period_override(env_data: Mapping[str, str]) -> dict[str, Any] | None:
    start_date = _parse_report_date(env_data.get("SALES_REPORT_DATE_FROM"), option_name="--date-from")
    end_date = _parse_report_date(env_data.get("SALES_REPORT_DATE_TO"), option_name="--date-to")
    if start_date is None and end_date is None:
        return None
    if start_date is None or end_date is None:
        raise SalesAgentError("Для произвольного периода нужны оба параметра: --date-from и --date-to.")
    if end_date < start_date:
        raise SalesAgentError("Дата окончания периода не может быть раньше даты начала.")

    start = datetime.combine(start_date, time.min, tzinfo=MOSCOW_TZ)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=MOSCOW_TZ)
    return {
        "start": start,
        "end": end,
        "start_date": start_date,
        "end_date": end_date,
    }


def _sales_daily_history_path(env_data: Mapping[str, str]) -> Path:
    raw_path = str(env_data.get("SALES_DAILY_HISTORY_FILE") or "").strip()
    if raw_path:
        return Path(raw_path).expanduser()
    sales_log_file = str(env_data.get("SALES_LOG_FILE") or "").strip()
    if sales_log_file:
        return Path(sales_log_file).expanduser().resolve().parent / "sales_daily_history.json"
    return DEFAULT_SALES_DAILY_HISTORY_FILE


def _load_sales_daily_history(env_data: Mapping[str, str]) -> dict[str, Any]:
    path = _sales_daily_history_path(env_data)
    if not path.exists():
        return {"records": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"records": {}}
    if not isinstance(payload, dict):
        return {"records": {}}
    records = payload.get("records")
    if not isinstance(records, dict):
        payload["records"] = {}
    return payload


def _save_sales_daily_history(env_data: Mapping[str, str], payload: Mapping[str, Any]) -> None:
    path = _sales_daily_history_path(env_data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _daily_history_record(
    *,
    now: datetime,
    analysis: Mapping[str, Any],
    risk_report: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = dict(analysis.get("metrics") or {})
    risk_totals = dict(risk_report.get("summary_totals") or risk_report.get("totals") or {})
    report_day = previous_business_day(now.date())
    return {
        "run_day": now.date().isoformat(),
        "report_day": report_day.isoformat(),
        "captured_at": now.isoformat(timespec="seconds"),
        "current_metrics": {
            "deals_in_work": int(metrics.get("deals_in_work") or 0),
            "pipeline_amount": float(metrics.get("pipeline_amount") or 0.0),
            "moving_deals_last_week": int(metrics.get("moving_deals_last_week") or 0),
            "stagnant_deals_last_week": int(metrics.get("stagnant_deals_last_week") or 0),
            "postponed_deals_now": int(metrics.get("postponed_deals_now") or 0),
            "postponed_deals_now_amount": float(metrics.get("postponed_deals_now_amount") or 0.0),
            "hot_stage_deals": int(metrics.get("hot_stage_deals") or 0),
            "hot_stage_amount": float(metrics.get("hot_stage_amount") or 0.0),
            "deal_risks": int(risk_totals.get("deal_risks") or 0),
            "risk_amount": float(risk_totals.get("risk_amount") or 0.0),
            "stagnant_risk_deals": int((risk_report.get("category_totals") or {}).get("stagnant_deals") or 0),
            "stagnant_risk_amount": float((risk_report.get("category_totals") or {}).get("stagnant_amount") or 0.0),
            "deals_without_next_step": int(metrics.get("deals_without_next_step") or 0),
            "deals_without_next_step_amount": float(metrics.get("deals_without_next_step_amount") or 0.0),
            "stale_communication_deals": int(metrics.get("stale_communication_deals") or 0),
            "stale_communication_amount": float(metrics.get("stale_communication_amount") or 0.0),
            "overdue_deal_task_deals": int(metrics.get("overdue_deal_task_deals") or 0),
            "overdue_deal_task_amount": float(metrics.get("overdue_deal_task_amount") or 0.0),
        },
        "report_day_metrics": {
            "new_deals_yesterday": int(metrics.get("new_deals_yesterday") or 0),
            "conducted_meetings_yesterday": int(metrics.get("conducted_meetings_yesterday") or 0),
            "accepted_briefs_yesterday": int(metrics.get("accepted_briefs_yesterday") or 0),
            "postponed_deals_yesterday": int(metrics.get("postponed_deals_yesterday") or 0),
            "postponed_deals_yesterday_amount": float(metrics.get("postponed_deals_yesterday_amount") or 0.0),
            "lost_deals_yesterday": int(metrics.get("lost_deals_yesterday") or 0),
            "lost_deals_yesterday_amount": float(metrics.get("lost_deals_yesterday_amount") or 0.0),
        },
    }


def _load_previous_business_day_record(env_data: Mapping[str, str], *, now: datetime) -> dict[str, Any]:
    history = _load_sales_daily_history(env_data)
    records = history.get("records")
    if not isinstance(records, dict):
        return {}
    previous_run_day = previous_business_day(now.date()).isoformat()
    record = records.get(previous_run_day)
    return record if isinstance(record, dict) else {}


def _store_daily_history_record(
    env_data: Mapping[str, str],
    *,
    now: datetime,
    analysis: Mapping[str, Any],
    risk_report: Mapping[str, Any],
) -> None:
    history = _load_sales_daily_history(env_data)
    records = history.setdefault("records", {})
    if not isinstance(records, dict):
        records = {}
        history["records"] = records
    record = _daily_history_record(now=now, analysis=analysis, risk_report=risk_report)
    records[str(record["run_day"])] = record
    _save_sales_daily_history(env_data, history)


def _attach_hot_stage_product_rows(env_data: Mapping[str, str], analysis: dict[str, Any]) -> None:
    hot_stage_deals = list(analysis.get("hot_stage_deals") or [])
    deal_ids = [deal.get("id") for deal in hot_stage_deals if str(deal.get("id") or "").strip()]
    if not deal_ids:
        return

    def fetch_product_rows(timeout_override_sec: int | None) -> dict[str, list[dict[str, Any]]] | None:
        try:
            adapter_env = dict(env_data)
            if timeout_override_sec is not None:
                adapter_env["BITRIX_TIMEOUT_SEC"] = str(timeout_override_sec)
            adapter = BitrixSalesAdapter.from_env(adapter_env)
            product_rows = adapter.get_deal_product_rows(deal_ids)
        except Exception as error:  # noqa: BLE001
            _append_sales_log(
                "sales_product_rows_fetch_error",
                timeout_sec=timeout_override_sec,
                deal_ids=[str(item) for item in deal_ids],
                error=str(error),
            )
            return None
        if not isinstance(product_rows, dict):
            return None
        return product_rows

    product_rows_timeout_sec = max(int(str(env_data.get("SALES_PRODUCT_ROWS_TIMEOUT_SEC") or "6").strip() or "6"), 1)
    current_timeout_sec = int(str(env_data.get("BITRIX_TIMEOUT_SEC") or "20").strip() or "20")

    product_rows_map = fetch_product_rows(min(current_timeout_sec, product_rows_timeout_sec))
    rows_count = sum(len(list(rows or [])) for rows in (product_rows_map or {}).values())
    if rows_count == 0 and current_timeout_sec > product_rows_timeout_sec:
        fallback_rows_map = fetch_product_rows(current_timeout_sec)
        fallback_rows_count = sum(len(list(rows or [])) for rows in (fallback_rows_map or {}).values())
        if fallback_rows_count > 0:
            product_rows_map = fallback_rows_map
            rows_count = fallback_rows_count

    if not isinstance(product_rows_map, dict):
        return
    for deal in hot_stage_deals:
        deal_id = str(deal.get("id") or "").strip()
        if deal_id and deal_id in product_rows_map:
            deal["product_rows"] = list(product_rows_map.get(deal_id) or [])

    _append_sales_log(
        "sales_product_rows_attached",
        deal_ids=[str(item) for item in deal_ids],
        rows_count=rows_count,
        deals_with_rows=sum(1 for deal in hot_stage_deals if deal.get("product_rows")),
    )


def _resolve_sales_chat_id(
    env_data: Mapping[str, str],
    *,
    explicit_chat_id: str | None = None,
    report_type: str | None = None,
) -> str:
    explicit_value = normalize_chat_id(explicit_chat_id)
    if explicit_value:
        return explicit_value

    report = str(report_type or "").strip().lower()
    candidates: list[str | None]
    if report == "weekly":
        candidates = [
            env_data.get("SALES_WEEKLY_TELEGRAM_CHAT_ID"),
            env_data.get("SALES_TELEGRAM_CHAT_ID"),
            env_data.get("SALES_TELEGRAM_OWNER_ID"),
            env_data.get("TELEGRAM_CHAT_ID"),
        ]
    else:
        candidates = [
            env_data.get("SALES_TELEGRAM_CHAT_ID"),
            env_data.get("SALES_DAILY_TELEGRAM_CHAT_ID"),
            env_data.get("SALES_WEEKLY_TELEGRAM_CHAT_ID"),
            env_data.get("SALES_TELEGRAM_OWNER_ID"),
            env_data.get("TELEGRAM_CHAT_ID"),
        ]

    for candidate in candidates:
        value = normalize_chat_id(candidate)
        if value:
            return value
    return ""


def _telegram_ready(env_data: Mapping[str, str]) -> bool:
    return bool(_resolve_sales_chat_id(env_data)) and (
        bool(resolve_lev_petrovich_bot_token(env_data))
        or str(env_data.get("TELEGRAM_DRY_RUN") or env_data.get("SALES_TELEGRAM_DRY_RUN") or "") == "1"
    )


def _split_telegram_text(text: str, limit: int = 3500) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return [""]
    if len(raw) <= limit:
        return [raw]

    parts: list[str] = []
    current = ""
    for block in raw.split("\n\n"):
        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
            current = ""
        if len(block) <= limit:
            current = block
            continue
        lines = block.split("\n")
        line_chunk = ""
        for line in lines:
            candidate_line = line if not line_chunk else f"{line_chunk}\n{line}"
            if len(candidate_line) <= limit:
                line_chunk = candidate_line
                continue
            if line_chunk:
                parts.append(line_chunk)
            if len(line) <= limit:
                line_chunk = line
                continue
            start_pos = 0
            while start_pos < len(line):
                parts.append(line[start_pos:start_pos + limit])
                start_pos += limit
            line_chunk = ""
        if line_chunk:
            current = line_chunk

    if current:
        parts.append(current)
    return [part for part in parts if part]


class SalesAgent:
    def __init__(
        self,
        *,
        provider: BitrixProvider,
        now: datetime,
        inactivity_days: int = 5,
        late_stage_days: int = 5,
        stale_communication_days: int = 14,
        large_deal_amount: float = 150000.0,
        monthly_target: float | None = None,
        env_data: Mapping[str, str] | None = None,
    ) -> None:
        self.provider = provider
        self.now = now.astimezone(MOSCOW_TZ)
        self.inactivity_days = int(inactivity_days)
        self.late_stage_days = int(late_stage_days)
        self.stale_communication_days = int(stale_communication_days)
        self.large_deal_amount = float(large_deal_amount)
        self.monthly_target = monthly_target
        self.env_data = dict(env_data or {})

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "SalesAgent":
        env_data = _env_dict(env)
        provider = BitrixProvider.from_env(env=env_data)
        return cls(
            provider=provider,
            now=_resolve_now(env_data),
            inactivity_days=int(env_data.get("SALES_INACTIVITY_DAYS") or "5"),
            late_stage_days=int(env_data.get("SALES_LATE_STAGE_INACTIVITY_DAYS") or "5"),
            stale_communication_days=int(env_data.get("SALES_STALE_COMMUNICATION_DAYS") or "14"),
            large_deal_amount=float(env_data.get("SALES_LARGE_DEAL_AMOUNT") or "150000"),
            monthly_target=_optional_float(env_data.get("SALES_MONTHLY_TARGET")),
            env_data=env_data,
        )

    def build_report_payload(self, *, report_type: str = "sales") -> dict[str, Any]:
        period_override = _resolve_period_override(self.env_data)
        weekly_window: dict[str, Any] | None = None
        if report_type == "weekly":
            if period_override:
                current_week_start = period_override["start"]
                current_week_end = period_override["end"]
                week_start_date = period_override["start_date"]
                week_end_date = period_override["end_date"]
                previous_week_end = current_week_start
                previous_week_start = previous_week_end - (current_week_end - current_week_start)
                weekly_window = {
                    "start": current_week_start,
                    "end": current_week_end,
                    "previous_start": previous_week_start,
                    "previous_end": previous_week_end,
                    "start_date": week_start_date,
                    "end_date": week_end_date,
                    "custom_period": True,
                    "title": "📊 Отчёт Льва Петровича по периоду",
                    "summary_heading": "1. Что произошло за период",
                    "people_heading": "3. Люди за период",
                    "problem_deals_heading": "5. Проблемные сделки периода",
                }
            else:
                current_week_start, current_week_end = current_business_week_window(self.now)
                previous_week_start, previous_week_end = previous_business_week_window(self.now)
                week_start_date, week_end_date = current_business_week(self.now)
                weekly_window = {
                    "start": current_week_start,
                    "end": current_week_end,
                    "previous_start": previous_week_start,
                    "previous_end": previous_week_end,
                    "start_date": week_start_date,
                    "end_date": week_end_date,
                    "custom_period": False,
                }

        snapshot = get_sales_snapshot(
            self.env_data,
            period_start=weekly_window.get("start") if weekly_window else None,
            period_end=weekly_window.get("end") if weekly_window else None,
        )
        department_filter = resolve_sales_team_filter(
            self.env_data,
            snapshot=snapshot,
        )
        analysis = analyze_pipeline(
            snapshot,
            now=self.now,
            large_deal_amount=self.large_deal_amount,
            inactivity_days=self.inactivity_days,
            stale_communication_days=self.stale_communication_days,
            department_filter=department_filter,
        )
        risk_report = detect_risks(
            analysis,
            inactivity_days=self.inactivity_days,
            late_stage_days=self.late_stage_days,
            stale_communication_days=self.stale_communication_days,
        )
        weekly_summary: dict[str, Any] | None = None
        previous_weekly_summary: dict[str, Any] | None = None
        if weekly_window:
            weekly_summary = get_communications_summary_for_window(
                self.env_data,
                snapshot=snapshot,
                analysis=analysis,
                period_start=weekly_window["start"],
                period_end=weekly_window["end"],
                department_filter=department_filter,
            )
            previous_weekly_summary = get_communications_summary_for_window(
                self.env_data,
                snapshot=snapshot,
                analysis=None,
                period_start=weekly_window["previous_start"],
                period_end=weekly_window["previous_end"],
                department_filter=department_filter,
            )
            communications_summary = weekly_summary
        else:
            communications_summary = get_yesterday_communications_summary(
                self.env_data,
                snapshot=snapshot,
                analysis=analysis,
                now=self.now,
                department_filter=department_filter,
            )
        department_filter = communications_summary.get("department_filter") or department_filter
        _append_sales_log(
            "sales_department_filter",
            mode=department_filter.get("mode"),
            found_departments=department_filter.get("found_departments") or [],
            missing_departments=department_filter.get("missing_departments") or [],
            allowlist_department_ids=department_filter.get("allowlist_department_ids") or [],
            allowlist_count=int(department_filter.get("allowlist_count") or 0),
            allowlist_users=department_filter.get("allowlist_users") or [],
            scoped_active_users_count=int(department_filter.get("scoped_active_users_count") or 0),
            scoped_active_users=department_filter.get("scoped_active_users") or [],
            excluded_users=department_filter.get("excluded_users") or [],
            warnings=department_filter.get("warnings") or [],
        )
        _append_sales_log(
            "sales_snapshot",
            source=snapshot.get("source"),
            deals=len(snapshot.get("active_deals") or snapshot.get("recent_deals") or []),
            leads=len(snapshot.get("active_leads") or snapshot.get("recent_leads") or []),
            meetings=len(snapshot.get("conducted_meetings") or []),
            briefs=len(snapshot.get("accepted_briefs") or []),
            tasks=len(snapshot.get("tasks") or []),
            communication_managers=len(communications_summary.get("managers") or []),
        )
        _append_sales_log(
            "sales_analysis_scope",
            allowlist_users=(analysis.get("sales_scope") or {}).get("allowlist_users") or [],
            excluded_entity_counts=(analysis.get("sales_scope") or {}).get("excluded_entity_counts") or {},
            excluded_users=(analysis.get("sales_scope") or {}).get("excluded_users") or [],
        )
        _attach_hot_stage_product_rows(self.env_data, analysis)
        analysis["daily_comparison"] = {
            "report_day": previous_business_day(self.now.date()).isoformat(),
            "previous_run": _load_previous_business_day_record(self.env_data, now=self.now),
        }
        payload = {
            "snapshot": snapshot,
            "analysis": analysis,
            "risk_report": risk_report,
            "communications_summary": communications_summary,
        }
        if weekly_window:
            if weekly_window.get("custom_period") and weekly_window.get("end_date") < self.now.date():
                limitations = list(analysis.get("limitations") or [])
                note = (
                    "Для прошедших периодов риск, люди и текущая воронка считаются по текущему состоянию "
                    "открытых сделок; исторический снимок Bitrix на конец периода в этом отчёте не хранится."
                )
                if note not in limitations:
                    limitations.append(note)
                analysis["limitations"] = limitations
            payload["weekly_context"] = {
                **weekly_window,
                "communications_summary": weekly_summary or {},
                "previous_communications_summary": previous_weekly_summary or {},
            }
        return payload

    def render(self, report_type: str, payload: dict[str, Any]) -> str:
        if report_type not in REPORT_TYPES:
            raise SalesAgentError(f"Неизвестный тип отчета: {report_type}")

        analysis = payload["analysis"]
        risk_report = payload["risk_report"]
        communications_summary = payload.get("communications_summary") or {}

        if report_type == "sales":
            return format_sales_brief(
                analysis,
                risk_report,
                communications_summary=communications_summary,
                monthly_target=self.monthly_target,
            )
        if report_type == "pipeline":
            return format_sales_brief(
                analysis,
                risk_report,
                communications_summary=communications_summary,
                monthly_target=self.monthly_target,
            )
        if report_type == "risks":
            return format_risks_report(
                analysis,
                risk_report,
                communications_summary=communications_summary,
            )
        if report_type == "focus":
            return format_focus_sales_report(
                analysis,
                risk_report,
                communications_summary=communications_summary,
            )
        if report_type == "followup":
            return format_followup_report(analysis, risk_report)
        return format_weekly_review(
            analysis,
            risk_report,
            weekly_context=payload.get("weekly_context") or {},
            monthly_target=self.monthly_target,
        )

    def send_to_telegram(
        self,
        text: str,
        *,
        chat_id: str | None = None,
        parse_mode: str | None = TELEGRAM_PARSE_MODE,
        report_type: str | None = None,
    ) -> dict[str, Any]:
        env_data = dict(self.env_data)
        target_chat_id = _resolve_sales_chat_id(
            env_data,
            explicit_chat_id=chat_id,
            report_type=report_type,
        )
        if not target_chat_id:
            raise SalesAgentError("Не задан chat_id для sales-отчета")
        masked_chat_id = _mask_value(target_chat_id)

        dry_run = str(env_data.get("SALES_TELEGRAM_DRY_RUN") or env_data.get("TELEGRAM_DRY_RUN") or "") == "1"
        chunks = _split_telegram_text(text)
        if dry_run:
            _append_sales_log("telegram_send_dry_run", chat_id=masked_chat_id, chunks=len(chunks))
            return {"status": "dry_run", "chat_id_masked": masked_chat_id, "chunks": len(chunks), "message_ids": []}

        bot_token = resolve_lev_petrovich_bot_token(env_data)
        if not bot_token:
            raise SalesAgentError(
                "Не задан отдельный Telegram token Льва Петровича "
                "(SALES_TELEGRAM_BOT_TOKEN или SALES_TELEGRAM_BOT_TOKEN_FILE)"
            )

        api_base = str(
            env_data.get("SALES_TELEGRAM_API_BASE_URL")
            or env_data.get("TELEGRAM_API_BASE_URL")
            or "https://api.telegram.org"
        ).strip()
        message_ids: list[str] = []
        last_payload: dict[str, Any] = {}
        for chunk in chunks:
            request = Request(
                f"{api_base.rstrip('/')}/bot{bot_token}/sendMessage",
                method="POST",
                data=json.dumps(
                    {
                        "chat_id": target_chat_id,
                        "text": chunk,
                        "disable_web_page_preview": True,
                        "parse_mode": parse_mode or TELEGRAM_PARSE_MODE,
                    },
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )

            try:
                with urlopen(request, timeout=15) as response:  # noqa: S310
                    raw = response.read().decode("utf-8", errors="replace")
            except Exception as error:  # noqa: BLE001
                raise SalesAgentError(f"Ошибка отправки sales-отчета в Telegram: {error}") from error

            payload = json.loads(raw or "{}")
            if payload.get("ok") is not True:
                description = payload.get("description") or "unknown error"
                raise SalesAgentError(f"Telegram sendMessage failed: {description}")

            last_payload = payload
            message_id = str((payload.get("result") or {}).get("message_id") or "").strip()
            if message_id:
                message_ids.append(message_id)

        _append_sales_log("telegram_send_ok", chat_id=masked_chat_id, chunks=len(chunks), message_ids=message_ids)
        return {
            "status": "sent",
            "chat_id_masked": masked_chat_id,
            "payload": last_payload,
            "chunks": len(chunks),
            "message_ids": message_ids,
        }

    def run(
        self,
        *,
        report_type: str = "sales",
        send: bool = False,
        chat_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self.build_report_payload(report_type=report_type)
        trigger = str(self.env_data.get("SALES_TRIGGER") or "manual").strip() or "manual"
        job_name = str(self.env_data.get("SALES_JOB_NAME") or report_type).strip() or report_type
        workflow_name = str(self.env_data.get("SALES_WORKFLOW_NAME") or "agents.lev_petrovich").strip() or "agents.lev_petrovich"
        route_meta = describe_lev_petrovich_route()
        main_format = report_format_metadata(report_type)
        try:
            text = self.render(report_type, payload)
        except Exception as error:  # noqa: BLE001
            _append_sales_log(
                "sales_report_error",
                report_type=report_type,
                requested_report_type=report_type,
                trigger=trigger,
                job_name=job_name,
                workflow_name=workflow_name,
                route_key=route_meta["route_key"],
                display_name=route_meta["display_name"],
                bot_username=route_meta["bot_username"],
                stage="render",
                error=str(error),
                format_version=main_format["format_version"],
                formatter_module=main_format["formatter_module"],
                template_id=main_format["template_id"],
            )
            raise
        main_markers = report_marker_status(report_type, text)
        followup_messages: list[dict[str, Any]] = []
        followup_build_errors: list[dict[str, Any]] = []
        if report_type == "sales":
            for followup_report_type in sales_followup_report_types(report_type):
                followup_format = report_format_metadata(followup_report_type)
                try:
                    followup_text = self.render(followup_report_type, payload)
                    followup_messages.append(
                        {
                            "report_type": followup_report_type,
                            "text": followup_text,
                            "parse_mode": TELEGRAM_PARSE_MODE,
                            "format_version": followup_format["format_version"],
                            "formatter_module": followup_format["formatter_module"],
                            "template_id": followup_format["template_id"],
                        }
                    )
                except Exception as error:  # noqa: BLE001
                    followup_build_errors.append(
                        {
                            "report_type": followup_report_type,
                            "stage": "render",
                            "error": str(error),
                        }
                    )
                    _append_sales_log(
                        "sales_report_error",
                        report_type=followup_report_type,
                        requested_report_type=report_type,
                        trigger=trigger,
                        job_name=job_name,
                        workflow_name=workflow_name,
                        route_key=route_meta["route_key"],
                        display_name=route_meta["display_name"],
                        bot_username=route_meta["bot_username"],
                        stage="render",
                        error=str(error),
                        format_version=followup_format["format_version"],
                        formatter_module=followup_format["formatter_module"],
                        template_id=followup_format["template_id"],
                    )
        format_validation_errors: list[dict[str, Any]] = []
        if main_markers["missing"]:
            error_text = "Отсутствуют обязательные секции формата: " + ", ".join(main_markers["missing"])
            format_validation_errors.append(
                {
                    "report_type": report_type,
                    "stage": "format_validation",
                    "error": error_text,
                }
            )
            _append_sales_log(
                "sales_report_error",
                report_type=report_type,
                requested_report_type=report_type,
                trigger=trigger,
                job_name=job_name,
                workflow_name=workflow_name,
                route_key=route_meta["route_key"],
                display_name=route_meta["display_name"],
                bot_username=route_meta["bot_username"],
                stage="format_validation",
                error=error_text,
                format_markers=main_markers["present"],
                missing_format_markers=main_markers["missing"],
                format_version=main_format["format_version"],
                formatter_module=main_format["formatter_module"],
                template_id=main_format["template_id"],
            )
        followup_marker_statuses: dict[str, dict[str, list[str]]] = {}
        for followup in followup_messages:
            followup_report_type = str(followup.get("report_type") or report_type).strip() or report_type
            markers = report_marker_status(followup_report_type, str(followup.get("text") or ""))
            followup_marker_statuses[followup_report_type] = markers
            if markers["missing"]:
                followup_format = {
                    **report_format_metadata(followup_report_type),
                    **{
                        key: str(followup.get(key) or "").strip()
                        for key in ("format_version", "formatter_module", "template_id")
                        if followup.get(key)
                    },
                }
                error_text = "Отсутствуют обязательные секции формата: " + ", ".join(markers["missing"])
                format_validation_errors.append(
                    {
                        "report_type": followup_report_type,
                        "stage": "format_validation",
                        "error": error_text,
                    }
                )
                _append_sales_log(
                    "sales_report_error",
                    report_type=followup_report_type,
                    requested_report_type=report_type,
                    trigger=trigger,
                    job_name=job_name,
                    workflow_name=workflow_name,
                    route_key=route_meta["route_key"],
                    display_name=route_meta["display_name"],
                    bot_username=route_meta["bot_username"],
                    stage="format_validation",
                    error=error_text,
                    format_markers=markers["present"],
                    missing_format_markers=markers["missing"],
                    format_version=followup_format["format_version"],
                    formatter_module=followup_format["formatter_module"],
                    template_id=followup_format["template_id"],
                )
        result = {
            "ok": True,
            "report_type": report_type,
            "text": text,
            "parse_mode": TELEGRAM_PARSE_MODE,
            "format_version": main_format["format_version"],
            "formatter_module": main_format["formatter_module"],
            "template_id": main_format["template_id"],
            "format_markers": main_markers["present"],
            "missing_format_markers": main_markers["missing"],
            "analysis": payload["analysis"],
            "risk_report": payload["risk_report"],
            "communications_summary": payload.get("communications_summary") or {},
            "followup_messages": followup_messages,
            "followup_build_errors": followup_build_errors,
            "format_validation_errors": format_validation_errors,
        }
        source_mode = str((payload.get("analysis") or {}).get("source") or "").strip()
        if source_mode != "fixture":
            try:
                _store_daily_history_record(
                    self.env_data,
                    now=self.now,
                    analysis=payload["analysis"],
                    risk_report=payload["risk_report"],
                )
            except OSError as error:
                _append_sales_log(
                    "sales_history_write_error",
                    report_type=report_type,
                    trigger=trigger,
                    job_name=job_name,
                    workflow_name=workflow_name,
                    route_key=route_meta["route_key"],
                    display_name=route_meta["display_name"],
                    bot_username=route_meta["bot_username"],
                    error=str(error),
                )
        if send:
            _append_sales_log(
                "sales_dispatch_start",
                report_type=report_type,
                trigger=trigger,
                job_name=job_name,
                workflow_name=workflow_name,
                route_key=route_meta["route_key"],
                display_name=route_meta["display_name"],
                bot_username=route_meta["bot_username"],
                format_version=main_format["format_version"],
                formatter_module=main_format["formatter_module"],
                template_id=main_format["template_id"],
                format_markers=main_markers["present"],
                missing_format_markers=main_markers["missing"],
            )
            deliveries: dict[str, Any] = {"main": None, "followups": []}
            delivery_errors: list[str] = [
                f"{item['report_type']} ({item['stage']}): {item['error']}" for item in format_validation_errors
            ]

            try:
                main_delivery = self.send_to_telegram(
                    text,
                    chat_id=chat_id,
                    parse_mode=result["parse_mode"],
                    report_type=report_type,
                )
                deliveries["main"] = main_delivery
                _append_sales_log(
                    "sales_report_sent",
                    report_type=report_type,
                    requested_report_type=report_type,
                    trigger=trigger,
                    job_name=job_name,
                    workflow_name=workflow_name,
                    route_key=route_meta["route_key"],
                    display_name=route_meta["display_name"],
                    bot_username=route_meta["bot_username"],
                    chat_id=main_delivery.get("chat_id_masked"),
                    chunks=main_delivery.get("chunks"),
                    message_ids=main_delivery.get("message_ids") or [],
                    format_markers=main_markers["present"],
                    missing_format_markers=main_markers["missing"],
                    format_version=main_format["format_version"],
                    formatter_module=main_format["formatter_module"],
                    template_id=main_format["template_id"],
                )
            except Exception as error:  # noqa: BLE001
                delivery_errors.append(f"{report_type}: {error}")
                _append_sales_log(
                    "sales_report_error",
                    report_type=report_type,
                    requested_report_type=report_type,
                    trigger=trigger,
                    job_name=job_name,
                    workflow_name=workflow_name,
                    route_key=route_meta["route_key"],
                    display_name=route_meta["display_name"],
                    bot_username=route_meta["bot_username"],
                    stage="delivery",
                    error=str(error),
                    format_version=main_format["format_version"],
                    formatter_module=main_format["formatter_module"],
                    template_id=main_format["template_id"],
                )

            followup_deliveries: list[dict[str, Any]] = []
            for followup in followup_messages:
                followup_report_type = str(followup.get("report_type") or report_type)
                followup_format = {
                    **report_format_metadata(followup_report_type),
                    **{key: str(followup.get(key) or "").strip() for key in ("format_version", "formatter_module", "template_id") if followup.get(key)},
                }
                try:
                    followup_markers = followup_marker_statuses.get(followup_report_type) or report_marker_status(
                        followup_report_type,
                        str(followup.get("text") or ""),
                    )
                    followup_delivery = self.send_to_telegram(
                        str(followup.get("text") or ""),
                        chat_id=chat_id,
                        parse_mode=str(followup.get("parse_mode") or TELEGRAM_PARSE_MODE),
                        report_type=followup_report_type,
                    )
                    followup_deliveries.append(followup_delivery)
                    _append_sales_log(
                        "sales_report_sent",
                        report_type=followup_report_type,
                        requested_report_type=report_type,
                        trigger=trigger,
                        job_name=job_name,
                        workflow_name=workflow_name,
                        route_key=route_meta["route_key"],
                        display_name=route_meta["display_name"],
                        bot_username=route_meta["bot_username"],
                        chat_id=followup_delivery.get("chat_id_masked"),
                        chunks=followup_delivery.get("chunks"),
                        message_ids=followup_delivery.get("message_ids") or [],
                        format_markers=followup_markers["present"],
                        missing_format_markers=followup_markers["missing"],
                        format_version=followup_format["format_version"],
                        formatter_module=followup_format["formatter_module"],
                        template_id=followup_format["template_id"],
                    )
                except Exception as error:  # noqa: BLE001
                    delivery_errors.append(f"{followup_report_type}: {error}")
                    _append_sales_log(
                        "sales_report_error",
                        report_type=followup_report_type,
                        requested_report_type=report_type,
                        trigger=trigger,
                        job_name=job_name,
                        workflow_name=workflow_name,
                        route_key=route_meta["route_key"],
                        display_name=route_meta["display_name"],
                        bot_username=route_meta["bot_username"],
                        stage="delivery",
                        error=str(error),
                        format_version=followup_format["format_version"],
                        formatter_module=followup_format["formatter_module"],
                        template_id=followup_format["template_id"],
                    )

            if followup_build_errors:
                for followup_error in followup_build_errors:
                    delivery_errors.append(
                        f"{followup_error['report_type']} ({followup_error['stage']}): {followup_error['error']}"
                    )

            result["telegram"] = {
                "main": deliveries["main"],
                "followups": followup_deliveries,
            }
            _append_sales_log(
                "sales_dispatch_complete",
                report_type=report_type,
                trigger=trigger,
                job_name=job_name,
                workflow_name=workflow_name,
                route_key=route_meta["route_key"],
                display_name=route_meta["display_name"],
                bot_username=route_meta["bot_username"],
                ok=not delivery_errors,
                sent_reports=[
                    report_type if deliveries["main"] else None,
                    *[str(item.get("report_type") or "") for item in followup_messages[: len(followup_deliveries)]],
                ],
                errors=delivery_errors,
                format_markers=main_markers["present"],
                missing_format_markers=main_markers["missing"],
                format_version=main_format["format_version"],
                formatter_module=main_format["formatter_module"],
                template_id=main_format["template_id"],
            )
            if delivery_errors:
                raise SalesAgentError("Ошибки доставки sales-отчетов: " + "; ".join(delivery_errors))
        return result


def build_sales_report_from_env(
    env: Mapping[str, str] | None = None,
    *,
    report_type: str = "sales",
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    env_data = _env_dict(env)
    if env_data.get("BITRIX_CRM_FIXTURES_FILE") and not env_data.get("SALES_LOG_FILE"):
        env_data["SALES_LOG_FILE"] = str(DEFAULT_FIXTURE_SALES_LOG_FILE)
    if date_from:
        env_data["SALES_REPORT_DATE_FROM"] = str(date_from)
    if date_to:
        env_data["SALES_REPORT_DATE_TO"] = str(date_to)
    return SalesAgent.from_env(env_data).run(report_type=report_type)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sales Copilot для Cloudbot")
    parser.add_argument("--report", choices=sorted(REPORT_TYPES), default="sales")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--chat-id", default="")
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    env_data = _env_dict()
    if args.date_from:
        env_data["SALES_REPORT_DATE_FROM"] = str(args.date_from)
    if args.date_to:
        env_data["SALES_REPORT_DATE_TO"] = str(args.date_to)
    agent = SalesAgent.from_env(env_data)

    try:
        result = agent.run(
            report_type=args.report,
            send=bool(args.send),
            chat_id=args.chat_id or None,
        )
    except SalesAgentError as error:
        print(f"Sales Copilot error: {error}", file=sys.stderr)
        _append_sales_log("sales_error", error=str(error), report_type=args.report)
        return 1
    except Exception as error:  # noqa: BLE001
        print(f"Critical sales error: {error}", file=sys.stderr)
        _append_sales_log("sales_error", error=str(error), report_type=args.report)
        return 1

    print(result["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
