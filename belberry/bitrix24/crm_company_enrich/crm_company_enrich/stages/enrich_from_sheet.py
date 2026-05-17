"""Batch-обогащение сделок из Google Sheets."""
from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import (
    CCE_BIZPROC_UPDATE_ID,
    DEAL_UF_INN,
    DEAL_UF_REVENUE_NUMBER,
    DEAL_UF_REVENUE_TEXT,
    LOG_DIR,
    TM_NO_REQUISITES_SHEET_ID,
    TM_NO_REQUISITES_TAB_GID,
    TM_SHEET_RESULT_HEADERS,
)
from ..sheets_client import SheetsClient

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
PROGRESS_PATH = LOG_DIR / "enrich_from_sheet_progress.json"
AUDIT_PATH = LOG_DIR / "enrich_from_sheet.csv"
AUDIT_HEADERS = [
    "timestamp",
    "deal_id",
    "company_id",
    "status",
    "updated_fields_count",
    "director_inn_set",
    "auto_rejected",
    "error",
]


@dataclass
class EnrichmentOutcome:
    row_number: int
    deal_id: str
    company_id: str = ""
    status: str = ""
    updated_fields: dict = field(default_factory=dict)
    company_title: str = ""
    company_inn: str = ""
    company_revenue: str = ""
    deal_stage: str = ""
    deal_assignee: str = ""
    director_inn: str = ""
    rejected_reason: str = ""
    error: str = ""
    enriched_at: str = ""


def run(
    bx: BitrixClient,
    sheets: SheetsClient,
    *,
    sheet_id: str | None = None,
    tab_gid: int | None = None,
    dry_run: bool = True,
    limit: int | None = None,
    skip_already_enriched: bool = True,
    enable_auto_reject: bool = True,
    enable_dedupe_contacts: bool = True,
    enable_enrich_director_inn: bool = True,
    trigger_bp: bool = True,
    resume: bool = False,
) -> dict:
    if sheet_id and sheet_id != getattr(sheets, "sheet_id", None):
        sheets = SheetsClient(sheet_id=sheet_id, service_account_path=sheets.service_account_path)

    tab_title = sheets.get_sheet_title_by_id(tab_gid or TM_NO_REQUISITES_TAB_GID)
    if not tab_title:
        raise ValueError(f"Не найдена вкладка gid={tab_gid or TM_NO_REQUISITES_TAB_GID}")

    rows = sheets.read(tab_title, "A1:Z")
    if not rows:
        return _summary([], dry_run=dry_run, skipped=0, tab_title=tab_title)

    header = list(rows[0])
    header, added_columns = _ensure_result_columns(sheets, tab_title, header, dry_run=dry_run)
    deal_id_col = _find_column(header, ("deal_id", "id сделки", "сделка"))
    status_col = _find_column(header, ("status", "статус"))
    enriched_at_col = _find_column(header, ("enriched_at", "обновлено"))
    links = _read_links(sheets, tab_title, len(rows))
    start_row = _resume_start_row(resume)

    outcomes: list[EnrichmentOutcome] = []
    skipped = 0
    for row_number, row in enumerate(rows[1:], start=2):
        if row_number < start_row:
            skipped += 1
            continue
        deal_id = _extract_deal_id(row, deal_id_col, links, row_number)
        if not deal_id:
            skipped += 1
            continue
        if skip_already_enriched and _is_recently_enriched(row, status_col, enriched_at_col):
            skipped += 1
            continue
        if limit and len(outcomes) >= limit:
            break

        _write_checkpoint(row_number=row_number - 1, deals_done=[o.deal_id for o in outcomes])
        outcome = _process_deal(
            bx=bx,
            deal_id=deal_id,
            row_number=row_number,
            dry_run=dry_run,
            enable_auto_reject=enable_auto_reject,
            enable_dedupe_contacts=enable_dedupe_contacts,
            enable_enrich_director_inn=enable_enrich_director_inn,
            trigger_bp=trigger_bp,
        )
        outcomes.append(outcome)
        _append_audit_row(outcome)
        _write_checkpoint(row_number=row_number, deals_done=[o.deal_id for o in outcomes])

        if not dry_run:
            _update_sheet_row(sheets, tab_title, row_number, row, outcome, header)

    summary = _summary(outcomes, dry_run=dry_run, skipped=skipped, tab_title=tab_title)
    summary["added_columns"] = added_columns
    summary["sheet_id"] = sheet_id or TM_NO_REQUISITES_SHEET_ID
    return summary


