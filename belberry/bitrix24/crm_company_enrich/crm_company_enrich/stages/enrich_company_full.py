"""End-to-end orchestrator обогащения компании для телемаркетинга."""
from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import (
    CCE_BIZPROC_FIRST_ENTRY_ID,
    CCE_BIZPROC_POLL_S,
    CCE_BIZPROC_TIMEOUT_S,
    CCE_BIZPROC_UPDATE_ID,
    CCE_BIZPROC_WAIT_S,
    CCE_PRESET_ID,
    COMPANY_ORGANIZATION_STATUS_ENUM,
    COMPANY_UF_CITY,
    COMPANY_UF_ORGANIZATION_STATUS,
    COMPANY_UF_REGION,
    DEAL_UF_INN,
    DEAL_UF_SITE_MULTI,
    DEAL_UF_SITE_PRIMARY,
    ENTITY_TYPE_COMPANY,
    HOLD_MARKER_FLAG_FIELD,
    HOLD_REASON_COMMENT_FIELD,
    HOLD_REASON_FIELD,
    HOLD_REVENUE_THRESHOLD_RUB,
    LAST_AUTO_ACTION_DESC_FIELD,
    LOG_DIR,
    ORG_STATUS_LIQUIDATED,
    PORTAL_DOMAIN,
    REACTIVATION_COUNT_FIELD,
    REVIVE_COUNT_FIELD,
    REVIVE_NEXT_COMMUNICATION_FIELD,
    TELEMARKETING_ASSIGNEES,
    TELEMARKETING_CATEGORY_ID,
    TELEMARKETING_NEW_STAGE_ID,
    TELEMARKETING_OPEN_STAGES,
    TELEMARKETING_REVIVE_SOURCE_ID,
    TELEMARKETING_REVIVE_TARGET_STAGE,
    TELEMARKETING_REVIVED_FROM_LOSE_STAGE,
    TELEMARKETING_SOURCE_ID,
    UF_BRAND_BELBERRY,
    UF_BRAND_FIELD,
)
from ..models import normalize_inn
from . import auto_reject_telemarketing, dedupe_contacts, enrich_empty_companies, enrich_web, sync_deals, telemarketing_dedupe
from .reactivation_apology import COOLDOWN_BY_REASON_MONTHS

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
AUDIT_PATH = LOG_DIR / "enrich_company_full.csv"
STATE_PATH = LOG_DIR / "enrich_company_full_state.json"
DEAL_OWNER_TYPE_ID = 2
FINAL_STATUSES = {"ENRICHED", "REJECTED", "SKIPPED", "PARTIAL", "FAILED"}


@dataclass
class StepOutcome:
    step: str
    status: str
    details: dict = field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0


@dataclass
class FullEnrichmentOutcome:
    input_kind: str
    input_value: str
    company_id: str = ""
    deal_id: str = ""
    contact_ids: list[str] = field(default_factory=list)
    duplicate_company_ids: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    steps: list[StepOutcome] = field(default_factory=list)
    final_status: str = ""
    rejected_reason: str = ""
    timestamp: str = ""
    bitrix_links: dict = field(default_factory=dict)


