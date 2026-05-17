"""Автозакрытие заведомо непригодных сделок телемаркетинга."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import (
    HOLD_MARKER_DESC_FIELD,
    HOLD_MARKER_FLAG_FIELD,
    HOLD_REASON_BUSINESS_CLOSED,
    HOLD_REASON_COMMENT_FIELD,
    HOLD_REASON_FIELD,
    HOLD_REASON_LOW_REVENUE,
    HOLD_REVENUE_THRESHOLD_RUB,
    LOG_DIR,
    ORG_STATUS_LIQUIDATED,
    TELEMARKETING_AUTO_REJECT_SCAN_STAGES,
    TELEMARKETING_CATEGORY_ID,
)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
APOLOGY_STAGE_ID = "C50:APOLOGY"
DEAL_OWNER_TYPE_ID = 2
CSV_HEADERS = ["timestamp", "deal_id", "company_id", "reason_id", "reason_desc", "assigned_by"]


@dataclass
class AutoRejectOutcome:
    deal_id: str
    company_id: str
    status: str
    reason_id: str = ""
    reason_desc: str = ""
    skipped_reason: str = ""
    error: str = ""


def classify_for_rejection(company: dict | None) -> tuple[str, str] | None:
    """Возвращает (reason_id, reason_desc) или None — оставить менеджеру."""
    if not company:
        return None

    org_status = str(company.get("UF_CRM_ORG_STATUS") or "").strip()
    if org_status == ORG_STATUS_LIQUIDATED:
        return (
            HOLD_REASON_BUSINESS_CLOSED,
            "auto: организация ликвидирована по ЕГРЮЛ (UF_CRM_ORG_STATUS=8852)",
        )

    revenue = _extract_company_revenue(company)
    if revenue is not None and revenue < HOLD_REVENUE_THRESHOLD_RUB:
        reason = (
            f"auto: годовая выручка по rusprofile = {revenue:,} ₽ "
            f"< {HOLD_REVENUE_THRESHOLD_RUB:,} ₽"
        ).replace(",", " ")
        return (HOLD_REASON_LOW_REVENUE, reason)
    return None


def _extract_company_revenue(company: dict) -> int | None:
    """Извлекает выручку из company UF/REVENUE."""
    for field in ("UF_CRM_1737098549301", "UF_CRM_1584876707", "REVENUE"):
        raw = company.get(field)
        if raw in (None, "", "0", 0):
            continue
        try:
            cleaned = re.sub(r"[^\d.\-]", "", str(raw))
            if not cleaned:
                continue
            value = int(float(cleaned))
            if value <= 0:
                continue
            return value
        except (ValueError, TypeError):
            continue
    return None


def run(
    bx: BitrixClient,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    stages: list[str] | None = None,
) -> dict:
    requested_stages = list(stages or TELEMARKETING_AUTO_REJECT_SCAN_STAGES)
    allowed_stages = set(TELEMARKETING_AUTO_REJECT_SCAN_STAGES)
    scan_stages = [stage for stage in requested_stages if stage in allowed_stages]

    deals = bx.list_deals_by_stages(
        category_id=int(TELEMARKETING_CATEGORY_ID),
        stage_ids=scan_stages,
        closed="N",
    ) if scan_stages else []
    if limit:
        deals = deals[:limit]
    companies_by_id = _prefetch_companies(bx, deals)

    outcomes: list[AutoRejectOutcome] = []
    counters = {
        "examined": len(deals),
        "rejected": 0,
        "dry_run_updates": 0,
        "skipped": 0,
        "no_company": 0,
        "failed": 0,
        "rejected_8538": 0,
        "rejected_8542": 0,
        "dry_run_8538": 0,
        "dry_run_8542": 0,
    }

    for deal in deals:
        outcome = _process_deal(
            bx,
            deal,
            dry_run=dry_run,
            allowed_stages=allowed_stages,
            companies_by_id=companies_by_id,
        )
        outcomes.append(outcome)
        _update_counters(counters, outcome, dry_run=dry_run)

    return {
        "dry_run": dry_run,
        "scan_stages": scan_stages,
        **counters,
        "outcomes": [outcome.__dict__ for outcome in outcomes],
    }


def _process_deal(
    bx: BitrixClient,
    deal: dict[str, Any],
    *,
    dry_run: bool,
    allowed_stages: set[str],
    companies_by_id: dict[str, dict | None],
) -> AutoRejectOutcome:
    deal_id = str(deal.get("ID") or "")
    company_id = str(deal.get("COMPANY_ID") or "")

    if str(deal.get("STAGE_ID") or "") not in allowed_stages:
        return AutoRejectOutcome(deal_id, company_id, "SKIPPED", skipped_reason="stage_not_allowed")
    if _marker_already_set(deal.get(HOLD_MARKER_FLAG_FIELD)):
        return AutoRejectOutcome(deal_id, company_id, "SKIPPED", skipped_reason="already_auto_rejected")
    if not company_id or company_id == "0":
        return AutoRejectOutcome(deal_id, company_id, "NO_COMPANY", skipped_reason="empty_company_id")

    company = companies_by_id.get(company_id)
    if not company:
        return AutoRejectOutcome(deal_id, company_id, "NO_COMPANY", skipped_reason="company_not_found")

    decision = classify_for_rejection(company)
    if not decision:
        return AutoRejectOutcome(deal_id, company_id, "SKIPPED", skipped_reason="no_reject_signal")

    reason_id, reason_desc = decision
    if dry_run:
        return AutoRejectOutcome(deal_id, company_id, "DRY_RUN", reason_id, reason_desc)

    fields = _reject_fields(reason_id, reason_desc)
    try:
        ok = bx.update_deal(
            deal_id,
            fields,
            params={"REGISTER_SONET_EVENT": "Y"},
        )
        if not ok:
            return AutoRejectOutcome(deal_id, company_id, "FAILED", reason_id, reason_desc, error="crm.deal.update returned false")
        bx.add_timeline_comment(
            owner_type_id=DEAL_OWNER_TYPE_ID,
            owner_id=deal_id,
            text=f"[auto-reject] {reason_id}: {reason_desc}",
        )
        _append_audit_row(deal, reason_id, reason_desc)
    except Exception as exc:  # noqa: BLE001
        return AutoRejectOutcome(deal_id, company_id, "FAILED", reason_id, reason_desc, error=str(exc)[:300])
    return AutoRejectOutcome(deal_id, company_id, "REJECTED", reason_id, reason_desc)


def _prefetch_companies(bx: BitrixClient, deals: list[dict[str, Any]]) -> dict[str, dict | None]:
    company_ids = sorted(
        {
            str(deal.get("COMPANY_ID") or "")
            for deal in deals
            if str(deal.get("COMPANY_ID") or "") and str(deal.get("COMPANY_ID") or "") != "0"
            and str(deal.get("STAGE_ID") or "") in set(TELEMARKETING_AUTO_REJECT_SCAN_STAGES)
            and not _marker_already_set(deal.get(HOLD_MARKER_FLAG_FIELD))
        },
        key=lambda x: int(x) if x.isdigit() else x,
    )
    if not company_ids:
        return {}
    if not hasattr(bx, "batch"):
        return {company_id: bx.get_company(company_id) for company_id in company_ids}

    out: dict[str, dict | None] = {}
    for off in range(0, len(company_ids), 50):
        chunk = company_ids[off : off + 50]
        commands = {f"co_{company_id}": ("crm.company.get", {"id": company_id}) for company_id in chunk}
        try:
            result = bx.batch(commands)
        except Exception:  # noqa: BLE001
            for company_id in chunk:
                out[company_id] = bx.get_company(company_id)
            continue
        for company_id in chunk:
            company = result.get(f"co_{company_id}")
            out[company_id] = company if isinstance(company, dict) else None
    return out


def _reject_fields(reason_id: str, reason_desc: str) -> dict[str, str]:
    return {
        "STAGE_ID": APOLOGY_STAGE_ID,
        "CLOSED": "Y",
        HOLD_REASON_FIELD: reason_id,
        HOLD_REASON_COMMENT_FIELD: reason_desc,
        HOLD_MARKER_FLAG_FIELD: "1",
        HOLD_MARKER_DESC_FIELD: f"auto-reject {reason_id} @ {date.today().isoformat()}",
    }


def _marker_already_set(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().upper() in {"1", "Y", "TRUE"}


def _update_counters(counters: dict[str, int], outcome: AutoRejectOutcome, *, dry_run: bool) -> None:
    if outcome.status == "REJECTED":
        counters["rejected"] += 1
        if outcome.reason_id == HOLD_REASON_BUSINESS_CLOSED:
            counters["rejected_8538"] += 1
        elif outcome.reason_id == HOLD_REASON_LOW_REVENUE:
            counters["rejected_8542"] += 1
    elif outcome.status == "DRY_RUN":
        counters["dry_run_updates"] += 1
        if outcome.reason_id == HOLD_REASON_BUSINESS_CLOSED:
            counters["dry_run_8538"] += 1
        elif outcome.reason_id == HOLD_REASON_LOW_REVENUE:
            counters["dry_run_8542"] += 1
    elif outcome.status == "NO_COMPANY":
        counters["no_company"] += 1
    elif outcome.status == "FAILED":
        counters["failed"] += 1
    else:
        counters["skipped"] += 1


def _append_audit_row(deal: dict[str, Any], reason_id: str, reason_desc: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "auto_reject_telemarketing.csv"
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
                "deal_id": str(deal.get("ID") or ""),
                "company_id": str(deal.get("COMPANY_ID") or ""),
                "reason_id": reason_id,
                "reason_desc": reason_desc,
                "assigned_by": str(deal.get("ASSIGNED_BY_ID") or ""),
            }
        )