def _process_deal(
    bx: BitrixClient,
    deal_id: str,
    row_number: int,
    **flags: Any,
) -> EnrichmentOutcome:
    dry_run = bool(flags["dry_run"])
    enriched_at = _now_iso()
    deal = bx.get_deal(str(deal_id))
    if not deal:
        return EnrichmentOutcome(row_number, str(deal_id), status="NO_DEAL", error="deal not found", enriched_at=enriched_at)

    company_id = str(deal.get("COMPANY_ID") or "")
    if not company_id or company_id == "0":
        return EnrichmentOutcome(row_number, str(deal_id), company_id=company_id, status="SKIPPED", error="deal has no company", enriched_at=enriched_at)

    updated_fields: dict[str, Any] = {}
    rejected_reason = ""
    error = ""
    status = "ENRICHED"

    try:
        from . import sync_deals

        sync_summary = sync_deals.run(
            bx,
            deal_id=str(deal_id),
            dry_run=dry_run,
            overwrite=False,
            active_only=False,
            dedupe_contacts=False,
            auto_reject_telemarketing=False,
        )
        updated_fields.update(_fields_from_sync_summary(sync_summary))
        if sync_summary.get("failed"):
            raise RuntimeError(_first_error(sync_summary) or "sync_deals failed")

        company = bx.get_company(company_id) or {}
        company_inn = _clean(company.get("UF_CRM_1735331882180"))
        if flags.get("trigger_bp") and company_inn and CCE_BIZPROC_UPDATE_ID:
            updated_fields["bizproc_update"] = str(CCE_BIZPROC_UPDATE_ID)
            if not dry_run:
                bx.start_workflow(int(CCE_BIZPROC_UPDATE_ID), ["crm", "CCrmDocumentCompany", f"COMPANY_{company_id}"])
                time.sleep(3)

        if flags.get("enable_dedupe_contacts"):
            from . import dedupe_contacts

            dedupe_summary = dedupe_contacts.run_company(bx, company_id=company_id, dry_run=dry_run)
            if _summary_changed(dedupe_summary):
                updated_fields["dedupe_contacts"] = _compact_summary(dedupe_summary)

        director_inn = ""
        if flags.get("enable_enrich_director_inn"):
            director_inn = _run_director_inn_if_available(bx, company_id=company_id, dry_run=dry_run)
            if director_inn:
                updated_fields["director_inn"] = director_inn

        if flags.get("enable_auto_reject"):
            from . import auto_reject_telemarketing

            reject_summary = auto_reject_telemarketing.run_deal(bx, deal_id=str(deal_id), dry_run=dry_run)
            reject_outcome = _first_outcome(reject_summary)
            if reject_outcome.get("status") in {"REJECTED", "DRY_RUN"} and reject_outcome.get("reason_id"):
                status = "REJECTED"
                rejected_reason = str(reject_outcome.get("reason_desc") or reject_outcome.get("reason_id") or "")
                updated_fields["auto_reject"] = reject_outcome.get("reason_id")
            elif reject_summary.get("failed"):
                raise RuntimeError(_first_error(reject_summary) or "auto_reject failed")

        if not updated_fields and status != "REJECTED":
            status = "SKIPPED"
    except Exception as exc:  # noqa: BLE001
        status = "FAILED"
        error = str(exc)[:500]
        director_inn = ""

    final_deal = bx.get_deal(str(deal_id)) or deal
    final_company = bx.get_company(company_id) or {}
    return EnrichmentOutcome(
        row_number=row_number,
        deal_id=str(deal_id),
        company_id=company_id,
        status=status,
        updated_fields=updated_fields,
        company_title=_clean(final_company.get("TITLE")),
        company_inn=_clean(final_company.get("UF_CRM_1735331882180") or final_deal.get(DEAL_UF_INN)),
        company_revenue=_clean(final_company.get("UF_CRM_1737098549301") or final_company.get("UF_CRM_1584876707") or final_deal.get(DEAL_UF_REVENUE_NUMBER) or final_deal.get(DEAL_UF_REVENUE_TEXT)),
        deal_stage=_clean(final_deal.get("STAGE_ID")),
        deal_assignee=_clean(final_deal.get("ASSIGNED_BY_ID")),
        director_inn=director_inn,
        rejected_reason=rejected_reason,
        error=error,
        enriched_at=enriched_at,
    )


