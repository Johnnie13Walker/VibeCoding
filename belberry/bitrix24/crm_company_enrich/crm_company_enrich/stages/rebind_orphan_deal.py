"""Rebind orphan C50 deal to a freshly resolved/enriched company."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..bitrix_client import BitrixClient
from ..config import COMPANY_UF_ORGANIZATION_STATUS, ORG_STATUS_LIQUIDATED
from ..models import normalize_inn
from . import enrich_company_full, sync_deals
from .enrich_web import HttpFetcher, try_web


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
    - enrich-company-full не ищет и не трогает существующие сделки новой компании;
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
        no_touch_existing_deals=True,
        skip_telemarketing_dedupe=True,
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
    if not dry_run:
        verification = _verify_resolved_company(bx, company=company, company_id=outcome.new_company_id, url=url)
        outcome.steps.append(verification)
        if verification.get("status") == "FAILED":
            outcome.status = "FAILED"
            outcome.error = str(verification.get("reason") or "verification_failed")
            return asdict(outcome)
    else:
        outcome.steps.append({"step": "VERIFY_RESOLVED_COMPANY", "status": "DRY_RUN"})

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


def _verify_resolved_company(
    bx: BitrixClient,
    *,
    company: dict | None,
    company_id: str,
    url: str,
) -> dict[str, Any]:
    expected_site_key = enrich_company_full._site_key(url)
    if not company:
        return {"step": "VERIFY_RESOLVED_COMPANY", "status": "FAILED", "reason": "company_not_found", "company_id": company_id}
    company_site_keys = _company_site_keys(company)
    if not expected_site_key or expected_site_key not in company_site_keys:
        return {
            "step": "VERIFY_RESOLVED_COMPANY",
            "status": "FAILED",
            "reason": "site_mismatch",
            "expected_site_key": expected_site_key,
            "company_site_keys": sorted(company_site_keys),
            "company_id": company_id,
        }

    expected_inn = normalize_inn((try_web(url, HttpFetcher().fetch, sleep_s=0.1) or ("", ""))[0])
    if not expected_inn:
        return {
            "step": "VERIFY_RESOLVED_COMPANY",
            "status": "FAILED",
            "reason": "no_inn_verification",
            "company_id": company_id,
            "expected_site_key": expected_site_key,
        }
    company_inns = _company_requisite_inns(bx, company_id)
    if not company_inns:
        return {
            "step": "VERIFY_RESOLVED_COMPANY",
            "status": "FAILED",
            "reason": "no_inn_verification",
            "company_id": company_id,
            "expected_inn": expected_inn,
        }
    if expected_inn not in company_inns:
        return {
            "step": "VERIFY_RESOLVED_COMPANY",
            "status": "FAILED",
            "reason": "inn_mismatch",
            "company_id": company_id,
            "expected_inn": expected_inn,
            "company_inns": sorted(company_inns),
        }
    return {
        "step": "VERIFY_RESOLVED_COMPANY",
        "status": "DONE",
        "company_id": company_id,
        "expected_site_key": expected_site_key,
        "expected_inn": expected_inn,
    }


def _company_site_keys(company: dict) -> set[str]:
    keys = {
        enrich_company_full._site_key(item.get("VALUE") if isinstance(item, dict) else item)
        for item in company.get("WEB") or []
    }
    keys.add(enrich_company_full._site_key(company.get("UF_CRM_5DEF838D882A2") or ""))
    keys.discard("")
    return keys


def _company_requisite_inns(bx: BitrixClient, company_id: str) -> set[str]:
    return {
        inn
        for inn in (normalize_inn(req.get("RQ_INN")) for req in bx.list_company_requisites(company_id))
        if inn
    }
