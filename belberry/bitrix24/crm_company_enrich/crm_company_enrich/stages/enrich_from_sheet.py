"""Batch-wrapper над orchestrator enrich_company_full."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from ..config import LOG_DIR, PORTAL_DOMAIN
from ..models import normalize_inn
from . import enrich_company_full

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
TECH_LEAD_EMAIL = "eshchemelev@gmail.com"
OUTPUT_HEADERS = [
    "timestamp_msk",
    "company_id",
    "title",
    "final_status",
    "deal_id",
    "flags",
    "duplicate_company_ids",
    "bitrix_company_link",
    "bitrix_deal_link",
    "error_summary",
    "dry_run",
]
STATE_PATH = LOG_DIR / "enrich_from_sheet_state.json"


@dataclass
class BatchInput:
    company_id: str = ""
    inn: str = ""
    url: str = ""
    source_row_ref: str = ""


@dataclass
class BatchOutcome:
    outcome: enrich_company_full.FullEnrichmentOutcome | None
    source_row_ref: str
    dry_run: bool
    error_summary: str = ""


def load_inputs_from_sheet(sheets, sheet_id: str, tab: str, id_column: str) -> list[BatchInput]:
    """Загрузить входы из указанной колонки Google Sheets."""
    rows = _with_sheet_id(sheets, sheet_id, lambda: sheets.read(tab, "A1:ZZ10000"))
    if not rows:
        return []
    headers = [str(value).strip() for value in rows[0]]
    try:
        col_idx = headers.index(id_column)
    except ValueError as exc:
        raise ValueError(f"Колонка не найдена: {id_column}") from exc

    inputs: list[BatchInput] = []
    for row_idx, row in enumerate(rows[1:], start=2):
        value = str(row[col_idx]).strip() if col_idx < len(row) else ""
        parsed = _parse_input_value(value, f"sheet:{sheet_id}:{tab}:{row_idx}")
        if parsed:
            inputs.append(parsed)
    return inputs


def load_inputs_from_bitrix_filter(bx, filter_json: str | dict) -> list[BatchInput]:
    """Загрузить компании через crm.company.list filter."""
    filter_ = json.loads(filter_json) if isinstance(filter_json, str) else dict(filter_json or {})
    companies = bx.list_companies(select=["ID", "TITLE", "WEB", "UF_*"], filter_=filter_)
    inputs: list[BatchInput] = []
    for idx, company in enumerate(companies, start=1):
        company_id = str(company.get("ID") or "").strip()
        if company_id:
            inputs.append(BatchInput(company_id=company_id, source_row_ref=f"filter:{idx}"))
    return inputs


def load_inputs_from_file(path: str | Path) -> list[BatchInput]:
    """Загрузить company_id/inn/url из простого текстового файла."""
    source = Path(path)
    inputs: list[BatchInput] = []
    with source.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            value = line.strip()
            parsed = _parse_input_value(value, f"file:{source}:{line_no}")
            if parsed:
                inputs.append(parsed)
    return inputs


def deduplicate_inputs(inputs: list[BatchInput]) -> list[BatchInput]:
    """Dedup по приоритету company_id -> inn -> url, сохраняя первый source_row_ref."""
    seen: set[tuple[str, str]] = set()
    result: list[BatchInput] = []
    for inp in inputs:
        key = _dedup_key(inp)
        if key is None or key in seen:
            continue
        seen.add(key)
        result.append(inp)
    return result


def is_within_window(now_msk: datetime) -> bool:
    local = _to_msk(now_msk)
    return 0 <= local.hour < 8


def determine_skip_bp(
    now_msk: datetime,
    explicit_skip: bool | None,
    explicit_full: bool,
) -> bool:
    """В окне 00:00-08:00 МСК BP включён, вне окна BP пропускается."""
    if explicit_skip:
        return True
    if explicit_full:
        return False
    return not is_within_window(now_msk)


def should_stop(
    start_ts: datetime,
    max_duration_min: int | None,
    *,
    now_msk: datetime | None = None,
    cron_mode: bool = False,
) -> bool:
    now = _to_msk(now_msk or datetime.now(MOSCOW_TZ))
    start = _to_msk(start_ts)
    if max_duration_min is not None and now >= start + timedelta(minutes=max_duration_min):
        return True
    return bool(cron_mode and not is_within_window(now))


def append_output_row(sheets, sheet_id: str, tab: str, outcome: BatchOutcome) -> None:
    """Append одной строки результата в output Sheet."""
    _ensure_output_tab(sheets, sheet_id, tab)
    row = _outcome_to_row(outcome)
    _with_sheet_id(sheets, sheet_id, lambda: sheets.append(tab, [row]))


def run(
    bx,
    sheets,
    *,
    inputs: list[BatchInput],
    output_sheet_id: str,
    output_tab: str,
    dry_run: bool = True,
    skip_bp: bool | None = None,
    full_bp: bool = False,
    max_duration_min: int = 480,
    limit: int | None = None,
    cron_mode: bool = False,
    skip_cross_category_dup_check: bool = False,
    skip_on_closed_dup: bool = False,
) -> dict:
    """Главный batch-runner. Возвращает summary с counters."""
    start_ts = datetime.now(MOSCOW_TZ)
    started_monotonic = time_monotonic()
    output_sheet_id = _prepare_output_sheet(sheets, output_sheet_id)
    _ensure_output_tab(sheets, output_sheet_id, output_tab)

    summary: dict[str, Any] = {
        "started_at_msk": start_ts.isoformat(timespec="seconds"),
        "output_sheet_id": output_sheet_id,
        "output_tab": output_tab,
        "dry_run": dry_run,
        "processed": 0,
        "failed": 0,
        "stopped_by_window": 0,
        "stopped_by_duration": 0,
        "status_counts": {},
    }

    if cron_mode and not is_within_window(start_ts):
        summary["stopped_by_window"] = 1
        summary["duration_s"] = 0
        _write_state(summary, next_index=0)
        return summary

    status_counts: Counter[str] = Counter()
    selected = inputs[:limit] if limit is not None else inputs
    for idx, inp in enumerate(selected):
        now = datetime.now(MOSCOW_TZ)
        if cron_mode and not is_within_window(now):
            summary["stopped_by_window"] = 1
            break
        if max_duration_min is not None and now >= start_ts + timedelta(minutes=max_duration_min):
            summary["stopped_by_duration"] = 1
            break

        effective_skip_bp = determine_skip_bp(now, skip_bp, full_bp)
        try:
            full = enrich_company_full.run(
                bx,
                company_id=inp.company_id,
                inn=inp.inn,
                url=inp.url,
                dry_run=dry_run,
                skip_bp=effective_skip_bp,
                skip_cross_category_dup_check=skip_cross_category_dup_check,
                skip_on_closed_dup=skip_on_closed_dup,
            )
            batch_outcome = BatchOutcome(full, inp.source_row_ref, dry_run)
            status = full.final_status or "UNKNOWN"
        except Exception as exc:  # noqa: BLE001
            batch_outcome = BatchOutcome(None, inp.source_row_ref, dry_run, str(exc)[:500])
            status = "EXCEPTION"

        status_counts[status] += 1
        if status in {"FAILED", "EXCEPTION"}:
            summary["failed"] += 1
        append_output_row(sheets, output_sheet_id, output_tab, batch_outcome)
        summary["processed"] += 1
        _write_state(summary, next_index=idx + 1)

    summary["status_counts"] = dict(status_counts)
    summary["duration_s"] = round(time_monotonic() - started_monotonic, 3)
    _write_state(summary, next_index=summary["processed"])
    return summary


def _parse_input_value(value: str, source_row_ref: str) -> BatchInput | None:
    clean = value.strip()
    if not clean:
        return None
    if clean.startswith(("http://", "https://")) or "." in clean and not clean.isdigit():
        return BatchInput(url=clean, source_row_ref=source_row_ref)
    inn = normalize_inn(clean)
    if inn and len(inn) in {10, 12}:
        return BatchInput(inn=inn, source_row_ref=source_row_ref)
    return BatchInput(company_id=clean, source_row_ref=source_row_ref)


def _dedup_key(inp: BatchInput) -> tuple[str, str] | None:
    if inp.company_id:
        return ("company_id", str(inp.company_id).strip())
    if inp.inn:
        return ("inn", normalize_inn(inp.inn) or str(inp.inn).strip())
    if inp.url:
        return ("url", _normalize_url(inp.url))
    return None


def _normalize_url(url: str) -> str:
    return str(url or "").strip().lower().removeprefix("https://").removeprefix("http://").rstrip("/")


def _prepare_output_sheet(sheets, output_sheet_id: str) -> str:
    if output_sheet_id != "auto":
        return output_sheet_id
    if hasattr(sheets, "create_spreadsheet"):
        return str(sheets.create_spreadsheet(_auto_title(), share_with=TECH_LEAD_EMAIL))
    spreadsheet = sheets.service.spreadsheets().create(
        body={"properties": {"title": _auto_title()}},
        fields="spreadsheetId",
    ).execute()
    new_sheet_id = str(spreadsheet["spreadsheetId"])
    _share_spreadsheet_if_possible(sheets, new_sheet_id, TECH_LEAD_EMAIL)
    return new_sheet_id


def _auto_title() -> str:
    return f"enrich_results_{datetime.now(MOSCOW_TZ).date().isoformat()}"


def _share_spreadsheet_if_possible(sheets, sheet_id: str, email: str) -> None:
    service_account_path = getattr(sheets, "service_account_path", None)
    if not service_account_path:
        return
    credentials = Credentials.from_service_account_file(
        str(service_account_path),
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    drive = build("drive", "v3", credentials=credentials)
    drive.permissions().create(
        fileId=sheet_id,
        body={"type": "user", "role": "writer", "emailAddress": email},
        sendNotificationEmail=False,
    ).execute()


def _ensure_output_tab(sheets, sheet_id: str, tab: str) -> None:
    def ensure() -> None:
        if hasattr(sheets, "ensure_sheet"):
            sheets.ensure_sheet(tab)
        rows = sheets.read(tab, "A1:K1")
        if not rows:
            sheets.update(tab, "A1:K1", [OUTPUT_HEADERS])

    _with_sheet_id(sheets, sheet_id, ensure)


def _outcome_to_row(batch: BatchOutcome) -> list[Any]:
    now = datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")
    if batch.outcome is None:
        return [now, "", "", "EXCEPTION", "", "", "", "", "", batch.error_summary, batch.dry_run]
    outcome = batch.outcome
    title = _title_from_outcome(outcome)
    return [
        now,
        outcome.company_id,
        title,
        outcome.final_status,
        outcome.deal_id,
        ",".join(outcome.flags),
        ",".join(outcome.duplicate_company_ids),
        outcome.bitrix_links.get("company") or _company_link(outcome.company_id),
        outcome.bitrix_links.get("deal") or _deal_link(outcome.deal_id),
        _error_summary(outcome),
        batch.dry_run,
    ]


def _title_from_outcome(outcome: enrich_company_full.FullEnrichmentOutcome) -> str:
    for step in outcome.steps:
        title = step.details.get("title") if isinstance(step.details, dict) else None
        if title:
            return str(title)
    return ""


def _error_summary(outcome: enrich_company_full.FullEnrichmentOutcome) -> str:
    if outcome.rejected_reason:
        return outcome.rejected_reason
    errors = [step.error for step in outcome.steps if step.error]
    return "; ".join(errors)[:500]


def _company_link(company_id: str) -> str:
    return f"https://{PORTAL_DOMAIN}/crm/company/details/{company_id}/" if company_id else ""


def _deal_link(deal_id: str) -> str:
    return f"https://{PORTAL_DOMAIN}/crm/deal/details/{deal_id}/" if deal_id else ""


def _write_state(summary: dict[str, Any], *, next_index: int) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {**summary, "next_index": next_index, "updated_at_msk": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")}
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _with_sheet_id(sheets, sheet_id: str, func):
    if not hasattr(sheets, "sheet_id"):
        return func()
    original = sheets.sheet_id
    sheets.sheet_id = sheet_id
    try:
        return func()
    finally:
        sheets.sheet_id = original


def _to_msk(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=MOSCOW_TZ)
    return value.astimezone(MOSCOW_TZ)


def time_monotonic() -> float:
    import time

    return time.monotonic()