def run(
    bx: BitrixClient,
    *,
    company_id: str = "",
    deal_id: str = "",
    inn: str = "",
    url: str = "",
    create_if_missing: bool = False,
    dry_run: bool = True,
    skip_bp: bool = False,
    skip_dedupe_contacts: bool = False,
    skip_director_inn: bool = False,
    skip_telemarketing_dedupe: bool = False,
    skip_auto_reject: bool = False,
    no_create_deal: bool = False,
    bizproc_wait_s: int | None = None,
) -> FullEnrichmentOutcome:
    """Главный orchestrator: resolve → enrich → deal workflow → audit."""
    input_kind = _detect_input_kind(company_id, deal_id, inn, url)
    input_value = {"company_id": company_id, "deal_id": deal_id, "inn": inn, "url": url}[input_kind]
    outcome = FullEnrichmentOutcome(
        input_kind=input_kind,
        input_value=str(input_value),
        timestamp=_now_iso(),
    )

    context: dict[str, Any] = {
        "company_id": str(company_id or ""),
        "deal_id": str(deal_id or ""),
        "inn": normalize_inn(inn) or "",
        "url": _normalize_url(url),
        "created_company": False,
        "had_requisites_before": False,
        "open_deals": [],
        "lose_deals": [],
        "apology_deals": [],
    }
    flags = {
        "create_if_missing": create_if_missing,
        "dry_run": dry_run,
        "skip_bp": skip_bp,
        "skip_dedupe_contacts": skip_dedupe_contacts,
        "skip_director_inn": skip_director_inn,
        "skip_telemarketing_dedupe": skip_telemarketing_dedupe,
        "skip_auto_reject": skip_auto_reject,
        "no_create_deal": no_create_deal,
        "bizproc_wait_s": CCE_BIZPROC_WAIT_S if bizproc_wait_s is None else bizproc_wait_s,
    }

    steps: list[tuple[str, Callable[..., StepOutcome]]] = [
        ("RESOLVE", _step_resolve),
        ("FIND_SITE", _step_find_site),
        ("FIND_INN", _step_find_inn),
        ("CHECK_INN_DUPLICATE", _step_check_inn_duplicate),
        ("APPLY_INN", _step_apply_inn),
        ("RUN_BP", _step_run_bp),
        ("VERIFY", _step_verify),
        ("SYNC_COMPANY", _step_sync_company),
        ("ADDRESS_SYNC", _step_address_sync),
        ("CHECK_BANKRUPTCY", _step_check_bankruptcy),
        ("RANK_DEAL_VIABILITY", _step_rank_deal_viability),
        ("RESOLVE_DEAL", _step_resolve_deal),
        ("CREATE_DEAL", _step_create_deal),
        ("SYNC_DEAL", _step_sync_deal),
        ("REVIVE_DEAL", _step_revive_deal),
        ("DEDUPE_CONTACTS", _step_dedupe_contacts),
        ("ENRICH_DIRECTOR_INN", _step_enrich_director_inn),
        ("TELEMARKETING_DEDUPE_SCOPED", _step_telemarketing_dedupe_scoped),
        ("WRITE_AUDIT", _step_write_audit),
        ("RETURN_OUTCOME", _step_return_outcome),
    ]

    for step_name, handler in steps:
        if outcome.final_status in {"FAILED", "REJECTED", "SKIPPED"} and step_name not in {"WRITE_AUDIT", "RETURN_OUTCOME"}:
            continue
        if step_name == "WRITE_AUDIT" and not outcome.final_status:
            statuses = {step.status for step in outcome.steps}
            outcome.final_status = "PARTIAL" if "PARTIAL" in statuses else "ENRICHED"
        step = _run_step(step_name, handler, bx, outcome, context, flags)
        outcome.steps.append(step)
        if step.status == "FAILED" and not outcome.final_status:
            outcome.final_status = "FAILED"
        if outcome.final_status in FINAL_STATUSES and step_name == "RETURN_OUTCOME":
            break

    _refresh_links(outcome)
    return outcome


def _run_step(
    step_name: str,
    handler: Callable[..., StepOutcome],
    bx: BitrixClient,
    outcome: FullEnrichmentOutcome,
    context: dict[str, Any],
    flags: dict[str, Any],
) -> StepOutcome:
    started = time.monotonic()
    try:
        step = handler(bx, outcome, context, flags)
    except Exception as exc:  # noqa: BLE001
        step = StepOutcome(step_name, "FAILED", error=str(exc)[:500])
    step.duration_ms = int((time.monotonic() - started) * 1000)
    return step


