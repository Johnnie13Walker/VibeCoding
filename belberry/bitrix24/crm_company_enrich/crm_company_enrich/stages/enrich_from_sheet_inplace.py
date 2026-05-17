"""In-place batch enrichment of Telemarketing-без-реквизитов style sheets.

Read source rows with hyperlinks (deal Bitrix URL in col A), run orchestrator
enrich_company_full per row, write source/result fields back to columns E-H and
technical results back to columns I-U of the SAME tab, colorize each row
green/red/yellow by final_status.

Resume-safe: rows with col K (status) already filled are skipped.
Kill-switch: stops at end of 00-08 MSK window if cron_mode=True, or after
max_duration_min.

Source/result writeback layout:
  E  Компания в сделке
  F  ИНН
  G  Оборот компании
  H  Причина / результат

Output column layout (col I=index 8, U=index 20):
  I  deal_id
  J  enriched_at
  K  status
  L  updated_fields
  M  company_id
  N  company_title
  O  company_inn
  P  company_revenue
  Q  deal_stage
  R  deal_assignee
  S  director_inn
  T  rejected_reason
  U  error
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..config import LOG_DIR, PORTAL_DOMAIN
from . import enrich_company_full
from .enrich_from_sheet import (
    BatchInput,
    determine_skip_bp,
    is_within_window,
    time_monotonic,
)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

DEAL_URL_RE = re.compile(r"/crm/deal/details/(\d+)/?", re.IGNORECASE)
DOMAIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+)(?:/[^\s)]*)?",
    re.IGNORECASE,
)

# Колонки col A=0 ... col U=20. Source writeback E-H, output блок I-U.
SOURCE_COL_START = 4   # E
SOURCE_COL_END = 7     # H inclusive
OUTPUT_COL_START = 8   # I
OUTPUT_COL_END = 20    # U inclusive
STATUS_COL_INDEX = 10  # K

# Цвета строк по final_status (RGB 0..1).
COLOR_SUCCESS = {"red": 0.851, "green": 0.918, "blue": 0.827}   # #d9ead3 light green
COLOR_FAILURE = {"red": 0.957, "green": 0.800, "blue": 0.800}   # #f4cccc light red
COLOR_NEUTRAL = {"red": 1.000, "green": 0.949, "blue": 0.800}   # #fff2cc light yellow
SUCCESS_STATUSES = {"ENRICHED", "REJECTED"}
FAILURE_STATUSES = {"PARTIAL", "FAILED", "SKIPPED", "EXCEPTION"}
INPLACE_HEADERS_H_U = [
    "Причина / результат",
    "deal_id",
    "enriched_at",
    "status",
    "updated_fields",
    "company_id",
    "company_title",
    "company_inn",
    "company_revenue",
    "deal_stage",
    "deal_assignee",
    "director_inn",
    "rejected_reason",
    "error",
]

STATE_PATH = LOG_DIR / "enrich_from_sheet_inplace_state.json"


@dataclass
class RowInput:
    row_number: int             # 1-based, includes header (so data starts at row 2)
    deal_id: str = ""
    url: str = ""
    company_title: str = ""
    existing_status: str = ""   # K (status) column current value
    raw_text: str = ""          # col A displayed text


def parse_deal_id_from_url(url: str) -> str:
    """Extract Bitrix deal_id from /crm/deal/details/<ID>/ URL."""
    if not url:
        return ""
    match = DEAL_URL_RE.search(url)
    return match.group(1) if match else ""


def normalize_url_value(raw: str) -> str:
    """Return scheme-stripped lower-case host[+path] for plain text URL columns."""
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text.removeprefix("https://").removeprefix("http://").rstrip("/")
    return text.lower()


def extract_business_url(raw: str) -> str:
    """Extract a company website URL from a displayed deal title/text value."""
    text = normalize_url_value(raw)
    if not text:
        return ""
    match = DOMAIN_RE.search(text)
    if not match:
        return ""
    domain = match.group(1).lower()
    if domain == PORTAL_DOMAIN.lower():
        return ""
    return "https://" + domain


def extract_row_inputs(grid_data: dict[str, Any]) -> list[RowInput]:
    """Parse grid data response into RowInput list.

    Expects grid_data shape: {"sheets":[{"data":[{"rowData":[{"values":[{"formattedValue":..,
    "hyperlink":..,"effectiveValue":..,"userEnteredFormat":..}, ...]}, ...]}]}]}

    Row 0 is header; we skip it. Each row's col A hyperlink → deal_id; if no
    hyperlink → URL fallback. Col E (index 4) → company_title. Col K (index 10) →
    existing status (for resume).
    """
    result: list[RowInput] = []
    sheets = grid_data.get("sheets") or []
    if not sheets:
        return result
    data_blocks = sheets[0].get("data") or []
    if not data_blocks:
        return result
    row_data = data_blocks[0].get("rowData") or []
    for offset, row in enumerate(row_data):
        if offset == 0:
            continue  # skip header
        values = row.get("values") or []
        if not values:
            continue
        row_number = offset + 1  # 1-based; header at row 1, data starts at 2
        cell_a = values[0] if len(values) > 0 else {}
        cell_e = values[4] if len(values) > 4 else {}
        cell_k = values[STATUS_COL_INDEX] if len(values) > STATUS_COL_INDEX else {}

        raw_text = str(cell_a.get("formattedValue") or "").strip()
        hyperlink = str(cell_a.get("hyperlink") or "").strip()
        deal_id = parse_deal_id_from_url(hyperlink)

        # Если hyperlink ведёт на Bitrix-сделку, всё равно вытаскиваем URL компании
        # из displayed text col A (например 'plastica-s.ru'). Иначе orchestrator
        # получит deal_id без URL и для сделок без COMPANY_ID создаст пустую
        # "Компания без названия" вместо обогащения по домену.
        url = extract_business_url(raw_text)
        if not url and hyperlink and not deal_id:
            url = extract_business_url(hyperlink)

        company_title = str(cell_e.get("formattedValue") or "").strip()
        existing_status = str(cell_k.get("formattedValue") or "").strip()

        if not raw_text and not deal_id and not url:
            continue  # truly empty row
        result.append(RowInput(
            row_number=row_number,
            deal_id=deal_id,
            url=url,
            company_title=company_title,
            existing_status=existing_status,
            raw_text=raw_text,
        ))
    return result


def filter_unprocessed(inputs: list[RowInput]) -> list[RowInput]:
    """Drop rows whose status (col K) is already filled."""
    return [inp for inp in inputs if not inp.existing_status]


def to_batch_input(row: RowInput) -> BatchInput:
    """Convert RowInput → existing BatchInput used by orchestrator wrapper."""
    return BatchInput(
        company_id="",
        inn="",
        url=row.url,
        source_row_ref=f"row:{row.row_number}",
    )


def outcome_to_cells(
    outcome: enrich_company_full.FullEnrichmentOutcome | None,
    *,
    bx: Any | None,
    error_summary: str = "",
) -> list[Any]:
    """Build 13 cell values for columns I..U from orchestrator outcome.

    Order MUST match column layout above (I..U inclusive = 13 columns).
    """
    now_iso = datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")
    if outcome is None:
        return [
            "",        # I deal_id
            now_iso,   # J enriched_at
            "EXCEPTION",  # K status
            "",        # L updated_fields
            "",        # M company_id
            "",        # N company_title
            "",        # O company_inn
            "",        # P company_revenue
            "",        # Q deal_stage
            "",        # R deal_assignee
            "",        # S director_inn
            "",        # T rejected_reason
            error_summary[:500],  # U error
        ]

    updated_fields = _updated_fields(outcome)
    deal_extra = _deal_extras(outcome, bx)
    director_inn = _director_inn(outcome)
    company_extra = _company_extras(outcome, bx)
    return [
        outcome.deal_id or "",
        now_iso,
        outcome.final_status or "UNKNOWN",
        updated_fields,
        outcome.company_id or "",
        company_extra.get("title", ""),
        company_extra.get("inn", ""),
        company_extra.get("revenue", ""),
        deal_extra.get("stage", ""),
        deal_extra.get("assignee", ""),
        director_inn,
        outcome.rejected_reason or "",
        _step_errors(outcome)[:500],
    ]


def source_cells_from_outcome(
    outcome: enrich_company_full.FullEnrichmentOutcome | None,
    *,
    bx: Any | None,
    error_summary: str = "",
) -> list[Any]:
    """Build 4 visible sheet values for columns E..H from CRM/enrichment result."""
    if outcome is None:
        return ["", "", "", _visible_result("EXCEPTION", "", error_summary)]

    company_extra = _company_extras(outcome, bx)
    return [
        company_extra.get("title", ""),
        company_extra.get("inn", ""),
        company_extra.get("revenue", ""),
        _visible_result(outcome.final_status or "UNKNOWN", outcome.rejected_reason or "", _step_errors(outcome)),
    ]


def row_writeback_cells(
    outcome: enrich_company_full.FullEnrichmentOutcome | None,
    *,
    bx: Any | None,
    error_summary: str = "",
) -> list[Any]:
    """Build full row writeback values for columns E..U."""
    return source_cells_from_outcome(outcome, bx=bx, error_summary=error_summary) + outcome_to_cells(
        outcome,
        bx=bx,
        error_summary=error_summary,
    )


def color_for_status(status: str) -> dict[str, float]:
    """Map orchestrator final_status to RGB row color."""
    upper = (status or "").upper()
    if upper in SUCCESS_STATUSES:
        return COLOR_SUCCESS
    if upper in FAILURE_STATUSES:
        return COLOR_FAILURE
    return COLOR_NEUTRAL


def is_successful_for_removal(status: str) -> bool:
    """Whether row can be removed from the source worklist after live writeback."""
    return (status or "").upper() in SUCCESS_STATUSES


def build_color_request(sheet_gid: int, row_number: int, color: dict[str, float]) -> dict[str, Any]:
    """Build a repeatCell request that paints background of cols A..U on this row."""
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_gid,
                "startRowIndex": row_number - 1,  # 0-based exclusive
                "endRowIndex": row_number,
                "startColumnIndex": 0,
                "endColumnIndex": OUTPUT_COL_END + 1,
            },
            "cell": {"userEnteredFormat": {"backgroundColor": color}},
            "fields": "userEnteredFormat.backgroundColor",
        }
    }


def fetch_grid_data(service, sheet_id: str, tab_title: str) -> dict[str, Any]:
    """Read full tab with hyperlinks via spreadsheets.get(includeGridData=True)."""
    return service.spreadsheets().get(
        spreadsheetId=sheet_id,
        ranges=[f"'{tab_title}'!A1:U10000"],
        includeGridData=True,
        fields="sheets(properties(sheetId,title),data(rowData(values(formattedValue,hyperlink,userEnteredFormat))))",
    ).execute()


def sheet_gid_from_grid(grid_data: dict[str, Any]) -> int | None:
    sheets = grid_data.get("sheets") or []
    if not sheets:
        return None
    return sheets[0].get("properties", {}).get("sheetId")


def write_row_updates_and_color(
    service,
    sheet_id: str,
    tab_title: str,
    sheet_gid: int,
    row_number: int,
    cells: list[Any],
    color: dict[str, float],
) -> None:
    """Write cells to E..U of given row + apply background color in one API call."""
    output_range = f"'{tab_title}'!E{row_number}:U{row_number}"
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=output_range,
        valueInputOption="RAW",
        body={"values": [cells]},
    ).execute()

    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [build_color_request(sheet_gid, row_number, color)]},
    ).execute()


def ensure_inplace_headers(service, sheet_id: str, tab_title: str) -> None:
    """Keep H..U headers aligned with E..U writeback layout."""
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_title}'!H1:U1",
        valueInputOption="RAW",
        body={"values": [INPLACE_HEADERS_H_U]},
    ).execute()


def delete_rows_desc(service, sheet_id: str, sheet_gid: int, row_numbers: list[int]) -> None:
    """Delete rows by 1-based numbers, descending to keep indexes stable."""
    requests: list[dict[str, Any]] = []
    for row_number in sorted(set(row_numbers), reverse=True):
        requests.append({
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_gid,
                    "dimension": "ROWS",
                    "startIndex": row_number - 1,
                    "endIndex": row_number,
                }
            }
        })
    if not requests:
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": requests},
    ).execute()


def run_in_place(
    bx,
    service,
    *,
    sheet_id: str,
    tab_title: str,
    dry_run: bool = True,
    skip_bp: bool | None = None,
    full_bp: bool = False,
    max_duration_min: int = 480,
    limit: int | None = None,
    cron_mode: bool = False,
    skip_already_processed: bool = True,
    delete_successful: bool = False,
) -> dict[str, Any]:
    """Main entry. Reads tab, processes unprocessed rows, writes back per-row.

    `service` is a googleapiclient discovery client for Sheets v4.
    `bx` is a BitrixClient.
    """
    start_ts = datetime.now(MOSCOW_TZ)
    started_monotonic = time_monotonic()

    grid_data = fetch_grid_data(service, sheet_id, tab_title)
    sheet_gid = sheet_gid_from_grid(grid_data)
    if sheet_gid is None:
        raise RuntimeError(f"sheet gid not found for tab {tab_title!r}")

    all_inputs = extract_row_inputs(grid_data)
    inputs = filter_unprocessed(all_inputs) if skip_already_processed else all_inputs
    if limit is not None:
        inputs = inputs[:limit]

    summary: dict[str, Any] = {
        "started_at_msk": start_ts.isoformat(timespec="seconds"),
        "sheet_id": sheet_id,
        "tab": tab_title,
        "sheet_gid": sheet_gid,
        "dry_run": dry_run,
        "delete_successful": delete_successful,
        "total_rows_in_tab": len(all_inputs),
        "already_processed_skipped": len(all_inputs) - len(inputs) if skip_already_processed else 0,
        "to_process": len(inputs),
        "processed": 0,
        "failed": 0,
        "successful_rows_deleted": 0,
        "stopped_by_window": 0,
        "stopped_by_duration": 0,
        "status_counts": {},
    }

    if cron_mode and not is_within_window(start_ts):
        summary["stopped_by_window"] = 1
        summary["duration_s"] = 0
        _write_state(summary, next_index=0)
        return summary

    if not dry_run:
        ensure_inplace_headers(service, sheet_id, tab_title)

    status_counts: Counter[str] = Counter()
    rows_to_delete: list[int] = []
    for idx, row in enumerate(inputs):
        now = datetime.now(MOSCOW_TZ)
        if cron_mode and not is_within_window(now):
            summary["stopped_by_window"] = 1
            break
        if max_duration_min is not None and now >= start_ts + timedelta(minutes=max_duration_min):
            summary["stopped_by_duration"] = 1
            break

        effective_skip_bp = determine_skip_bp(now, skip_bp, full_bp)

        outcome: enrich_company_full.FullEnrichmentOutcome | None = None
        error_summary = ""
        try:
            outcome = enrich_company_full.run(
                bx,
                deal_id=row.deal_id,
                url=row.url,
                dry_run=dry_run,
                skip_bp=effective_skip_bp,
                create_if_missing=True,
            )
            status = outcome.final_status or "UNKNOWN"
        except Exception as exc:  # noqa: BLE001
            error_summary = str(exc)[:500]
            status = "EXCEPTION"

        status_counts[status] += 1
        if status in {"FAILED", "EXCEPTION"}:
            summary["failed"] += 1

        # CRITICAL: writeback в Sheet делаем ТОЛЬКО при --live. dry-run должен
        # быть полностью read-only (как orchestrator). Иначе dry-run "проверка"
        # засирает таб мусором (DRY_RUN_COMPANY marker, недо-резолвленные
        # outcome'ы), который ловится потом filter_unprocessed и блокирует
        # повторные прогоны.
        if not dry_run:
            cells = row_writeback_cells(outcome, bx=bx, error_summary=error_summary)
            color = color_for_status(status)
            try:
                write_row_updates_and_color(service, sheet_id, tab_title, sheet_gid, row.row_number, cells, color)
                if delete_successful and is_successful_for_removal(status):
                    rows_to_delete.append(row.row_number)
            except Exception as exc:  # noqa: BLE001
                # Sheet write failed — record but continue. Row may need manual fix.
                summary.setdefault("sheet_write_errors", []).append({
                    "row": row.row_number, "error": str(exc)[:300]
                })

        summary["processed"] += 1
        _write_state(summary, next_index=idx + 1)

    summary["status_counts"] = dict(status_counts)
    if not dry_run and delete_successful and rows_to_delete:
        try:
            delete_rows_desc(service, sheet_id, sheet_gid, rows_to_delete)
            summary["successful_rows_deleted"] = len(set(rows_to_delete))
        except Exception as exc:  # noqa: BLE001
            summary["delete_successful_error"] = str(exc)[:500]
    summary["duration_s"] = round(time_monotonic() - started_monotonic, 3)
    _write_state(summary, next_index=summary["processed"])
    return summary


def _updated_fields(outcome: enrich_company_full.FullEnrichmentOutcome) -> str:
    parts: list[str] = []
    for step in outcome.steps:
        if step.status != "DONE":
            continue
        details = step.details if isinstance(step.details, dict) else {}
        if step.step in {"APPLY_INN", "FIND_SITE", "SYNC_COMPANY", "ADDRESS_SYNC", "SYNC_DEAL"} and details:
            parts.append(step.step)
    return ",".join(parts)


def _deal_extras(outcome: enrich_company_full.FullEnrichmentOutcome, bx: Any | None) -> dict[str, str]:
    if not outcome.deal_id or not bx or outcome.deal_id == "DRY_RUN_DEAL":
        return {}
    try:
        deal = bx.get_deal(outcome.deal_id) or {}
    except Exception:  # noqa: BLE001
        return {}
    return {
        "stage": str(deal.get("STAGE_ID") or ""),
        "assignee": str(deal.get("ASSIGNED_BY_ID") or ""),
    }


def _company_extras(outcome: enrich_company_full.FullEnrichmentOutcome, bx: Any | None) -> dict[str, str]:
    if not outcome.company_id or not bx:
        return {}
    try:
        company = bx.get_company(outcome.company_id) or {}
    except Exception:  # noqa: BLE001
        return {}
    inn = ""
    try:
        reqs = bx.list_company_requisites(outcome.company_id) or []
        inn = next((str(r.get("RQ_INN") or "").strip() for r in reqs if r.get("RQ_INN")), "")
    except Exception:  # noqa: BLE001
        pass
    revenue = str(company.get("UF_CRM_1737098549301") or "")
    return {
        "title": str(company.get("TITLE") or ""),
        "inn": inn,
        "revenue": revenue,
    }


def _director_inn(outcome: enrich_company_full.FullEnrichmentOutcome) -> str:
    for step in outcome.steps:
        if step.step != "ENRICH_DIRECTOR_INN":
            continue
        details = step.details if isinstance(step.details, dict) else {}
        summary = details.get("summary") if isinstance(details, dict) else None
        if not isinstance(summary, dict):
            continue
        for o in summary.get("outcomes") or []:
            inn = str(o.get("director_inn") or "")
            if inn:
                return inn
    return ""


def _step_errors(outcome: enrich_company_full.FullEnrichmentOutcome) -> str:
    errors = [step.error for step in outcome.steps if step.error]
    return "; ".join(errors)


def _visible_result(status: str, rejected_reason: str, error_summary: str) -> str:
    upper = (status or "UNKNOWN").upper()
    if upper in {"ENRICHED", "PARTIAL"}:
        return "OK: компания и сделка обогащены"
    if upper == "SKIPPED":
        reason = rejected_reason or error_summary
        if "no_inn_no_company" in reason:
            return "SKIPPED: ИНН не найден, компания не создана"
        return f"SKIPPED: {reason}" if reason else "SKIPPED"
    if upper == "REJECTED":
        return f"REJECTED: {rejected_reason}" if rejected_reason else "REJECTED"
    if upper == "FAILED":
        detail = rejected_reason or error_summary
        return f"FAILED: {detail}" if detail else "FAILED"
    if upper == "EXCEPTION":
        return f"EXCEPTION: {error_summary}" if error_summary else "EXCEPTION"
    detail = rejected_reason or error_summary
    return f"{upper}: {detail}" if detail else upper


def _write_state(summary: dict[str, Any], *, next_index: int) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **summary,
        "next_index": next_index,
        "updated_at_msk": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
    }
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
