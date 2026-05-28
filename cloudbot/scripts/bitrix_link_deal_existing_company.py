#!/usr/bin/env python3
"""Безопасная привязка сделки Bitrix24 к существующей компании."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.bitrix_sync_deal_company_contacts import _load_auth_env, _string_id, _valid_id, build_sync_plan


def _contact_id(item: Mapping[str, Any]) -> str:
    return _string_id(item.get("CONTACT_ID") or item.get("contactId") or item.get("contact_id"))


def _items(auth: Any, method: str, entity_id: str) -> list[dict[str, Any]]:
    items = auth.call_method(method, {"id": entity_id}, default=[])
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _deal_contact_company_additions(
    *,
    deal_contact_items: Sequence[Mapping[str, Any]],
    company_contact_items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    company_contact_ids = {_contact_id(item) for item in company_contact_items if _contact_id(item)}
    additions: list[dict[str, Any]] = []
    max_sort = 0
    for item in company_contact_items:
        try:
            max_sort = max(max_sort, int(float(str(item.get("SORT") or 0))))
        except ValueError:
            continue
    for item in deal_contact_items:
        contact_id = _contact_id(item)
        if not contact_id or contact_id in company_contact_ids:
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
        company_contact_ids.add(contact_id)
    return additions


def link_deal_existing_company(
    auth: Any,
    *,
    deal_id: str,
    company_id: str,
    apply_changes: bool,
    overwrite_company: bool,
) -> dict[str, Any]:
    deal_id = _valid_id(deal_id)
    company_id = _valid_id(company_id)
    if not deal_id or not company_id:
        return {"ok": False, "status": "invalid_ids", "deal_id": deal_id, "company_id": company_id}

    deal = auth.call_method("crm.deal.get", {"id": deal_id}, default={})
    company = auth.call_method("crm.company.get", {"id": company_id}, default={})
    if not isinstance(deal, Mapping) or not deal:
        return {"ok": False, "status": "deal_not_found", "deal_id": deal_id}
    if not isinstance(company, Mapping) or not company:
        return {"ok": False, "status": "company_not_found", "company_id": company_id}

    current_company_id = _valid_id(deal.get("COMPANY_ID"))
    if current_company_id and current_company_id != company_id and not overwrite_company:
        return {
            "ok": False,
            "status": "deal_has_other_company",
            "deal_id": deal_id,
            "current_company_id": current_company_id,
            "target_company_id": company_id,
        }

    deal_contact_items = _items(auth, "crm.deal.contact.items.get", deal_id)
    company_contact_items = _items(auth, "crm.company.contact.items.get", company_id)
    company_contact_additions = _deal_contact_company_additions(
        deal_contact_items=deal_contact_items,
        company_contact_items=company_contact_items,
    )

    operations: list[dict[str, Any]] = [
        {
            "operation": "crm.deal.update",
            "id": deal_id,
            "fields": {"COMPANY_ID": int(company_id)},
            "needed": current_company_id != company_id,
        }
    ]
    applied_company_contacts: list[dict[str, Any]] = []
    if apply_changes:
        if current_company_id != company_id:
            auth.call_method("crm.deal.update", {"id": deal_id, "fields": {"COMPANY_ID": int(company_id)}}, default=None)
        for fields in company_contact_additions:
            result = auth.call_method("crm.company.contact.add", {"id": company_id, "fields": fields}, default=None)
            applied_company_contacts.append({"fields": fields, "result": result})

    company_contact_items_after = _items(auth, "crm.company.contact.items.get", company_id) if apply_changes else company_contact_items
    if apply_changes and company_contact_additions:
        company_contact_items_after = _items(auth, "crm.company.contact.items.get", company_id)
    deal_contact_items_after = _items(auth, "crm.deal.contact.items.get", deal_id)
    sync_plan = build_sync_plan(
        deal_id=deal_id,
        company_id=company_id,
        company_contact_items=company_contact_items_after,
        deal_contact_items=deal_contact_items_after,
    )
    applied_deal_contacts: list[dict[str, Any]] = []
    if apply_changes:
        for addition in sync_plan.get("additions", []):
            fields = {
                "CONTACT_ID": addition["CONTACT_ID"],
                "SORT": addition["SORT"],
                "IS_PRIMARY": addition["IS_PRIMARY"],
            }
            result = auth.call_method("crm.deal.contact.add", {"id": deal_id, "fields": fields}, default=None)
            applied_deal_contacts.append({"fields": fields, "result": result})

    final_deal = auth.call_method("crm.deal.get", {"id": deal_id}, default={}) if apply_changes else deal
    final_company_contacts = _items(auth, "crm.company.contact.items.get", company_id) if apply_changes else company_contact_items
    final_deal_contacts = _items(auth, "crm.deal.contact.items.get", deal_id) if apply_changes else deal_contact_items
    return {
        "ok": True,
        "status": "applied" if apply_changes else "dry_run",
        "deal": {
            "id": deal_id,
            "title": str(deal.get("TITLE") or ""),
            "initial_company_id": current_company_id,
            "final_company_id": _valid_id(final_deal.get("COMPANY_ID")) if isinstance(final_deal, Mapping) else current_company_id,
        },
        "company": {
            "id": company_id,
            "title": str(company.get("TITLE") or ""),
        },
        "operations": operations,
        "company_contact_additions": company_contact_additions,
        "applied_company_contacts": applied_company_contacts,
        "deal_contact_sync_plan": sync_plan,
        "applied_deal_contacts": applied_deal_contacts,
        "final": {
            "company_contact_items": final_company_contacts,
            "deal_contact_items": final_deal_contacts,
        },
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Привязать сделку Bitrix24 к существующей компании без перезаписи реквизитов.")
    parser.add_argument("--deal-id", required=True)
    parser.add_argument("--company-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite-company", action="store_true")
    parser.add_argument("--no-remote-bridge", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    auth, tmp_dir = _load_auth_env(use_remote_bridge=not args.no_remote_bridge)
    try:
        payload = link_deal_existing_company(
            auth,
            deal_id=_string_id(args.deal_id),
            company_id=_string_id(args.company_id),
            apply_changes=bool(args.apply),
            overwrite_company=bool(args.overwrite_company),
        )
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