def _update_sheet_row(
    sheets: SheetsClient,
    tab: str,
    row_num: int,
    existing_row: list[Any],
    outcome: EnrichmentOutcome,
    header: list[str],
) -> None:
    values = _build_row_values_for_outcome(existing_row, outcome, header)
    end_col = _column_letter(len(header))
    sheets.update(tab, f"A{row_num}:{end_col}{row_num}", [values])


def _build_row_values_for_outcome(existing_row: list[Any], outcome: EnrichmentOutcome, header: list[str]) -> list[Any]:
    row = list(existing_row) + [""] * (len(header) - len(existing_row))
    data = {
        "deal_id": outcome.deal_id,
        "enriched_at": outcome.enriched_at,
        "status": outcome.status,
        "updated_fields": json.dumps(outcome.updated_fields, ensure_ascii=False, sort_keys=True),
        "company_id": outcome.company_id,
        "company_title": outcome.company_title,
        "company_inn": outcome.company_inn,
        "company_revenue": outcome.company_revenue,
        "deal_stage": outcome.deal_stage,
        "deal_assignee": outcome.deal_assignee,
        "director_inn": outcome.director_inn,
        "rejected_reason": outcome.rejected_reason,
        "error": outcome.error,
    }
    normalized = [_norm_header(h) for h in header]
    for key, value in data.items():
        if key in normalized:
            row[normalized.index(key)] = value
    return row[:len(header)]


def _ensure_result_columns(
    sheets: SheetsClient,
    tab_title: str,
    header: list[str],
    *,
    dry_run: bool,
) -> tuple[list[str], list[str]]:
    normalized = {_norm_header(h) for h in header}
    missing = [h for h in TM_SHEET_RESULT_HEADERS if _norm_header(h) not in normalized]
    if not missing:
        return header, []
    updated = header + missing
    if not dry_run:
        sheets.update(tab_title, f"A1:{_column_letter(len(updated))}1", [updated])
    return updated, missing


def _read_links(sheets: SheetsClient, tab_title: str, row_count: int) -> list[list[str]]:
    if not hasattr(sheets, "read_cell_hyperlinks"):
        return []
    try:
        return sheets.read_cell_hyperlinks(tab_title, f"A1:A{row_count}")
    except Exception:  # noqa: BLE001
        return []


def _extract_deal_id(row: list[Any], deal_id_col: int, links: list[list[str]], row_number: int) -> str:
    raw = _row_value(row, deal_id_col)
    if raw.isdigit():
        return raw
    if row_number - 1 < len(links):
        link = _row_value(links[row_number - 1], 0)
        parsed = _deal_id_from_text(link)
        if parsed:
            return parsed
    return _deal_id_from_text(raw)


def _deal_id_from_text(value: str) -> str:
    match = re.search(r"/crm/deal/details/(\d+)/?", str(value or ""))
    if match:
        return match.group(1)
    match = re.search(r"\bdeal[_\s-]*id[:=\s]+(\d+)\b", str(value or ""), flags=re.I)
    return match.group(1) if match else ""


def _find_column(header: list[str], variants: tuple[str, ...]) -> int:
    normalized = [_norm_header(h) for h in header]
    for variant in variants:
        needle = _norm_header(variant)
        for idx, value in enumerate(normalized):
            if needle == value or needle in value:
                return idx
    return 0


