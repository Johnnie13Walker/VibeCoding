"""Rebind orphan C50 deal to a freshly resolved/enriched company."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..bitrix_client import BitrixClient
from ..config import COMPANY_UF_ORGANIZATION_STATUS, ORG_STATUS_LIQUIDATED
from . import enrich_company_full, sync_deals


@dataclass
class OrphanRebindOutcome:
    deal_id: str
    url: str
    dry_run: bool
    status: str = ""
    old_company_id: str = ""
    new_company_id: str = ""
    old_stage_id: str = ""
    title: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    enrich: dict[str, Any] = field(default_factory=dict)
    sync_deal: dict[str, Any] = field(default_factory=dict)
    error: str = ""


def run(
    bx: BitrixClient,
    *,
    deal_id: str,
    url: str,
    dry_run: bool = True,
    allow_live_company: bool = False,
    allow_liquidated: bool = False,
    bizproc_wait_s: int | None = None,
) -> dict[str, Any]:
    """Обогатить компанию по URL и перевязать существующую orphan-сделку.

    Важные гарантии:
    - enrich-company-full запускается с no_create_deal=True;
    - существующий SOURCE_ID сделки не перезаписывается;
    - стадия сделки не меняется;
    - COMPANY_ID обновляется только после успешного enrich.
    """
    outcome = OrphanRebindOutcome(deal_id=str(deal_id), url=url, dry_run=dry_run)

    deal = bx.get_deal(str(deal_id))
    if not deal:
        outcome.status = "FAILED"
        outcome.error = "deal_not_found"
        outcome.steps.append({"step": "LOAD_DEAL", "status": "FAILED", "reason": "deal_not_found"})
        return asdict(outcome)

    outcome.old_company_id = _clean_id(deal.get("COMPANY_ID"))
    outcome.old_stage_id = str(deal.get("STAGE_ID") or "")
    outcome.title = str(deal.get("TITLE") or "")
    outcome.steps.append({
        "step": "LOAD_DEAL",
        "status": "DONE",
        "old_company_id": outcome.old_company_id,
        "stage_id": outcome.old_stage_id,
        "title": outcome.title,
    })

    if outcome.old_company_id:
        old_company = bx.get_company(outcome.old_company_id)
        if old_company and not allow_live_company:
            outcome.status = "SKIPPED"
            outcome.error = "old_company_still_live"
            outcome.steps.append({
                "step": "CHECK_ORPHAN",
                "status": "SKIPPED",
                "reason": "old_company_still_live",
                "old_company_id": outcome.old_company_id,
            })
            return asdict(outcome)
    outcome.steps.append({"step": "CHECK_ORPHAN", "status": "DONE"})

    enrich_outcome = enrich_company_full.run(
        bx,
        url=url,
        create_if_missing=True,
        dry_run=dry_run,
        skip_auto_reject=True,
        no_create_deal=True,
        bizproc_wait_s=bizproc_wait_s,
    )
    outcome.enrich = asdict(enrich_outcome)
    outcome.new_company_id = str(enrich_outcome.company_id or "")
    if enrich_outcome.final_status == "FAILED" or not outcome.new_company_id:
        outcome.status = "FAILED"
        outcome.error = f"enrich_failed:{enrich_outcome.final_status or 'no_company'}"
        outcome.steps.append({"step": "ENRICH_COMPANY", "status": "FAILED", "final_status": enrich_outcome.final_status})
        return asdict(outcome)
    if enrich_outcome.final_status == "SKIPPED":
        outcome.status = "SKIPPED"
        outcome.error = "enrich_skipped"
        outcome.steps.append({"step": "ENRICH_COMPANY", "status": "SKIPPED", "final_status": enrich_outcome.final_status})
        return asdict(outcome)
    outcome.steps.append({"step": "ENRICH_COMPANY", "status": "DONE", "final_status": enrich_outcome.final_status, "company_id": outcome.new_company_id})

    company = bx.get_company(outcome.new_company_id) if not dry_run else None
    if company and str(company.get(COMPANY_UF_ORGANIZATION_STATUS) or "") == ORG_STATUS_LIQUIDATED and not allow_liquidated:
        outcome.status = "SKIPPED"
        outcome.error = "company_liquidated"
        outcome.steps.append({"step": "CHECK_LIQUIDATED", "status": "SKIPPED", "reason": "company_liquidated"})
        return asdict(outcome)
    outcome.steps.append({"step": "CHECK_LIQUIDATED", "status": "DONE"})

    clean_title = _domain_from_url(url)
    deal_fields = {"COMPANY_ID": outcome.new_company_id}
    if clean_title and clean_title != outcome.title:
        deal_fields["TITLE"] = clean_title
    if dry_run:
        outcome.steps.append({"step": "REBIND_DEAL", "status": "DRY_RUN", "fields": deal_fields})
        outcome.sync_deal = {"dry_run": True, "planned_deal_id": str(deal_id), "planned_company_id": outcome.new_company_id}
        outcome.steps.append({"step": "SYNC_DEAL", "status": "DRY_RUN", "summary": outcome.sync_deal})
        outcome.status = "DRY_RUN"
        return asdict(outcome)
    else:
        bx.update_deal(str(deal_id), deal_fields, params={"REGISTER_SONET_EVENT": "Y"})
        outcome.steps.append({"step": "REBIND_DEAL", "status": "DONE", "fields": deal_fields})

        fresh_deal = bx.get_deal(str(deal_id)) or {}
        if str(fresh_deal.get("COMPANY_ID") or "") != outcome.new_company_id:
            outcome.status = "FAILED"
            outcome.error = "verify_rebind_failed"
            outcome.steps.append({"step": "VERIFY_REBIND", "status": "FAILED", "actual_company_id": fresh_deal.get("COMPANY_ID")})
            return asdict(outcome)
        outcome.steps.append({"step": "VERIFY_REBIND", "status": "DONE"})

    outcome.sync_deal = sync_deals.run(
        bx,
        deal_id=str(deal_id),
        dry_run=dry_run,
        overwrite=False,
        active_only=False,
        telemarketing_workflow=False,
    )
    sync_status = "FAILED" if outcome.sync_deal.get("failed") else "DONE"
    outcome.steps.append({"step": "SYNC_DEAL", "status": sync_status, "summary": outcome.sync_deal})
    outcome.status = "FAILED" if outcome.sync_deal.get("failed") else "DRY_RUN" if dry_run else "OK"
    return asdict(outcome)


def _clean_id(value: Any) -> str:
    raw = str(value or "").strip()
    return "" if raw == "0" else raw


def _domain_from_url(url: str) -> str:
    return enrich_company_full._title_from_url(url)
