#!/usr/bin/env python3
"""Add-only синхронизация контактов компании в контакты сделки Bitrix24."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAppAuth
from scripts.run_sales_copilot import (
    DEFAULT_REMOTE_ENV_FILE,
    DEFAULT_REMOTE_STATE_DIR,
    _build_agent_env,
    _fetch_remote_env,
    _load_runtime_env,
    _resolve_remote_host,
    _sync_remote_state,
)


def _string_id(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    return raw


def _valid_id(value: Any) -> str:
    item_id = _string_id(value)
    return item_id if item_id and item_id != "0" else ""


def _int_or(value: Any, default: int) -> int:
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _is_primary(value: Any) -> bool:
    return str(value or "").strip().upper() == "Y"


def _normalize_link(item: Mapping[str, Any], *, default_sort: int) -> dict[str, Any] | None:
    contact_id = _string_id(item.get("CONTACT_ID") or item.get("contactId") or item.get("contact_id"))
    if not contact_id:
        return None
    return {
        "CONTACT_ID": int(contact_id),
        "SORT": _int_or(item.get("SORT") or item.get("sort"), default_sort),
        "ROLE_ID": _int_or(item.get("ROLE_ID") or item.get("roleId") or item.get("role_id"), 0),
        "IS_PRIMARY": "Y" if _is_primary(item.get("IS_PRIMARY") or item.get("isPrimary") or item.get("is_primary")) else "N",
    }


def _normalize_links(items: Sequence[Mapping[str, Any]], *, default_sort: int = 10) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        link = _normalize_link(item, default_sort=default_sort + (index * 10))
        if not link:
            continue
        contact_id = str(link["CONTACT_ID"])
        if contact_id in seen:
            continue
        seen.add(contact_id)
        links.append(link)
    return links


def build_sync_plan(
    *,
    deal_id: str,
    company_id: str,
    company_contact_items: Sequence[Mapping[str, Any]],
    deal_contact_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Строит add-only план: какие контакты компании добавить в сделку."""
    company_links = _normalize_links(company_contact_items)
    deal_links = _normalize_links(deal_contact_items)

    existing_deal_ids = {str(item["CONTACT_ID"]) for item in deal_links}
    deal_has_primary = any(_is_primary(item.get("IS_PRIMARY")) for item in deal_links)
    primary_assigned = deal_has_primary
    max_sort = max([_int_or(item.get("SORT"), 0) for item in deal_links] + [0])
    additions: list[dict[str, Any]] = []
    skipped_existing: list[str] = []

    for company_link in sorted(company_links, key=lambda item: (_int_or(item.get("SORT"), 0), str(item["CONTACT_ID"]))):
        contact_id = str(company_link["CONTACT_ID"])
        if contact_id in existing_deal_ids:
            skipped_existing.append(contact_id)
            continue

        max_sort = max(max_sort + 10, _int_or(company_link.get("SORT"), 0))
        addition = {
            "CONTACT_ID": company_link["CONTACT_ID"],
            "SORT": max_sort,
            "ROLE_ID": company_link["ROLE_ID"],
            "IS_PRIMARY": "N",
        }
        if not primary_assigned:
            addition["IS_PRIMARY"] = "Y"
            primary_assigned = True
        additions.append(addition)
        existing_deal_ids.add(contact_id)

    return {
        "deal_id": str(deal_id),
        "company_id": str(company_id),
        "existing_deal_contact_ids": [str(item["CONTACT_ID"]) for item in deal_links],
        "company_contact_ids": [str(item["CONTACT_ID"]) for item in company_links],
        "skipped_existing_contact_ids": skipped_existing,
        "additions": additions,
        "additions_count": len(additions),
    }


def _load_auth_env(*, use_remote_bridge: bool) -> tuple[BitrixAppAuth, tempfile.TemporaryDirectory[str] | None]:
    env = _load_runtime_env()
    if not use_remote_bridge:
        return BitrixAppAuth.from_env(env), None

    remote_host = _resolve_remote_host(env)
    remote_env_file = str(env.get("SALES_REMOTE_ENV_FILE") or DEFAULT_REMOTE_ENV_FILE).strip() or DEFAULT_REMOTE_ENV_FILE
    remote_state_dir = str(env.get("SALES_REMOTE_STATE_DIR") or DEFAULT_REMOTE_STATE_DIR).strip() or DEFAULT_REMOTE_STATE_DIR
    remote_env = _fetch_remote_env(env, remote_host, remote_env_file)
    tmp_root = ROOT_DIR / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp_dir = tempfile.TemporaryDirectory(prefix="bitrix-sync-deal-contacts-state-", dir=str(tmp_root))
    state_root = _sync_remote_state(env, remote_host, remote_state_dir, Path(tmp_dir.name))
    agent_env = _build_agent_env(env, remote_env, state_root, ROOT_DIR)
    return BitrixAppAuth.from_env(agent_env), tmp_dir