def _row_value(row: list[Any], idx: int) -> str:
    if idx < 0 or idx >= len(row):
        return ""
    return _clean(row[idx])


def _is_recently_enriched(row: list[Any], status_col: int, enriched_at_col: int) -> bool:
    if _row_value(row, status_col).upper() != "ENRICHED":
        return False
    raw = _row_value(row, enriched_at_col)
    if not raw:
        return False
    try:
        value = datetime.fromisoformat(raw)
        if value.tzinfo is None:
            value = value.replace(tzinfo=MOSCOW_TZ)
    except ValueError:
        return False
    return value >= datetime.now(MOSCOW_TZ) - timedelta(days=30)


def _fields_from_sync_summary(summary: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in summary.get("outcomes") or []:
        if not isinstance(item, dict):
            continue
        for group in ("fields", "company_fields", "contact_communications"):
            value = item.get(group)
            if value:
                out[group] = value
        if item.get("contacts_added"):
            out["contacts_added"] = item["contacts_added"]
    return out


def _run_director_inn_if_available(bx: BitrixClient, *, company_id: str, dry_run: bool) -> str:
    try:
        from . import enrich_director_inn  # type: ignore
    except ImportError:
        return ""
    summary = enrich_director_inn.run_company(bx, company_id=company_id, dry_run=dry_run)
    outcome = _first_outcome(summary)
    return _clean(outcome.get("director_inn") or summary.get("director_inn"))


def _summary_changed(summary: dict[str, Any]) -> bool:
    return any(
        _positive_metric(summary.get(key))
        for key in ("merged", "dry_run_merges", "contacts_added", "deals_updated", "failed")
    ) or any(
        (item.get("status") in {"DRY_RUN", "MERGED"} if isinstance(item, dict) else False)
        for item in (summary.get("outcomes") or [])
    )


def _positive_metric(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False


def _compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in summary.items() if k in {"status", "merged", "dry_run", "failed", "outcomes"}}


def _first_outcome(summary: dict[str, Any]) -> dict[str, Any]:
    outcomes = summary.get("outcomes") or []
    return outcomes[0] if outcomes and isinstance(outcomes[0], dict) else {}


def _first_error(summary: dict[str, Any]) -> str:
    for item in summary.get("outcomes") or []:
        if isinstance(item, dict) and item.get("error"):
            return str(item["error"])
    return str(summary.get("error") or "")


def _append_audit_row(outcome: EnrichmentOutcome) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    exists = AUDIT_PATH.exists()
    with AUDIT_PATH.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=AUDIT_HEADERS)
        if not exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": outcome.enriched_at,
            "deal_id": outcome.deal_id,
            "company_id": outcome.company_id,
            "status": outcome.status,
            "updated_fields_count": len(outcome.updated_fields),
            "director_inn_set": "1" if outcome.director_inn else "0",
            "auto_rejected": "1" if outcome.status == "REJECTED" else "0",
            "error": outcome.error,
        })


def _write_checkpoint(*, row_number: int, deals_done: list[str]) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_row_processed": row_number,
        "started_at": _now_iso(),
        "deals_done": deals_done,
    }
    PROGRESS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resume_start_row(resume: bool) -> int:
    if not resume or not PROGRESS_PATH.exists():
        return 2
    try:
        payload = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 2
    return int(payload.get("last_row_processed") or 1) + 1


def _summary(outcomes: list[EnrichmentOutcome], *, dry_run: bool, skipped: int, tab_title: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    return {
        "dry_run": dry_run,
        "tab_title": tab_title,
        "examined": len(outcomes),
        "skipped_rows": skipped,
        "counts": counts,
        "failed": counts.get("FAILED", 0),
        "outcomes": [outcome.__dict__ for outcome in outcomes],
    }


def _column_letter(idx_1based: int) -> str:
    out = ""
    idx = idx_1based
    while idx:
        idx, rem = divmod(idx - 1, 26)
        out = chr(65 + rem) + out
    return out


def _norm_header(value: Any) -> str:
    return re.sub(r"\s+", "_", str(value or "").strip().lower())


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")
