#!/usr/bin/env python3
"""Read-only отчёт по обогащению данных сделок воронки Продажи Bitrix24."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlencode

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAppAuth, _flatten_params
from scripts.bitrix_sales_enrichment_candidates import (
    DEFAULT_PORTAL_BASE_URL,
    SALES_DEAL_CATEGORY_ID,
    _batch_id_get,
    _call_list_all,
    _contact_name,
    _int_or,
    _is_spam_stage,
    _load_contacts,
    _load_sales_stages,
    _lower,
    _portal_link,
    _stage_bucket,
    _stage_id,
    _stage_name,
    _stage_semantics,
    _valid_id,
)
from scripts.bitrix_sync_deal_company_contacts import _load_auth_env, _string_id, build_sync_plan

COMPANY_ENTITY_TYPE_ID = 4
BP_TEMPLATE_ID = "5938"
BP_DATA_FIELDS = ["RQ_INN", "RQ_KPP", "RQ_OGRN"]
CLIENT_SITE_FIELD_FALLBACKS = ("UF_CRM_1776434217",)
LOST_REASON_FIELD_FALLBACKS = ("UF_CRM_1771495464",)


def _encode_params(params: Mapping[str, Any]) -> str:
    return urlencode(_flatten_params("", params))


def _chunks(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _stage_bucket_with_success(stage: Mapping[str, Any]) -> str:
    name = _stage_name(stage)
    normalized = _lower(name).replace("ё", "е")
    semantics = _stage_semantics(stage)
    if _is_spam_stage(name):
        return "excluded_spam"
    if semantics == "S" or "успех" in normalized or "успеш" in normalized or "оплат" in normalized:
        return "успех"
    return _stage_bucket(stage)


def _load_companies_extended(auth: BitrixAppAuth, company_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    ids = sorted({_valid_id(value) for value in company_ids if _valid_id(value)}, key=lambda item: int(item))
    companies: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(ids, 50):
        page = _call_list_all(
            auth,
            "crm.company.list",
            {
                "filter": {"ID": list(chunk)},
                "select": [
                    "ID",
                    "TITLE",
                    "COMPANY_TYPE",
                    "INDUSTRY",
                    "WEB",
                    "PHONE",
                    "EMAIL",
                    "DATE_CREATE",
                    "DATE_MODIFY",
                    "ASSIGNED_BY_ID",
                    "*",
                    "UF_*",
                ],
            },
        )
        for item in page:
            company_id = _string_id(item.get("ID"))
            if company_id:
                companies[company_id] = item
    return companies


def _load_deals_extended(auth: BitrixAppAuth, *, category_id: int, stage_ids: Sequence[str]) -> list[dict[str, Any]]:
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
                "*",
                "UF_*",
            ],
            "order": {"ID": "DESC"},
        },
    )


def _load_entity_fields(auth: BitrixAppAuth, method: str) -> dict[str, dict[str, Any]]:
    payload = auth.call_payload(method, default={})
    result = payload.get("result") if isinstance(payload, Mapping) else payload
    if not isinstance(result, Mapping):
        return {}
    return {str(key): value for key, value in result.items() if isinstance(value, dict)}


def _field_labels(code: str, meta: Mapping[str, Any]) -> list[str]:
    labels = [code]
    for key in ("title", "formLabel", "listLabel", "filterLabel", "label", "name"):
        value = str(meta.get(key) or "").strip()
        if value:
            labels.append(value)
    return labels


def _is_client_site_field(code: str, meta: Mapping[str, Any]) -> bool:
    labels = [_lower(label).replace("ё", "е") for label in _field_labels(code, meta)]
    return any("сайт клиента" in label or ("сайт" in label and "клиент" in label) for label in labels)


def _client_site_field_codes(fields: Mapping[str, Mapping[str, Any]], *, include_fallbacks: bool) -> list[str]:
    explicit = [
        field.strip()
        for field in str(os.environ.get("BITRIX_CLIENT_SITE_FIELD") or "").split(",")
        if field.strip()
    ]
    codes: list[str] = []
    fallback_codes = CLIENT_SITE_FIELD_FALLBACKS if include_fallbacks else ()
    for code in [*explicit, *fields.keys(), *fallback_codes]:
        if code in codes:
            continue
        if code in explicit or code in CLIENT_SITE_FIELD_FALLBACKS or _is_client_site_field(code, fields.get(code, {})):
            codes.append(code)
    return codes


def _field_value_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if value is False:
        return ""
    if isinstance(value, Mapping):
        for key in ("VALUE", "value", "TEXT", "text", "TITLE", "title", "NAME", "name"):
            nested = _field_value_text(value.get(key))
            if nested:
                return nested
        return ""
    if isinstance(value, list):
        values: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = _field_value_text(item)
            if text and text not in seen:
                seen.add(text)
                values.append(text)
        return ", ".join(values)
    return str(value).strip()


def _first_field_value(item: Mapping[str, Any], field_codes: Sequence[str]) -> tuple[str, str]:
    for field_code in field_codes:
        value = _field_value_text(item.get(field_code))
        if value:
            return value, field_code
    return "", ""


def _is_lost_reason_field(code: str, meta: Mapping[str, Any]) -> bool:
    if not str(code).startswith("UF_CRM_"):
        return False
    labels = [_lower(label).replace("ё", "е") for label in _field_labels(code, meta)]
    return any("причин" in label or "причина" in label or "reason" in label for label in labels)


def _lost_reason_field_codes(fields: Mapping[str, Mapping[str, Any]]) -> list[str]:
    explicit = [
        field.strip()
        for field in str(os.environ.get("BITRIX_LOST_REASON_FIELD") or "").split(",")
        if field.strip()
    ]
    codes: list[str] = []
    for code in [*explicit, *fields.keys(), *LOST_REASON_FIELD_FALLBACKS]:
        if code in codes:
            continue
        if code in explicit or code in LOST_REASON_FIELD_FALLBACKS or _is_lost_reason_field(code, fields.get(code, {})):
            codes.append(code)
    return codes


def _field_resolved_values(value: Any, meta: Mapping[str, Any]) -> list[str]:
    if value in (None, "", [], {}):
        return []
    values = value if isinstance(value, list) else [value]
    enum_map = {
        str(item.get("ID") or "").strip(): str(item.get("VALUE") or "").strip()
        for item in meta.get("items") or []
        if isinstance(item, Mapping)
        and str(item.get("ID") or "").strip()
        and str(item.get("VALUE") or "").strip()
    }
    resolved: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        text = enum_map.get(str(raw_value or "").strip()) or _field_value_text(raw_value)
        text = " ".join(str(text or "").split()).strip()
        if text and text not in seen:
            seen.add(text)
            resolved.append(text)
    return resolved


def _deal_lost_reason_values(
    deal: Mapping[str, Any],
    fields: Mapping[str, Mapping[str, Any]],
    field_codes: Sequence[str],
) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for field_code in field_codes:
        for value in _field_resolved_values(deal.get(field_code), fields.get(field_code, {})):
            if value not in seen:
                seen.add(value)
                values.append(value)
    return values


def _is_spam_reason(value: str) -> bool:
    normalized = _lower(value).replace("ё", "е")
    return bool(re.search(r"(^|[^a-zа-я0-9])(spam|спам)([^a-zа-я0-9]|$)", normalized, flags=re.IGNORECASE))


def _load_company_requisites(auth: BitrixAppAuth, company_ids: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    ids = sorted({_valid_id(value) for value in company_ids if _valid_id(value)}, key=lambda item: int(item))
    result_by_id: dict[str, list[dict[str, Any]]] = {item_id: [] for item_id in ids}
    select = [
        "ID",
        "ENTITY_TYPE_ID",
        "ENTITY_ID",
        "PRESET_ID",
        "NAME",
        "RQ_NAME",
        "RQ_COMPANY_NAME",
        "RQ_COMPANY_FULL_NAME",
        "RQ_INN",
        "RQ_KPP",
        "RQ_OGRN",
        "RQ_OGRNIP",
        "RQ_OKPO",
    ]
    for chunk in _chunks(ids, 50):
        key_to_id = {f"r{company_id}": company_id for company_id in chunk}
        cmd = {
            key: "crm.requisite.list?"
            + _encode_params(
                {
                    "filter": {
                        "ENTITY_TYPE_ID": COMPANY_ENTITY_TYPE_ID,
                        "ENTITY_ID": company_id,
                    },
                    "select": select,
                }
            )
            for key, company_id in key_to_id.items()
        }
        payload = auth.call_payload("batch", {"halt": 0, "cmd": cmd}, default={})
        root = payload.get("result") if isinstance(payload, Mapping) else None
        batch_results = root.get("result") if isinstance(root, Mapping) else {}
        if not isinstance(batch_results, Mapping):
            continue
        for key, company_id in key_to_id.items():
            value = batch_results.get(key, [])
            result_by_id[company_id] = [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    return result_by_id


def _load_running_bp_instances(
    auth: BitrixAppAuth,
    company_ids: Iterable[str],
    *,
    template_id: str,
) -> dict[str, list[dict[str, Any]]]:
    ids = sorted({_valid_id(value) for value in company_ids if _valid_id(value)}, key=lambda item: int(item))
    result_by_id: dict[str, list[dict[str, Any]]] = {item_id: [] for item_id in ids}
    for chunk in _chunks(ids, 50):
        key_to_id = {f"bp{company_id}": company_id for company_id in chunk}
        cmd = {
            key: "bizproc.workflow.instances?"
            + _encode_params(
                {
                    "SELECT": [
                        "ID",
                        "MODULE_ID",
                        "ENTITY",
                        "DOCUMENT_ID",
                        "STARTED",
                        "STARTED_BY",
                        "TEMPLATE_ID",
                    ],
                    "FILTER": {
                        "MODULE_ID": "crm",
                        "ENTITY": "CCrmDocumentCompany",
                        "DOCUMENT_ID": f"COMPANY_{company_id}",
                        "TEMPLATE_ID": template_id,
                    },
                }
            )
            for key, company_id in key_to_id.items()
        }
        payload = auth.call_payload("batch", {"halt": 0, "cmd": cmd}, default={})
        root = payload.get("result") if isinstance(payload, Mapping) else None
        batch_results = root.get("result") if isinstance(root, Mapping) else {}
        if not isinstance(batch_results, Mapping):
            continue
        for key, company_id in key_to_id.items():
            value = batch_results.get(key, [])
            result_by_id[company_id] = [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    return result_by_id


def _extract_multi_values(company: Mapping[str, Any], field: str) -> list[str]:
    raw = company.get(field)
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            value = str(item.get("VALUE") or item.get("value") or "").strip()
            if value:
                values.append(value)
    return values


def _first_filled(items: Sequence[Mapping[str, Any]], field: str) -> str:
    for item in items:
        value = str(item.get(field) or "").strip()
        if value:
            return value
    return ""


def _inn_values(requisites: Sequence[Mapping[str, Any]]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in requisites:
        value = str(item.get("RQ_INN") or "").strip()
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _contact_summary(contact: Mapping[str, Any], *, portal_base_url: str) -> str:
    contact_id = _string_id(contact.get("ID"))
    post = str(contact.get("POST") or "").strip()
    suffix = f", {post}" if post else ""
    return f"{_contact_name(contact)}{suffix} [{contact_id}]"


def _priority(stage_bucket: str, problems: Sequence[str]) -> str:
    if not problems:
        return "ОК"
    if stage_bucket in {"в работе", "отложка"}:
        return "Высокий"
    if stage_bucket == "успех":
        return "Средний"
    return "Низкий"


def _status_sort_key(item: Mapping[str, Any]) -> tuple[int, int, int]:
    bucket_weight = {"в работе": 0, "отложка": 1, "успех": 2, "отказ": 3}.get(str(item.get("stage_bucket")), 9)
    problem_weight = 0 if item.get("problems") else 1
    return (bucket_weight, problem_weight, -_int_or(item.get("deal_id"), 0))


def _action_text(actions: Sequence[str]) -> str:
    return "\n".join(f"{index}. {action}" for index, action in enumerate(actions, 1)) if actions else "Ничего не делать: критичных пробелов не найдено."


def build_report(
    auth: BitrixAppAuth,
    *,
    category_id: int,
    portal_base_url: str,
    bp_template_id: str,
) -> dict[str, Any]:
    stages = _load_sales_stages(auth, category_id)
    stage_meta = {
        _stage_id(stage): {
            "id": _stage_id(stage),
            "name": _stage_name(stage),
            "semantics": _stage_semantics(stage),
            "bucket": _stage_bucket_with_success(stage),
        }
        for stage in stages
        if _stage_id(stage)
    }
    included_buckets = {"в работе", "отложка", "отказ", "успех"}
    included_stage_ids = [stage_id for stage_id, item in stage_meta.items() if item["bucket"] in included_buckets]
    deal_fields = _load_entity_fields(auth, "crm.deal.fields")
    company_fields = _load_entity_fields(auth, "crm.company.fields")
    client_site_deal_fields = _client_site_field_codes(deal_fields, include_fallbacks=True)
    client_site_company_fields = _client_site_field_codes(company_fields, include_fallbacks=False)
    lost_reason_fields = _lost_reason_field_codes(deal_fields)
    deals = _load_deals_extended(auth, category_id=category_id, stage_ids=included_stage_ids)
    excluded_spam_reason_deals: list[dict[str, Any]] = []
    included_deals: list[dict[str, Any]] = []
    for deal in deals:
        lost_reasons = _deal_lost_reason_values(deal, deal_fields, lost_reason_fields)
        if any(_is_spam_reason(reason) for reason in lost_reasons):
            excluded_spam_reason_deals.append(
                {
                    "deal_id": _valid_id(deal.get("ID")),
                    "deal_title": str(deal.get("TITLE") or ""),
                    "stage_id": _string_id(deal.get("STAGE_ID")),
                    "lost_reasons": lost_reasons,
                }
            )
            continue
        included_deals.append(deal)
    deals = included_deals
    company_ids = [_valid_id(deal.get("COMPANY_ID")) for deal in deals]
    companies = _load_companies_extended(auth, company_ids)
    requisites_by_company = _load_company_requisites(auth, company_ids)
    bp_load_warning = ""
    try:
        running_bp_by_company = _load_running_bp_instances(auth, company_ids, template_id=bp_template_id)
    except Exception as error:  # noqa: BLE001 - отчёт не должен падать из-за недоступной истории БП.
        running_bp_by_company = {}
        bp_load_warning = f"Не удалось проверить активные БП через bizproc.workflow.instances: {error}"
    company_contact_cache = _batch_id_get(auth, method="crm.company.contact.items.get", ids=company_ids)
    deal_contact_cache = _batch_id_get(auth, method="crm.deal.contact.items.get", ids=[deal.get("ID") for deal in deals])

    all_contact_ids: set[str] = set()
    contact_plans: dict[str, dict[str, Any]] = {}
    for deal in deals:
        deal_id = _valid_id(deal.get("ID"))
        company_id = _valid_id(deal.get("COMPANY_ID"))
        if not deal_id or not company_id:
            continue
        plan = build_sync_plan(
            deal_id=deal_id,
            company_id=company_id,
            company_contact_items=[item for item in company_contact_cache.get(company_id, []) if isinstance(item, Mapping)],
            deal_contact_items=[item for item in deal_contact_cache.get(deal_id, []) if isinstance(item, Mapping)],
        )
        contact_plans[deal_id] = plan
        all_contact_ids.update(str(contact_id) for contact_id in plan.get("company_contact_ids", []))
        all_contact_ids.update(str(contact_id) for contact_id in plan.get("existing_deal_contact_ids", []))
        for addition in plan.get("additions", []):
            if isinstance(addition, Mapping):
                all_contact_ids.add(str(addition.get("CONTACT_ID") or ""))

    contacts = _load_contacts(auth, all_contact_ids)
    rows: list[dict[str, Any]] = []
    problem_counter: Counter[str] = Counter()
    action_counter: Counter[str] = Counter()
    bucket_counter: Counter[str] = Counter()

    for deal in deals:
        deal_id = _valid_id(deal.get("ID"))
        company_id = _valid_id(deal.get("COMPANY_ID"))
        stage_id = _string_id(deal.get("STAGE_ID"))
        stage = stage_meta.get(stage_id, {"name": stage_id, "bucket": ""})
        stage_bucket = str(stage.get("bucket") or "")
        bucket_counter[stage_bucket] += 1
        company = companies.get(company_id, {})
        requisites = requisites_by_company.get(company_id, [])
        inn_list = _inn_values(requisites)
        has_inn = bool(inn_list)
        has_ogrn = bool(_first_filled(requisites, "RQ_OGRN") or _first_filled(requisites, "RQ_OGRNIP"))
        has_kpp = bool(_first_filled(requisites, "RQ_KPP"))
        web_values = _extract_multi_values(company, "WEB")
        client_site, client_site_source = _first_field_value(deal, client_site_deal_fields)
        if not client_site:
            client_site, client_site_source = _first_field_value(company, client_site_company_fields)
        plan = contact_plans.get(
            deal_id,
            {
                "company_contact_ids": [],
                "existing_deal_contact_ids": [],
                "additions": [],
                "additions_count": 0,
            },
        )
        missing_contact_ids = [str(item.get("CONTACT_ID")) for item in plan.get("additions", []) if isinstance(item, Mapping)]
        missing_contacts = [
            _contact_summary(contacts.get(contact_id, {"ID": contact_id}), portal_base_url=portal_base_url)
            for contact_id in missing_contact_ids
        ]
        running_bp = running_bp_by_company.get(company_id, [])

        problems: list[str] = []
        actions: list[str] = []

        if not company_id:
            problems.append("У сделки не привязана компания")
            actions.append("Привязать корректную компанию к сделке; после этого проверить ИНН, контакты и БП.")
        else:
            if not has_inn:
                problems.append("Не заполнен ИНН в реквизитах компании")
                if web_values:
                    actions.append("Найти ИНН по сайту/названию компании и заполнить реквизиты компании.")
                else:
                    actions.append("Найти ИНН вручную по названию компании: в карточке компании нет сайта.")
                actions.append("После заполнения ИНН запустить бизнес-процесс обновления данных юрлица.")

            if not plan.get("company_contact_ids"):
                problems.append("В компании нет привязанных контактов")
                actions.append("Добавить контакты в компанию; затем синхронизировать контакты компании в сделку.")
            elif int(plan.get("additions_count") or 0) > 0:
                problems.append("Не все контакты компании добавлены в сделку")
                actions.append(f"Добавить в сделку контакты компании: {', '.join(missing_contacts)}.")

            if has_inn and not running_bp and (not has_ogrn or not has_kpp):
                problems.append("Данные юрлица неполные: БП обновления данных, вероятно, не запускался или не завершил обогащение")
                actions.append("Запустить бизнес-процесс обновления данных по компании и проверить заполнение ОГРН/КПП.")
            elif has_inn and running_bp:
                problems.append("Бизнес-процесс обновления данных сейчас в работе")
                actions.append("Дождаться завершения БП и повторно проверить реквизиты.")

            if not web_values and not has_inn:
                problems.append("Нет сайта в карточке компании для быстрого поиска ИНН")

        for problem in problems:
            problem_counter[problem] += 1
        for action in actions:
            action_counter[action.split(":", 1)[0]] += 1

        row = {
            "deal_id": deal_id,
            "deal_title": str(deal.get("TITLE") or ""),
            "deal_url": _portal_link(f"crm/deal/details/{deal_id}/", portal_base_url=portal_base_url) if deal_id else "",
            "stage_id": stage_id,
            "stage_name": str(stage.get("name") or stage_id),
            "stage_bucket": stage_bucket,
            "closed": str(deal.get("CLOSED") or ""),
            "company_id": company_id,
            "company_title": str(company.get("TITLE") or ""),
            "company_url": _portal_link(f"crm/company/details/{company_id}/", portal_base_url=portal_base_url) if company_id else "",
            "company_web": ", ".join(web_values),
            "client_site": client_site,
            "client_site_source": client_site_source,
            "inn": ", ".join(inn_list),
            "kpp": _first_filled(requisites, "RQ_KPP"),
            "ogrn": _first_filled(requisites, "RQ_OGRN") or _first_filled(requisites, "RQ_OGRNIP"),
            "requisites_count": len(requisites),
            "bp_template_id": bp_template_id,
            "running_bp_count": len(running_bp),
            "company_contacts_count": len(plan.get("company_contact_ids") or []),
            "deal_contacts_count": len(plan.get("existing_deal_contact_ids") or []),
            "missing_contacts_count": int(plan.get("additions_count") or 0),
            "missing_contacts": "; ".join(missing_contacts),
            "problems_count": len(problems),
            "problems": "\n".join(problems),
            "recommended_actions": _action_text(actions),
            "priority": _priority(stage_bucket, problems),
            "opportunity": str(deal.get("OPPORTUNITY") or ""),
            "currency": str(deal.get("CURRENCY_ID") or ""),
            "date_create": str(deal.get("DATE_CREATE") or ""),
            "date_modify": str(deal.get("DATE_MODIFY") or ""),
            "assigned_by_id": str(deal.get("ASSIGNED_BY_ID") or ""),
        }
        rows.append(row)

    rows.sort(key=_status_sort_key)
    problem_rows = [row for row in rows if int(row.get("problems_count") or 0) > 0]
    by_bucket_with_problems: Counter[str] = Counter(str(row.get("stage_bucket") or "") for row in problem_rows)
    by_problem: Counter[str] = Counter()
    for row in problem_rows:
        for problem in str(row.get("problems") or "").split("\n"):
            if problem:
                by_problem[problem] += 1

    return {
        "ok": True,
        "category_id": category_id,
        "bp_template_id": bp_template_id,
        "portal_base_url": portal_base_url,
        "stages": sorted(stage_meta.values(), key=lambda item: str(item["id"])),
        "included_stage_ids": included_stage_ids,
        "excluded_stage_ids": [
            stage_id for stage_id, item in stage_meta.items() if item["bucket"] not in included_buckets
        ],
        "deals_checked_count": len(rows),
        "excluded_spam_reason_count": len(excluded_spam_reason_deals),
        "excluded_spam_reason_deals": excluded_spam_reason_deals,
        "deals_with_problems_count": len(problem_rows),
        "deals_without_problems_count": len(rows) - len(problem_rows),
        "by_bucket": dict(sorted(bucket_counter.items())),
        "by_bucket_with_problems": dict(sorted(by_bucket_with_problems.items())),
        "by_problem": dict(by_problem.most_common()),
        "action_kinds": dict(action_counter.most_common()),
        "client_site_fields": {
            "deal": client_site_deal_fields,
            "company": client_site_company_fields,
        },
        "lost_reason_fields": lost_reason_fields,
        "warnings": [bp_load_warning] if bp_load_warning else [],
        "rows": rows,
    }


CSV_FIELDS = [
    "priority",
    "stage_bucket",
    "stage_name",
    "deal_id",
    "deal_title",
    "deal_url",
    "company_id",
    "company_title",
    "company_url",
    "company_web",
    "client_site",
    "inn",
    "kpp",
    "ogrn",
    "requisites_count",
    "running_bp_count",
    "company_contacts_count",
    "deal_contacts_count",
    "missing_contacts_count",
    "missing_contacts",
    "problems_count",
    "problems",
    "recommended_actions",
    "opportunity",
    "currency",
    "date_create",
    "date_modify",
    "assigned_by_id",
]


def write_csv(report: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = report.get("rows")
    if not isinstance(rows, list):
        rows = []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for item in rows:
            if not isinstance(item, Mapping):
                continue
            writer.writerow({field: item.get(field, "") for field in CSV_FIELDS})


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Сформировать отчёт качества данных сделок воронки Продажи.")
    parser.add_argument("--category-id", type=int, default=int(os.environ.get("BITRIX_SALES_DATA_QUALITY_CATEGORY_ID", str(SALES_DEAL_CATEGORY_ID))))
    parser.add_argument("--portal-base-url", default=os.environ.get("BITRIX_PORTAL_BASE_URL", DEFAULT_PORTAL_BASE_URL))
    parser.add_argument("--bp-template-id", default=os.environ.get("BITRIX_COMPANY_DATA_BP_TEMPLATE_ID", BP_TEMPLATE_ID))
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--json", action="store_true", default=os.environ.get("BITRIX_SALES_DATA_QUALITY_JSON") == "1")
    parser.add_argument("--no-remote-bridge", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    auth, tmp_dir = _load_auth_env(use_remote_bridge=not args.no_remote_bridge)
    try:
        report = build_report(
            auth,
            category_id=int(args.category_id),
            portal_base_url=str(args.portal_base_url),
            bp_template_id=str(args.bp_template_id),
        )
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