def sync_deal_company_contacts(
    auth: BitrixAppAuth,
    *,
    deal_id: str,
    apply_changes: bool,
) -> dict[str, Any]:
    deal = auth.call_method("crm.deal.get", {"id": deal_id}, default={})
    company_id = _valid_id(deal.get("COMPANY_ID") if isinstance(deal, Mapping) else "")
    if not company_id:
        return {
            "ok": False,
            "status": "no_company",
            "message": "У сделки нет привязанной компании",
            "deal_id": str(deal_id),
        }

    company_items = auth.call_method("crm.company.contact.items.get", {"id": company_id}, default=[])
    deal_items = auth.call_method("crm.deal.contact.items.get", {"id": deal_id}, default=[])
    if not isinstance(company_items, list):
        company_items = []
    if not isinstance(deal_items, list):
        deal_items = []

    plan = build_sync_plan(
        deal_id=str(deal_id),
        company_id=company_id,
        company_contact_items=[item for item in company_items if isinstance(item, Mapping)],
        deal_contact_items=[item for item in deal_items if isinstance(item, Mapping)],
    )
    applied: list[dict[str, Any]] = []
    if apply_changes:
        for addition in plan["additions"]:
            fields = {
                "CONTACT_ID": addition["CONTACT_ID"],
                "SORT": addition["SORT"],
                "IS_PRIMARY": addition["IS_PRIMARY"],
            }
            result = auth.call_method(
                "crm.deal.contact.add",
                {
                    "id": deal_id,
                    "fields": fields,
                },
                default=None,
            )
            applied.append({"fields": fields, "result": result})

    final_items = auth.call_method("crm.deal.contact.items.get", {"id": deal_id}, default=[]) if apply_changes else deal_items
    return {
        "ok": True,
        "status": "applied" if apply_changes else "dry_run",
        "deal": {
            "ID": deal.get("ID") if isinstance(deal, Mapping) else str(deal_id),
            "TITLE": deal.get("TITLE") if isinstance(deal, Mapping) else "",
            "COMPANY_ID": company_id,
        },
        "plan": plan,
        "applied": applied,
        "final_deal_contact_items": final_items,
    }


def _print_text(payload: Mapping[str, Any]) -> None:
    print("Синхронизация контактов компании в сделку Bitrix24")
    print(f"Статус: {payload.get('status')}")
    if payload.get("message"):
        print(f"Сообщение: {payload.get('message')}")
    deal = payload.get("deal") if isinstance(payload.get("deal"), Mapping) else {}
    plan = payload.get("plan") if isinstance(payload.get("plan"), Mapping) else {}
    if deal:
        print(f"Сделка: {deal.get('ID')} — {deal.get('TITLE') or '-'}")
        print(f"Компания: {deal.get('COMPANY_ID') or '-'}")
    if plan:
        print(f"Контактов компании: {len(plan.get('company_contact_ids') or [])}")
        print(f"Контактов уже в сделке: {len(plan.get('existing_deal_contact_ids') or [])}")
        print(f"К добавлению: {plan.get('additions_count')}")
        for item in plan.get("additions") or []:
            print(
                "- CONTACT_ID={CONTACT_ID}, SORT={SORT}, ROLE_ID={ROLE_ID}, IS_PRIMARY={IS_PRIMARY}".format(**item)
            )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add-only синхронизация контактов компании в сделку Bitrix24.")
    parser.add_argument("--deal-id", default=os.environ.get("BITRIX_SYNC_DEAL_CONTACTS_DEAL_ID", ""))
    parser.add_argument("--apply", action="store_true", default=os.environ.get("BITRIX_SYNC_DEAL_CONTACTS_APPLY") == "1")
    parser.add_argument("--json", action="store_true", default=os.environ.get("BITRIX_SYNC_DEAL_CONTACTS_JSON") == "1")
    parser.add_argument("--no-remote-bridge", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    deal_id = _string_id(args.deal_id)
    if not deal_id:
        print("ОШИБКА: укажи --deal-id или BITRIX_SYNC_DEAL_CONTACTS_DEAL_ID", file=sys.stderr)
        return 2

    auth, tmp_dir = _load_auth_env(use_remote_bridge=not args.no_remote_bridge)
    try:
        payload = sync_deal_company_contacts(auth, deal_id=deal_id, apply_changes=bool(args.apply))
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
