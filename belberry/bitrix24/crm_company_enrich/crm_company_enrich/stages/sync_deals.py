"""Синхронизация кастомных полей сделки из обогащённой компании.

Эта стадия закрывает разрыв между company-enrich и CRM-сделками: BP/DaData
наполняют карточку компании и реквизиты, но поля сделки вроде «Сайт клиента»,
«Город», «ИНН», «Оборот» не всегда подтягиваются автоматически.

Безопасность:
- команда требует явный --company-id или --deal-id;
- по умолчанию заполняет только пустые поля сделки;
- --overwrite нужен для принудительной перезаписи;
- dry-run не пишет в Bitrix.
"""
from __future__ import annotations

import re
import io
import contextlib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..bitrix_client import BitrixClient
from ..region_rf_config import REGION_RF_VALUES
from ..config import (
    COMPANY_REGION_ENUM_MAP,
    COMPANY_UF_RUSPROFILE_CHECKO_URL,
    COMPANY_UF_CITY,
    COMPANY_UF_ORGANIZATION_STATUS,
    COMPANY_UF_REGION,
    COMPANY_ORGANIZATION_STATUS_ENUM,
    COMPANY_INDUSTRY_STATUS,
    DEAL_BRAND_ENUM,
    DEAL_REGION_ENUM_MAP,
    DEAL_INDUSTRY_ENUM,
    DEAL_UF_BRAND_PROJECT,
    DEAL_UF_CITY,
    DEAL_UF_REGION,
    DEAL_UF_INDUSTRY,
    DEAL_UF_INN,
    DEAL_UF_REVENUE_MONEY,
    DEAL_UF_REVENUE_NUMBER,
    DEAL_UF_REVENUE_TEXT,
    DEAL_UF_RUSPROFILE_URL,
    DEAL_UF_SITE_MULTI,
    DEAL_UF_SITE_PRIMARY,
    HOLD_MARKER_FLAG_FIELD,
    MANDATORY_DEAL_SYNC_FIELDS,
    TELEMARKETING_ASSIGNEES,
    TELEMARKETING_CATEGORY_ID,
    TELEMARKETING_NEW_STAGE_ID,
    TELEMARKETING_REFUSAL_SEMANTIC,
    TELEMARKETING_REFUSAL_STAGE_IDS,
    TELEMARKETING_SOURCE_ID,
    UF_BRAND_FIELD,
    UF_BRAND_ACOOLA,
    UF_BRAND_BELBERRY,
)
from ..models import is_medical_company, normalize_inn


@dataclass
class SyncOutcome:
    deal_id: str
    company_id: str
    status: str
    fields: dict[str, Any]
    skipped: dict[str, str]
    company_fields: dict[str, Any] | None = None
    company_skipped: dict[str, str] | None = None
    contacts_added: list[str] | None = None
    company_contacts_added: list[str] | None = None
    contacts_skipped: dict[str, str] | None = None
    contact_communications: dict[str, dict[str, Any]] | None = None
    error: str = ""


@dataclass
class CompanySyncOutcome:
    company_id: str
    status: str
    fields: dict[str, Any]
    skipped: dict[str, str]
    error: str = ""


@dataclass
class SiteVerification:
    site: str
    working: bool
    identity_verified: bool
    evidence: list[str]


DEAL_SELECT = [
    "ID",
    "TITLE",
    "COMPANY_ID",
    "CATEGORY_ID",
    "STAGE_ID",
    "CLOSED",
    "ASSIGNED_BY_ID",
    DEAL_UF_SITE_PRIMARY,
    DEAL_UF_SITE_MULTI,
    DEAL_UF_BRAND_PROJECT,
    DEAL_UF_CITY,
    DEAL_UF_REGION,
    DEAL_UF_INN,
    DEAL_UF_REVENUE_TEXT,
    DEAL_UF_REVENUE_MONEY,
    DEAL_UF_REVENUE_NUMBER,
    DEAL_UF_INDUSTRY,
    DEAL_UF_RUSPROFILE_URL,
]


