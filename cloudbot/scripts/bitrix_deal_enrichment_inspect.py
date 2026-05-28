#!/usr/bin/env python3
"""Read-only инспекция сделки Bitrix24 для оценки обогащения."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.bitrix_sales_data_quality_report import (
    BP_TEMPLATE_ID,
    COMPANY_ENTITY_TYPE_ID,
    DEFAULT_PORTAL_BASE_URL,
    _client_site_field_codes,
    _extract_multi_values,
    _field_value_text,
    _first_field_value,
    _load_entity_fields,
    _load_running_bp_instances,
)
from scripts.bitrix_sales_enrichment_candidates import _call_list_all, _contact_name, _load_contacts, _portal_link, _valid_id
from scripts.bitrix_sync_deal_company_contacts import _load_auth_env, _string_id, build_sync_plan


def _company_requisites(auth: Any, company_id: str) -> list[dict[str, Any]]:
    return _call_list_all(
        auth,
        "crm.requisite.list",
        {
            "filter": {"ENTITY_TYPE_ID": COMPANY_ENTITY_TYPE_ID, "ENTITY_ID": company_id},
            "select": [
                "ID",
                "ENTITY_ID",
                "RQ_COMPANY_NAME",
                "RQ_COMPANY_FULL_NAME",
                "RQ_INN",
                "RQ_KPP",
                "RQ_OGRN",
                "RQ_OGRNIP",
            ],
        },
    )


def _search_companies_by_title(auth: Any, query: str) -> list[dict[str, Any]]:
    query = " ".join(str(query or "").replace(".", " ").replace("-", " ").split()).strip()
    if not query:
        return []
    candidates = []
    for token in [query, query.upper(), query.lower()]:
        candidates.extend(
            _call_list_all(
                auth,
                "crm.company.list",
                {
                    "filter": {"%TITLE": token},
                    "select": ["ID", "TITLE", "WEB", "PHONE", "EMAIL", "ASSIGNED_BY_ID", "DATE_MODIFY", "*", "UF_*"],
                    "order": {"ID": "DESC"},
                },
                page_limit=2,
            )
        )
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in candidates:
        company_id = _string_id(item.get("ID"))
        if company_id and company_id not in seen:
            seen.add(company_id)
            unique.append(item)
    return unique[:20]


def _search_companies_by_inn(auth: Any, inn: str) -> list[dict[str, Any]]:
    inn = "".join(ch for ch in str(inn or "") if ch.isdigit())
    if not inn:
        return []
    requisites = _call_list_all(
        auth,
        "crm.requisite.list",
        {
            "filter": {"ENTITY_TYPE_ID": COMPANY_ENTITY_TYPE_ID, "RQ_INN": inn},
            "select": [
                "ID",
                "ENTITY_ID",
                "RQ_COMPANY_NAME",
                "RQ_COMPANY_FULL_NAME",
                "RQ_INN",
                "RQ_KPP",
                "RQ_OGRN",
                "RQ_OGRNIP",
            ],
        },
    )
    company_ids = sorted({_valid_id(item.get("ENTITY_ID")) for item in requisites if _valid_id(item.get("ENTITY_ID"))}, key=int)
    companies: list[dict[str, Any]] = []
    for company_id in company_ids:
        company = auth.call_method("crm.company.get", {"id": company_id}, default={})
        if isinstance(company, dict) and company:
            company["_matched_requisites"] = [item for item in requisites if _valid_id(item.get("ENTITY_ID")) == company_id]
            companies.append(company)
    return companies


def _contact_items(auth: Any, method: str, entity_id: str) -> list[dict[str, Any]]:
    if not entity_id:
        return []
    items = auth.call_method(method, {"id": entity_id}, default=[])
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _short_contact(contact: Mapping[str, Any], *, portal_base_url: str) -> dict[str, str]:
    contact_id = _string_id(contact.get("ID"))
    return {
        "id": contact_id,
        "name": _contact_name(contact),
        "post": str(contact.get("POST") or "").strip(),
        "url": _portal_link(f"crm/contact/details/{contact_id}/", portal_base_url=portal_base_url) if contact_id else "",
    }


def inspect_deal(
    auth: Any,
    *,
    deal_id: str,
    portal_base_url: str,
    bp_template_id: str,
    inn: str = "",
    company_title: str = "",
) -> dict[str, Any]:
    deal = auth.call_method("crm.deal.get", {"id": deal_id}, default={})
    if not isinstance(deal, Mapping) or not deal:
        return {"ok": False, "status": "deal_not_found", "deal_id": deal_id}

    deal_fields = _load_entity_fields(auth, "crm.deal.fields")
    company_fields = _load_entity_fields(auth, "crm.company.fields")
    client_site, client_site_source = _first_field_value(deal, _client_site_field_codes(deal_fields, include_fallbacks=True))
    company_id = _valid_id(deal.get("COMPANY_ID"))
    company = auth.call_method("crm.company.get", {"id": company_id}, default={}) if company_id else {}
    company = company if isinstance(company, Mapping) else {}
    if not client_site and company:
        client_site, client_site_source = _first_field_value(company, _client_site_field_codes(company_fields, include_fallbacks=False))

    deal_contact_items = _contact_items(auth, "crm.deal.contact.items.get", deal_id)
    company_contact_items = _contact_items(auth, "crm.company.contact.items.get", company_id) if company_id else []
    plan = (
        build_sync_plan(
            deal_id=deal_id,
            company_id=company_id,
            company_contact_items=company_contact_items,
            deal_contact_items=deal_contact_items,
        )
        if company_id
        else {}
    )
    contact_ids = {str(item.get("CONTACT_ID") or "") for item in [*deal_contact_items, *company_contact_items] if isinstance(item, Mapping)}
    for item in plan.get("additions", []) if isinstance(plan, Mapping) else []:
        if isinstance(item, Mapping):
            contact_ids.add(str(item.get("CONTACT_ID") or ""))
    contacts = _load_contacts(auth, contact_ids)
    requisites = _company_requisites(auth, company_id) if company_id else []
    running_bp = _load_running_bp_instances(auth, [company_id], template_id=bp_template_id).get(company_id, []) if company_id else []

    title = str(deal.get("TITLE") or "")
    search_text = client_site or title
    company_candidates = [*_search_companies_by_title(auth, search_text), *_search_companies_by_title(auth, company_title), *_search_companies_by_inn(auth, inn)]
    seen_company_ids: set[str] = set()
    candidate_rows = []
    for candidate in company_candidates:
        candidate_id = _string_id(candidate.get("ID"))
        if not candidate_id or candidate_id in seen_company_ids:
            continue
        seen_company_ids.add(candidate_id)
        candidate_rows.append(
            {
                "company_id": candidate_id,
                "title": str(candidate.get("TITLE") or ""),
                "url": _portal_link(f"crm/company/details/{candidate_id}/", portal_base_url=portal_base_url),
                "web": ", ".join(_extract_multi_values(candidate, "WEB")),
                "requisites": candidate.get("_matched_requisites") or _company_requisites(auth, candidate_id),
            }
        )

    return {
        "ok": True,
        "deal": {
            "id": deal_id,
            "title": title,
            "url": _portal_link(f"crm/deal/details/{deal_id}/", portal_base_url=portal_base_url),
            "stage_id": str(deal.get("STAGE_ID") or ""),
            "company_id": company_id,
            "client_site": client_site,
            "client_site_source": client_site_source,
            "opportunity": str(deal.get("OPPORTUNITY") or ""),
            "currency": str(deal.get("CURRENCY_ID") or ""),
            "date_create": str(deal.get("DATE_CREATE") or ""),
            "date_modify": str(deal.get("DATE_MODIFY") or ""),
        },
        "company": {
            "id": company_id,
            "title": str(company.get("TITLE") or ""),
            "url": _portal_link(f"crm/company/details/{company_id}/", portal_base_url=portal_base_url) if company_id else "",
            "web": ", ".join(_extract_multi_values(company, "WEB")) if company else "",
            "requisites": requisites,
            "running_bp_count": len(running_bp),
        },
        "deal_contacts": [_short_contact(contacts.get(str(item.get("CONTACT_ID")), {"ID": item.get("CONTACT_ID")}), portal_base_url=portal_base_url) for item in deal_contact_items],
        "company_contacts": [_short_contact(contacts.get(str(item.get("CONTACT_ID")), {"ID": item.get("CONTACT_ID")}), portal_base_url=portal_base_url) for item in company_contact_items],
        "contact_sync_plan": plan,
        "company_candidates": candidate_rows,
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only инспекция сделки Bitrix24 для обогащения.")
    parser.add_argument("deal_id")
    parser.add_argument("--inn", default="")
    parser.add_argument("--company-title", default="")
    parser.add_argument("--portal-base-url", default=DEFAULT_PORTAL_BASE_URL)
    parser.add_argument("--bp-template-id", default=BP_TEMPLATE_ID)
    parser.add_argument("--no-remote-bridge", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    auth, tmp_dir = _load_auth_env(use_remote_bridge=not args.no_remote_bridge)
    try:
        payload = inspect_deal(
            auth,
            deal_id=str(args.deal_id),
            portal_base_url=str(args.portal_base_url),
            bp_template_id=str(args.bp_template_id),
            inn=str(args.inn),
            company_title=str(args.company_title),
        )
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
