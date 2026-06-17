#!/usr/bin/env python3
"""Read-only отчёт по сделкам, где контакты компании можно добавить в сделку."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlencode

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAppAuth
from scripts.bitrix_sync_deal_company_contacts import _load_auth_env, _string_id, build_sync_plan

SALES_DEAL_CATEGORY_ID = 10
DEFAULT_PORTAL_BASE_URL = "https://belberrycrm.bitrix24.ru"


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _int_or(value: Any, default: int = 0) -> int:
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _stage_id(stage: Mapping[str, Any]) -> str:
    return _string_id(stage.get("STATUS_ID") or stage.get("ID"))


def _stage_name(stage: Mapping[str, Any]) -> str:
    return str(stage.get("NAME") or stage.get("TITLE") or _stage_id(stage)).strip()


def _stage_semantics(stage: Mapping[str, Any]) -> str:
    return str(stage.get("SEMANTICS") or stage.get("STATUS_SEMANTIC_ID") or "").strip().upper()


def _is_spam_stage(name: str) -> bool:
    normalized = _lower(name).replace("ё", "е")
    return "спам" in normalized or "spam" in normalized


def _stage_bucket(stage: Mapping[str, Any]) -> str:
    name = _stage_name(stage)
    normalized = _lower(name).replace("ё", "е")
    semantics = _stage_semantics(stage)
    if _is_spam_stage(name):
        return "excluded_spam"
    if semantics == "S" or "успех" in normalized or "успеш" in normalized or "оплат" in normalized:
        return "excluded_success"
    if "отлож" in normalized:
        return "отложка"
    if "отказ" in normalized or "отвал" in normalized or "проигр" in normalized or semantics == "F":
        return "отказ"
    return "в работе"


def _call_list_all(auth: BitrixAppAuth, method: str, params: Mapping[str, Any], *, page_limit: int = 50) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    start: int | str = 0
    while True:
        page_params = dict(params)
        page_params["start"] = start
        payload = auth.call_payload(method, page_params, default={})
        result = payload.get("result") if isinstance(payload, Mapping) else None
        if not isinstance(result, list):
            return items
        items.extend(item for item in result if isinstance(item, dict))
        next_start = payload.get("next") if isinstance(payload, Mapping) else None
        if next_start is None:
            return items
        start = _int_or(next_start, 0)
        if len(items) >= page_limit * 1000:
            return items


def _chunks(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _valid_id(value: Any) -> str:
    item_id = _string_id(value)
    return item_id if item_id and item_id != "0" else ""


def _batch_id_get(auth: BitrixAppAuth, *, method: str, ids: Iterable[Any]) -> dict[str, list[dict[str, Any]]]:
    unique_ids = sorted({_valid_id(value) for value in ids if _valid_id(value)}, key=lambda item: int(item))
    result_by_id: dict[str, list[dict[str, Any]]] = {item_id: [] for item_id in unique_ids}
    for chunk in _chunks(unique_ids, 50):
        key_to_id = {f"i{item_id}": item_id for item_id in chunk}
        cmd = {key: f"{method}?{urlencode({'id': item_id})}" for key, item_id in key_to_id.items()}
        payload = auth.call_payload("batch", {"halt": 0, "cmd": cmd}, default={})
        root = payload.get("result") if isinstance(payload, Mapping) else None
        batch_results = root.get("result") if isinstance(root, Mapping) else {}
        if not isinstance(batch_results, Mapping):
            continue
        for key, item_id in key_to_id.items():
            value = batch_results.get(key, [])
            result_by_id[item_id] = value if isinstance(value, list) else []
    return result_by_id


def _load_sales_stages(auth: BitrixAppAuth, category_id: int) -> list[dict[str, Any]]:
    result = auth.call_method("crm.dealcategory.stage.list", {"id": category_id}, default=[])
    stages = result if isinstance(result, list) else []
    return [stage for stage in stages if isinstance(stage, dict)]


def _load_deals(auth: BitrixAppAuth, *, category_id: int, stage_ids: Sequence[str]) -> list[dict[str, Any]]:
    if not stage_ids:
        return []
    return _call_list_all(
        auth,
        "crm.deal.list",
        {
            "filter": {
                "CATEGORY_ID": category_id,
                "STAGE_ID": list(stage_ids),
            },
            "select": [
                "ID",
                "TITLE",
                "STAGE_ID",
                "CATEGORY_ID",
                "COMPANY_ID",
                "CONTACT_ID",
                "CLOSED",
                "DATE_CREATE",
                "DATE_MODIFY",
                "ASSIGNED_BY_ID",
                "OPPORTUNITY",
                "CURRENCY_ID",
            ],
            "order": {"ID": "DESC"},
        },
    )


def _load_contacts(auth: BitrixAppAuth, contact_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    ids = sorted({_valid_id(value) for value in contact_ids if _valid_id(value)}, key=lambda item: int(item))
    contacts: dict[str, dict[str, Any]] = {}
    for index in range(0, len(ids), 50):
        chunk = ids[index : index + 50]
        page = _call_list_all(
            auth,
            "crm.contact.list",
            {
                "filter": {"ID": chunk},
                "select": ["ID", "NAME", "LAST_NAME", "SECOND_NAME", "POST", "COMPANY_ID"],
            },
        )
        for item in page:
            contact_id = _string_id(item.get("ID"))
            if contact_id:
                contacts[contact_id] = item
    return contacts


def _load_companies(auth: BitrixAppAuth, company_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    ids = sorted({_valid_id(value) for value in company_ids if _valid_id(value)}, key=lambda item: int(item))
    companies: dict[str, dict[str, Any]] = {}
    for index in range(0, len(ids), 50):
        chunk = ids[index : index + 50]
        page = _call_list_all(
            auth,
            "crm.company.list",
            {
                "filter": {"ID": chunk},
                "select": ["ID", "TITLE", "COMPANY_TYPE", "INDUSTRY", "WEB", "PHONE", "EMAIL"],
            },
        )
        for item in page:
            company_id = _string_id(item.get("ID"))
            if company_id:
                companies[company_id] = item
    return companies


def _contact_name(contact: Mapping[str, Any]) -> str:
    parts = [
        str(contact.get("LAST_NAME") or "").strip(),
        str(contact.get("NAME") or "").strip(),
        str(contact.get("SECOND_NAME") or "").strip(),
    ]
    name = " ".join(part for part in parts if part).strip()
    return name or _string_id(contact.get("ID")) or "-"


def _portal_link(path: str, *, portal_base_url: str) -> str:
    return f"{portal_base_url.rstrip('/')}/{path.lstrip('/')}"


def build_report(auth: BitrixAppAuth, *, category_id: int, portal_base_url: str) -> dict[str, Any]:
    stages = _load_sales_stages(auth, category_id)
    stage_meta = {
        _stage_id(stage): {
            "id": _stage_id(stage),
            "name": _stage_name(stage),
            "semantics": _stage_semantics(stage),
            "bucket": _stage_bucket(stage),
        }
        for stage in stages
        if _stage_id(stage)
    }
    included_stage_ids = [
        stage_id
        for stage_id, item in stage_meta.items()
        if item["bucket"] in {"в работе", "отложка", "отказ"}
    ]
    deals = _load_deals(auth, category_id=category_id, stage_ids=included_stage_ids)
    companies = _load_companies(auth, [deal.get("COMPANY_ID") for deal in deals])
    company_contact_cache = _batch_id_get(
        auth,
        method="crm.company.contact.items.get",
        ids=[deal.get("COMPANY_ID") for deal in deals],
    )
    deal_contact_cache = _batch_id_get(
        auth,
        method="crm.deal.contact.items.get",
        ids=[deal.get("ID") for deal in deals],
    )

    all_missing_contact_ids: set[str] = set()
    candidates: list[dict[str, Any]] = []
    skipped: dict[str, int] = defaultdict(int)

    for deal in deals:
        deal_id = _valid_id(deal.get("ID"))
        company_id = _valid_id(deal.get("COMPANY_ID"))
        stage_id = _string_id(deal.get("STAGE_ID"))
        if not company_id:
            skipped["no_company"] += 1
            continue

        plan = build_sync_plan(
            deal_id=deal_id,
            company_id=company_id,
            company_contact_items=[item for item in company_contact_cache[company_id] if isinstance(item, Mapping)],
            deal_contact_items=[item for item in deal_contact_cache[deal_id] if isinstance(item, Mapping)],
        )
        if not plan["company_contact_ids"]:
            skipped["company_without_contacts"] += 1
            continue
        if int(plan["additions_count"]) <= 0:
            skipped["already_synced"] += 1
            continue

        missing_ids = [str(item["CONTACT_ID"]) for item in plan["additions"]]
        all_missing_contact_ids.update(missing_ids)
        company = companies.get(company_id, {})
        candidates.append(
            {
                "deal_id": deal_id,
                "deal_title": str(deal.get("TITLE") or ""),
                "deal_url": _portal_link(f"crm/deal/details/{deal_id}/", portal_base_url=portal_base_url),
                "company_id": company_id,
                "company_title": str(company.get("TITLE") or ""),
                "company_url": _portal_link(f"crm/company/details/{company_id}/", portal_base_url=portal_base_url),
                "stage_id": stage_id,
                "stage_name": stage_meta.get(stage_id, {}).get("name", stage_id),
                "stage_bucket": stage_meta.get(stage_id, {}).get("bucket", ""),
                "closed": str(deal.get("CLOSED") or ""),
                "company_contacts_count": len(plan["company_contact_ids"]),
                "deal_contacts_count": len(plan["existing_deal_contact_ids"]),
                "missing_contacts_count": int(plan["additions_count"]),
                "missing_contact_ids": missing_ids,
                "opportunity": str(deal.get("OPPORTUNITY") or ""),
                "currency": str(deal.get("CURRENCY_ID") or ""),
                "date_modify": str(deal.get("DATE_MODIFY") or ""),
            }
        )

    contacts = _load_contacts(auth, all_missing_contact_ids)
    for item in candidates:
        enriched_contacts = []
        for contact_id in item["missing_contact_ids"]:
            contact = contacts.get(str(contact_id), {})
            post = str(contact.get("POST") or "").strip()
            enriched_contacts.append(
                {
                    "id": str(contact_id),
                    "name": _contact_name(contact),
                    "post": post,
                    "url": _portal_link(f"crm/contact/details/{contact_id}/", portal_base_url=portal_base_url),
                }
            )
        item["missing_contacts"] = enriched_contacts

    candidates.sort(
        key=lambda item: (
            str(item["stage_bucket"]),
            -int(item["missing_contacts_count"]),
            -_int_or(item["deal_id"]),
        )
    )
    by_bucket: dict[str, int] = defaultdict(int)
    by_stage: dict[str, int] = defaultdict(int)
    for item in candidates:
        by_bucket[str(item["stage_bucket"])] += 1
        by_stage[str(item["stage_name"])] += 1

    return {
        "ok": True,
        "category_id": category_id,
        "stages": sorted(stage_meta.values(), key=lambda item: str(item["id"])),
        "included_stage_ids": included_stage_ids,
        "excluded_stage_ids": [
            stage_id
            for stage_id, item in stage_meta.items()
            if item["bucket"] not in {"в работе", "отложка", "отказ"}
        ],
        "deals_checked_count": len(deals),
        "candidates_count": len(candidates),
        "missing_contacts_total": sum(int(item["missing_contacts_count"]) for item in candidates),
        "skipped": dict(skipped),
        "by_bucket": dict(sorted(by_bucket.items())),
        "by_stage": dict(sorted(by_stage.items())),
        "candidates": candidates,
    }


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = report.get("candidates")
    if not isinstance(rows, list):
        rows = []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "deal_id",
                "deal_title",
                "deal_url",
                "company_id",
                "company_title",
                "company_url",
                "stage_name",
                "stage_bucket",
                "company_contacts_count",
                "deal_contacts_count",
                "missing_contacts_count",
                "missing_contacts",
                "date_modify",
            ],
        )
        writer.writeheader()
        for item in rows:
            contacts = item.get("missing_contacts")
            contacts_text = ""
            if isinstance(contacts, list):
                contacts_text = "; ".join(
                    f"{contact.get('name')} ({contact.get('post') or '-'}) [{contact.get('id')}]"
                    for contact in contacts
                    if isinstance(contact, Mapping)
                )
            writer.writerow(
                {
                    "deal_id": item.get("deal_id"),
                    "deal_title": item.get("deal_title"),
                    "deal_url": item.get("deal_url"),
                    "company_id": item.get("company_id"),
                    "company_title": item.get("company_title"),
                    "company_url": item.get("company_url"),
                    "stage_name": item.get("stage_name"),
                    "stage_bucket": item.get("stage_bucket"),
                    "company_contacts_count": item.get("company_contacts_count"),
                    "deal_contacts_count": item.get("deal_contacts_count"),
                    "missing_contacts_count": item.get("missing_contacts_count"),
                    "missing_contacts": contacts_text,
                    "date_modify": item.get("date_modify"),
                }
            )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Найти сделки, которые можно обогатить контактами компании.")
    parser.add_argument("--category-id", type=int, default=int(os.environ.get("BITRIX_SALES_ENRICHMENT_CATEGORY_ID", str(SALES_DEAL_CATEGORY_ID))))
    parser.add_argument("--portal-base-url", default=os.environ.get("BITRIX_PORTAL_BASE_URL", DEFAULT_PORTAL_BASE_URL))
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--json", action="store_true", default=os.environ.get("BITRIX_SALES_ENRICHMENT_JSON") == "1")
    parser.add_argument("--no-remote-bridge", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    auth, tmp_dir = _load_auth_env(use_remote_bridge=not args.no_remote_bridge)
    try:
        report = build_report(auth, category_id=int(args.category_id), portal_base_url=str(args.portal_base_url))
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()

    if args.csv:
        write_csv(report, args.csv)
        report["csv_path"] = str(args.csv)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
