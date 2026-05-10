#!/usr/bin/env python3
"""Scanner дублей по TITLE в воронке Bitrix24 для feeder Sheet."""

from __future__ import annotations

import argparse
import json
from typing import Any, Mapping, Sequence

from belberry.bitrix24.config.loader import load_config
from belberry.bitrix24.providers.bitrix_oauth import BitrixOAuth, urllib_transport as bitrix_transport
from belberry.bitrix24.providers.google_sheets import GoogleSheetsClient
from belberry.bitrix24.providers.logging import sanitize
from belberry.bitrix24.tools.title_duplicates import find_title_duplicates

DEFAULT_FUNNEL_NAME = "Реанимация"
DEFAULT_TARGET_SHEET = "Дубликаты 3"
DEAL_SELECT = (
    "ID",
    "TITLE",
    "STAGE_ID",
    "ASSIGNED_BY_ID",
    "COMPANY_ID",
    "CONTACT_ID",
    "SOURCE_ID",
    "DATE_CREATE",
    "DATE_MODIFY",
)
HEADER = ("Группа", "Title", "ID сделки", "Стадия", "Ответственный", "Дата создания", "Ссылка")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dry-run", "write"], default="dry-run")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--funnel-name", default=DEFAULT_FUNNEL_NAME)
    parser.add_argument("--target-sheet", default=DEFAULT_TARGET_SHEET)
    parser.add_argument("--limit-deals", type=int, default=10000)
    return parser


def _extract_categories(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result = payload.get("result")
    if isinstance(result, Mapping):
        categories = result.get("categories")
        if isinstance(categories, list):
            return [item for item in categories if isinstance(item, Mapping)]
    if isinstance(result, list):
        return [item for item in result if isinstance(item, Mapping)]
    return []


def find_category_id(oauth: BitrixOAuth, funnel_name: str) -> str:
    clean_name = str(funnel_name or "").strip()
    if not clean_name:
        raise ValueError("funnel_name is required")
    payload = oauth.call_payload("crm.category.list", {"entityTypeId": 2})
    for category in _extract_categories(payload):
        name = str(category.get("name") or category.get("NAME") or "").strip()
        if name.lower() == clean_name.lower():
            category_id = str(category.get("id") or category.get("ID") or "").strip()
            if category_id:
                return category_id
    raise RuntimeError(f"Bitrix funnel not found: {clean_name}")


def load_deals(oauth: BitrixOAuth, *, category_id: str, limit_deals: int) -> list[Mapping[str, Any]]:
    if int(limit_deals) < 1:
        raise ValueError("limit_deals must be positive")
    return oauth.list_method(
        "crm.deal.list",
        {
            "filter": {"CATEGORY_ID": str(category_id)},
            "select": list(DEAL_SELECT),
            "order": {"DATE_CREATE": "ASC"},
        },
        limit=int(limit_deals),
    )


def _sheet_exists(metadata: Mapping[str, Any], sheet_name: str) -> bool:
    sheets = metadata.get("sheets")
    if not isinstance(sheets, list):
        return False
    for item in sheets:
        if not isinstance(item, Mapping):
            continue
        properties = item.get("properties")
        if isinstance(properties, Mapping) and str(properties.get("title") or "") == sheet_name:
            return True
    return False


def _deal_link(portal_base_url: str, deal_id: str) -> str:
    return f"{portal_base_url.rstrip('/')}/crm/deal/details/{deal_id}/"


def build_rows(groups: Mapping[str, Sequence[Mapping[str, Any]]], *, portal_base_url: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for group_index, (title, deals) in enumerate(groups.items(), start=1):
        for deal in deals:
            deal_id = str(deal.get("ID") or "")
            rows.append(
                [
                    str(group_index),
                    title,
                    deal_id,
                    str(deal.get("STAGE_ID") or ""),
                    str(deal.get("ASSIGNED_BY_ID") or ""),
                    str(deal.get("DATE_CREATE") or ""),
                    _deal_link(portal_base_url, deal_id) if deal_id else "",
                ]
            )
    return rows


def summarize_dry_run(
    *,
    funnel_name: str,
    category_id: str,
    deals: Sequence[Mapping[str, Any]],
    groups: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "funnel": funnel_name,
        "category_id": str(category_id),
        "total_deals": len(deals),
        "total_groups": len(groups),
        "total_duplicate_deals": sum(len(items) for items in groups.values()),
        "top_groups": [
            {
                "title": title,
                "count": len(items),
                "first_deal_id": str(items[0].get("ID") or "") if items else "",
            }
            for title, items in list(groups.items())[:5]
        ],
    }


def run_scan(
    *,
    mode: str,
    confirm_write: bool,
    funnel_name: str,
    target_sheet: str,
    limit_deals: int,
    oauth: BitrixOAuth,
    sheets: GoogleSheetsClient,
    sheet_id: str,
    portal_base_url: str,
) -> dict[str, Any]:
    category_id = find_category_id(oauth, funnel_name)
    deals = load_deals(oauth, category_id=category_id, limit_deals=limit_deals)
    groups = find_title_duplicates(deals)
    if mode == "dry-run":
        return summarize_dry_run(funnel_name=funnel_name, category_id=category_id, deals=deals, groups=groups)

    if not confirm_write:
        raise SystemExit("--write требует --confirm-write")
    metadata = sheets.metadata(sheet_id)
    if _sheet_exists(metadata, target_sheet):
        raise RuntimeError(f"target sheet already exists: {target_sheet}")
    rows = build_rows(groups, portal_base_url=portal_base_url)
    sheets.add_sheet(sheet_id, target_sheet)
    sheets.write_header(sheet_id, target_sheet, HEADER)
    sheets.append_rows(sheet_id, target_sheet, rows)
    return {
        "mode": "write",
        "funnel": funnel_name,
        "target_sheet": target_sheet,
        "created": True,
        "total_groups": len(groups),
        "total_rows": len(rows),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "write" and not args.confirm_write:
        raise SystemExit("--write требует --confirm-write")
    config = load_config()
    oauth = BitrixOAuth.from_env(transport=bitrix_transport)
    sheets = GoogleSheetsClient.from_env()
    summary = run_scan(
        mode=args.mode,
        confirm_write=args.confirm_write,
        funnel_name=args.funnel_name,
        target_sheet=args.target_sheet,
        limit_deals=args.limit_deals,
        oauth=oauth,
        sheets=sheets,
        sheet_id=config.sheet_id,
        portal_base_url=config.portal_base_url,
    )
    print(json.dumps(sanitize(summary), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