def _step_resolve(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    company: dict | None = None
    deal_had_company = False
    if outcome.input_kind == "company_id":
        company = bx.get_company(context["company_id"])
    elif outcome.input_kind == "deal_id":
        deal = bx.get_deal(context["deal_id"])
        if deal:
            context["deal_id"] = str(deal.get("ID") or context["deal_id"])
            context["company_id"] = str(deal.get("COMPANY_ID") or "")
            if context["company_id"] == "0":
                context["company_id"] = ""
            outcome.deal_id = context["deal_id"]
            deal_had_company = bool(context["company_id"])
            company = bx.get_company(context["company_id"]) if context["company_id"] else None
            if not company and context.get("url") and flags["create_if_missing"]:
                context["site"] = context["url"]
                found, _name = enrich_web.try_web(context["url"], enrich_web.HttpFetcher().fetch, sleep_s=0.1)
                if found:
                    context["inn"] = found
    elif outcome.input_kind == "inn":
        reqs = bx.search_requisite_by_inn(context["inn"])
        company_id = str((reqs[0] if reqs else {}).get("ENTITY_ID") or "")
        if company_id:
            context["company_id"] = company_id
            company = bx.get_company(company_id)
    elif outcome.input_kind == "url":
        company = _find_company_by_url(bx, context["url"])
        if company:
            context["company_id"] = str(company.get("ID") or "")

    if not company and flags["create_if_missing"]:
        if not context.get("inn") and context.get("url"):
            found, _name = enrich_web.try_web(context["url"], enrich_web.HttpFetcher().fetch, sleep_s=0.1)
            if found:
                context["inn"] = found
        if not context.get("inn"):
            outcome.flags.append("no_inn_no_company")
            outcome.final_status = "SKIPPED"
            return StepOutcome("RESOLVE", "SKIPPED", {"reason": "no_inn_no_company", "url": context.get("url", "")})
        if flags["dry_run"]:
            context["company_id"] = "DRY_RUN_COMPANY"
            outcome.company_id = context["company_id"]
            context["created_company"] = True
            context["company"] = {"ID": context["company_id"], "TITLE": _title_from_url(context["url"]) or context["inn"], "WEB": _web_values(context["url"])}
            if outcome.input_kind == "deal_id" and context.get("deal_id") and not deal_had_company:
                context["attached_input_deal"] = True
            outcome.flags.append("would_create_company")
            return StepOutcome("RESOLVE", "DONE", {"created": "dry_run", "company_id": context["company_id"]})
        fields = _minimum_company_fields(context)
        context["company_id"] = _add_company(bx, fields)
        context["created_company"] = True
        company = bx.get_company(context["company_id"]) or {"ID": context["company_id"], **fields}
        if outcome.input_kind == "deal_id" and context.get("deal_id") and not deal_had_company:
            bx.update_deal(context["deal_id"], {"COMPANY_ID": context["company_id"]})
            context["attached_input_deal"] = True

    if not company:
        outcome.final_status = "FAILED"
        return StepOutcome("RESOLVE", "FAILED", error="cannot_resolve_company")

    context["company_id"] = str(company.get("ID") or context["company_id"])
    context["company"] = company
    outcome.company_id = context["company_id"]
    return StepOutcome("RESOLVE", "DONE", {"company_id": outcome.company_id, "title": company.get("TITLE")})


def _step_find_site(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    company = _company(bx, context)
    site = _primary_site(company) or context.get("url", "")
    if site:
        context["site"] = site
        return StepOutcome("FIND_SITE", "SKIPPED", {"site": site, "reason": "already_present"})
    return StepOutcome("FIND_SITE", "SKIPPED", {"reason": "site_not_found"})


def _step_find_inn(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    reqs = bx.list_company_requisites(outcome.company_id)
    context["had_requisites_before"] = bool(reqs)
    req_inn = _first_requisite_inn(reqs)
    if req_inn:
        context["inn"] = req_inn
        return StepOutcome("FIND_INN", "SKIPPED", {"inn": req_inn, "source": "requisite"})
    company = _company(bx, context)
    company_inn = normalize_inn(company.get("UF_CRM_1735331882180")) or context.get("inn", "")
    if company_inn:
        context["inn"] = company_inn
        return StepOutcome("FIND_INN", "DONE", {"inn": company_inn, "source": "company_or_input"})
    site = context.get("site") or _primary_site(company)
    if site:
        found, _name = enrich_web.try_web(site, enrich_web.HttpFetcher().fetch, sleep_s=0.1)
        if found:
            context["inn"] = found
            return StepOutcome("FIND_INN", "DONE", {"inn": found, "source": "web"})
    title = str(company.get("TITLE") or "")
    if title:
        found, _name, _geo = enrich_web.try_rusprofile(title, enrich_web.HttpFetcher().fetch)
        if found:
            context["inn"] = found
            return StepOutcome("FIND_INN", "DONE", {"inn": found, "source": "rusprofile"})
    outcome.flags.append("no_inn_found")
    return StepOutcome("FIND_INN", "PARTIAL", {"flag": "no_inn_found"})


def _step_check_inn_duplicate(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    inn = context.get("inn", "")
    if not inn:
        return StepOutcome("CHECK_INN_DUPLICATE", "SKIPPED", {"reason": "no_inn"})
    reqs = bx.search_requisite_by_inn(inn)
    duplicate_info = enrich_empty_companies.duplicate_info_from_requisites(bx, reqs, outcome.company_id)
    outcome.duplicate_company_ids = [str(x) for x in duplicate_info.get("duplicate_company_ids", [])]
    if outcome.duplicate_company_ids:
        outcome.flags.append("duplicate_inn")
    return StepOutcome("CHECK_INN_DUPLICATE", "DONE", duplicate_info)


def _step_apply_inn(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    inn = context.get("inn", "")
    if not inn:
        return StepOutcome("APPLY_INN", "SKIPPED", {"reason": "no_inn"})
    reqs = bx.list_company_requisites(outcome.company_id)
    if any(str(req.get("RQ_INN") or "").strip() == inn for req in reqs):
        return StepOutcome("APPLY_INN", "SKIPPED", {"reason": "requisite_exists", "inn": inn})
    payload = {
        "ENTITY_TYPE_ID": ENTITY_TYPE_COMPANY,
        "ENTITY_ID": outcome.company_id,
        "PRESET_ID": CCE_PRESET_ID,
        "NAME": f"ИНН {inn}",
        "RQ_INN": inn,
    }
    if flags["dry_run"]:
        return StepOutcome("APPLY_INN", "DONE", {"dry_run": True, "payload": payload})
    req_id = bx.add_requisite(payload)
    context["created_requisite_id"] = req_id
    return StepOutcome("APPLY_INN", "DONE", {"requisite_id": req_id, "inn": inn})


def _step_run_bp(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    if flags["skip_bp"]:
        outcome.flags.append("bp_skipped")
        return StepOutcome("RUN_BP", "SKIPPED", {"reason": "skip_bp"})
    if not context.get("inn"):
        return StepOutcome("RUN_BP", "SKIPPED", {"reason": "no_inn"})
    planned = []
    if not context.get("had_requisites_before"):
        planned.append(CCE_BIZPROC_FIRST_ENTRY_ID)
    planned.append(CCE_BIZPROC_UPDATE_ID)
    if flags["dry_run"]:
        return StepOutcome("RUN_BP", "DONE", {"dry_run": True, "planned_template_ids": planned})
    results = []
    if not context.get("had_requisites_before"):
        results.append(_start_bp_and_wait(bx, outcome.company_id, CCE_BIZPROC_FIRST_ENTRY_ID))
    results.append(_start_bp_and_wait(bx, outcome.company_id, CCE_BIZPROC_UPDATE_ID))
    return StepOutcome("RUN_BP", "DONE", {"results": results})


def _step_verify(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    if flags["skip_bp"] or not context.get("inn"):
        return StepOutcome("VERIFY", "SKIPPED", {"reason": "bp_skipped_or_no_inn"})
    wait_s = int(flags.get("bizproc_wait_s") or 0)
    if flags["dry_run"]:
        company = _company(bx, context)
        reqs = bx.list_company_requisites(outcome.company_id)
        verified = _has_verified_data(company, reqs)
        return StepOutcome("VERIFY", "DONE" if verified else "PARTIAL", {"dry_run": True, "verified": verified})
    for attempt in range(3):
        time.sleep(wait_s)
        company = bx.get_company(outcome.company_id) or {}
        context["company"] = company
        reqs = bx.list_company_requisites(outcome.company_id)
        if _has_verified_data(company, reqs):
            return StepOutcome("VERIFY", "DONE", {"attempt": attempt + 1})
    outcome.flags.append("verify_pending")
    return StepOutcome("VERIFY", "PARTIAL", {"flag": "verify_pending"})


def _start_bp_and_wait(bx: BitrixClient, company_id: str, template_id: int | None) -> dict[str, Any]:
    if not template_id:
        return {"template_id": template_id, "skipped": True}
    result = bx.start_workflow(template_id, ["crm", "CCrmDocumentCompany", f"COMPANY_{company_id}"])
    workflow_id = str(result.get("workflow_id") or "")
    result["template_id"] = template_id
    if workflow_id and hasattr(bx, "wait_workflow_finished"):
        result["wait_finished"] = bx.wait_workflow_finished(
            workflow_id,
            timeout_s=CCE_BIZPROC_TIMEOUT_S,
            poll_s=CCE_BIZPROC_POLL_S,
        )
    return result


def _step_sync_company(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    if not outcome.company_id or outcome.company_id == "DRY_RUN_COMPANY":
        return StepOutcome("SYNC_COMPANY", "SKIPPED", {"reason": "no_real_company"})
    summary = sync_deals.run_company(
        bx,
        company_id=outcome.company_id,
        inn=context.get("inn", ""),
        site=context.get("site", ""),
        dry_run=flags["dry_run"],
        overwrite=False,
    )
    if not flags["dry_run"]:
        context["company"] = bx.get_company(outcome.company_id) or context.get("company") or {}
    return StepOutcome("SYNC_COMPANY", "DONE" if not summary.get("failed") else "FAILED", {"summary": summary})


def _step_address_sync(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    company = _company(bx, context)
    planned = _address_updates(company)
    if not planned:
        return StepOutcome("ADDRESS_SYNC", "SKIPPED", {"reason": "no_missing_address_fields"})
    if flags["dry_run"]:
        return StepOutcome("ADDRESS_SYNC", "DONE", {"dry_run": True, "fields": planned})
    updated = enrich_empty_companies.fill_company_address_fields(bx, outcome.company_id, company)
    context["company"] = bx.get_company(outcome.company_id) or company
    return StepOutcome("ADDRESS_SYNC", "DONE", {"fields": updated})


def _step_check_bankruptcy(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    inn = context.get("inn", "")
    if not inn:
        return StepOutcome("CHECK_BANKRUPTCY", "SKIPPED", {"reason": "no_inn"})
    html = sync_deals.fetch_rusprofile_html(inn)
    status = sync_deals.parse_organization_status(html) if html else ""
    if status != "Ликвидирована":
        return StepOutcome("CHECK_BANKRUPTCY", "DONE", {"organization_status": status or "unknown"})
    company = _company(bx, context)
    if str(company.get(COMPANY_UF_ORGANIZATION_STATUS) or "") == ORG_STATUS_LIQUIDATED:
        return StepOutcome("CHECK_BANKRUPTCY", "DONE", {"organization_status": "Ликвидирована", "already_set": True})
    if flags["dry_run"]:
        return StepOutcome("CHECK_BANKRUPTCY", "DONE", {"dry_run": True, "would_set": ORG_STATUS_LIQUIDATED})
    bx.update_company(outcome.company_id, {COMPANY_UF_ORGANIZATION_STATUS: ORG_STATUS_LIQUIDATED})
    context["company"] = bx.get_company(outcome.company_id) or company
    return StepOutcome("CHECK_BANKRUPTCY", "DONE", {"set": ORG_STATUS_LIQUIDATED})


def _step_rank_deal_viability(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    if flags["skip_auto_reject"]:
        return StepOutcome("RANK_DEAL_VIABILITY", "SKIPPED", {"reason": "skip_auto_reject"})
    company = _company(bx, context)
    decision = auto_reject_telemarketing.classify_for_rejection(company)
    if not decision:
        return StepOutcome("RANK_DEAL_VIABILITY", "DONE", {"decision": "continue"})
    reason_id, reason_desc = decision
    open_deal = _first_open_c50_deal(bx, outcome.company_id)
    if not open_deal:
        outcome.final_status = "SKIPPED"
        reason = "liquidated_no_deal" if reason_id == "8538" else "low_revenue_no_deal"
        outcome.rejected_reason = reason_desc
        return StepOutcome("RANK_DEAL_VIABILITY", "SKIPPED", {"reason": reason, "reason_id": reason_id})
    outcome.deal_id = str(open_deal.get("ID") or "")
    context["deal_id"] = outcome.deal_id
    summary = auto_reject_telemarketing.run_deal(bx, deal_id=outcome.deal_id, dry_run=flags["dry_run"])
    outcome.final_status = "REJECTED"
    outcome.rejected_reason = reason_desc
    return StepOutcome("RANK_DEAL_VIABILITY", "DONE", {"reason_id": reason_id, "reason_desc": reason_desc, "auto_reject": summary})


def _step_resolve_deal(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    if outcome.final_status in {"REJECTED", "SKIPPED"}:
        return StepOutcome("RESOLVE_DEAL", "SKIPPED", {"reason": "final_status_already_set"})
    if context.get("attached_input_deal") and outcome.deal_id:
        context["deal_action"] = "sync"
        return StepOutcome("RESOLVE_DEAL", "DONE", {
            "action": "sync",
            "deal_id": outcome.deal_id,
            "attached_input_deal": True,
        })
    deals = bx.list_company_deals(outcome.company_id)
    open_deals = [d for d in deals if _is_open_c50(d)]
    lose_deals = [d for d in deals if str(d.get("STAGE_ID") or "") == TELEMARKETING_REVIVED_FROM_LOSE_STAGE and str(d.get("CLOSED") or "") == "Y"]
    apology_deals = [d for d in deals if str(d.get("STAGE_ID") or "") == "C50:APOLOGY" and str(d.get("CLOSED") or "") == "Y"]
    context.update({"open_deals": open_deals, "lose_deals": lose_deals, "apology_deals": apology_deals})
    if open_deals:
        outcome.deal_id = str(open_deals[0].get("ID") or "")
        context["deal_action"] = "sync"
    elif _due_lose_deal(lose_deals):
        outcome.deal_id = str(_due_lose_deal(lose_deals).get("ID") or "")
        context["deal_action"] = "revive_lose"
    elif _eligible_apology_deal(apology_deals):
        outcome.deal_id = str(_eligible_apology_deal(apology_deals).get("ID") or "")
        context["deal_action"] = "reactivate_apology"
    elif not deals:
        context["deal_action"] = "create"
    else:
        outcome.final_status = "SKIPPED"
        context["deal_action"] = "skip"
    return StepOutcome("RESOLVE_DEAL", "DONE", {"action": context.get("deal_action"), "deal_id": outcome.deal_id})


def _step_create_deal(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    if context.get("deal_action") != "create":
        return StepOutcome("CREATE_DEAL", "SKIPPED", {"reason": "not_needed"})
    if flags.get("no_create_deal"):
        context["deal_action"] = "skip"
        return StepOutcome("CREATE_DEAL", "SKIPPED", {"reason": "flag_no_create"})
    company = _company(bx, context)
    site = _primary_site(company)
    if not site:
        outcome.flags.append("no_site_skipped")
        outcome.final_status = "SKIPPED"
        context["deal_action"] = "skip"
        return StepOutcome("CREATE_DEAL", "SKIPPED", {"reason": "no_site_skipped"})
    rotation_index = _read_persistent_rotation_index()
    assignee = TELEMARKETING_ASSIGNEES[rotation_index % len(TELEMARKETING_ASSIGNEES)][0]
    fields = _new_deal_fields(bx, outcome.company_id, assignee)
    if flags["dry_run"]:
        outcome.deal_id = "DRY_RUN_DEAL"
        return StepOutcome("CREATE_DEAL", "DONE", {"dry_run": True, "fields": fields, "rotation_index": rotation_index})
    outcome.deal_id = _add_deal(bx, fields)
    _write_persistent_rotation_index(rotation_index + 1)
    context["deal_id"] = outcome.deal_id
    return StepOutcome("CREATE_DEAL", "DONE", {"deal_id": outcome.deal_id, "assignee": assignee})


def _step_sync_deal(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    if context.get("deal_action") not in {"sync", "create"} or not outcome.deal_id or outcome.deal_id == "DRY_RUN_DEAL":
        return StepOutcome("SYNC_DEAL", "SKIPPED", {"reason": "not_needed"})
    if flags["dry_run"] and context.get("attached_input_deal") and context.get("created_company"):
        return StepOutcome("SYNC_DEAL", "SKIPPED", {"reason": "dry_run_attached_input_deal"})
    summary = sync_deals.run(
        bx,
        deal_id=outcome.deal_id,
        dry_run=flags["dry_run"],
        overwrite=False,
        active_only=True,
        telemarketing_workflow=True,
    )
    return StepOutcome("SYNC_DEAL", "DONE" if not summary.get("failed") else "FAILED", {"summary": summary})


def _step_revive_deal(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    action = context.get("deal_action")
    if action not in {"revive_lose", "reactivate_apology"}:
        return StepOutcome("REVIVE_DEAL", "SKIPPED", {"reason": "not_needed"})
    deal = bx.get_deal(outcome.deal_id) or {}
    active_users = _active_user_ids(bx)
    assignee = _next_assignee(str(deal.get("ASSIGNED_BY_ID") or ""), active_users)
    if flags["dry_run"]:
        return StepOutcome("REVIVE_DEAL", "DONE", {"dry_run": True, "deal_id": outcome.deal_id, "new_assignee": assignee, "action": action})
    if action == "revive_lose":
        fields = {
            "STAGE_ID": TELEMARKETING_REVIVE_TARGET_STAGE,
            "CLOSED": "N",
            "SOURCE_ID": TELEMARKETING_REVIVE_SOURCE_ID,
            "ASSIGNED_BY_ID": assignee,
            REVIVE_COUNT_FIELD: _int_value(deal.get(REVIVE_COUNT_FIELD)) + 1,
            LAST_AUTO_ACTION_DESC_FIELD: f"enrich-full revive {date.today().isoformat()}",
        }
    else:
        fields = {
            "STAGE_ID": TELEMARKETING_NEW_STAGE_ID,
            "CLOSED": "N",
            "SOURCE_ID": TELEMARKETING_REVIVE_SOURCE_ID,
            "ASSIGNED_BY_ID": assignee,
            REACTIVATION_COUNT_FIELD: _int_value(deal.get(REACTIVATION_COUNT_FIELD)) + 1,
            LAST_AUTO_ACTION_DESC_FIELD: f"enrich-full reactivation {date.today().isoformat()}",
        }
    bx.update_deal(outcome.deal_id, fields, params={"REGISTER_SONET_EVENT": "Y"})
    bx.add_timeline_comment(owner_type_id=DEAL_OWNER_TYPE_ID, owner_id=outcome.deal_id, text="[enrich-full] сделка возвращена в работу")
    return StepOutcome("REVIVE_DEAL", "DONE", {"deal_id": outcome.deal_id, "fields": fields})


def _step_dedupe_contacts(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    if flags["skip_dedupe_contacts"]:
        return StepOutcome("DEDUPE_CONTACTS", "SKIPPED", {"reason": "skip_dedupe_contacts"})
    if flags["dry_run"] and context.get("created_company"):
        return StepOutcome("DEDUPE_CONTACTS", "SKIPPED", {"reason": "dry_run_created_company"})
    summary = dedupe_contacts.run_company(
        bx,
        company_id=outcome.company_id,
        dry_run=flags["dry_run"],
        attach_unrelated_company_contacts=False,
    )
    return StepOutcome("DEDUPE_CONTACTS", "DONE" if not summary.get("failed") else "FAILED", {"summary": summary})


def _step_enrich_director_inn(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    if flags["skip_director_inn"]:
        return StepOutcome("ENRICH_DIRECTOR_INN", "SKIPPED", {"reason": "skip_director_inn"})
    if flags["dry_run"] and context.get("created_company"):
        return StepOutcome("ENRICH_DIRECTOR_INN", "SKIPPED", {"reason": "dry_run_created_company"})
    try:
        from . import enrich_director_inn  # type: ignore
    except ImportError:
        outcome.flags.append("director_inn_unavailable")
        return StepOutcome("ENRICH_DIRECTOR_INN", "SKIPPED", {"flag": "director_inn_unavailable"})
    reqs = bx.list_company_requisites(outcome.company_id)
    if any(str(req.get("RQ_OGRNIP") or "").strip() for req in reqs):
        return StepOutcome("ENRICH_DIRECTOR_INN", "SKIPPED", {"reason": "individual_entrepreneur"})
    summary = enrich_director_inn.run_company(bx, company_id=outcome.company_id, dry_run=flags["dry_run"])
    return StepOutcome("ENRICH_DIRECTOR_INN", "DONE" if not summary.get("failed") else "FAILED", {"summary": summary})


def _step_telemarketing_dedupe_scoped(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    if flags["skip_telemarketing_dedupe"]:
        return StepOutcome("TELEMARKETING_DEDUPE_SCOPED", "SKIPPED", {"reason": "skip_telemarketing_dedupe"})
    if flags["dry_run"] and context.get("created_company"):
        return StepOutcome("TELEMARKETING_DEDUPE_SCOPED", "SKIPPED", {"reason": "dry_run_created_company"})
    summary = telemarketing_dedupe.run_company(bx, company_id=outcome.company_id, dry_run=flags["dry_run"], rotation_index=0)
    status = "DONE" if not summary.get("failed") and not summary.get("unresolved") else "PARTIAL"
    return StepOutcome("TELEMARKETING_DEDUPE_SCOPED", status, {"summary": summary})


def _step_write_audit(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    _write_audit(outcome)
    return StepOutcome("WRITE_AUDIT", "DONE", {"path": str(AUDIT_PATH), "dry_run": flags["dry_run"]})


def _step_return_outcome(bx: BitrixClient, outcome: FullEnrichmentOutcome, context: dict[str, Any], flags: dict[str, Any]) -> StepOutcome:
    if not outcome.final_status:
        statuses = {step.status for step in outcome.steps}
        outcome.final_status = "PARTIAL" if "PARTIAL" in statuses else "ENRICHED"
    _refresh_links(outcome)
    return StepOutcome("RETURN_OUTCOME", "DONE", {"final_status": outcome.final_status})


def _detect_input_kind(company_id: str, deal_id: str, inn: str, url: str) -> str:
    present = [(name, value) for name, value in (("company_id", company_id), ("deal_id", deal_id), ("inn", inn), ("url", url)) if str(value or "").strip()]
    if len(present) == 2 and present[0][0] == "deal_id" and present[1][0] == "url":
        return "deal_id"
    if len(present) != 1:
        raise ValueError("Нужен ровно один вход: company_id, deal_id, inn или url")
    return present[0][0]


def _find_company_by_url(bx: BitrixClient, url: str) -> dict | None:
    key = _site_key(url)
    candidates = bx.list_companies(filter_={"%WEB": key}, select=["ID", "TITLE", "WEB", "UF_*"])
    for company in candidates:
        if any(_site_key(item.get("VALUE") if isinstance(item, dict) else item) == key for item in company.get("WEB") or []):
            return company
    return candidates[0] if candidates else None


def _minimum_company_fields(context: dict[str, Any]) -> dict[str, Any]:
    title = _title_from_url(context.get("url", "")) or f"Компания {context.get('inn') or 'без названия'}"
    fields: dict[str, Any] = {"TITLE": title}
    if context.get("url"):
        fields["WEB"] = _web_values(context["url"])
        fields["UF_CRM_5DEF838D882A2"] = _normalize_url(context["url"])
    if context.get("inn"):
        fields["UF_CRM_1735331882180"] = context["inn"]
    if _looks_medical(title, context.get("url", "")):
        fields[UF_BRAND_FIELD] = UF_BRAND_BELBERRY
    return fields


def _add_company(bx: BitrixClient, fields: dict[str, Any]) -> str:
    if hasattr(bx, "add_company"):
        return bx.add_company(fields, params={"REGISTER_SONET_EVENT": "Y"})
    body = bx.call("crm.company.add", {"fields": fields, "params": {"REGISTER_SONET_EVENT": "Y"}})
    return str(body.get("result") or "")


def _add_deal(bx: BitrixClient, fields: dict[str, Any]) -> str:
    if hasattr(bx, "add_deal"):
        return bx.add_deal(fields, params={"REGISTER_SONET_EVENT": "Y"})
    body = bx.call("crm.deal.add", {"fields": fields, "params": {"REGISTER_SONET_EVENT": "Y"}})
    return str(body.get("result") or "")


def _company(bx: BitrixClient, context: dict[str, Any]) -> dict:
    if context.get("company_id") == "DRY_RUN_COMPANY" and isinstance(context.get("company"), dict):
        return context["company"]
    company = bx.get_company(context["company_id"]) or context.get("company") or {}
    context["company"] = company
    return company


def _first_requisite_inn(reqs: list[dict]) -> str:
    for req in reqs or []:
        inn = normalize_inn(req.get("RQ_INN"))
        if inn:
            return inn
    return ""


def _primary_site(company: dict) -> str:
    web = company.get("WEB") or []
    if isinstance(web, list):
        for item in web:
            value = item.get("VALUE") if isinstance(item, dict) else item
            if str(value or "").strip():
                return _normalize_url(str(value))
    return _normalize_url(str(company.get("UF_CRM_5DEF838D882A2") or ""))


def _first_open_c50_deal(bx: BitrixClient, company_id: str) -> dict | None:
    for deal in bx.list_company_deals(company_id):
        if _is_open_c50(deal):
            return deal
    return None


def _is_open_c50(deal: dict) -> bool:
    return (
        str(deal.get("CATEGORY_ID") or "") == str(TELEMARKETING_CATEGORY_ID)
        and str(deal.get("STAGE_ID") or "") in TELEMARKETING_OPEN_STAGES
        and str(deal.get("CLOSED") or "") != "Y"
    )


def _due_lose_deal(deals: list[dict]) -> dict | None:
    today = datetime.now(MOSCOW_TZ).date()
    for deal in deals:
        due = _date_from_value(deal.get(REVIVE_NEXT_COMMUNICATION_FIELD))
        if due and due <= today:
            return deal
    return None


def _eligible_apology_deal(deals: list[dict]) -> dict | None:
    today = datetime.now(MOSCOW_TZ).date()
    for deal in deals:
        reason = str(deal.get(HOLD_REASON_FIELD) or "")
        cooldown = COOLDOWN_BY_REASON_MONTHS.get(reason)
        if not isinstance(cooldown, int):
            continue
        close_date = _date_from_value(deal.get("CLOSEDATE") or deal.get("DATE_MODIFY"))
        if close_date and (today - close_date).days >= cooldown * 30:
            return deal
    return None


def _new_deal_fields(bx: BitrixClient, company_id: str, assignee: str) -> dict[str, Any]:
    company = bx.get_company(company_id) or {}
    deal_fields = sync_deals.build_deal_fields_from_company(company)
    title = _title_from_url(_primary_site(company)) or str(company.get("TITLE") or f"Компания {company_id}")
    fields: dict[str, Any] = {
        "TITLE": title,
        "CATEGORY_ID": TELEMARKETING_CATEGORY_ID,
        "STAGE_ID": TELEMARKETING_NEW_STAGE_ID,
        "SOURCE_ID": TELEMARKETING_SOURCE_ID,
        "CLOSED": "N",
        "OPENED": "Y",
        "COMPANY_ID": company_id,
        "ASSIGNED_BY_ID": assignee,
    }
    fields.update(deal_fields)
    return fields


def _active_user_ids(bx: BitrixClient) -> set[str]:
    try:
        return bx.list_active_users()
    except Exception:  # noqa: BLE001
        return {str(item[0]) for item in TELEMARKETING_ASSIGNEES}


def _next_assignee(current: str, active_users: set[str]) -> str:
    pool = [str(item[0]) for item in TELEMARKETING_ASSIGNEES if str(item[0]) in active_users] or [str(item[0]) for item in TELEMARKETING_ASSIGNEES]
    for item in pool:
        if item != current:
            return item
    return pool[0] if pool else current


def _address_updates(company: dict) -> dict[str, Any]:
    return enrich_empty_companies._fill_company_address_fields(_DryRunAddressBx(), "__dry_run__", company)


class _DryRunAddressBx:
    def update_company(self, company_id: str, fields: dict[str, Any]) -> bool:
        return True


def _has_verified_data(company: dict, reqs: list[dict]) -> bool:
    if str(company.get(COMPANY_UF_ORGANIZATION_STATUS) or "").strip():
        return True
    if any(str(req.get("RQ_OGRN") or req.get("RQ_OGRNIP") or "").strip() for req in reqs):
        return True
    return bool(company.get("REG_ADDRESS_CITY") or company.get("REG_ADDRESS_REGION") or company.get("UF_CRM_1737098549301") or company.get("REVENUE"))


def _write_audit(outcome: FullEnrichmentOutcome) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    exists = AUDIT_PATH.exists()
    with AUDIT_PATH.open("a", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "timestamp_msk",
            "company_id",
            "deal_id",
            "input_kind",
            "input_value",
            "final_status",
            "steps_done",
            "steps_skipped",
            "steps_failed",
            "duplicate_company_ids",
            "flags",
            "error_summary",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow({
            "timestamp_msk": outcome.timestamp,
            "company_id": outcome.company_id,
            "deal_id": outcome.deal_id,
            "input_kind": outcome.input_kind,
            "input_value": outcome.input_value,
            "final_status": outcome.final_status,
            "steps_done": json.dumps([s.step for s in outcome.steps if s.status == "DONE"], ensure_ascii=False),
            "steps_skipped": json.dumps([s.step for s in outcome.steps if s.status == "SKIPPED"], ensure_ascii=False),
            "steps_failed": json.dumps([asdict(s) for s in outcome.steps if s.status == "FAILED"], ensure_ascii=False),
            "duplicate_company_ids": json.dumps(outcome.duplicate_company_ids, ensure_ascii=False),
            "flags": json.dumps(outcome.flags, ensure_ascii=False),
            "error_summary": "; ".join(s.error for s in outcome.steps if s.error),
        })


def _read_persistent_rotation_index() -> int:
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return int(payload.get("rotation_index") or 0)
    except Exception:  # noqa: BLE001
        return 0


def _write_persistent_rotation_index(idx: int) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"rotation_index": idx}, ensure_ascii=False, indent=2), encoding="utf-8")


def _refresh_links(outcome: FullEnrichmentOutcome) -> None:
    if outcome.company_id:
        outcome.bitrix_links["company"] = f"https://{PORTAL_DOMAIN}/crm/company/details/{outcome.company_id}/"
    if outcome.deal_id and not outcome.deal_id.startswith("DRY_RUN"):
        outcome.bitrix_links["deal"] = f"https://{PORTAL_DOMAIN}/crm/deal/details/{outcome.deal_id}/"


def _done_step_names(outcome: FullEnrichmentOutcome) -> str:
    return ", ".join(step.step for step in outcome.steps if step.status == "DONE")


def _date_from_value(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _web_values(url: str) -> list[dict[str, str]]:
    normalized = _normalize_url(url)
    return [{"VALUE": normalized, "VALUE_TYPE": "WORK"}] if normalized else []


def _normalize_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw.rstrip("/")


def _site_key(url: str) -> str:
    parsed = urlparse(_normalize_url(url))
    host = (parsed.netloc or parsed.path).lower()
    return host[4:] if host.startswith("www.") else host


def _title_from_url(url: str) -> str:
    key = _site_key(url)
    return key or ""


def _looks_medical(title: str, url: str) -> bool:
    text = f"{title} {url}".lower()
    return any(token in text for token in ("med", "clinic", "клиник", "мед", "леч"))


def _now_iso() -> str:
    return datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")