def run_company(
    bx: BitrixClient,
    *,
    company_id: str,
    inn: str = "",
    site: str = "",
    dry_run: bool = True,
    overwrite: bool = False,
    dedupe_telemarketing: bool = False,
) -> dict:
    if not company_id:
        raise ValueError("Нужен company_id")

    company_id = str(company_id)
    company = bx.get_company(str(company_id))
    if not company:
        outcome = CompanySyncOutcome(str(company_id), "COMPANY_NOT_FOUND", {}, {}, "company not found")
        return {
            "dry_run": dry_run,
            "overwrite": overwrite,
            "examined": 1,
            "updated": 0,
            "dry_run_updates": 0,
            "noop": 0,
            "failed": 1,
            "outcomes": [outcome.__dict__],
        }

    effective_inn = _clean(inn) or _clean(company.get("UF_CRM_1735331882180"))
    enriched_company = dict(company)
    if effective_inn:
        enriched_company["UF_CRM_1735331882180"] = effective_inn

    organization_status = _organization_status_from_inn(effective_inn) if effective_inn else ""
    industry_override = _industry_from_inn(effective_inn) if effective_inn else ""
    desired = build_company_fields_from_company(
        enriched_company,
        organization_status=organization_status,
        industry_override=industry_override,
    )
    if effective_inn:
        desired["UF_CRM_1735331882180"] = effective_inn

    site_verification = _verified_site(site, enriched_company, effective_inn)
    if not site_verification.identity_verified:
        site_verification = _verified_site_from_company(enriched_company, effective_inn)
    if site_verification.identity_verified:
        desired["UF_CRM_5DEF838D882A2"] = site_verification.site

    existing_industry = _clean(company.get("INDUSTRY"))
    if industry_override == "Медицина" or existing_industry == COMPANY_INDUSTRY_STATUS["Медицина"]:
        brand = UF_BRAND_BELBERRY
    else:
        brand = _deal_brand_from_company(enriched_company)
    if brand:
        desired[UF_BRAND_FIELD] = brand

    fields, skipped = _filter_existing_fields(company, desired, overwrite=overwrite)
    _allow_dead_site_replacement(
        fields,
        skipped,
        company,
        desired,
        site_field="UF_CRM_5DEF838D882A2",
    )
    if not fields:
        outcome = CompanySyncOutcome(str(company_id), "NOOP", {}, skipped)
        summary = {
            "dry_run": dry_run,
            "overwrite": overwrite,
            "examined": 1,
            "updated": 0,
            "dry_run_updates": 0,
            "noop": 1,
            "failed": 0,
            "outcomes": [outcome.__dict__],
        }
        _attach_scoped_dedupe_summary(
            bx,
            summary,
            company_ids=[company_id],
            dry_run=dry_run,
            dedupe_telemarketing=dedupe_telemarketing,
        )
        return summary

    if dry_run:
        outcome = CompanySyncOutcome(str(company_id), "DRY_RUN", fields, skipped)
        summary = {
            "dry_run": dry_run,
            "overwrite": overwrite,
            "examined": 1,
            "updated": 0,
            "dry_run_updates": 1,
            "noop": 0,
            "failed": 0,
            "outcomes": [outcome.__dict__],
        }
        _attach_scoped_dedupe_summary(
            bx,
            summary,
            company_ids=[company_id],
            dry_run=dry_run,
            dedupe_telemarketing=dedupe_telemarketing,
        )
        return summary

    try:
        bx.update_company(str(company_id), fields)
    except Exception as exc:  # noqa: BLE001
        outcome = CompanySyncOutcome(str(company_id), "FAILED", fields, skipped, str(exc)[:300])
        return {
            "dry_run": dry_run,
            "overwrite": overwrite,
            "examined": 1,
            "updated": 0,
            "dry_run_updates": 0,
            "noop": 0,
            "failed": 1,
            "outcomes": [outcome.__dict__],
        }

    outcome = CompanySyncOutcome(str(company_id), "UPDATED", fields, skipped)
    summary = {
        "dry_run": dry_run,
        "overwrite": overwrite,
        "examined": 1,
        "updated": 1,
        "dry_run_updates": 0,
        "noop": 0,
        "failed": 0,
        "outcomes": [outcome.__dict__],
    }
    _attach_scoped_dedupe_summary(
        bx,
        summary,
        company_ids=[company_id],
        dry_run=dry_run,
        dedupe_telemarketing=dedupe_telemarketing,
    )
    return summary


def run(
    bx: BitrixClient,
    *,
    company_id: str | None = None,
    deal_id: str | None = None,
    dry_run: bool = True,
    overwrite: bool = False,
    active_only: bool = True,
    limit: int | None = None,
    telemarketing_workflow: bool = False,
    rotation_index: int = 0,
    dedupe_telemarketing: bool = False,
) -> dict:
    if not company_id and not deal_id:
        raise ValueError("Нужен company_id или deal_id")

    deals = _resolve_deals(bx, company_id=company_id, deal_id=deal_id, active_only=active_only)
    if limit:
        deals = deals[:limit]

    outcomes: list[SyncOutcome] = []
    updated = 0
    dry = 0
    noop = 0
    failed = 0
    missing_company = 0
    company_updated = 0
    company_dry = 0
    contacts_added = 0
    contacts_dry = 0
    company_contacts_added = 0
    company_contacts_dry = 0
    contact_communications_updated = 0
    contact_communications_dry = 0
    processed_company_ids: set[str] = set()

    for deal in deals:
        did = str(deal.get("ID") or "")
        cid = str(deal.get("COMPANY_ID") or company_id or "")
        if not did or not cid:
            outcomes.append(SyncOutcome(did, cid, "FAILED", {}, {}, error="deal has no ID/COMPANY_ID"))
            failed += 1
            continue
        processed_company_ids.add(cid)

        company = bx.get_company(cid)
        if not company:
            outcomes.append(SyncOutcome(did, cid, "COMPANY_NOT_FOUND", {}, {}, error="company not found"))
            missing_company += 1
            continue

        inn = _clean(company.get("UF_CRM_1735331882180"))
        organization_status = _organization_status_from_inn(inn) if inn else ""
        industry_override = _industry_from_inn(inn) if inn else ""
        company_fields, company_skipped = _company_fields(
            company,
            organization_status=organization_status,
            industry_override=industry_override,
        )
        desired = build_deal_fields_from_company(company, industry_override=industry_override)
        fields, skipped = _filter_existing_fields(deal, desired, overwrite=overwrite)
        if telemarketing_workflow:
            tm_fields, tm_skipped = build_telemarketing_existing_deal_fields(
                deal,
                rotation_index=rotation_index,
            )
            fields.update(tm_fields)
            skipped.update(tm_skipped)
        _allow_dead_site_replacement(
            fields,
            skipped,
            deal,
            desired,
            site_field=DEAL_UF_SITE_PRIMARY,
        )
        contacts_to_add, contacts_skipped = _missing_deal_contacts(bx, cid, did)
        contact_ids = _deal_company_contact_ids(
            bx,
            company_id=cid,
            deal_id=did,
            contacts_to_add=contacts_to_add,
        )
        contact_communications = _contact_communication_updates(bx, company, contact_ids)
        company_contacts_to_add, company_contact_skipped = _missing_company_contacts(bx, cid, did)
        contacts_skipped.update(company_contact_skipped)

        if not fields and not company_fields and not contacts_to_add and not company_contacts_to_add and not contact_communications:
            outcomes.append(SyncOutcome(did, cid, "NOOP", {}, skipped, {}, company_skipped, [], [], contacts_skipped, {}))
            noop += 1
            continue

        if dry_run:
            outcomes.append(SyncOutcome(did, cid, "DRY_RUN", fields, skipped, company_fields, company_skipped, contacts_to_add, company_contacts_to_add, contacts_skipped, contact_communications))
            if fields:
                dry += 1
            if company_fields:
                company_dry += 1
            contacts_dry += len(contacts_to_add)
            company_contacts_dry += len(company_contacts_to_add)
            contact_communications_dry += len(contact_communications)
            continue

        try:
            if company_fields:
                bx.update_company(cid, company_fields)
                company_updated += 1
            if fields:
                bx.update_deal(did, fields)
            added_now = []
            for contact_id in contacts_to_add:
                if bx.add_deal_contact(did, contact_id):
                    added_now.append(contact_id)
            company_added_now = []
            for contact_id in company_contacts_to_add:
                if bx.add_contact_company_relation(contact_id, cid):
                    company_added_now.append(contact_id)
            updated_contact_communications = {}
            for contact_id, contact_fields in contact_communications.items():
                if bx.update_contact(contact_id, contact_fields):
                    updated_contact_communications[contact_id] = contact_fields
        except Exception as exc:  # noqa: BLE001
            outcomes.append(SyncOutcome(did, cid, "FAILED", fields, skipped, company_fields, company_skipped, contacts_to_add, company_contacts_to_add, contacts_skipped, contact_communications, str(exc)[:300]))
            failed += 1
            continue

        contacts_added += len(added_now)
        company_contacts_added += len(company_added_now)
        contact_communications_updated += len(updated_contact_communications)
        outcomes.append(SyncOutcome(did, cid, "UPDATED", fields, skipped, company_fields, company_skipped, added_now, company_added_now, contacts_skipped, updated_contact_communications))
        if fields:
            updated += 1

    summary = {
        "dry_run": dry_run,
        "overwrite": overwrite,
        "active_only": active_only,
        "telemarketing_workflow": telemarketing_workflow,
        "examined": len(deals),
        "updated": updated,
        "dry_run_updates": dry,
        "noop": noop,
        "missing_company": missing_company,
        "company_updated": company_updated,
        "company_dry_run_updates": company_dry,
        "contacts_added": contacts_added,
        "contacts_dry_run_adds": contacts_dry,
        "company_contacts_added": company_contacts_added,
        "company_contacts_dry_run_adds": company_contacts_dry,
        "contact_communications_updated": contact_communications_updated,
        "contact_communications_dry_run_updates": contact_communications_dry,
        "failed": failed,
        "outcomes": [o.__dict__ for o in outcomes],
    }
    _attach_scoped_dedupe_summary(
        bx,
        summary,
        company_ids=sorted(processed_company_ids, key=lambda x: int(x) if x.isdigit() else x),
        dry_run=dry_run,
        dedupe_telemarketing=dedupe_telemarketing,
    )
    return summary


