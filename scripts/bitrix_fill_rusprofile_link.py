#!/usr/bin/env python3
"""Автозаполнение ссылки Rusprofile в сделке по ИНН компании."""

from __future__ import annotations

import argparse
import json
from html import unescape
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.bitrix_deal_enrichment_inspect import _company_requisites
from scripts.bitrix_sales_data_quality_report import _field_labels, _field_value_text, _load_entity_fields
from scripts.bitrix_sync_deal_company_contacts import _load_auth_env, _string_id

RUSPROFILE_BASE_URL = "https://www.rusprofile.ru"


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _find_rusprofile_deal_fields(fields: Mapping[str, Mapping[str, Any]]) -> list[str]:
    explicit = [
        field.strip()
        for field in str(__import__("os").environ.get("BITRIX_RUSPROFILE_DEAL_FIELD") or "").split(",")
        if field.strip()
    ]
    matches: list[str] = []
    for code in [*explicit, *fields.keys()]:
        if code in matches:
            continue
        labels = " ".join(_field_labels(code, fields.get(code, {}))).casefold()
        if code in explicit or "руспроф" in labels or "rusprofile" in labels:
            matches.append(code)
    return matches


def _first_inn(requisites: Sequence[Mapping[str, Any]]) -> str:
    for requisite in requisites:
        inn = _digits(requisite.get("RQ_INN"))
        if inn:
            return inn
    return ""


def _fetch_url(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; Cloudbot/1.0; +https://belberrycrm.bitrix24.ru)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=25) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def _extract_canonical_url(html: str) -> str:
    patterns = [
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            url = unescape(match.group(1)).strip()
            return url if url.startswith("http") else f"{RUSPROFILE_BASE_URL}{url}"
    return ""


def resolve_rusprofile_url(inn: str) -> dict[str, Any]:
    inn = _digits(inn)
    if not inn:
        return {"ok": False, "status": "no_inn"}
    search_url = f"{RUSPROFILE_BASE_URL}/search?query={quote(inn)}"
    try:
        html = _fetch_url(search_url)
    except URLError as error:
        return {"ok": False, "status": "fetch_error", "search_url": search_url, "error": str(error)}
    canonical = _extract_canonical_url(html)
    if not canonical or "/id/" not in canonical:
        return {"ok": False, "status": "canonical_not_found", "search_url": search_url}
    if inn not in html:
        return {"ok": False, "status": "inn_not_confirmed_on_page", "search_url": search_url, "url": canonical}
    return {"ok": True, "status": "resolved", "search_url": search_url, "url": canonical}


def fill_rusprofile_link(auth: Any, *, deal_id: str, apply_changes: bool, overwrite: bool) -> dict[str, Any]:
    deal = auth.call_method("crm.deal.get", {"id": deal_id}, default={})
    if not isinstance(deal, Mapping) or not deal:
        return {"ok": False, "status": "deal_not_found", "deal_id": deal_id}
    company_id = _string_id(deal.get("COMPANY_ID"))
    if not company_id:
        return {"ok": False, "status": "deal_without_company", "deal_id": deal_id}

    requisites = _company_requisites(auth, company_id)
    inn = _first_inn(requisites)
    if not inn:
        return {"ok": False, "status": "company_without_inn", "deal_id": deal_id, "company_id": company_id}

    fields = _load_entity_fields(auth, "crm.deal.fields")
    rusprofile_fields = _find_rusprofile_deal_fields(fields)
    if not rusprofile_fields:
        return {"ok": False, "status": "rusprofile_field_not_found", "deal_id": deal_id, "company_id": company_id, "inn": inn}
    if len(rusprofile_fields) > 1:
        return {
            "ok": False,
            "status": "ambiguous_rusprofile_fields",
            "deal_id": deal_id,
            "company_id": company_id,
            "inn": inn,
            "fields": rusprofile_fields,
        }

    field_code = rusprofile_fields[0]
    current_value = _field_value_text(deal.get(field_code))
    resolved = resolve_rusprofile_url(inn)
    if not resolved.get("ok"):
        return {
            "ok": False,
            "status": "rusprofile_not_resolved",
            "deal_id": deal_id,
            "company_id": company_id,
            "inn": inn,
            "field_code": field_code,
            "current_value": current_value,
            "rusprofile": resolved,
        }

    url = str(resolved["url"])
    should_update = overwrite or not current_value or current_value != url
    result = None
    if apply_changes and should_update:
        result = auth.call_method("crm.deal.update", {"id": deal_id, "fields": {field_code: url}}, default=None)
    final_deal = auth.call_method("crm.deal.get", {"id": deal_id}, default={}) if apply_changes else deal
    final_value = _field_value_text(final_deal.get(field_code)) if isinstance(final_deal, Mapping) else ""
    return {
        "ok": True,
        "status": "updated" if apply_changes and should_update else "dry_run" if not apply_changes else "already_actual",
        "deal_id": deal_id,
        "company_id": company_id,
        "inn": inn,
        "field_code": field_code,
        "field_label": _field_labels(field_code, fields.get(field_code, {})),
        "current_value": current_value,
        "target_value": url,
        "should_update": should_update,
        "apply": apply_changes,
        "update_result": result,
        "final_value": final_value,
        "rusprofile": resolved,
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Заполнить ссылку Rusprofile в сделке по ИНН компании.")
    parser.add_argument("--deal-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-remote-bridge", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    auth, tmp_dir = _load_auth_env(use_remote_bridge=not args.no_remote_bridge)
    try:
        payload = fill_rusprofile_link(
            auth,
            deal_id=_string_id(args.deal_id),
            apply_changes=bool(args.apply),
            overwrite=bool(args.overwrite),
        )
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
