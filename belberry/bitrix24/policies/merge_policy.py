"""Policy для безопасного объединения дублей сделок Bitrix24.

Портирован из legacy `scripts/bitrix_policy_merge_deals.py` без зависимостей
от scripts.* и cloudbot.* — pure-функции от backup → policy plan.

Bitrix merge сам по себе делает штатный API. Эта policy делает три вещи:
1. Выбирает canonical target и earliest deal детерминированно.
2. Считает финальные значения полей через два authority-набора:
   target — для STAGE/ASSIGNED/BEGINDATE/CLOSEDATE/OPENED/TYPE/CONTACT,
   earliest — для SOURCE и UTM_*.
3. Строит список deal_updates для нормализации перед merge и contact_additions
   для добавления контактов из дублей в target.

Решения manual_review_* возвращаются вместо merge при:
- разные компании в группе;
- разные product signatures;
- < 2 валидных сделок или target отсутствует в группе.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

ATTRIBUTION_FIELDS = (
    "SOURCE_ID",
    "SOURCE_DESCRIPTION",
    "UTM_SOURCE",
    "UTM_MEDIUM",
    "UTM_CAMPAIGN",
    "UTM_CONTENT",
    "UTM_TERM",
)

TARGET_AUTHORITY_FIELDS = (
    "STAGE_ID",
    "ASSIGNED_BY_ID",
    "BEGINDATE",
    "CLOSEDATE",
    "OPENED",
    "TYPE_ID",
    "CONTACT_ID",
)

LOST_REASON_FIELD = "UF_CRM_1771495464"
EMPTY_VALUES = (None, "", [], False)


def _is_empty(value: Any) -> bool:
    return value in EMPTY_VALUES


def _string_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.isdigit() else ""


def _valid_id(value: Any) -> str:
    return _string_id(value)


def _normalize_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _product_signature(rows: Any) -> str:
    if not isinstance(rows, list):
        return ""
    parts: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        raw = row.get("PRODUCT_ID") or row.get("PRODUCT_NAME") or row.get("NAME") or row.get("productName")
        label = _normalize_label(raw)
        if label:
            parts.append(label)
    return "|".join(sorted(dict.fromkeys(parts)))


def _date_sort(value: Any) -> str:
    return str(value or "").strip()


def _earliest_deal(deals: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    return min(deals, key=lambda deal: (_date_sort(deal.get("DATE_CREATE")), _string_id(deal.get("ID"))))


def _find_backup_item(backup: Mapping[str, Any], deal_id: str) -> Mapping[str, Any]:
    for item in backup.get("deals", []):
        if isinstance(item, Mapping) and _string_id(item.get("id")) == deal_id:
            return item
    return {}


def _deal_from_backup(backup: Mapping[str, Any], deal_id: str) -> Mapping[str, Any]:
    item = _find_backup_item(backup, deal_id)
    deal = item.get("deal") if isinstance(item, Mapping) else {}
    return deal if isinstance(deal, Mapping) else {}


def unique_company_ids(backup: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for item in backup.get("deals", []):
        deal = item.get("deal") if isinstance(item, Mapping) else {}
        if isinstance(deal, Mapping):
            company_id = _string_id(deal.get("COMPANY_ID"))
            if company_id:
                result.add(company_id)
    return result


def unique_product_signatures(backup: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for item in backup.get("deals", []):
        if not isinstance(item, Mapping):
            continue
        signature = _product_signature(item.get("product_rows"))
        if signature:
            result.add(signature)
    return result


def _contact_additions(backup: Mapping[str, Any], target_id: str) -> list[dict[str, Any]]:
    target_item = _find_backup_item(backup, target_id)
    target_contacts = target_item.get("contacts") if isinstance(target_item.get("contacts"), list) else []
    existing = {
        _string_id(item.get("CONTACT_ID") or item.get("contactId"))
        for item in target_contacts
        if isinstance(item, Mapping)
    }
    additions: list[dict[str, Any]] = []
    max_sort = 0
    for item in target_contacts:
        if not isinstance(item, Mapping):
            continue
        try:
            max_sort = max(max_sort, int(float(str(item.get("SORT") or 0))))
        except ValueError:
            continue

    for source_item in backup.get("deals", []):
        if not isinstance(source_item, Mapping) or _string_id(source_item.get("id")) == target_id:
            continue
        contacts = source_item.get("contacts") if isinstance(source_item.get("contacts"), list) else []
        for item in contacts:
            if not isinstance(item, Mapping):
                continue
            contact_id = _string_id(item.get("CONTACT_ID") or item.get("contactId"))
            if not contact_id or contact_id in existing:
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
            existing.add(contact_id)
    return additions


def build_policy_plan(backup: Mapping[str, Any], *, target_id: str) -> dict[str, Any]:
    """Строит безопасный план правок, которые снимают типовые merge-конфликты."""
    target_id = _valid_id(target_id)
    target = _deal_from_backup(backup, target_id)
    deals = [
        item.get("deal")
        for item in backup.get("deals", [])
        if isinstance(item, Mapping) and isinstance(item.get("deal"), Mapping)
    ]
    if not target or len(deals) < 2:
        return {"ok": False, "status": "invalid_backup", "target_id": target_id}

    company_ids = unique_company_ids(backup)
    if len(company_ids) > 1:
        return {
            "ok": False,
            "status": "manual_review_different_companies",
            "target_id": target_id,
            "company_ids": sorted(company_ids),
        }

    product_signatures = unique_product_signatures(backup)
    if len(product_signatures) > 1:
        return {
            "ok": False,
            "status": "manual_review_different_products",
            "target_id": target_id,
            "product_signatures": sorted(product_signatures),
        }

    earliest = _earliest_deal(deals)
    final_values: dict[str, Any] = {}
    for field in TARGET_AUTHORITY_FIELDS:
        if not _is_empty(target.get(field)):
            final_values[field] = target.get(field)
    for field in ATTRIBUTION_FIELDS:
        if not _is_empty(earliest.get(field)):
            final_values[field] = earliest.get(field)
    if _is_empty(target.get(LOST_REASON_FIELD)):
        for deal in sorted(deals, key=lambda item: (_date_sort(item.get("DATE_CREATE")), _string_id(item.get("ID")))):
            if not _is_empty(deal.get(LOST_REASON_FIELD)):
                final_values[LOST_REASON_FIELD] = deal.get(LOST_REASON_FIELD)
                break
    elif not _is_empty(target.get(LOST_REASON_FIELD)):
        final_values[LOST_REASON_FIELD] = target.get(LOST_REASON_FIELD)

    updates: list[dict[str, Any]] = []
    for deal in deals:
        deal_id = _string_id(deal.get("ID"))
        fields: dict[str, Any] = {}
        for field, value in final_values.items():
            if deal.get(field) != value:
                fields[field] = value
        if fields:
            updates.append({"deal_id": deal_id, "fields": fields})

    return {
        "ok": True,
        "status": "ready",
        "target_id": target_id,
        "earliest_deal_id": _string_id(earliest.get("ID")),
        "final_values": final_values,
        "deal_updates": updates,
        "contact_additions": _contact_additions(backup, target_id),
    }