def _attach_scoped_dedupe_summary(
    bx: BitrixClient,
    summary: dict,
    *,
    company_ids: list[str],
    dry_run: bool,
    dedupe_telemarketing: bool,
) -> None:
    if not dedupe_telemarketing:
        return
    from .telemarketing_dedupe import run_company as dedupe_run_company

    dedupe_by_company = {
        company_id: dedupe_run_company(
            bx,
            company_id=company_id,
            dry_run=dry_run,
            rotation_index=0,
        )
        for company_id in company_ids
    }
    if len(dedupe_by_company) == 1:
        summary["telemarketing_dedupe"] = next(iter(dedupe_by_company.values()))
    else:
        summary["telemarketing_dedupe"] = dedupe_by_company


def telemarketing_assignee_for_new_deal(*, rotation_index: int = 0) -> str:
    """Ответственный для новой сделки: простая ротация по пулу телемаркетинга."""
    return _assignee_by_rotation(rotation_index)


def build_telemarketing_existing_deal_fields(
    deal: dict[str, Any],
    *,
    rotation_index: int = 0,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Поля возврата существующей сделки в телемаркетинг.

    Правило:
    - отказная сделка на Дарье возвращается Аркадию;
    - отказная сделка на Аркадии возвращается Дарье;
    - отказная сделка на другом ответственном возвращается по ротации;
    - неотказная сделка не переназначается;
    - SOURCE_ID существующей сделки не меняется. Телемаркетинг ставится только
      при создании новой сделки.
    """
    if _is_auto_rejected_deal(deal):
        return {}, {
            "STAGE_ID": "auto_reject_closed",
            "CLOSED": "auto_reject_closed",
            "ASSIGNED_BY_ID": "auto_reject_closed",
        }

    fields: dict[str, Any] = {
        "CATEGORY_ID": TELEMARKETING_CATEGORY_ID,
        "STAGE_ID": TELEMARKETING_NEW_STAGE_ID,
        "CLOSED": "N",
    }
    skipped: dict[str, str] = {}

    current_stage = _clean(deal.get("STAGE_ID"))
    current_assignee = _clean(deal.get("ASSIGNED_BY_ID"))
    if _is_refusal_deal(deal):
        fields["ASSIGNED_BY_ID"] = telemarketing_assignee_for_refusal(
            current_assignee,
            rotation_index=rotation_index,
        )
    else:
        skipped["ASSIGNED_BY_ID"] = "not_refusal_deal"
        if current_stage == TELEMARKETING_NEW_STAGE_ID:
            skipped["STAGE_ID"] = "already_in_work"
    return fields, skipped


def _is_auto_rejected_deal(deal: dict[str, Any]) -> bool:
    marker = deal.get(HOLD_MARKER_FLAG_FIELD)
    marker_set = marker is True or str(marker or "").strip().upper() in {"1", "Y", "TRUE"}
    return marker_set and str(deal.get("CLOSED") or "").strip().upper() == "Y"


def telemarketing_assignee_for_refusal(
    current_assignee_id: str,
    *,
    rotation_index: int = 0,
) -> str:
    """Ответственный при возврате отказной сделки в работу."""
    current = _clean(current_assignee_id)
    assignee_ids = [str(item[0]) for item in TELEMARKETING_ASSIGNEES]
    if current in assignee_ids:
        for assignee_id in assignee_ids:
            if assignee_id != current:
                return assignee_id
    return _assignee_by_rotation(rotation_index)


def _assignee_by_rotation(rotation_index: int) -> str:
    assignee_ids = [str(item[0]) for item in TELEMARKETING_ASSIGNEES]
    if not assignee_ids:
        raise ValueError("TELEMARKETING_ASSIGNEES is empty")
    return assignee_ids[int(rotation_index) % len(assignee_ids)]


def _is_refusal_deal(deal: dict[str, Any]) -> bool:
    stage_id = _clean(deal.get("STAGE_ID"))
    if stage_id in TELEMARKETING_REFUSAL_STAGE_IDS:
        return True
    # Доп. защита: если Bitrix указал STAGE_SEMANTIC_ID="F" (failure),
    # это отказ, даже если STATUS_ID не в нашем списке. Защищает от
    # появления новых отказных стадий в воронке.
    if _clean(deal.get("STAGE_SEMANTIC_ID")) == TELEMARKETING_REFUSAL_SEMANTIC:
        return True
    return False


def _missing_deal_contacts(bx: BitrixClient, company_id: str, deal_id: str) -> tuple[list[str], dict[str, str]]:
    """Контакты компании, которых ещё нет в сделке.

    Bitrix не подтягивает связи контактов автоматически при создании сделки по
    COMPANY_ID, поэтому переносим только уже существующие связи company→contact.
    Новые контакты здесь не создаются.
    """
    company_contacts_full = _company_contacts_full_for_attach(bx, company_id)
    company_contacts = [str(c.get("ID") or "") for c in company_contacts_full if str(c.get("ID") or "").strip()]
    if not company_contacts:
        return [], {}

    existing_raw = bx.list_deal_contacts(deal_id)
    existing = {
        str(item.get("CONTACT_ID") or item.get("ID") or "")
        for item in existing_raw
        if isinstance(item, dict)
    }
    missing: list[str] = []
    skipped: dict[str, str] = {}
    seen: set[str] = set()
    by_fio: dict[str, list[dict]] = {}
    for contact in company_contacts_full:
        by_fio.setdefault(_contact_attach_fio(contact), []).append(contact)

    for contact in company_contacts_full:
        contact_id = str(contact.get("ID") or "")
        if not contact_id:
            continue
        if contact_id in seen:
            skipped[contact_id] = "duplicate_company_contact"
            continue
        seen.add(contact_id)
        if contact_id in existing:
            skipped[contact_id] = "already_linked"
            continue
        if _is_placeholder_contact_for_attach(contact):
            fio = _contact_attach_fio(contact)
            has_real_alternative = any(
                not _is_placeholder_contact_for_attach(other)
                and str(other.get("ID") or "") != contact_id
                for other in by_fio.get(fio, [])
            )
            if has_real_alternative:
                skipped[contact_id] = "placeholder_has_real_contact"
                continue
        missing.append(contact_id)
    return missing, skipped


def _missing_company_contacts(bx: BitrixClient, company_id: str, deal_id: str) -> tuple[list[str], dict[str, str]]:
    """Найти контакты сделки, которые надо привязать к компании."""
    if not hasattr(bx, "add_contact_company_relation"):
        return [], {"company_contact_relation": "unsupported"}
    company_contacts = {str(cid) for cid in bx.get_company_contacts(company_id) if str(cid).strip()}
    deal_contacts = [
        str(item.get("CONTACT_ID") or item.get("ID") or "")
        for item in bx.list_deal_contacts(deal_id)
        if str(item.get("CONTACT_ID") or item.get("ID") or "").strip()
    ]
    missing: list[str] = []
    skipped: dict[str, str] = {}
    for contact_id in deal_contacts:
        if contact_id in company_contacts:
            skipped[f"company_contact:{contact_id}"] = "already_linked"
            continue
        contact = bx.get_contact(contact_id) or {}
        contact_company_id = _clean(contact.get("COMPANY_ID"))
        if contact_company_id and contact_company_id not in {"0", company_id}:
            skipped[f"company_contact:{contact_id}"] = f"other_primary_company:{contact_company_id}"
            continue
        missing.append(contact_id)
    return missing, skipped


def _company_contacts_full_for_attach(bx: BitrixClient, company_id: str) -> list[dict]:
    if hasattr(bx, "list_company_contacts_full"):
        contacts = bx.list_company_contacts_full(company_id)
        if contacts:
            return [c for c in contacts if isinstance(c, dict)]

    out: list[dict] = []
    for contact_id in bx.get_company_contacts(company_id):
        cid = str(contact_id or "")
        if not cid:
            continue
        contact = bx.get_contact(cid) if hasattr(bx, "get_contact") else None
        if isinstance(contact, dict) and contact:
            out.append(contact)
        else:
            out.append({"ID": cid})
    return out


def _contact_attach_fio(contact: dict) -> str:
    parts = [str(contact.get(k) or "").strip() for k in ("LAST_NAME", "NAME", "SECOND_NAME")]
    joined = " ".join(p for p in parts if p).lower()
    joined = re.sub(r"^!\s*", "", joined)
    joined = joined.replace(".", " ")
    joined = re.sub(r"\s+", " ", joined).strip()
    return joined


def _is_placeholder_contact_for_attach(contact: dict) -> bool:
    if _is_director_contact_for_attach(contact):
        return False
    last_name = str(contact.get("LAST_NAME") or "").strip()
    return last_name == "!" or last_name.startswith("! ")


def _is_director_contact_for_attach(contact: dict) -> bool:
    post = f"{contact.get('POST') or ''} {contact.get('TITLE') or ''}".lower()
    return any(
        keyword in post
        for keyword in ("директор", "руководитель", "гендиректор", "управляющий", "ceo", "general", "founder")
    )


def _deal_company_contact_ids(
    bx: BitrixClient,
    *,
    company_id: str,
    deal_id: str,
    contacts_to_add: list[str],
) -> list[str]:
    company_contacts = [str(cid) for cid in bx.get_company_contacts(company_id) if str(cid).strip()]
    if not company_contacts:
        return []

    linked_raw = bx.list_deal_contacts(deal_id)
    linked = {
        str(item.get("CONTACT_ID") or item.get("ID") or "")
        for item in linked_raw
        if isinstance(item, dict)
    }
    linked.update(str(cid) for cid in contacts_to_add)

    result: list[str] = []
    seen: set[str] = set()
    for contact_id in company_contacts:
        if contact_id in seen or contact_id not in linked:
            continue
        seen.add(contact_id)
        result.append(contact_id)
    return result


def _contact_communication_updates(
    bx: BitrixClient,
    company: dict[str, Any],
    contact_ids: list[str],
) -> dict[str, dict[str, Any]]:
    company_phone = _multi_values(company.get("PHONE"))
    company_email = _multi_values(company.get("EMAIL"))
    if not company_phone and not company_email:
        return {}

    updates: dict[str, dict[str, Any]] = {}
    for contact_id in contact_ids:
        contact = bx.get_contact(contact_id)
        if not contact:
            continue
        fields: dict[str, Any] = {}
        if company_phone and not _multi_values(contact.get("PHONE")):
            fields["PHONE"] = company_phone
        if company_email and not _multi_values(contact.get("EMAIL")):
            fields["EMAIL"] = company_email
        if fields:
            updates[str(contact_id)] = fields
    return updates


def _multi_values(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        raw = item.get("VALUE") if isinstance(item, dict) else item
        cleaned = _clean(raw)
        if not cleaned:
            continue
        value_type = _clean(item.get("VALUE_TYPE") if isinstance(item, dict) else "") or "WORK"
        type_id = _clean(item.get("TYPE_ID") if isinstance(item, dict) else "")
        key = (type_id, cleaned)
        if key in seen:
            continue
        seen.add(key)
        normalized = {"VALUE": cleaned, "VALUE_TYPE": value_type}
        if type_id:
            normalized["TYPE_ID"] = type_id
        out.append(normalized)
    return out


def build_deal_fields_from_company(
    company: dict[str, Any],
    *,
    industry_override: str = "",
) -> dict[str, Any]:
    site_primary = _verified_site_from_company(company, _clean(company.get("UF_CRM_1735331882180"))).site
    sites = _site_values(company, site_primary)
    inn = _clean(company.get("UF_CRM_1735331882180"))
    city = _clean(company.get(COMPANY_UF_CITY) or company.get("REG_ADDRESS_CITY") or company.get("ADDRESS_CITY"))
    region = _company_region_for_deal(company)
    revenue = _clean(
        company.get("UF_CRM_1737098549301")
        or company.get("UF_CRM_1584876707")
        or company.get("REVENUE")
    )

    out: dict[str, Any] = {}
    if site_primary:
        out[DEAL_UF_SITE_PRIMARY] = site_primary
    if sites:
        out[DEAL_UF_SITE_MULTI] = sites
    if inn:
        out[DEAL_UF_INN] = inn
        out[DEAL_UF_RUSPROFILE_URL] = _rusprofile_url(inn)
    if city:
        out[DEAL_UF_CITY] = city
    if DEAL_UF_REGION and region:
        out[DEAL_UF_REGION] = region
    if revenue and revenue != "0":
        out[DEAL_UF_REVENUE_TEXT] = revenue
        out[DEAL_UF_REVENUE_NUMBER] = _number_or_string(revenue)
        out[DEAL_UF_REVENUE_MONEY] = f"{revenue}|RUB"

    brand = _deal_brand_from_company(company)
    brand_id = DEAL_BRAND_ENUM.get(brand)
    if brand_id:
        out[DEAL_UF_BRAND_PROJECT] = brand_id

    industry = industry_override or _industry_from_company(company)
    industry_id = DEAL_INDUSTRY_ENUM.get(industry, "")
    if industry_id:
        out[DEAL_UF_INDUSTRY] = industry_id

    return out


def build_company_fields_from_company(
    company: dict[str, Any],
    *,
    organization_status: str = "",
    industry_override: str = "",
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    industry = industry_override or _industry_from_company(company)
    industry_id = COMPANY_INDUSTRY_STATUS.get(industry, "")
    if industry_id:
        out["INDUSTRY"] = industry_id

    inn = _clean(company.get("UF_CRM_1735331882180"))
    if inn:
        out[COMPANY_UF_RUSPROFILE_CHECKO_URL] = _rusprofile_url(inn)
    organization_status_id = COMPANY_ORGANIZATION_STATUS_ENUM.get(organization_status, "")
    if organization_status_id:
        out[COMPANY_UF_ORGANIZATION_STATUS] = organization_status_id
    return out


def _company_region_for_deal(company: dict[str, Any]) -> str:
    company_region = _clean(company.get(COMPANY_UF_REGION))
    if company_region:
        if not DEAL_REGION_ENUM_MAP and DEAL_UF_REGION != COMPANY_UF_REGION:
            return _region_label_from_company_enum(company_region) or company_region
        return company_region
    raw_region = _clean(company.get("REG_ADDRESS_REGION") or company.get("ADDRESS_REGION"))
    if not raw_region:
        return ""
    if DEAL_REGION_ENUM_MAP:
        return _resolve_region_enum(raw_region, DEAL_REGION_ENUM_MAP)
    if COMPANY_REGION_ENUM_MAP and DEAL_UF_REGION == COMPANY_UF_REGION:
        return _resolve_region_enum(raw_region, COMPANY_REGION_ENUM_MAP)
    return raw_region


def _region_label_from_company_enum(enum_id: str) -> str:
    reverse: dict[str, str] = {}
    for value in REGION_RF_VALUES:
        enum_value = COMPANY_REGION_ENUM_MAP.get(_normalize_region_key(value))
        if enum_value:
            reverse[enum_value] = value
    return reverse.get(_clean(enum_id), "")


def _resolve_region_enum(raw_region: str, mapping: dict[str, str]) -> str:
    return mapping.get(_normalize_region_key(raw_region), "")


def _normalize_region_key(raw_region: str) -> str:
    norm = _clean(raw_region).lower()
    norm = re.sub(r"\([^)]*\)", "", norm)
    norm = re.split(r"\s+[—-]\s+", norm, maxsplit=1)[0]
    for token in (
        "автономный округ",
        "народная",
        "республика",
        "область",
        "край",
        "обл.",
        "обл ",
        "респ.",
        "респ ",
        "ао",
        "г.",
        "город ",
    ):
        norm = norm.replace(token, "")
    return re.sub(r"\s+", " ", norm).strip(" .,-")


def _deal_brand_from_company(company: dict[str, Any]) -> str:
    existing = _clean(company.get(UF_BRAND_FIELD))
    if existing in DEAL_BRAND_ENUM:
        return existing

    is_med = is_medical_company(
        bitrix_title=_clean(company.get("TITLE")),
        discovered_name=_clean(company.get("UF_CRM_1737098414068")),
        web=_first_non_empty(
            company.get("UF_CRM_5DEF838D882A2"),
            _first_multifield(company.get("WEB")),
            company.get("UF_CRM_1737098525088"),
        ),
        domain=_clean(company.get("UF_CRM_1737098525088")),
    )
    return UF_BRAND_BELBERRY if is_med else UF_BRAND_ACOOLA


def _resolve_deals(
    bx: BitrixClient,
    *,
    company_id: str | None,
    deal_id: str | None,
    active_only: bool,
) -> list[dict]:
    if deal_id:
        deal = bx.get_deal(str(deal_id))
        if not deal:
            return []
        # get_deal не всегда возвращает UF, поэтому добираем через list по ID.
        body = bx.call(
            "crm.deal.list",
            {"filter": {"ID": str(deal_id)}, "select": DEAL_SELECT, "start": -1},
        )
        rows = body.get("result")
        deals = rows if isinstance(rows, list) else [deal]
    else:
        deals = bx.list_company_deals(str(company_id), select=DEAL_SELECT)

    if active_only:
        deals = [d for d in deals if str(d.get("CLOSED") or "N") != "Y"]
    return deals


def _filter_existing_fields(
    deal: dict[str, Any],
    desired: dict[str, Any],
    *,
    overwrite: bool,
) -> tuple[dict[str, Any], dict[str, str]]:
    fields: dict[str, Any] = {}
    skipped: dict[str, str] = {}
    for key, value in desired.items():
        if _is_empty(value):
            continue
        current = deal.get(key)
        if key in MANDATORY_DEAL_SYNC_FIELDS:
            if not _same_value(current, value):
                fields[key] = value
            else:
                skipped[key] = "mandatory_already_synced"
            continue
        if _can_refine_placeholder_field(key, current, value):
            fields[key] = value
            continue
        if not overwrite and not _is_empty(current):
            skipped[key] = "already_filled"
            continue
        if _same_value(current, value):
            skipped[key] = "same_value"
            continue
        fields[key] = value
    return fields, skipped


def _can_refine_placeholder_field(key: str, current: Any, desired: Any) -> bool:
    """Разрешить замену общего placeholder-значения на более точную классификацию."""
    if key == "INDUSTRY":
        return _same_value(current, COMPANY_INDUSTRY_STATUS["Другое"]) and not _same_value(
            desired,
            COMPANY_INDUSTRY_STATUS["Другое"],
        )
    if key == DEAL_UF_INDUSTRY:
        return _clean(current) in {"2122", "604"} and _clean(desired) not in {"2122", "604"}
    return False


def _allow_dead_site_replacement(
    fields: dict[str, Any],
    skipped: dict[str, str],
    current_row: dict[str, Any],
    desired: dict[str, Any],
    *,
    site_field: str,
) -> None:
    desired_site = _clean(desired.get(site_field))
    current_site = _clean(current_row.get(site_field))
    if not desired_site or not current_site:
        return
    if site_field not in skipped:
        return
    if _verified_site(current_site, current_row, _clean(current_row.get("UF_CRM_1735331882180"))).identity_verified:
        return
    fields[site_field] = desired_site
    skipped.pop(site_field, None)


def _company_fields(
    company: dict[str, Any],
    *,
    organization_status: str = "",
    industry_override: str = "",
) -> tuple[dict[str, Any], dict[str, str]]:
    desired = build_company_fields_from_company(
        company,
        organization_status=organization_status,
        industry_override=industry_override,
    )
    if not desired:
        return {}, {"company": "no_fields"}
    fields, skipped = _filter_existing_fields(company, desired, overwrite=True)
    current_industry = _clean(company.get("INDUSTRY"))
    desired_industry = _clean(desired.get("INDUSTRY"))
    if (
        fields.get("INDUSTRY") == COMPANY_INDUSTRY_STATUS["Другое"]
        and current_industry
        and current_industry != COMPANY_INDUSTRY_STATUS["Другое"]
    ):
        fields.pop("INDUSTRY", None)
        skipped["INDUSTRY"] = "keep_specific_industry"
    elif (
        desired_industry
        and current_industry == COMPANY_INDUSTRY_STATUS["Другое"]
        and desired_industry != COMPANY_INDUSTRY_STATUS["Другое"]
    ):
        fields["INDUSTRY"] = desired_industry
        skipped.pop("INDUSTRY", None)
    return fields, skipped


def _industry_from_company(company: dict[str, Any]) -> str:
    text = " ".join(
        _clean(company.get(k))
        for k in (
            "UF_CRM_1737100327954",
            "TITLE",
            "UF_CRM_1737098414068",
            "UF_CRM_1737098422264",
        )
    )
    parsed = _industry_from_text(text)
    if parsed:
        return parsed

    industry_value = _clean(company.get("INDUSTRY"))
    for label, enum_id in COMPANY_INDUSTRY_STATUS.items():
        if industry_value == enum_id:
            return label
    return ""


def _industry_from_text(text: str, *, fallback_other: bool = False) -> str:
    text = _clean(text).lower()
    if any(s in text for s in ("47.", "рознич", "магазин", "интернет-магаз", "e-commerce", "маркетплейс")):
        return "E-commerce"
    if any(s in text for s in ("86.", "клиник", "медицин", "медцентр", "медико", "стомат", "дент", "доктор", "doctor", "врач")):
        return "Медицина"
    if any(s in text for s in ("туризм", "турист", "турагент", "туроператор", "путешеств", "отдых")):
        return "Туризм, отдых, путешествия"
    if any(s in text for s in ("оптов", "50.30", "автомобильными детал", "автодетал")):
        return "Другое"
    if fallback_other and text:
        return "Другое"
    return ""


def _site_values(company: dict[str, Any], primary: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    if primary:
        normalized_primary = _normalize_site_url(primary)
        if normalized_primary:
            values.append(normalized_primary)
            seen.add(_site_key(normalized_primary))
    inn_val = _clean(company.get("UF_CRM_1735331882180"))
    for item in company.get("WEB") or []:
        if isinstance(item, dict):
            v = _clean(item.get("VALUE"))
            key = _site_key(v)
            verification = _verified_site(v, company, inn_val)
            normalized = _normalize_site_url(v)
            if normalized and key not in seen and verification.working:
                values.append(normalized)
                seen.add(key)
    multi = _clean(company.get("UF_CRM_1737098525088"))
    for raw in multi.replace(";", "\n").splitlines():
        v = _clean(raw)
        key = _site_key(v)
        verification = _verified_site(v, company, inn_val)
        normalized = _normalize_site_url(v)
        if normalized and key not in seen and verification.working:
            values.append(normalized)
            seen.add(key)
    return values


def _verified_site_from_company(company: dict[str, Any], inn: str = "") -> SiteVerification:
    first_working: SiteVerification | None = None
    for candidate in _site_candidates(company):
        verification = _verified_site(candidate, company, inn)
        if verification.identity_verified:
            return SiteVerification(
                _normalize_site_url(verification.site),
                verification.working,
                verification.identity_verified,
                verification.evidence,
            )
        if verification.working and first_working is None:
            first_working = SiteVerification(
                _normalize_site_url(verification.site),
                verification.working,
                verification.identity_verified,
                verification.evidence,
            )
    return first_working or SiteVerification("", False, False, [])


def _working_site(value: str) -> str:
    cleaned = _clean(value)
    return cleaned if cleaned and _is_working_site(cleaned) else ""


def _verified_site(value: str, company: dict[str, Any], inn: str = "") -> SiteVerification:
    site = _clean(value)
    if not site:
        return SiteVerification("", False, False, [])
    if not _is_working_site(site):
        return SiteVerification(site, False, False, [])

    evidence = _site_identity_evidence(site, company, inn)
    return SiteVerification(site, True, bool(evidence), evidence)


def _site_identity_evidence(site: str, company: dict[str, Any], inn: str = "") -> list[str]:
    text = _site_identity_text(site)
    if not text:
        return []

    lowered = text.lower()
    compact_digits = re.sub(r"\D+", "", text)
    evidence: list[str] = []

    normalized_inn = normalize_inn(inn) or normalize_inn(_clean(company.get("UF_CRM_1735331882180"))) or ""
    if normalized_inn and normalized_inn in compact_digits:
        evidence.append(f"site_contains_inn:{normalized_inn}")

    for req in company.get("REQUISITES") or []:
        ogrn = re.sub(r"\D+", "", _clean(req.get("RQ_OGRN") or req.get("RQ_OGRNIP")))
        if ogrn and ogrn in compact_digits:
            evidence.append(f"site_contains_ogrn:{ogrn}")

    title = _clean(company.get("TITLE"))
    title_tokens = [t for t in re.split(r"[\s\"'«».,()]+", title.lower()) if len(t) >= 4]
    if title_tokens and any(token in lowered for token in title_tokens):
        evidence.append("site_contains_company_title")

    for field in ("PHONE", "EMAIL"):
        for item in company.get(field) or []:
            value = _clean(item.get("VALUE") if isinstance(item, dict) else item)
            if not value:
                continue
            if field == "PHONE":
                phone_digits = re.sub(r"\D+", "", value)
                if phone_digits and phone_digits[-10:] in compact_digits:
                    evidence.append("site_contains_phone")
            elif value.lower() in lowered:
                evidence.append("site_contains_email")
    return evidence


def _site_identity_text(site: str) -> str:
    texts: list[str] = []
    urls = _site_identity_urls(site)
    for url in urls:
        text = _fetch_site_text(url)
        if text:
            texts.append(text)
    return "\n".join(texts)


def _site_identity_urls(site: str) -> list[str]:
    base_urls = _site_probe_urls(site)
    if not base_urls:
        return []
    root = base_urls[0]
    parsed = urllib.parse.urlsplit(root)
    base = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    paths = (
        "/",
        "/contacts/",
        "/kontakty/",
        "/about/",
        "/o-kompanii/",
        "/rekvizity/",
        "/requisites/",
        "/upload/docs/15_rekvizity.pdf",
        "/upload/Anti-Corruption_Policy.pdf",
    )
    urls = [urllib.parse.urljoin(base, path) for path in paths]
    root_text = _fetch_site_text(root)
    for href in re.findall(r"href=[\"']([^\"']+)[\"']", root_text, flags=re.IGNORECASE):
        lowered = href.lower()
        if not any(marker in lowered for marker in ("rekviz", "requisit", "реквиз", "pdf", "policy", "docs")):
            continue
        absolute = urllib.parse.urljoin(base, href)
        parsed_href = urllib.parse.urlsplit(absolute)
        if parsed_href.netloc == parsed.netloc and absolute not in urls:
            urls.append(absolute)
        if len(urls) >= 12:
            break
    return urls[:12]


def _fetch_site_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 Cloudbot identity-check"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            status = getattr(resp, "status", 0)
            if status and status >= 400 and status not in {401, 403}:
                return ""
            content_type = str(resp.headers.get("Content-Type") or "").lower()
            data = resp.read(2_000_000)
    except Exception:  # noqa: BLE001
        return ""
    if "pdf" in content_type or url.lower().split("?", 1)[0].endswith(".pdf"):
        return _extract_pdf_text(data)
    return data.decode("utf-8", errors="ignore")


def _extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore

        with contextlib.redirect_stderr(io.StringIO()):
            reader = PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages[:5])
    except Exception:  # noqa: BLE001
        return data.decode("utf-8", errors="ignore")


def _site_candidates(company: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for value in (
        company.get("UF_CRM_5DEF838D882A2"),
        _first_multifield(company.get("WEB")),
        company.get("UF_CRM_1737098525088"),
    ):
        for candidate in _split_site_values(value):
            key = _site_key(candidate)
            if candidate and key and key not in seen:
                candidates.append(candidate)
                seen.add(key)
    return candidates


def _split_site_values(value: Any) -> list[str]:
    raw = _clean(value)
    if not raw:
        return []
    return [part.strip() for part in re.split(r"[;,\n]+", raw) if part.strip()]


def _is_working_site(value: str) -> bool:
    for url in _site_probe_urls(value):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 Cloudbot site-check"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
                status = getattr(resp, "status", 0)
                if 200 <= status < 400 or status in {401, 403}:
                    return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _site_probe_urls(value: str) -> list[str]:
    cleaned = _clean(value).strip().strip("/")
    if not cleaned:
        return []
    if not re.match(r"^https?://", cleaned, flags=re.IGNORECASE):
        cleaned = f"https://{cleaned}"
    parsed = urllib.parse.urlsplit(cleaned)
    host = parsed.hostname or ""
    if not host:
        return []
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return []
    netloc = ascii_host
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    path = parsed.path or "/"
    https_url = urllib.parse.urlunsplit(("https", netloc, path, parsed.query, ""))
    http_url = urllib.parse.urlunsplit(("http", netloc, path, parsed.query, ""))
    return [https_url, http_url] if https_url != http_url else [https_url]


def _rusprofile_url(inn: str) -> str:
    return f"https://www.rusprofile.ru/search?query={inn}"


def _organization_status_from_inn(inn: str) -> str:
    html = _fetch_rusprofile_html(inn)
    if not html:
        return ""
    return _parse_organization_status(html)


def _industry_from_inn(inn: str) -> str:
    html = _fetch_rusprofile_html(inn)
    if not html:
        return ""
    activity = _parse_main_activity(html)
    return _industry_from_text(activity, fallback_other=True)


def _parse_main_activity(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    patterns = (
        r"Основной вид деятельности.+?[-—:]\s*(.+?)(?:\s+и\s+\d+\s+дополнительн|\. Состоит|$)",
        r"Основной вид деятельности\s*[:\-—]\s*(.+?)(?:\s+Дополнительные|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" .;")
    return ""


def _parse_organization_status(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).lower()
    if any(marker in text for marker in (
        "ликвидированная организация",
        "организация ликвидирована",
        "статус ликвидировано",
        "статус: ликвидировано",
        "прекратила деятельность",
        "прекращение деятельности",
        "есть решение фнс о ликвидации",
        "решение фнс о ликвидации",
        "в стадии банкротства",
        "признано несостоятельным",
        "признана несостоятельным",
        "конкурсное производство",
        "конкурсный управляющий",
    )):
        return "Ликвидирована"
    if any(marker in text for marker in (
        "действующая организация",
        "действующее юридическое лицо",
        "статус действующее",
        "статус: действующее",
        "имеет статус действующее",
        "действует с",
    )):
        return "Действующая"
    return ""


def parse_organization_status(html: str) -> str:
    """Публичная обёртка парсинга статуса организации из HTML rusprofile."""
    return _parse_organization_status(html)


def _fetch_rusprofile_html(inn: str) -> str:
    req = urllib.request.Request(
        _rusprofile_url(inn),
        headers={"User-Agent": "Mozilla/5.0 Cloudbot enrichment"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:  # noqa: S310
            status = getattr(resp, "status", 0)
            if status and status >= 400:
                return ""
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""


def fetch_rusprofile_html(inn: str) -> str:
    """Публичная обёртка загрузки HTML rusprofile по ИНН."""
    return _fetch_rusprofile_html(inn)


def _site_key(value: str) -> str:
    cleaned = _clean(value).strip().rstrip("/").lower()
    if not cleaned:
        return ""
    if cleaned.startswith(("mailto:", "tel:", "javascript:")):
        return ""
    if not re.match(r"^https?://", cleaned):
        cleaned = "https://" + cleaned
    try:
        host = urllib.parse.urlsplit(cleaned).hostname or ""
        if host.startswith("www."):
            host = host[4:]
        return host
    except ValueError:
        return cleaned


def _normalize_site_url(value: str) -> str:
    cleaned = _clean(value).strip().rstrip("/")
    if not cleaned:
        return ""
    cleaned = re.sub(r"^https?://", "", cleaned, flags=re.IGNORECASE)
    return "https://" + cleaned


def _first_multifield(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    for item in values:
        if isinstance(item, dict):
            value = _clean(item.get("VALUE"))
            if value:
                return value
    return ""


def _first_non_empty(*values: Any) -> str:
    for value in values:
        cleaned = _clean(value)
        if cleaned:
            return cleaned
    return ""


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return ""
    return str(value).strip()


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if value is False:
        return True
    if isinstance(value, str):
        return value.strip() in {"", "0"}
    if isinstance(value, list):
        return len(value) == 0
    return False


def _same_value(current: Any, desired: Any) -> bool:
    if isinstance(current, list) or isinstance(desired, list):
        return current == desired
    return _clean(current) == _clean(desired)


def _number_or_string(value: str) -> int | str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits and digits == value:
        return int(digits)
    return value
