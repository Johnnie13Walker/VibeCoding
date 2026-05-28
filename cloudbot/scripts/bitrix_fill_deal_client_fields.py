#!/usr/bin/env python3
"""Точечное заполнение пустых клиентских полей сделки Bitrix24."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.bitrix_deal_company_enrich_apply import LEGAL_ADDRESS_TYPE_ID, _load_addresses
from scripts.bitrix_deal_enrichment_inspect import _company_requisites
from scripts.bitrix_sales_data_quality_report import _extract_multi_values, _field_labels, _field_value_text, _load_entity_fields
from scripts.bitrix_sync_deal_company_contacts import _load_auth_env, _string_id, _valid_id

DEFAULT_CLIENT_SITE_FIELD_CODES = ("UF_CRM_1776434217", "UF_CRM_69E8AB2E0715A")
DEFAULT_CITY_FIELD_CODES = ("UF_CRM_5FB3854A1EDBC",)


def _split_field_codes(value: str, default: Sequence[str]) -> list[str]:
    codes = [item.strip() for item in value.split(",") if item.strip()]
    result: list[str] = []
    for code in [*codes, *default]:
        if code not in result:
            result.append(code)
    return result


def _first_company_site(company: Mapping[str, Any]) -> str:
    values = _extract_multi_values(company, "WEB")
    return values[0] if values else ""


def _clean_domain(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    domain = parsed.netloc or parsed.path.split("/", 1)[0]
    domain = domain.removeprefix("www.").strip(". ")
    return domain


def _clean_site_url(value: Any) -> str:
    domain = _clean_domain(value)
    return f"https://{domain}" if domain else ""


def _first_legal_city(auth: Any, requisites: Sequence[Mapping[str, Any]]) -> str:
    for requisite in requisites:
        requisite_id = _valid_id(requisite.get("ID"))
        if not requisite_id:
            continue
        addresses = _load_addresses(auth, requisite_id)
        for address in addresses:
            if str(address.get("TYPE_ID") or "") != str(LEGAL_ADDRESS_TYPE_ID):
                continue
            city = _field_value_text(address.get("CITY")) or _field_value_text(address.get("PROVINCE"))
            if city:
                return city
    return ""


def _plan_field_update(
    deal: Mapping[str, Any],
    fields_meta: Mapping[str, Mapping[str, Any]],
    *,
    field_kind: str,
    field_codes: Sequence[str],
    target_value: str,
    overwrite: bool,
) -> tuple[dict[str, str], dict[str, Any]]:
    available_codes = [code for code in field_codes if code in fields_meta]
    existing_values = {
        code: _field_value_text(deal.get(code))
        for code in available_codes
        if _field_value_text(deal.get(code))
    }
    note: dict[str, Any] = {
        "field_kind": field_kind,
        "status": "",
        "selected_field": "",
        "candidate_fields": list(field_codes),
        "available_fields": available_codes,
        "target_value": target_value,
        "existing_values": existing_values,
    }
    if not target_value:
        note["status"] = "no_value"
        return {}, note
    if existing_values and not overwrite:
        note["status"] = "already_filled"
        return {}, note
    if not available_codes:
        note["status"] = "field_not_found"
        return {}, note

    selected = next((code for code in available_codes if code in existing_values), "")
    if not selected:
        selected = next((code for code in available_codes if code not in existing_values), available_codes[0])
    note["selected_field"] = selected
    if _field_value_text(deal.get(selected)) == target_value:
        note["status"] = "already_actual"
        return {}, note
    note["status"] = "planned"
    return {selected: target_value}, note


def fill_deal_client_fields(
    auth: Any,
    *,
    deal_id: str,
    apply_changes: bool,
    overwrite: bool,
    site: str,
    city: str,
    client_site_field_codes: Sequence[str],
    city_field_codes: Sequence[str],
) -> dict[str, Any]:
    deal = auth.call_method("crm.deal.get", {"id": deal_id}, default={})
    if not isinstance(deal, Mapping) or not deal:
        return {"ok": False, "status": "deal_not_found", "deal_id": deal_id}

    company_id = _valid_id(deal.get("COMPANY_ID"))
    company = auth.call_method("crm.company.get", {"id": company_id}, default={}) if company_id else {}
    company = company if isinstance(company, Mapping) else {}
    requisites = _company_requisites(auth, company_id) if company_id else []
    fields_meta = _load_entity_fields(auth, "crm.deal.fields")

    current_site = ""
    for field_code in client_site_field_codes:
        current_site = _field_value_text(deal.get(field_code))
        if current_site:
            break
    target_site = _clean_site_url(site.strip() or current_site or _first_company_site(company) or deal.get("TITLE"))
    target_title = _clean_domain(target_site)
    target_city = city.strip() or _first_legal_city(auth, requisites)
    updates: dict[str, str] = {}
    notes: list[dict[str, Any]] = []
    site_updates, site_note = _plan_field_update(
        deal,
        fields_meta,
        field_kind="client_site",
        field_codes=client_site_field_codes,
        target_value=target_site,
        overwrite=True,
    )
    current_title = _field_value_text(deal.get("TITLE"))
    title_note: dict[str, Any] = {
        "field_kind": "deal_title",
        "status": "",
        "selected_field": "TITLE",
        "target_value": target_title,
        "existing_values": {"TITLE": current_title} if current_title else {},
    }
    if not target_title:
        title_note["status"] = "no_value"
    elif current_title == target_title:
        title_note["status"] = "already_actual"
    else:
        title_note["status"] = "planned"
        updates["TITLE"] = target_title
    city_updates, city_note = _plan_field_update(
        deal,
        fields_meta,
        field_kind="city",
        field_codes=city_field_codes,
        target_value=target_city,
        overwrite=overwrite,
    )
    updates.update(site_updates)
    updates.update(city_updates)
    notes.extend([site_note, title_note, city_note])

    update_result = None
    if apply_changes and updates:
        update_result = auth.call_method("crm.deal.update", {"id": deal_id, "fields": updates}, default=None)

    final_deal = auth.call_method("crm.deal.get", {"id": deal_id}, default={}) if apply_changes else deal
    final_values = {
        code: _field_value_text(final_deal.get(code)) if isinstance(final_deal, Mapping) else ""
        for code in [*client_site_field_codes, *city_field_codes]
        if code in fields_meta
    }
    final_values["TITLE"] = _field_value_text(final_deal.get("TITLE")) if isinstance(final_deal, Mapping) else ""

    return {
        "ok": True,
        "status": "updated" if apply_changes and updates else "dry_run" if not apply_changes else "already_actual",
        "deal_id": deal_id,
        "company_id": company_id,
        "updates": updates,
        "notes": notes,
        "apply": apply_changes,
        "overwrite": overwrite,
        "update_result": update_result,
        "final_values": final_values,
        "field_labels": {code: _field_labels(code, fields_meta.get(code, {})) for code in final_values},
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Заполнить пустые поля 'Сайт клиента' и 'Город' в сделке Bitrix24.")
    parser.add_argument("--deal-id", required=True)
    parser.add_argument("--site", default="")
    parser.add_argument("--city", default="")
    parser.add_argument("--client-site-fields", default=os.environ.get("BITRIX_CLIENT_SITE_FIELD") or "")
    parser.add_argument("--city-fields", default=os.environ.get("BITRIX_DEAL_CITY_FIELD") or "")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-remote-bridge", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    auth, tmp_dir = _load_auth_env(use_remote_bridge=not args.no_remote_bridge)
    try:
        payload = fill_deal_client_fields(
            auth,
            deal_id=_string_id(args.deal_id),
            apply_changes=bool(args.apply),
            overwrite=bool(args.overwrite),
            site=str(args.site or ""),
            city=str(args.city or ""),
            client_site_field_codes=_split_field_codes(str(args.client_site_fields or ""), DEFAULT_CLIENT_SITE_FIELD_CODES),
            city_field_codes=_split_field_codes(str(args.city_fields or ""), DEFAULT_CITY_FIELD_CODES),
        )
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
