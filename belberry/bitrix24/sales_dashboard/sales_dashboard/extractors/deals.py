"""Экстрактор сделок из Bitrix24.

Инкрементально тянет crm.deal.list по DATE_MODIFY > since.
Поля выбраны под типовой sales-дашборд (воронка, конверсии, KPI менеджера).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from ..bitrix_client import BitrixClient
from ..config import DEAL_CATEGORIES, MOSCOW_TZ

# Колонки в Sheet (порядок = порядок в header).
HEADER = [
    "deal_id",
    "title",
    "category_id",
    "category_name",        # ← join из categories
    "stage_id",
    "stage_name",           # ← join из stages
    "stage_semantic",       # P=in progress, S=success, F=fail
    "is_closed",
    "is_won",
    "is_lost",
    "opportunity",          # сумма сделки
    "currency_id",
    "assigned_by_id",
    "manager",              # ← join из users
    "created_by_id",
    "source_id",
    "type_id",
    "company_id",
    "contact_id",
    "date_create",
    "date_modify",
    "begindate",
    "closedate",
    "lead_id",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "url",                  # ссылка на карточку
]

DEAL_FIELDS = [
    "ID",
    "TITLE",
    "CATEGORY_ID",
    "STAGE_ID",
    "STAGE_SEMANTIC_ID",
    "CLOSED",
    "OPPORTUNITY",
    "CURRENCY_ID",
    "ASSIGNED_BY_ID",
    "CREATED_BY_ID",
    "SOURCE_ID",
    "TYPE_ID",
    "COMPANY_ID",
    "CONTACT_ID",
    "DATE_CREATE",
    "DATE_MODIFY",
    "BEGINDATE",
    "CLOSEDATE",
    "LEAD_ID",
    "UTM_SOURCE",
    "UTM_MEDIUM",
    "UTM_CAMPAIGN",
]


def extract_deals(
    client: BitrixClient,
    since: datetime | None,
    portal_domain: str,
    user_names: dict[int, str] | None = None,
    stage_names: dict[str, str] | None = None,
    category_names: dict[int, str] | None = None,
) -> list[list]:
    """Возвращает список строк для Sheets.

    since=None → полная выгрузка. Иначе DATE_MODIFY > since (MSK).
    user_names / stage_names / category_names — карты для denormalization
    (чтобы в Looker Studio видеть имена, а не голые ID).
    """
    flt: dict = {}
    if since is not None:
        flt[">DATE_MODIFY"] = since.astimezone(MOSCOW_TZ).strftime("%Y-%m-%dT%H:%M:%S")
    if DEAL_CATEGORIES:
        flt["CATEGORY_ID"] = DEAL_CATEGORIES

    params = {
        "filter": flt,
        "select": DEAL_FIELDS,
    }

    rows: list[list] = []
    for d in client.paginate("crm.deal.list", params, id_field="ID"):
        rows.append(
            _to_row(d, portal_domain, user_names or {}, stage_names or {}, category_names or {})
        )
    return rows


def _to_row(
    d: dict,
    portal_domain: str,
    user_names: dict[int, str],
    stage_names: dict[str, str],
    category_names: dict[int, str],
) -> list:
    stage_semantic = d.get("STAGE_SEMANTIC_ID") or ""
    closed = (d.get("CLOSED") or "N") == "Y"
    cat_id = _as_int(d.get("CATEGORY_ID"))
    stage_id = d.get("STAGE_ID") or ""
    assigned = _as_int(d.get("ASSIGNED_BY_ID"))
    return [
        _as_int(d.get("ID")),
        d.get("TITLE") or "",
        cat_id,
        category_names.get(cat_id, "") if isinstance(cat_id, int) else "",
        stage_id,
        stage_names.get(stage_id, ""),
        stage_semantic,
        "Y" if closed else "N",
        "Y" if closed and stage_semantic == "S" else "N",
        "Y" if closed and stage_semantic == "F" else "N",
        _as_float(d.get("OPPORTUNITY")),
        d.get("CURRENCY_ID") or "",
        assigned,
        user_names.get(assigned, "") if isinstance(assigned, int) else "",
        _as_int(d.get("CREATED_BY_ID")),
        _as_int(d.get("SOURCE_ID")) if d.get("SOURCE_ID") else "",
        _as_int(d.get("TYPE_ID")) if d.get("TYPE_ID") else "",
        _as_int(d.get("COMPANY_ID")),
        _as_int(d.get("CONTACT_ID")),
        d.get("DATE_CREATE") or "",
        d.get("DATE_MODIFY") or "",
        d.get("BEGINDATE") or "",
        d.get("CLOSEDATE") or "",
        _as_int(d.get("LEAD_ID")) if d.get("LEAD_ID") else "",
        d.get("UTM_SOURCE") or "",
        d.get("UTM_MEDIUM") or "",
        d.get("UTM_CAMPAIGN") or "",
        f"https://{portal_domain}/crm/deal/details/{d.get('ID')}/",
    ]


def _as_int(v) -> int | str:
    try:
        return int(v)
    except (TypeError, ValueError):
        return ""


def _as_float(v) -> float | str:
    try:
        return float(v)
    except (TypeError, ValueError):
        return ""
