#!/usr/bin/env python3
"""Soft-merge дубля компании Bitrix24 в основную компанию."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.bitrix_deal_enrichment_inspect import _company_requisites
from scripts.bitrix_sales_enrichment_candidates import _call_list_all
from scripts.bitrix_sync_deal_company_contacts import _load_auth_env, _string_id, _valid_id, build_sync_plan


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _first_requisite_signature(requisites: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    for requisite in requisites:
        signature = {
            "inn": _digits(requisite.get("RQ_INN")),
            "kpp": _digits(requisite.get("RQ_KPP")),
            "ogrn": _digits(requisite.get("RQ_OGRN")),
        }
        if any(signature.values()):
            return signature
    return {"inn": "", "kpp": "", "ogrn": ""}


def _company_contact_items(auth: Any, company_id: str) -> list[dict[str, Any]]:
    items = auth.call_method("crm.company.contact.items.get", {"id": company_id}, default=[])
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _deal_contact_items(auth: Any, deal_id: str) -> list[dict[str, Any]]:
    items = auth.call_method("crm.deal.contact.items.get", {"id": deal_id}, default=[])
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _company_deals(auth: Any, company_id: str) -> list[dict[str, Any]]:
    return _call_list_all(
        auth,
        "crm.deal.list",
        {
            "filter": {"COMPANY_ID": company_id},
            "select": ["ID", "TITLE", "COMPANY_ID", "STAGE_ID", "DATE_MODIFY"],
            "order": {"ID": "ASC"},
        },
    )


def _contact_id(item: Mapping[str, Any]) -> str:
    return _string_id(item.get("CONTACT_ID") or item.get("contactId") or item.get("contact_id"))


def _sort_key(item: Mapping[str, Any]) -> tuple[int, str]:
    try:
        sort = int(float(str(item.get("SORT") or 10)))
    except ValueError:
        sort = 10
    return sort, _contact_id(item)


def _missing_company_contact_links(
    *,
    source_items: Sequence[Mapping[str, Any]],
    target_items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    target_ids = {_contact_id(item) for item in target_items if _contact_id(item)}
    additions: list[dict[str, Any]] = []
    max_sort = 0
    for item in target_items:
        try:
            max_sort = max(max_sort, int(float(str(item.get("SORT") or 0))))
        except ValueError:
            continue
    for item in sorted(source_items, key=_sort_key):
        contact_id = _contact_id(item)
        if not contact_id or contact_id in target_ids:
            continue
        max_sort = max_sort + 10 if max_sort else 10
        additions.append(
            {
                "CONTACT_ID": int(contact_id),
                "SORT": max_sort,
                "ROLE_ID": int(float(str(item.get("ROLE_ID") or 0))),
                "IS_PRIMARY": "N",
            }
        )
        target_ids.add(contact_id)
    return additions


def merge_company_duplicate(
    auth: Any,
    *,
    target_company_id: str,
    source_company_id: str,
    deal_id: str,
    apply_changes: bool,
    allow_requisite_mismatch: bool,
) -> dict[str, Any]:
    target_company_id = _valid_id(target_company_id)
    source_company_id = _valid_id(source_company_id)
    deal_id = _valid_id(deal_id)
    if not target_company_id or not source_company_id or target_company_id == source_company_id:
        return {"ok": False, "status": "invalid_company_ids", "target_company_id": target_company_id, "source_company_id": source_company_id}

    target_company = auth.call_method("crm.company.get", {"id": target_company_id}, default={})
    source_company = auth.call_method("crm.company.get", {"id": source_company_id}, default={})
    if not isinstance(target_company, Mapping) or not target_company:
        return {"ok": False, "status": "target_company_not_found", "target_company_id": target_company_id}
    if not isinstance(source_company, Mapping) or not source_company:
        return {"ok": False, "status": "source_company_not_found", "source_company_id": source_company_id}

    target_requisites = _company_requisites(auth, target_company_id)
    source_requisites = _company_requisites(auth, source_company_id)
    target_signature = _first_requisite_signature(target_requisites)
    source_signature = _first_requisite_signature(source_requisites)
    signatures_match = target_signature == source_signature and bool(target_signature.get("inn"))
    if not signatures_match and not allow_requisite_mismatch:
        return {
            "ok": False,
            "status": "requisite_mismatch",
            "target_company_id": target_company_id,
            "source_company_id": source_company_id,
            "target_requisites": target_signature,
            "source_requisites": source_signature,
        }

    target_contacts_before = _company_contact_items(auth, target_company_id)
    source_contacts = _company_contact_items(auth, source_company_id)
    company_contact_additions = _missing_company_contact_links(
        source_items=source_contacts,
        target_items=target_contacts_before,
    )
    applied_company_contacts: list[dict[str, Any]] = []
    if apply_changes:
        for fields in company_contact_additions:
            result = auth.call_method("crm.company.contact.add", {"id": target_company_id, "fields": fields}, default=None)
            applied_company_contacts.append({"fields": fields, "result": result})

    source_deals = _company_deals(auth, source_company_id)
    deal_relinks = [
        {
            "deal_id": _string_id(deal.get("ID")),
            "title": str(deal.get("TITLE") or ""),
            "from_company_id": source_company_id,
            "to_company_id": target_company_id,
        }
        for deal in source_deals
        if _string_id(deal.get("ID"))
    ]
    applied_deal_relinks: list[dict[str, Any]] = []
    if apply_changes:
        for item in deal_relinks:
            result = auth.call_method(
                "crm.deal.update",
                {"id": item["deal_id"], "fields": {"COMPANY_ID": int(target_company_id)}},
                default=None,
            )
            applied_deal_relinks.append({"deal_id": item["deal_id"], "result": result})

    sync_plan: dict[str, Any] = {}
    applied_deal_contacts: list[dict[str, Any]] = []
    final_deal_contacts: list[dict[str, Any]] = []
    if deal_id:
        target_contacts_after = _company_contact_items(auth, target_company_id)
        deal_contacts = _deal_contact_items(auth, deal_id)
        sync_plan = build_sync_plan(
            deal_id=deal_id,
            company_id=target_company_id,
            company_contact_items=target_contacts_after,
            deal_contact_items=deal_contacts,
        )
        if apply_changes:
            for addition in sync_plan.get("additions", []):
                fields = {
                    "CONTACT_ID": addition["CONTACT_ID"],
                    "SORT": addition["SORT"],
                    "IS_PRIMARY": addition["IS_PRIMARY"],
                }
                result = auth.call_method("crm.deal.contact.add", {"id": deal_id, "fields": fields}, default=None)
                applied_deal_contacts.append({"fields": fields, "result": result})
            final_deal_contacts = _deal_contact_items(auth, deal_id)
        else:
            final_deal_contacts = deal_contacts

    final_target_contacts = _company_contact_items(auth, target_company_id) if apply_changes else target_contacts_before
    final_source_deals = _company_deals(auth, source_company_id) if apply_changes else source_deals
    return {
        "ok": True,
        "status": "applied" if apply_changes else "dry_run",
        "target_company": {
            "id": target_company_id,
            "title": str(target_company.get("TITLE") or ""),
            "requisites": target_signature,
        },
        "source_company": {
            "id": source_company_id,
            "title": str(source_company.get("TITLE") or ""),
            "requisites": source_signature,
        },
        "signatures_match": signatures_match,
        "company_contact_additions": company_contact_additions,
        "applied_company_contacts": applied_company_contacts,
        "deal_relinks": deal_relinks,
        "applied_deal_relinks": applied_deal_relinks,
        "deal_contact_sync_plan": sync_plan,
        "applied_deal_contacts": applied_deal_contacts,
        "final": {
            "target_company_contacts": final_target_contacts,
            "source_company_deals": final_source_deals,
            "deal_contacts": final_deal_contacts,
        },
        "note": "Soft-merge: дубль не удаляется, переносятся только связи контактов и сделок.",
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Soft-merge дубля компании Bitrix24 в основную компанию.")
    parser.add_argument("--target-company-id", required=True)
    parser.add_argument("--source-company-id", required=True)
    parser.add_argument("--deal-id", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-requisite-mismatch", action="store_true")
    parser.add_argument("--no-remote-bridge", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    auth, tmp_dir = _load_auth_env(use_remote_bridge=not args.no_remote_bridge)
    try:
        payload = merge_company_duplicate(
            auth,
            target_company_id=_string_id(args.target_company_id),
            source_company_id=_string_id(args.source_company_id),
            deal_id=_string_id(args.deal_id),
            apply_changes=bool(args.apply),
            allow_requisite_mismatch=bool(args.allow_requisite_mismatch),
        )
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
