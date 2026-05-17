"""Автоперевод готовых сделок из «База» в «К обзвону»."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..config import (
    COMPANY_UF_CITY,
    COMPANY_UF_ORGANIZATION_STATUS,
    COMPANY_UF_REGION,
    TELEMARKETING_ASSIGNEES,
    TELEMARKETING_CATEGORY_ID,
    TELEMARKETING_NEW_STAGE_ID,
    TELEMARKETING_REVIVE_SOURCE_ID,
)

BASE_STAGE_ID = "C50:UC_1S1KIU"
ACTIVE_ORG_STATUS = "8850"

REQUIRED_COMPANY_FIELDS = (
    "PHONE_PRESENT",
    "EMAIL_PRESENT",
    "INN_PRESENT",
    "CITY_PRESENT",
    "REGION_PRESENT",
    "ACTIVE_STATUS",
    "BITRIX_CONTACT",
)


@dataclass
class PromoteOutcome:
    deal_id: str
    company_id: str
    status: str
    new_assignee: str = ""
    missing_fields: list[str] = field(default_factory=list)
    skipped_reason: str = ""
    error: str = ""


def run(
    bx: Any,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    rotation_index: int = 0,
) -> dict[str, Any]:
    deals = list(
        bx.list_deals_by_stages(
            category_id=int(TELEMARKETING_CATEGORY_ID),
            stage_ids=[BASE_STAGE_ID],
            closed="N",
            select=[
                "ID",
                "TITLE",
                "COMPANY_ID",
                "STAGE_ID",
                "CLOSED",
                "ASSIGNED_BY_ID",
            ],
        )
    )
    if limit:
        deals = deals[:limit]

    outcomes: list[PromoteOutcome] = []
    used_rotation = 0
    for deal in deals:
        outcome, used = _process_deal(
            bx,
            deal,
            dry_run=dry_run,
            rotation_index=rotation_index + used_rotation,
        )
        if used:
            used_rotation += 1
        outcomes.append(outcome)
    return _summary(outcomes, dry_run=dry_run)


def _process_deal(
    bx: Any,
    deal: dict[str, Any],
    *,
    dry_run: bool,
    rotation_index: int,
) -> tuple[PromoteOutcome, bool]:
    deal_id = str(deal.get("ID") or "")
    company_id = str(deal.get("COMPANY_ID") or "")
    if not company_id or company_id == "0":
        return PromoteOutcome(deal_id, "", "SKIPPED", skipped_reason="missing_company_id"), False

    try:
        company = bx.get_company(company_id) or {}
    except Exception as exc:  # noqa: BLE001
        return PromoteOutcome(deal_id, company_id, "FAILED", error=f"company_get_failed: {str(exc)[:160]}"), False
    contacts = list(bx.list_company_contacts_full(company_id))
    requisites = list(bx.list_company_requisites(company_id))
    ready, missing = _evaluate_readiness(company, contacts, requisites)
    if not ready:
        return (
            PromoteOutcome(
                deal_id,
                company_id,
                "SKIPPED",
                missing_fields=missing,
                skipped_reason="missing_required_fields",
            ),
            False,
        )

    new_assignee = _telemarketing_assignee_by_rotation(rotation_index)
    if dry_run:
        return PromoteOutcome(deal_id, company_id, "DRY_RUN", new_assignee=new_assignee), True

    try:
        bx.update_deal(
            deal_id,
            {
                "STAGE_ID": TELEMARKETING_NEW_STAGE_ID,
                "CLOSED": "N",
                "SOURCE_ID": TELEMARKETING_REVIVE_SOURCE_ID,
                "ASSIGNED_BY_ID": new_assignee,
            },
            params={"REGISTER_SONET_EVENT": "Y"},
        )
    except Exception as exc:  # noqa: BLE001
        return PromoteOutcome(deal_id, company_id, "FAILED", new_assignee=new_assignee, error=str(exc)[:200]), True
    return PromoteOutcome(deal_id, company_id, "PROMOTED", new_assignee=new_assignee), True


def _evaluate_readiness(
    company: dict[str, Any],
    contacts: list[dict[str, Any]],
    requisites: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    missing: list[str] = []
    if not _has_phone(company, contacts):
        missing.append("PHONE_PRESENT")
    if not _has_email(company, contacts):
        missing.append("EMAIL_PRESENT")
    if not any(_clean(req.get("RQ_INN")) for req in requisites):
        missing.append("INN_PRESENT")
    if not _clean(company.get(COMPANY_UF_CITY)):
        missing.append("CITY_PRESENT")
    if not _clean(company.get(COMPANY_UF_REGION)):
        missing.append("REGION_PRESENT")
    if str(company.get(COMPANY_UF_ORGANIZATION_STATUS) or "") != ACTIVE_ORG_STATUS:
        missing.append("ACTIVE_STATUS")
    if not contacts:
        missing.append("BITRIX_CONTACT")
    return not missing, missing


def _has_phone(company: dict[str, Any], contacts: list[dict[str, Any]]) -> bool:
    return _has_multifield(company, "PHONE") or any(_has_multifield(c, "PHONE") for c in contacts)


def _has_email(company: dict[str, Any], contacts: list[dict[str, Any]]) -> bool:
    return _has_multifield(company, "EMAIL") or any(_has_multifield(c, "EMAIL") for c in contacts)


def _has_multifield(entity: dict[str, Any], field: str) -> bool:
    for item in entity.get(field) or []:
        value = item.get("VALUE") if isinstance(item, dict) else item
        if _clean(value):
            return True
    return False


def _telemarketing_assignee_by_rotation(rotation_index: int) -> str:
    return TELEMARKETING_ASSIGNEES[rotation_index % len(TELEMARKETING_ASSIGNEES)][0]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _summary(outcomes: list[PromoteOutcome], *, dry_run: bool) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "total": len(outcomes),
        "promoted": sum(1 for outcome in outcomes if outcome.status == "PROMOTED"),
        "dry_run_promotions": sum(1 for outcome in outcomes if outcome.status == "DRY_RUN"),
        "skipped": sum(1 for outcome in outcomes if outcome.status == "SKIPPED"),
        "failed": sum(1 for outcome in outcomes if outcome.status == "FAILED"),
        "outcomes": [asdict(outcome) for outcome in outcomes],
    }
