#!/usr/bin/env python3
"""Создание/обогащение компании для сделки Bitrix24 с проверкой результата."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Iterable, Mapping, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAPIError
from scripts.bitrix_deal_enrichment_inspect import _company_requisites
from scripts.bitrix_sales_data_quality_report import (
    BP_TEMPLATE_ID,
    CLIENT_SITE_FIELD_FALLBACKS,
    COMPANY_ENTITY_TYPE_ID,
    _client_site_field_codes,
    _extract_multi_values,
    _field_labels,
    _field_value_text,
    _load_entity_fields,
    _lower,
)
from scripts.bitrix_sales_enrichment_candidates import _call_list_all, _load_contacts, _portal_link, _valid_id
from scripts.bitrix_sync_deal_company_contacts import _load_auth_env, _normalize_links, _string_id, build_sync_plan

REQUISITE_ENTITY_TYPE_ID = 8
LEGAL_ADDRESS_TYPE_ID = 6

DEFAULT_DATA = {
    "deal_id": "214",
    "domain": "vegastom.ru",
    "company_title": 'ООО "ВЕГАСТОМ"',
    "company_full_title": 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ВЕГАСТОМ"',
    "inn": "7727212547",
    "kpp": "772701001",
    "ogrn": "1157746682268",
    "director_last_name": "Витехновский",
    "director_name": "Игорь",
    "director_second_name": "Витальевич",
    "director_post": "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР",
    "phone": "+7 495 331-66-11",
    "email": "info@vegastom.ru",
    "site": "https://vegastom.ru/",
    "postal_code": "117461",
    "city": "Москва",
    "address_1": "ул. Каховка, д. 33, к. 1",
    "country": "Россия",
}


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _normalize_domain(value: Any) -> str:
    raw = str(value or "").strip().lower()
    raw = raw.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return raw.strip("/ ")


def _truthy_text(value: Any) -> str:
    text = _field_value_text(value)
    return "" if text.lower() in {"false", "none", "null"} else text


def _env_field_codes(name: str) -> list[str]:
    return [item.strip() for item in str(os.environ.get(name) or "").split(",") if item.strip()]


def _deal_city_field_codes(fields: Mapping[str, Mapping[str, Any]]) -> list[str]:
    explicit = _env_field_codes("BITRIX_DEAL_CITY_FIELD")
    codes: list[str] = []
    for code in [*explicit, *fields.keys()]:
        if code in codes:
            continue
        labels = [_lower(label).replace("ё", "е") for label in _field_labels(code, fields.get(code, {}))]
        is_city = any(label == "город" or "город клиента" in label or "city" == label for label in labels)
        if code in explicit or is_city:
            codes.append(code)
    return codes


def _pick_empty_field_for_update(
    entity: Mapping[str, Any],
    *,
    field_codes: Sequence[str],
    value: str,
) -> tuple[str, str, dict[str, str]]:
    if not value:
        return "", "no_value", {}
    filled = {
        field_code: _truthy_text(entity.get(field_code))
        for field_code in field_codes
        if _truthy_text(entity.get(field_code))
    }
    if filled:
        return "", "already_filled", filled
    if not field_codes:
        return "", "field_not_found", {}
    if len(field_codes) > 1:
        return "", "ambiguous_fields", {}
    return field_codes[0], "planned", {}


def _deal_extra_fields(
    deal: Mapping[str, Any],
    *,
    data: Mapping[str, str],
    deal_fields_meta: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    updates: dict[str, Any] = {}
    notes: list[dict[str, Any]] = []

    city_codes = _deal_city_field_codes(deal_fields_meta)
    city_code, city_status, city_existing = _pick_empty_field_for_update(
        deal,
        field_codes=city_codes,
        value=str(data.get("city") or "").strip(),
    )
    if city_code:
        updates[city_code] = str(data.get("city") or "").strip()
    notes.append(
        {
            "field_kind": "city",
            "status": city_status,
            "selected_field": city_code,
            "candidate_fields": city_codes,
            "target_value": str(data.get("city") or "").strip(),
            "existing_values": city_existing,
        }
    )

    raw_client_site_codes = _client_site_field_codes(deal_fields_meta, include_fallbacks=True)
    present_client_site_codes = [code for code in raw_client_site_codes if code in deal_fields_meta]
    fallback_client_site_codes = [code for code in CLIENT_SITE_FIELD_FALLBACKS if code in present_client_site_codes]
    client_site_codes = [*fallback_client_site_codes, *[code for code in present_client_site_codes if code not in fallback_client_site_codes]]
    client_site_value = _normalize_domain(data.get("domain") or data.get("site") or "")
    site_code, site_status, site_existing = _pick_empty_field_for_update(
        deal,
        field_codes=client_site_codes,
        value=client_site_value,
    )
    if site_code:
        updates[site_code] = client_site_value
    notes.append(
        {
            "field_kind": "client_site",
            "status": site_status,
            "selected_field": site_code,
            "candidate_fields": client_site_codes,
            "target_value": client_site_value,
            "existing_values": site_existing,
        }
    )

    return updates, notes


def _merge_multifield(existing: Any, value: str, value_type: str) -> list[dict[str, str]]:
    items = [dict(item) for item in existing if isinstance(item, Mapping)] if isinstance(existing, list) else []
    value_digits = _digits(value)
    if value_digits and len(value_digits) >= 7:
        normalized_value = value_digits
    elif value_type == "WORK" and "." in value:
        normalized_value = _normalize_domain(value)
    else:
        normalized_value = str(value or "").strip().lower()
    for item in items:
        item_value = str(item.get("VALUE") or "").strip()
        item_digits = _digits(item_value)
        if item_digits and len(item_digits) >= 7:
            comparable = item_digits
        elif value_type == "WORK" and "." in item_value:
            comparable = _normalize_domain(item_value)
        else:
            comparable = item_value.lower()
        if comparable == normalized_value:
            return items
    if value:
        items.append({"VALUE": value, "VALUE_TYPE": value_type})
    return items


def _search_company_by_inn(auth: Any, inn: str) -> list[dict[str, Any]]:
    requisites = _call_list_all(
        auth,
        "crm.requisite.list",
        {
            "filter": {"ENTITY_TYPE_ID": COMPANY_ENTITY_TYPE_ID, "RQ_INN": _digits(inn)},
            "select": ["ID", "ENTITY_ID", "RQ_COMPANY_NAME", "RQ_COMPANY_FULL_NAME", "RQ_INN", "RQ_KPP", "RQ_OGRN"],
        },
    )
    company_ids = sorted({_valid_id(item.get("ENTITY_ID")) for item in requisites if _valid_id(item.get("ENTITY_ID"))}, key=int)
    companies: list[dict[str, Any]] = []
    for company_id in company_ids:
        company = auth.call_method("crm.company.get", {"id": company_id}, default={})
        if isinstance(company, dict) and company:
            company["_match_reason"] = "inn"
            company["_matched_requisites"] = [item for item in requisites if _valid_id(item.get("ENTITY_ID")) == company_id]
            companies.append(company)
    return companies


def _search_company_list(auth: Any, filters: Iterable[Mapping[str, Any]], *, reason: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for filter_data in filters:
        try:
            payload = auth.call_payload(
                "crm.company.list",
                {
                    "filter": dict(filter_data),
                    "select": ["ID", "TITLE", "WEB", "PHONE", "EMAIL", "ASSIGNED_BY_ID", "DATE_MODIFY", "*", "UF_*"],
                    "order": {"ID": "DESC"},
                    "start": 0,
                },
                default={},
            )
            result = payload.get("result") if isinstance(payload, Mapping) else []
            if isinstance(result, list):
                rows.extend(item for item in result if isinstance(item, dict))
        except BitrixAPIError:
            continue
    for row in rows:
        row["_match_reason"] = reason
    return rows


def _search_company_candidates(auth: Any, *, domain: str, title: str, inn: str) -> list[dict[str, Any]]:
    domain_clean = _normalize_domain(domain)
    domain_label = domain_clean.split(".", 1)[0]
    title_variants = [
        domain,
        domain_clean,
        domain_label,
        title,
        title.replace('"', ""),
        "ВЕГАСТОМ",
        "VEGASTOM",
    ]
    title_filters = [{"%TITLE": item} for item in title_variants if item]
    candidates = [
        *_search_company_by_inn(auth, inn),
        *_search_company_list(auth, title_filters, reason="title"),
    ]
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for company in candidates:
        company_id = _valid_id(company.get("ID"))
        if not company_id or company_id in seen:
            continue
        seen.add(company_id)
        unique.append(company)
    return unique


def _choose_company(candidates: Sequence[Mapping[str, Any]], *, domain: str, title: str) -> tuple[str, str]:
    if not candidates:
        return "", "create"
    inn_matches = [item for item in candidates if item.get("_match_reason") == "inn"]
    if len(inn_matches) == 1:
        return _valid_id(inn_matches[0].get("ID")), "reuse_by_inn"
    normalized_title = title.casefold()
    exact_title = [item for item in candidates if str(item.get("TITLE") or "").strip().casefold() == normalized_title]
    if len(exact_title) == 1:
        return _valid_id(exact_title[0].get("ID")), "reuse_by_exact_title"
    domain_clean = _normalize_domain(domain)
    web_matches = []
    for item in candidates:
        web_values = [_normalize_domain(value) for value in _extract_multi_values(item, "WEB")]
        if domain_clean in web_values:
            web_matches.append(item)
    if len(web_matches) == 1:
        return _valid_id(web_matches[0].get("ID")), "reuse_by_web"
    if len(candidates) == 1:
        return _valid_id(candidates[0].get("ID")), f"reuse_by_single_{candidates[0].get('_match_reason') or 'candidate'}"
    return "", "ambiguous"


def _load_industry_id(auth: Any) -> str:
    rows = _call_list_all(auth, "crm.status.list", {"filter": {"ENTITY_ID": "INDUSTRY"}})
    for row in rows:
        name = str(row.get("NAME") or "").casefold().replace("ё", "е")
        if "медицин" in name or "медицина" in name:
            return str(row.get("STATUS_ID") or "").strip()
    return ""


def _company_fields(company: Mapping[str, Any], data: Mapping[str, str], *, industry_id: str) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "TITLE": data["company_title"],
        "PHONE": _merge_multifield(company.get("PHONE"), data["phone"], "WORK"),
        "EMAIL": _merge_multifield(company.get("EMAIL"), data["email"], "WORK"),
        "WEB": _merge_multifield(company.get("WEB"), data["site"], "WORK"),
    }
    if industry_id:
        fields["INDUSTRY"] = industry_id
    return fields


def _requisite_preset_id(auth: Any) -> str:
    rows = _call_list_all(
        auth,
        "crm.requisite.preset.list",
        {
            "filter": {"ENTITY_TYPE_ID": COMPANY_ENTITY_TYPE_ID},
            "order": {"SORT": "ASC", "ID": "ASC"},
        },
    )
    if not rows:
        rows = _call_list_all(auth, "crm.requisite.preset.list", {"order": {"SORT": "ASC", "ID": "ASC"}})
    company_rows = [
        row
        for row in rows
        if str(row.get("ENTITY_TYPE_ID") or row.get("entityTypeId") or COMPANY_ENTITY_TYPE_ID) == str(COMPANY_ENTITY_TYPE_ID)
    ]
    rows = company_rows or rows
    active_rows = [row for row in rows if str(row.get("ACTIVE") or "Y").upper() != "N"]
    candidates = active_rows or rows
    for row in candidates:
        name = str(row.get("NAME") or "").casefold()
        if "организа" in name or "юр" in name:
            return _valid_id(row.get("ID"))
    return _valid_id(candidates[0].get("ID")) if candidates else "1"


def _requisite_fields(company_id: str, preset_id: str, data: Mapping[str, str]) -> dict[str, Any]:
    return {
        "ENTITY_TYPE_ID": COMPANY_ENTITY_TYPE_ID,
        "ENTITY_ID": int(company_id),
        "PRESET_ID": int(preset_id),
        "NAME": data["company_title"],
        "ACTIVE": "Y",
        "ADDRESS_ONLY": "N",
        "SORT": 500,
        "RQ_COMPANY_NAME": data["company_title"],
        "RQ_COMPANY_FULL_NAME": data["company_full_title"],
        "RQ_DIRECTOR": f"{data['director_last_name']} {data['director_name']} {data['director_second_name']}",
        "RQ_INN": data["inn"],
        "RQ_KPP": data["kpp"],
        "RQ_OGRN": data["ogrn"],
    }


def _address_fields(requisite_id: str, data: Mapping[str, str]) -> dict[str, Any]:
    return {
        "TYPE_ID": LEGAL_ADDRESS_TYPE_ID,
        "ENTITY_TYPE_ID": REQUISITE_ENTITY_TYPE_ID,
        "ENTITY_ID": int(requisite_id),
        "ADDRESS_1": data["address_1"],
        "CITY": data["city"],
        "POSTAL_CODE": data["postal_code"],
        "PROVINCE": data["city"],
        "COUNTRY": data["country"],
    }


def _find_requisite(requisites: Sequence[Mapping[str, Any]], inn: str) -> dict[str, Any]:
    for requisite in requisites:
        if _digits(requisite.get("RQ_INN")) == _digits(inn):
            return dict(requisite)
    return dict(requisites[0]) if requisites else {}


def _load_addresses(auth: Any, requisite_id: str) -> list[dict[str, Any]]:
    return _call_list_all(
        auth,
        "crm.address.list",
        {
            "filter": {"ENTITY_TYPE_ID": REQUISITE_ENTITY_TYPE_ID, "ENTITY_ID": requisite_id},
            "select": ["TYPE_ID", "ENTITY_TYPE_ID", "ENTITY_ID", "ADDRESS_1", "CITY", "POSTAL_CODE", "PROVINCE", "COUNTRY"],
        },
    )


def _deal_contact_ids(auth: Any, deal_id: str) -> list[str]:
    items = auth.call_method("crm.deal.contact.items.get", {"id": deal_id}, default=[])
    if not isinstance(items, list):
        return []
    return [str(item.get("CONTACT_ID")) for item in items if isinstance(item, Mapping) and item.get("CONTACT_ID")]


def _director_contact_id(auth: Any, deal: Mapping[str, Any], data: Mapping[str, str]) -> tuple[str, str]:
    deal_id = _valid_id(deal.get("ID"))
    deal_contact_ids = _deal_contact_ids(auth, deal_id)
    if deal_contact_ids:
        return deal_contact_ids[0], "reuse_deal_contact"
    contact_id = _valid_id(deal.get("CONTACT_ID"))
    if contact_id:
        return contact_id, "reuse_deal_primary_contact"
    rows = _call_list_all(
        auth,
        "crm.contact.list",
        {
            "filter": {
                "NAME": data["director_name"],
                "LAST_NAME": data["director_last_name"],
                "SECOND_NAME": data["director_second_name"],
            },
            "select": ["ID", "NAME", "LAST_NAME", "SECOND_NAME", "POST", "COMPANY_ID"],
        },
    )
    if rows:
        return _valid_id(rows[0].get("ID")), "reuse_exact_director_contact"
    return "", "create"


def _ensure_company_contact_link(auth: Any, *, company_id: str, contact_id: str, apply_changes: bool) -> dict[str, Any]:
    company_items = auth.call_method("crm.company.contact.items.get", {"id": company_id}, default=[])
    if not isinstance(company_items, list):
        company_items = []
    normalized = _normalize_links([item for item in company_items if isinstance(item, Mapping)])
    if contact_id in {str(item["CONTACT_ID"]) for item in normalized}:
        return {"status": "already_linked", "company_contact_items": company_items}
    fields = {"CONTACT_ID": int(contact_id), "SORT": 10, "IS_PRIMARY": "Y"}
    result = None
    if apply_changes:
        result = auth.call_method("crm.company.contact.add", {"id": company_id, "fields": fields}, default=None)
    return {"status": "planned" if not apply_changes else "linked", "fields": fields, "result": result}


def _sync_company_contacts_to_deal(auth: Any, *, deal_id: str, company_id: str, apply_changes: bool) -> dict[str, Any]:
    company_items = auth.call_method("crm.company.contact.items.get", {"id": company_id}, default=[])
    deal_items = auth.call_method("crm.deal.contact.items.get", {"id": deal_id}, default=[])
    if not isinstance(company_items, list):
        company_items = []
    if not isinstance(deal_items, list):
        deal_items = []
    plan = build_sync_plan(
        deal_id=deal_id,
        company_id=company_id,
        company_contact_items=[item for item in company_items if isinstance(item, Mapping)],
        deal_contact_items=[item for item in deal_items if isinstance(item, Mapping)],
    )
    applied = []
    if apply_changes:
        for addition in plan["additions"]:
            fields = {
                "CONTACT_ID": addition["CONTACT_ID"],
                "SORT": addition["SORT"],
                "IS_PRIMARY": addition["IS_PRIMARY"],
            }
            result = auth.call_method("crm.deal.contact.add", {"id": deal_id, "fields": fields}, default=None)
            applied.append({"fields": fields, "result": result})
    final_items = auth.call_method("crm.deal.contact.items.get", {"id": deal_id}, default=[]) if apply_changes else deal_items
    return {"plan": plan, "applied": applied, "final_deal_contact_items": final_items}


def enrich_deal_company(auth: Any, *, data: Mapping[str, str], apply_changes: bool, start_bp: bool, wait_seconds: int) -> dict[str, Any]:
    deal_id = str(data["deal_id"])
    deal = auth.call_method("crm.deal.get", {"id": deal_id}, default={})
    if not isinstance(deal, Mapping) or not deal:
        return {"ok": False, "status": "deal_not_found", "deal_id": deal_id}

    explicit_company_id = _valid_id(data.get("company_id"))
    if explicit_company_id:
        company_candidate = auth.call_method("crm.company.get", {"id": explicit_company_id}, default={})
        if not isinstance(company_candidate, Mapping) or not company_candidate:
            return {"ok": False, "status": "explicit_company_not_found", "deal_id": deal_id, "company_id": explicit_company_id}
        candidates = [dict(company_candidate, _match_reason="explicit_company_id")]
        selected_company_id, selection_reason = explicit_company_id, "reuse_by_explicit_company_id"
    else:
        candidates = _search_company_candidates(auth, domain=data["domain"], title=data["company_title"], inn=data["inn"])
        selected_company_id, selection_reason = _choose_company(candidates, domain=data["domain"], title=data["company_title"])
    if selection_reason == "ambiguous":
        return {
            "ok": False,
            "status": "ambiguous_company_candidates",
            "deal_id": deal_id,
            "candidates": [
                {
                    "id": _valid_id(item.get("ID")),
                    "title": str(item.get("TITLE") or ""),
                    "match_reason": str(item.get("_match_reason") or ""),
                    "web": _extract_multi_values(item, "WEB"),
                }
                for item in candidates
            ],
        }

    operations: list[dict[str, Any]] = []
    company: dict[str, Any] = {}
    industry_id = _load_industry_id(auth)

    if selected_company_id:
        company = auth.call_method("crm.company.get", {"id": selected_company_id}, default={})
        company = company if isinstance(company, dict) else {}
        fields = _company_fields(company, data, industry_id=industry_id)
        operations.append({"operation": "crm.company.update", "id": selected_company_id, "fields": fields, "reason": selection_reason})
        if apply_changes:
            auth.call_method("crm.company.update", {"id": selected_company_id, "fields": fields}, default=None)
        company_id = selected_company_id
    else:
        fields = _company_fields({}, data, industry_id=industry_id)
        operations.append({"operation": "crm.company.add", "fields": fields, "reason": selection_reason})
        if apply_changes:
            company_id = str(auth.call_method("crm.company.add", {"fields": fields, "params": {"REGISTER_SONET_EVENT": "N"}}, default=""))
        else:
            company_id = "DRY_RUN_COMPANY_ID"

    if apply_changes:
        company = auth.call_method("crm.company.get", {"id": company_id}, default={})
        company = company if isinstance(company, dict) else {}

    if company_id == "DRY_RUN_COMPANY_ID":
        preset_id = "DRY_RUN_PRESET_ID"
        requisites: list[dict[str, Any]] = []
    else:
        preset_id = _requisite_preset_id(auth)
        requisites = _company_requisites(auth, company_id)
    requisite = _find_requisite(requisites, data["inn"])
    requisite_fields = _requisite_fields(company_id if company_id != "DRY_RUN_COMPANY_ID" else "0", preset_id if preset_id != "DRY_RUN_PRESET_ID" else "1", data)
    if requisite:
        requisite_id = _valid_id(requisite.get("ID"))
        operations.append({"operation": "crm.requisite.update", "id": requisite_id, "fields": requisite_fields})
        if apply_changes:
            auth.call_method("crm.requisite.update", {"id": requisite_id, "fields": requisite_fields}, default=None)
    else:
        requisite_id = "DRY_RUN_REQUISITE_ID"
        operations.append({"operation": "crm.requisite.add", "fields": requisite_fields})
        if apply_changes:
            requisite_id = str(auth.call_method("crm.requisite.add", {"fields": requisite_fields}, default=""))

    address_fields = _address_fields(requisite_id if requisite_id != "DRY_RUN_REQUISITE_ID" else "0", data)
    addresses = [] if requisite_id.startswith("DRY_RUN") else _load_addresses(auth, requisite_id)
    legal_addresses = [item for item in addresses if str(item.get("TYPE_ID")) == str(LEGAL_ADDRESS_TYPE_ID)]
    address_operation = "crm.address.update" if legal_addresses else "crm.address.add"
    operations.append({"operation": address_operation, "fields": address_fields})
    if apply_changes:
        auth.call_method(address_operation, {"fields": address_fields}, default=None)

    contact_id, contact_reason = _director_contact_id(auth, deal, data)
    contact_fields = {
        "NAME": data["director_name"],
        "LAST_NAME": data["director_last_name"],
        "SECOND_NAME": data["director_second_name"],
        "POST": data["director_post"],
        "COMPANY_ID": int(company_id),
    }
    if contact_id:
        operations.append({"operation": "crm.contact.update", "id": contact_id, "fields": contact_fields, "reason": contact_reason})
        if apply_changes:
            auth.call_method("crm.contact.update", {"id": contact_id, "fields": contact_fields}, default=None)
    else:
        operations.append({"operation": "crm.contact.add", "fields": contact_fields, "reason": contact_reason})
        if apply_changes:
            contact_id = str(auth.call_method("crm.contact.add", {"fields": contact_fields}, default=""))
        else:
            contact_id = "DRY_RUN_CONTACT_ID"

    link_result = {"status": "planned"}
    if not company_id.startswith("DRY_RUN") and not contact_id.startswith("DRY_RUN"):
        link_result = _ensure_company_contact_link(auth, company_id=company_id, contact_id=contact_id, apply_changes=apply_changes)
    operations.append({"operation": "crm.company.contact.add", "result": link_result})

    deal_fields_meta = _load_entity_fields(auth, "crm.deal.fields")
    extra_deal_fields, extra_deal_field_notes = _deal_extra_fields(deal, data=data, deal_fields_meta=deal_fields_meta)
    deal_fields = {"COMPANY_ID": int(company_id), **extra_deal_fields}
    operations.append(
        {
            "operation": "crm.deal.update",
            "id": deal_id,
            "fields": deal_fields,
            "extra_field_notes": extra_deal_field_notes,
        }
    )
    if apply_changes:
        auth.call_method("crm.deal.update", {"id": deal_id, "fields": deal_fields}, default=None)

    sync_result = {"status": "planned"}
    if not company_id.startswith("DRY_RUN"):
        sync_result = _sync_company_contacts_to_deal(auth, deal_id=deal_id, company_id=company_id, apply_changes=apply_changes)
    operations.append({"operation": "sync_company_contacts_to_deal", "result": sync_result})

    bp_result = None
    if start_bp and not company_id.startswith("DRY_RUN"):
        bp_params = {
            "TEMPLATE_ID": int(BP_TEMPLATE_ID),
            "DOCUMENT_ID": ["crm", "CCrmDocumentCompany", f"COMPANY_{company_id}"],
            "PARAMETERS": {},
        }
        operations.append({"operation": "bizproc.workflow.start", "params": bp_params})
        if apply_changes:
            bp_result = auth.call_method("bizproc.workflow.start", bp_params, default=None)
            if wait_seconds > 0:
                time.sleep(wait_seconds)

    final: dict[str, Any] = {}
    if apply_changes:
        final_deal = auth.call_method("crm.deal.get", {"id": deal_id}, default={})
        final_company = auth.call_method("crm.company.get", {"id": company_id}, default={})
        final_requisites = _company_requisites(auth, company_id)
        final_addresses = _load_addresses(auth, _valid_id(final_requisites[0].get("ID"))) if final_requisites else []
        final_company_items = auth.call_method("crm.company.contact.items.get", {"id": company_id}, default=[])
        final_deal_items = auth.call_method("crm.deal.contact.items.get", {"id": deal_id}, default=[])
        contact_ids = {
            str(item.get("CONTACT_ID"))
            for item in [*(final_company_items if isinstance(final_company_items, list) else []), *(final_deal_items if isinstance(final_deal_items, list) else [])]
            if isinstance(item, Mapping) and item.get("CONTACT_ID")
        }
        contacts = _load_contacts(auth, contact_ids)
        final = {
            "deal_company_id": _valid_id(final_deal.get("COMPANY_ID")) if isinstance(final_deal, Mapping) else "",
            "company": final_company,
            "requisites": final_requisites,
            "addresses": final_addresses,
            "company_contact_items": final_company_items,
            "deal_contact_items": final_deal_items,
            "contacts": contacts,
        }

    return {
        "ok": True,
        "status": "applied" if apply_changes else "dry_run",
        "deal_id": deal_id,
        "company_id": company_id,
        "contact_id": contact_id,
        "candidate_count": len(candidates),
        "candidates": [
            {
                "id": _valid_id(item.get("ID")),
                "title": str(item.get("TITLE") or ""),
                "match_reason": str(item.get("_match_reason") or ""),
                "web": _extract_multi_values(item, "WEB"),
            }
            for item in candidates
        ],
        "selection_reason": selection_reason,
        "bp_result": bp_result,
        "operations": operations,
        "final": final,
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Создать/обогатить компанию и связки для сделки Bitrix24.")
    parser.add_argument("--deal-id", default=DEFAULT_DATA["deal_id"])
    parser.add_argument("--company-id", default="")
    parser.add_argument("--domain", default="")
    parser.add_argument("--company-title", default="")
    parser.add_argument("--company-full-title", default="")
    parser.add_argument("--inn", default="")
    parser.add_argument("--kpp", default="")
    parser.add_argument("--ogrn", default="")
    parser.add_argument("--director-last-name", default="")
    parser.add_argument("--director-name", default="")
    parser.add_argument("--director-second-name", default="")
    parser.add_argument("--director-post", default="")
    parser.add_argument("--phone", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--site", default="")
    parser.add_argument("--postal-code", default="")
    parser.add_argument("--city", default="")
    parser.add_argument("--address-1", default="")
    parser.add_argument("--country", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-bp", action="store_true")
    parser.add_argument("--allow-default-data", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=8)
    parser.add_argument("--no-remote-bridge", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    data = dict(DEFAULT_DATA)
    data["deal_id"] = str(args.deal_id)
    override_fields = {
        "company_id": args.company_id,
        "domain": args.domain,
        "company_title": args.company_title,
        "company_full_title": args.company_full_title,
        "inn": args.inn,
        "kpp": args.kpp,
        "ogrn": args.ogrn,
        "director_last_name": args.director_last_name,
        "director_name": args.director_name,
        "director_second_name": args.director_second_name,
        "director_post": args.director_post,
        "phone": args.phone,
        "email": args.email,
        "site": args.site,
        "postal_code": args.postal_code,
        "city": args.city,
        "address_1": args.address_1,
        "country": args.country,
    }
    has_overrides = any(str(value or "").strip() for value in override_fields.values())
    if data["deal_id"] != DEFAULT_DATA["deal_id"] and not has_overrides and not args.allow_default_data:
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": "default_data_blocked",
                    "message": "Для сделки, отличной от DEFAULT_DATA, укажи реквизиты явно или --allow-default-data.",
                    "deal_id": data["deal_id"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    for key, value in override_fields.items():
        if str(value or "").strip():
            data[key] = str(value).strip()
    auth, tmp_dir = _load_auth_env(use_remote_bridge=not args.no_remote_bridge)
    try:
        payload = enrich_deal_company(
            auth,
            data=data,
            apply_changes=bool(args.apply),
            start_bp=not bool(args.no_bp),
            wait_seconds=int(args.wait_seconds),
        )
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
