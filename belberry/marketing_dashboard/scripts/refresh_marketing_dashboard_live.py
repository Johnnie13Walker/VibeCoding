#!/usr/bin/env python3
"""Пересобирает live-слои маркетингового дашборда из Bitrix24."""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(os.environ.get("MARKETING_DASHBOARD_ROOT_DIR", Path(__file__).resolve().parents[1]))
ENGINEER_ROOT = Path(os.environ.get("MARKETING_DASHBOARD_ENGINEER_ROOT", Path(__file__).resolve().parents[3] / "cloudbot"))
TMP_DIR = Path("/tmp")

sys.path.insert(0, str(ROOT / "scripts"))
from bitrix_field_audit_gd324 import make_auth  # noqa: E402

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
SALES_CATEGORY_ID = 10
TELEMARKETING_CATEGORY_ID = 50
MEETINGS_ENTITY_TYPE_ID = 1048
MEETING_HELD_STAGE_ID = "DT1048_24:SUCCESS"
MEETING_SCHEDULED_AT_FIELD = "ufCrm16_1751009238"
TELEMARKETING_DEPARTMENT_ID = "1638"
TELEMARKETING_SOURCE_NAME = "Телемаркетинг"
BRAND_FIELD = "UF_CRM_1721661506"
REJECTION_REASON_FIELD = "UF_CRM_1771495464"
SPAM_REJECTION_REASONS = {"спам", "spam", "вход: нет связи", "нет связи"}
NON_LEAD_REJECTION_REASONS: set[str] = set()
START_DT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=MOSCOW_TZ)

STAGE_MAP = {
    "lead": "C10:PREPAYMENT_INVOIC",
    "kp": "C10:EXECUTING",
    "contract": "C10:UC_KC7195",
    "sale": "C10:WON",
}
STAGE_ORDER = ("lead", "kp", "contract", "sale")
DEAL_SELECT_FIELDS = [
    "ID",
    "TITLE",
    "DATE_CREATE",
    "CATEGORY_ID",
    "STAGE_ID",
    "SOURCE_ID",
    "ASSIGNED_BY_ID",
    "OPPORTUNITY",
    BRAND_FIELD,
    REJECTION_REASON_FIELD,
]
HISTORY_SELECT_FIELDS = ["ID", "OWNER_ID", "CATEGORY_ID", "STAGE_ID", "CREATED_TIME", "STAGE_SEMANTIC_ID"]


@dataclass
class DealCard:
    id: str
    title: str
    created_at: datetime | None
    category_id: str
    stage_id: str
    source_id: str
    assigned_id: str
    amount: float
    brand_raw: str
    rejection_reason_raw: str


def log(message: str) -> None:
    print(message, flush=True)


def to_iso(dt: datetime) -> str:
    return dt.astimezone(MOSCOW_TZ).isoformat(timespec="seconds")


def parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MOSCOW_TZ)
    return dt.astimezone(MOSCOW_TZ)


def month_key(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone(MOSCOW_TZ).strftime("%Y-%m")


def fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M")


def fmt_date(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone(MOSCOW_TZ).strftime("%d.%m.%Y")


def first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def as_float(value: Any) -> float:
    try:
        return float(str(value or "0").replace(" ", ""))
    except ValueError:
        return 0.0


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = str(value or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(key)
    return output


def payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        result = payload.get("result")
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict):
            for key in ("items", "result", "categories"):
                value = result.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
    return []


def make_deal_card(item: dict[str, Any]) -> DealCard:
    return DealCard(
        id=str(item.get("ID") or "").strip(),
        title=str(item.get("TITLE") or "").strip(),
        created_at=parse_dt(item.get("DATE_CREATE")),
        category_id=str(item.get("CATEGORY_ID") or "").strip(),
        stage_id=str(item.get("STAGE_ID") or "").strip(),
        source_id=str(item.get("SOURCE_ID") or "").strip(),
        assigned_id=str(item.get("ASSIGNED_BY_ID") or "").strip(),
        amount=as_float(item.get("OPPORTUNITY")),
        brand_raw=str(item.get(BRAND_FIELD) or "").strip(),
        rejection_reason_raw=str(item.get(REJECTION_REASON_FIELD) or "").strip(),
    )


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def ensure_tmp_dir() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)


def load_brand_map(auth: Any) -> dict[str, str]:
    payload = auth.call_payload("crm.deal.fields", default={})
    result = payload.get("result") if isinstance(payload, dict) else payload
    fields = result if isinstance(result, dict) else {}
    brand_meta = fields.get(BRAND_FIELD) if isinstance(fields, dict) else {}
    items = brand_meta.get("items") if isinstance(brand_meta, dict) else []
    mapping: dict[str, str] = {}
    for item in items if isinstance(items, list) else []:
        item_id = str(item.get("ID") or "").strip()
        item_value = str(item.get("VALUE") or "").strip()
        if item_id and item_value:
            mapping[item_id] = item_value
    return mapping


def load_deal_enum_map(auth: Any, field_code: str) -> dict[str, str]:
    payload = auth.call_payload("crm.deal.fields", default={})
    result = payload.get("result") if isinstance(payload, dict) else payload
    fields = result if isinstance(result, dict) else {}
    field_meta = fields.get(field_code) if isinstance(fields, dict) else {}
    items = field_meta.get("items") if isinstance(field_meta, dict) else []
    mapping: dict[str, str] = {}
    for item in items if isinstance(items, list) else []:
        item_id = str(item.get("ID") or "").strip()
        item_value = str(item.get("VALUE") or "").strip()
        if item_id and item_value:
            mapping[item_id] = item_value
    return mapping


def load_source_map(auth: Any) -> dict[str, str]:
    items = auth.list_method("crm.status.list", params={"filter": {"ENTITY_ID": "SOURCE"}})
    mapping: dict[str, str] = {}
    for item in items:
        key = str(item.get("STATUS_ID") or "").strip()
        value = str(item.get("NAME") or "").strip()
        if key and value:
            mapping[key] = value
    return mapping


def load_category_map(auth: Any) -> dict[str, str]:
    payload = auth.call_payload("crm.category.list", params={"entityTypeId": 2}, default={})
    items = payload_items(payload)
    mapping: dict[str, str] = {}
    for item in items:
        key = str(item.get("id") or item.get("ID") or "").strip()
        value = str(item.get("name") or item.get("NAME") or "").strip()
        if key and value:
            mapping[key] = value
    return mapping


def load_stage_maps(auth: Any, category_ids: list[str]) -> dict[str, dict[str, str]]:
    maps: dict[str, dict[str, str]] = {}
    for category_id in dedupe(category_ids):
        items = auth.list_method("crm.status.list", params={"filter": {"ENTITY_ID": f"DEAL_STAGE_{category_id}"}})
        stage_map: dict[str, str] = {}
        for item in items:
            key = str(item.get("STATUS_ID") or "").strip()
            value = str(item.get("NAME") or "").strip()
            if key and value:
                stage_map[key] = value
        maps[category_id] = stage_map
    return maps


def list_created_deals(auth: Any, end_dt: datetime) -> list[DealCard]:
    params = {
        "select": DEAL_SELECT_FIELDS,
        "filter": {
            ">=DATE_CREATE": to_iso(START_DT),
            "<=DATE_CREATE": to_iso(end_dt),
        },
        "order": {"DATE_CREATE": "ASC"},
    }
    items = auth.list_method("crm.deal.list", params=params)
    return [make_deal_card(item) for item in items if isinstance(item, dict)]


def list_deals_by_ids(auth: Any, deal_ids: list[str]) -> dict[str, DealCard]:
    result: dict[str, DealCard] = {}
    for chunk in chunked(dedupe(deal_ids), 50):
        items = auth.list_method(
            "crm.deal.list",
            params={"select": DEAL_SELECT_FIELDS, "filter": {"ID": chunk}, "order": {"ID": "ASC"}},
            limit=len(chunk),
        )
        for item in items:
            if not isinstance(item, dict):
                continue
            card = make_deal_card(item)
            if card.id:
                result[card.id] = card
    return result


def list_period_sales_history(auth: Any, end_dt: datetime) -> list[dict[str, Any]]:
    params = {
        "entityTypeId": 2,
        "select": HISTORY_SELECT_FIELDS,
        "filter": {
            "CATEGORY_ID": SALES_CATEGORY_ID,
            ">=CREATED_TIME": to_iso(START_DT),
            "<=CREATED_TIME": to_iso(end_dt),
        },
        "order": {"CREATED_TIME": "ASC"},
    }
    return auth.list_method("crm.stagehistory.list", params=params)


def list_sales_history_for_owners(auth: Any, owner_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    return list_stage_history_for_owners(auth, owner_ids, SALES_CATEGORY_ID)


def list_stage_history_for_owners(auth: Any, owner_ids: list[str], category_id: int) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunked(dedupe(owner_ids), 50):
        params = {
            "entityTypeId": 2,
            "select": HISTORY_SELECT_FIELDS,
            "filter": {"OWNER_ID": chunk, "CATEGORY_ID": category_id},
            "order": {"CREATED_TIME": "ASC"},
        }
        rows = auth.list_method("crm.stagehistory.list", params=params)
        for row in rows:
            if not isinstance(row, dict):
                continue
            owner_id = str(row.get("OWNER_ID") or "").strip()
            if owner_id:
                result[owner_id].append(row)
    for owner_id in result:
        result[owner_id].sort(key=lambda row: str(row.get("CREATED_TIME") or ""))
    return dict(result)


def resolve_stage_name(category_id: str, stage_id: str, stage_maps: dict[str, dict[str, str]]) -> str:
    return stage_maps.get(str(category_id or "").strip(), {}).get(str(stage_id or "").strip(), str(stage_id or "").strip())


def resolve_brand(raw_value: str, brand_map: dict[str, str]) -> str:
    if not raw_value:
        return "Без бренда"
    return brand_map.get(raw_value, raw_value)


def resolve_source(raw_value: str, source_map: dict[str, str]) -> str:
    if not raw_value:
        return "Без источника"
    return source_map.get(raw_value, raw_value)


def resolve_effective_source(deal: DealCard, source_map: dict[str, str], source_overrides: dict[str, str] | None = None) -> str:
    override = (source_overrides or {}).get(deal.id)
    if override:
        return override
    source = resolve_source(deal.source_id, source_map)
    if source == TELEMARKETING_SOURCE_NAME:
        return "Не выяснено"
    return source


def normalize_reason(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split()).replace("ё", "е")


def resolve_rejection_reason(raw_value: str, reason_map: dict[str, str]) -> str:
    raw = str(raw_value or "").strip()
    if not raw:
        return ""
    return reason_map.get(raw, raw)


def is_spam_rejection(raw_value: str, reason_map: dict[str, str]) -> bool:
    normalized = normalize_reason(resolve_rejection_reason(raw_value, reason_map))
    return normalized in SPAM_REJECTION_REASONS


def is_non_lead_rejection(raw_value: str, reason_map: dict[str, str]) -> bool:
    normalized = normalize_reason(resolve_rejection_reason(raw_value, reason_map))
    return normalized in NON_LEAD_REJECTION_REASONS


def format_manager_name(last_name: str, first_name: str, fallback: str = "") -> str:
    parts = [str(last_name or "").strip(), str(first_name or "").strip()]
    normalized = " ".join(part for part in parts if part).strip()
    return normalized or str(fallback or "").strip()


def list_users_by_ids(auth: Any, user_ids: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for user_id in dedupe(user_ids):
        rows = auth.list_method("user.get", params={"FILTER": {"ID": [user_id]}}, limit=1)
        for row in rows:
            if not isinstance(row, dict):
                continue
            uid = str(row.get("ID") or "").strip()
            full_name = format_manager_name(row.get("LAST_NAME") or "", row.get("NAME") or "", uid)
            if uid:
                result[uid] = full_name or uid
    return result


def list_user_department_ids(auth: Any, user_ids: list[str]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    ids = dedupe(user_ids)
    if not ids:
        return result
    rows = auth.list_method("user.get", params={"FILTER": {"ID": ids}}, limit=len(ids))
    for row in rows:
        if not isinstance(row, dict):
            continue
        uid = str(row.get("ID") or "").strip()
        departments = {str(item) for item in (row.get("UF_DEPARTMENT") or [])}
        if uid:
            result[uid] = departments
    return result


def list_meetings_for_deals(auth: Any, deal_ids: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for chunk in chunked(dedupe(deal_ids), 50):
        rows = auth.list_method(
            "crm.item.list",
            params={
                "entityTypeId": MEETINGS_ENTITY_TYPE_ID,
                "select": ["id", "title", "createdBy", "assignedById", "parentId2", "createdTime", "stageId", MEETING_SCHEDULED_AT_FIELD],
                "filter": {"parentId2": chunk},
                "order": {MEETING_SCHEDULED_AT_FIELD: "ASC"},
            },
        )
        result.extend(row for row in rows if isinstance(row, dict))
    return result


def has_telemarketing_to_sales_transition(
    telemarketing_rows: list[dict[str, Any]],
    sales_rows: list[dict[str, Any]],
) -> bool:
    telemarketing_dates = [dt for dt in (parse_dt(row.get("CREATED_TIME")) for row in telemarketing_rows) if dt is not None]
    sales_dates = [dt for dt in (parse_dt(row.get("CREATED_TIME")) for row in sales_rows) if dt is not None]
    if not telemarketing_dates or not sales_dates:
        return False
    return any(sales_dt >= tele_dt for tele_dt in telemarketing_dates for sales_dt in sales_dates)


def meeting_report_dt(meeting: dict[str, Any]) -> datetime | None:
    return parse_dt(meeting.get(MEETING_SCHEDULED_AT_FIELD)) or parse_dt(meeting.get("createdTime"))


def first_meeting_by_report_time(meetings: list[dict[str, Any]]) -> dict[str, Any] | None:
    dated_meetings = [
        (meeting_report_dt(meeting) or datetime.max.replace(tzinfo=MOSCOW_TZ), meeting)
        for meeting in meetings
    ]
    if not dated_meetings:
        return None
    return min(dated_meetings, key=lambda item: item[0])[1]


def first_held_meeting_by_report_time(meetings: list[dict[str, Any]]) -> dict[str, Any] | None:
    held_meetings = [
        meeting
        for meeting in meetings
        if str(meeting.get("stageId") or "").strip() == MEETING_HELD_STAGE_ID
    ]
    return first_meeting_by_report_time(held_meetings)


def build_telemarketing_source_overrides(
    auth: Any,
    deal_ids: list[str],
    sales_history_by_id: dict[str, list[dict[str, Any]]],
    telemarketing_history_by_id: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, str], dict[str, bool], dict[str, dict[str, Any]], dict[str, Any]]:
    meetings = list_meetings_for_deals(auth, deal_ids)
    meeting_creator_ids = dedupe([str(row.get("createdBy") or "").strip() for row in meetings])
    departments_by_user = list_user_department_ids(auth, meeting_creator_ids)
    telemarketing_users = {
        user_id
        for user_id, department_ids in departments_by_user.items()
        if TELEMARKETING_DEPARTMENT_ID in department_ids
    }

    meetings_by_deal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for meeting in meetings:
        deal_id = str(meeting.get("parentId2") or "").strip()
        creator_id = str(meeting.get("createdBy") or "").strip()
        if deal_id and creator_id in telemarketing_users:
            meetings_by_deal[deal_id].append(meeting)

    overrides: dict[str, str] = {}
    lead_allowed: dict[str, bool] = {}
    meeting_stats_by_deal: dict[str, dict[str, Any]] = {}
    matched_meeting_ids: list[str] = []
    for deal_id in dedupe(deal_ids):
        if not meetings_by_deal.get(deal_id):
            continue
        deal_meetings = meetings_by_deal[deal_id]
        first_meeting = first_meeting_by_report_time(deal_meetings)
        first_held_meeting = first_held_meeting_by_report_time(deal_meetings)
        first_meeting_at = meeting_report_dt(first_meeting or {})
        first_held_meeting_at = meeting_report_dt(first_held_meeting or {})
        lead_allowed[deal_id] = first_held_meeting is not None
        meeting_stats_by_deal[deal_id] = {
            "first_meeting_id": str((first_meeting or {}).get("id") or "").strip(),
            "first_meeting_at": to_iso(first_meeting_at) if first_meeting_at else "",
            "first_meeting_month": month_key(first_meeting_at),
            "first_meeting_held": str((first_meeting or {}).get("stageId") or "").strip() == MEETING_HELD_STAGE_ID,
            "first_held_meeting_id": str((first_held_meeting or {}).get("id") or "").strip(),
            "first_held_meeting_at": to_iso(first_held_meeting_at) if first_held_meeting_at else "",
            "first_held_meeting_month": month_key(first_held_meeting_at),
            "has_held_meeting": first_held_meeting is not None,
            "meetings_count": len(deal_meetings),
            "held_meetings_count": sum(1 for meeting in deal_meetings if str(meeting.get("stageId") or "").strip() == MEETING_HELD_STAGE_ID),
        }
        overrides[deal_id] = TELEMARKETING_SOURCE_NAME
        matched_meeting_ids.extend(str(meeting.get("id") or "").strip() for meeting in deal_meetings)

    control = {
        "source_name": TELEMARKETING_SOURCE_NAME,
        "deal_category_id": TELEMARKETING_CATEGORY_ID,
        "meetings_entity_type_id": MEETINGS_ENTITY_TYPE_ID,
        "meeting_deal_field": "parentId2",
        "meeting_creator_field": "createdBy",
        "meeting_scheduled_at_field": MEETING_SCHEDULED_AT_FIELD,
        "meeting_held_stage_id": MEETING_HELD_STAGE_ID,
        "telemarketing_department_id": TELEMARKETING_DEPARTMENT_ID,
        "meetings_found": len(meetings),
        "telemarketing_meetings_found": sum(len(rows) for rows in meetings_by_deal.values()),
        "telemarketing_users": sorted(telemarketing_users),
        "deals_with_telemarketing_history": sum(1 for deal_id in deal_ids if telemarketing_history_by_id.get(deal_id)),
        "deals_with_telemarketing_meetings": len(meetings_by_deal),
        "logic": "Источник Телемаркетинг определяется по встрече, созданной сотрудником отдела телемаркетинга; переход из воронки Телемаркетинг больше не обязателен, потому что до марта 2026 телемаркетологи работали из лидов.",
        "deals_overridden": len(overrides),
        "deals_with_held_meeting": sum(1 for allowed in lead_allowed.values() if allowed),
        "deals_without_held_meeting": sum(1 for allowed in lead_allowed.values() if not allowed),
        "deals_with_first_meeting_held": sum(1 for stats in meeting_stats_by_deal.values() if stats.get("first_meeting_held")),
        "deals_without_held_first_meeting": sum(1 for stats in meeting_stats_by_deal.values() if not stats.get("first_meeting_held")),
        "deal_ids": sorted(overrides),
        "lead_allowed_deal_ids": sorted(deal_id for deal_id, allowed in lead_allowed.items() if allowed),
        "lead_denied_deal_ids": sorted(deal_id for deal_id, allowed in lead_allowed.items() if not allowed),
        "meeting_stats_by_deal": meeting_stats_by_deal,
        "meeting_ids": sorted(dedupe(matched_meeting_ids)),
    }
    return overrides, lead_allowed, meeting_stats_by_deal, control


def list_product_rows(auth: Any, deal_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for deal_id in dedupe(deal_ids):
        rows = auth.call_method("crm.deal.productrows.get", params={"id": deal_id}, default=[])
        if isinstance(rows, list):
            result[deal_id] = [dict(item) for item in rows if isinstance(item, dict)]
        else:
            result[deal_id] = []
    return result


def build_first_stage_dates(history_rows: list[dict[str, Any]]) -> dict[str, datetime]:
    firsts: dict[str, datetime] = {}
    for row in history_rows:
        stage_id = str(row.get("STAGE_ID") or "").strip()
        dt = parse_dt(row.get("CREATED_TIME"))
        if dt is None:
            continue
        for key, wanted_stage_id in STAGE_MAP.items():
            if stage_id == wanted_stage_id and key not in firsts:
                firsts[key] = dt
    return firsts


def build_cohort_metrics(
    detail_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    dashboard_by_brand: dict[str, dict[str, float]] = defaultdict(lambda: {"obr": 0, "lead": 0, "kp": 0, "contract": 0, "sale": 0, "revenue": 0})
    cohort_by_brand: dict[str, dict[str, float]] = defaultdict(lambda: {"obr": 0, "lead": 0, "kp": 0, "contract": 0, "sale": 0, "revenue": 0})
    cohort_by_source: dict[str, dict[str, float]] = defaultdict(lambda: {"obr": 0, "lead": 0, "kp": 0, "contract": 0, "sale": 0, "revenue": 0})

    for row in detail_rows:
        brand = row["brand"]
        source = row["source"]
        month = row["month"]
        revenue = float(row["amount"] if row["sale"] else 0)
        dashboard_bucket = dashboard_by_brand[brand]
        dashboard_bucket["obr"] += 1
        dashboard_bucket["lead"] += 1 if row["lead"] else 0
        dashboard_bucket["kp"] += 1 if row["kp"] else 0
        dashboard_bucket["contract"] += 1 if row["contract"] else 0
        dashboard_bucket["sale"] += 1 if row["sale"] else 0
        dashboard_bucket["revenue"] += revenue

        brand_bucket = cohort_by_brand[f"{month}|||{brand}"]
        brand_bucket["obr"] += 1
        brand_bucket["lead"] += 1 if row["lead"] else 0
        brand_bucket["kp"] += 1 if row["kp"] else 0
        brand_bucket["contract"] += 1 if row["contract"] else 0
        brand_bucket["sale"] += 1 if row["sale"] else 0
        brand_bucket["revenue"] += revenue

        source_bucket = cohort_by_source[f"{month}|||{brand}|||{source}"]
        source_bucket["obr"] += 1
        source_bucket["lead"] += 1 if row["lead"] else 0
        source_bucket["kp"] += 1 if row["kp"] else 0
        source_bucket["contract"] += 1 if row["contract"] else 0
        source_bucket["sale"] += 1 if row["sale"] else 0
        source_bucket["revenue"] += revenue

    return dict(dashboard_by_brand), dict(cohort_by_brand), dict(cohort_by_source)


def build_event_rows(
    deal_by_id: dict[str, DealCard],
    history_by_id: dict[str, list[dict[str, Any]]],
    brand_map: dict[str, str],
    source_map: dict[str, str],
    source_overrides: dict[str, str],
    telemarketing_lead_allowed: dict[str, bool],
    telemarketing_meeting_stats: dict[str, dict[str, Any]],
    reason_map: dict[str, str],
    end_dt: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, float]], list[str]]:
    event_buckets: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"lead": 0, "kp": 0, "contract": 0, "sale": 0, "revenue": 0})
    event_source_buckets: dict[tuple[str, str, str], dict[str, float]] = defaultdict(lambda: {"lead": 0, "kp": 0, "contract": 0, "sale": 0, "revenue": 0})
    sales_buckets: dict[tuple[str, str, str], dict[str, float]] = defaultdict(lambda: {"sale": 0, "revenue": 0})
    months: set[str] = set()

    for deal_id, rows in history_by_id.items():
        deal = deal_by_id.get(deal_id)
        if deal is None:
            continue
        firsts = build_first_stage_dates(rows)
        brand = resolve_brand(deal.brand_raw, brand_map)
        source = resolve_effective_source(deal, source_map, source_overrides)
        spam_rejection = is_spam_rejection(deal.rejection_reason_raw, reason_map)
        if source == TELEMARKETING_SOURCE_NAME:
            meeting_stats = telemarketing_meeting_stats.get(deal_id, {})
            meeting_dt = parse_dt(meeting_stats.get("first_held_meeting_at"))
            if (
                meeting_dt is not None
                and START_DT <= meeting_dt <= end_dt
                and not spam_rejection
                and bool(meeting_stats.get("has_held_meeting"))
            ):
                month = month_key(meeting_dt)
                months.add(month)
                event_buckets[(month, brand)]["lead"] += 1
                event_source_buckets[(month, brand, source)]["lead"] += 1
        for stage_key in STAGE_ORDER:
            if stage_key == "lead" and source == TELEMARKETING_SOURCE_NAME:
                continue
            dt = firsts.get(stage_key)
            if dt is None or dt < START_DT or dt > end_dt:
                continue
            if stage_key == "lead" and spam_rejection:
                continue
            if stage_key == "lead" and source == TELEMARKETING_SOURCE_NAME and not telemarketing_lead_allowed.get(deal_id, False):
                continue
            month = month_key(dt)
            months.add(month)
            bucket = event_buckets[(month, brand)]
            bucket[stage_key] += 1
            source_bucket = event_source_buckets[(month, brand, source)]
            source_bucket[stage_key] += 1
            if stage_key == "sale":
                bucket["revenue"] += deal.amount
                source_bucket["revenue"] += deal.amount
                sales_bucket = sales_buckets[(month, brand, source)]
                sales_bucket["sale"] += 1
                sales_bucket["revenue"] += deal.amount

    event_rows = [
        {
            "month": month,
            "brand": brand,
            "lead": int(metrics["lead"]),
            "kp": int(metrics["kp"]),
            "contract": int(metrics["contract"]),
            "sale": int(metrics["sale"]),
            "revenue": round(metrics["revenue"], 2),
        }
        for (month, brand), metrics in sorted(event_buckets.items())
    ]
    sales_rows = [
        {
            "month": month,
            "brand": brand,
            "source": source,
            "sale": int(metrics["sale"]),
            "amount": round(metrics["revenue"], 2),
            "revenue": round(metrics["revenue"], 2),
        }
        for (month, brand, source), metrics in sorted(sales_buckets.items())
    ]
    event_by_source = {
        f"{month}|||{brand}|||{source}": {
            "lead": int(metrics["lead"]),
            "kp": int(metrics["kp"]),
            "contract": int(metrics["contract"]),
            "sale": int(metrics["sale"]),
            "revenue": round(metrics["revenue"], 2),
        }
        for (month, brand, source), metrics in sorted(event_source_buckets.items())
    }
    return event_rows, sales_rows, event_by_source, sorted(months)


def build_wins_payload(
    auth: Any,
    deal_by_id: dict[str, DealCard],
    history_by_id: dict[str, list[dict[str, Any]]],
    brand_map: dict[str, str],
    source_map: dict[str, str],
    source_overrides: dict[str, str],
    stage_maps: dict[str, dict[str, str]],
    category_map: dict[str, str],
    manager_map: dict[str, str],
    end_dt: datetime,
) -> dict[str, Any]:
    sale_deal_ids: list[str] = []
    won_at_by_id: dict[str, datetime] = {}
    for deal_id, rows in history_by_id.items():
        firsts = build_first_stage_dates(rows)
        sale_dt = firsts.get("sale")
        if sale_dt is None or sale_dt < START_DT or sale_dt > end_dt:
            continue
        sale_deal_ids.append(deal_id)
        won_at_by_id[deal_id] = sale_dt

    product_rows_by_deal = list_product_rows(auth, sale_deal_ids)
    deal_rows: list[dict[str, Any]] = []
    service_rows: list[dict[str, Any]] = []

    for deal_id in sorted(sale_deal_ids, key=lambda value: won_at_by_id[value]):
        deal = deal_by_id.get(deal_id)
        if deal is None:
            continue
        won_at = won_at_by_id[deal_id]
        brand = resolve_brand(deal.brand_raw, brand_map)
        source = resolve_effective_source(deal, source_map, source_overrides)
        manager = manager_map.get(deal.assigned_id, deal.assigned_id or "—")
        category_name = category_map.get(str(SALES_CATEGORY_ID), resolve_stage_name(deal.category_id, deal.stage_id, stage_maps))
        base_row = {
            "deal_id": deal_id,
            "title": deal.title or f"Сделка {deal_id}",
            "url": f"https://belberrycrm.bitrix24.ru/crm/deal/details/{deal_id}/",
            "won_at": fmt_date(won_at),
            "brand": brand,
            "source": source,
            "manager": manager,
            "category": category_name,
            "deal_amount": round(deal.amount, 2),
        }
        deal_rows.append(base_row)

        product_rows = product_rows_by_deal.get(deal_id, [])
        if product_rows:
            for row in product_rows:
                quantity = as_float(first_non_empty(row.get("QUANTITY"), row.get("quantity"), 1))
                line_amount = as_float(first_non_empty(row.get("PRICE_EXCLUSIVE"), row.get("PRICE"), row.get("PRICE_BRUTTO"))) * (quantity or 1)
                service_name = first_non_empty(row.get("PRODUCT_NAME"), row.get("NAME"), row.get("PRODUCT_ID"), "Без названия")
                service_rows.append(
                    {
                        **base_row,
                        "service": service_name,
                        "service_amount": round(line_amount if line_amount else deal.amount, 2),
                    }
                )
        else:
            service_rows.append({**base_row, "service": "Без product rows", "service_amount": round(deal.amount, 2)})

    return {"deal_rows": deal_rows, "service_rows": service_rows}


def build_detail_rows(
    cohort_deals: list[DealCard],
    history_by_id: dict[str, list[dict[str, Any]]],
    brand_map: dict[str, str],
    source_map: dict[str, str],
    source_overrides: dict[str, str],
    telemarketing_lead_allowed: dict[str, bool],
    telemarketing_meeting_stats: dict[str, dict[str, Any]],
    stage_maps: dict[str, dict[str, str]],
    category_map: dict[str, str],
    manager_map: dict[str, str],
    reason_map: dict[str, str],
    end_dt: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for deal in cohort_deals:
        history_rows = history_by_id.get(deal.id, [])
        if not history_rows and deal.id not in telemarketing_meeting_stats:
            continue
        firsts = build_first_stage_dates(history_rows)
        brand = resolve_brand(deal.brand_raw, brand_map)
        source = resolve_effective_source(deal, source_map, source_overrides)
        manager = manager_map.get(deal.assigned_id, deal.assigned_id or "—")
        created_at = deal.created_at
        lead_excluded = is_spam_rejection(deal.rejection_reason_raw, reason_map)
        report_dt = created_at
        telemarketing_lead = "lead" in firsts and not lead_excluded
        if source == TELEMARKETING_SOURCE_NAME:
            meeting_stats = telemarketing_meeting_stats.get(deal.id, {})
            meeting_dt = parse_dt(meeting_stats.get("first_meeting_at"))
            if meeting_dt is None or meeting_dt < START_DT or meeting_dt > end_dt:
                continue
            report_dt = meeting_dt
            telemarketing_lead = bool(meeting_stats.get("has_held_meeting")) and not lead_excluded
        telemarketing_lead_excluded = (
            source == TELEMARKETING_SOURCE_NAME
            and not telemarketing_lead_allowed.get(deal.id, False)
        )
        rows.append(
            {
                "id": deal.id,
                "title": deal.title or f"Сделка {deal.id}",
                "url": f"https://belberrycrm.bitrix24.ru/crm/deal/details/{deal.id}/",
                "created_at": fmt_date(report_dt),
                "month": month_key(report_dt),
                "brand": brand,
                "source": source,
                "manager": manager,
                "current_category": category_map.get(deal.category_id, deal.category_id or "—"),
                "current_stage": resolve_stage_name(deal.category_id, deal.stage_id, stage_maps) or "—",
                "lead": telemarketing_lead if source == TELEMARKETING_SOURCE_NAME else ("lead" in firsts and not lead_excluded and not telemarketing_lead_excluded),
                "kp": "kp" in firsts,
                "contract": "contract" in firsts,
                "sale": "sale" in firsts,
                "amount": round(deal.amount, 2),
                "_sort_created_at": report_dt.isoformat() if report_dt else "",
            }
        )
    rows.sort(key=lambda row: (row["_sort_created_at"], row["id"]))
    for row in rows:
        row.pop("_sort_created_at", None)
    return rows


def count_cohort_leads(
    deal_ids: list[str],
    history_by_id: dict[str, list[dict[str, Any]]],
    deal_by_id: dict[str, DealCard],
    reason_map: dict[str, str],
) -> int:
    total = 0
    for deal_id in deal_ids:
        deal = deal_by_id.get(deal_id)
        if deal is not None and is_spam_rejection(deal.rejection_reason_raw, reason_map):
            continue
        firsts = build_first_stage_dates(history_by_id.get(deal_id, []))
        total += 1 if "lead" in firsts else 0
    return total


def count_event_leads(
    deal_ids: list[str],
    history_by_id: dict[str, list[dict[str, Any]]],
    deal_by_id: dict[str, DealCard],
    reason_map: dict[str, str],
    end_dt: datetime,
) -> int:
    total = 0
    for deal_id in deal_ids:
        deal = deal_by_id.get(deal_id)
        if deal is not None and is_spam_rejection(deal.rejection_reason_raw, reason_map):
            continue
        lead_dt = build_first_stage_dates(history_by_id.get(deal_id, [])).get("lead")
        total += 1 if lead_dt is not None and START_DT <= lead_dt <= end_dt else 0
    return total


def spam_lead_sources(
    deal_ids: list[str],
    deal_by_id: dict[str, DealCard],
    history_by_id: dict[str, list[dict[str, Any]]],
    source_map: dict[str, str],
    source_overrides: dict[str, str],
    end_dt: datetime,
) -> dict[str, int]:
    sources: dict[str, int] = defaultdict(int)
    for deal_id in deal_ids:
        deal = deal_by_id.get(deal_id)
        if deal is None:
            continue
        lead_dt = build_first_stage_dates(history_by_id.get(deal_id, [])).get("lead")
        if lead_dt is None or lead_dt < START_DT or lead_dt > end_dt:
            continue
        sources[resolve_effective_source(deal, source_map, source_overrides)] += 1
    return dict(sorted(sources.items(), key=lambda item: (-item[1], item[0])))


def build_spam_source_rows(
    deal_ids: list[str],
    deal_by_id: dict[str, DealCard],
    history_by_id: dict[str, list[dict[str, Any]]],
    brand_map: dict[str, str],
    source_map: dict[str, str],
    source_overrides: dict[str, str],
    telemarketing_meeting_stats: dict[str, dict[str, Any]],
    reason_map: dict[str, str],
    end_dt: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for deal_id in deal_ids:
        deal = deal_by_id.get(deal_id)
        if deal is None:
            continue
        report_dt = deal.created_at
        source = resolve_effective_source(deal, source_map, source_overrides)
        if source == TELEMARKETING_SOURCE_NAME:
            meeting_dt = parse_dt(telemarketing_meeting_stats.get(deal_id, {}).get("first_meeting_at"))
            if meeting_dt is not None:
                report_dt = meeting_dt
        if report_dt is None or report_dt < START_DT or report_dt > end_dt:
            event_dates = [
                parsed
                for parsed in (parse_dt(row.get("CREATED_TIME")) for row in history_by_id.get(deal_id, []))
                if parsed is not None and START_DT <= parsed <= end_dt
            ]
            report_dt = min(event_dates) if event_dates else deal.created_at
        rows.append(
            {
                "id": deal.id,
                "title": deal.title or f"Сделка {deal.id}",
                "url": f"https://belberrycrm.bitrix24.ru/crm/deal/details/{deal.id}/",
                "created_at": fmt_date(deal.created_at),
                "month": month_key(report_dt),
                "brand": resolve_brand(deal.brand_raw, brand_map),
                "source": source,
                "rejection_reason": resolve_rejection_reason(deal.rejection_reason_raw, reason_map),
            }
        )
    rows.sort(key=lambda row: (row["month"], row["brand"], row["source"], row["id"]))
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ensure_tmp_dir()
    now_moscow = datetime.now(MOSCOW_TZ)
    end_dt = now_moscow
    log(f"Старт live-refresh: период {START_DT.date()} .. {end_dt.date()} ({fmt_dt(end_dt)} МСК)")

    auth = make_auth()
    brand_map = load_brand_map(auth)
    rejection_reason_map = load_deal_enum_map(auth, REJECTION_REASON_FIELD)
    source_map = load_source_map(auth)
    category_map = load_category_map(auth)
    stage_maps = load_stage_maps(auth, list(category_map))

    created_deals_raw = list_created_deals(auth, end_dt)
    created_ids_raw = [deal.id for deal in created_deals_raw]
    log(f"Сделок создано в периоде: {len(created_deals_raw)}")

    created_history = list_sales_history_for_owners(auth, created_ids_raw)
    cohort_ids_raw = sorted([deal_id for deal_id in created_ids_raw if created_history.get(deal_id)])
    log(f"Sales-only когорта по созданиям до спам-фильтра: {len(cohort_ids_raw)}")

    period_sales_history = list_period_sales_history(auth, end_dt)
    event_candidate_ids = sorted({str(row.get('OWNER_ID') or '').strip() for row in period_sales_history if str(row.get('OWNER_ID') or '').strip()})
    all_candidate_ids_raw = dedupe(cohort_ids_raw + event_candidate_ids)
    missing_deal_ids = [deal_id for deal_id in all_candidate_ids_raw if deal_id not in created_ids_raw]
    log(f"Кандидатов для событийного слоя до спам-фильтра: {len(all_candidate_ids_raw)}")

    deal_by_id = {deal.id: deal for deal in created_deals_raw}
    if missing_deal_ids:
        deal_by_id.update(list_deals_by_ids(auth, missing_deal_ids))
    log(f"Карточек сделок загружено: {len(deal_by_id)}")

    missing_history = list_sales_history_for_owners(auth, missing_deal_ids)
    history_by_id_raw: dict[str, list[dict[str, Any]]] = {}
    for deal_id in all_candidate_ids_raw:
        history_by_id_raw[deal_id] = sorted(
            [*created_history.get(deal_id, []), *missing_history.get(deal_id, [])],
            key=lambda row: str(row.get("CREATED_TIME") or ""),
        )
    telemarketing_history_by_id_raw = list_stage_history_for_owners(auth, all_candidate_ids_raw, TELEMARKETING_CATEGORY_ID)
    source_overrides_raw, telemarketing_lead_allowed_raw, telemarketing_meeting_stats_raw, telemarketing_control_raw = build_telemarketing_source_overrides(
        auth=auth,
        deal_ids=all_candidate_ids_raw,
        sales_history_by_id=history_by_id_raw,
        telemarketing_history_by_id=telemarketing_history_by_id_raw,
    )
    log(f"Телемаркетинг source override найдено: {len(source_overrides_raw)}")

    spam_deal_ids = sorted(
        deal_id
        for deal_id in all_candidate_ids_raw
        if is_spam_rejection(deal_by_id.get(deal_id, DealCard("", "", None, "", "", "", "", 0.0, "", "")).rejection_reason_raw, rejection_reason_map)
    )
    created_deals = created_deals_raw
    created_ids = [deal.id for deal in created_deals]
    cohort_ids = cohort_ids_raw
    all_candidate_ids = all_candidate_ids_raw
    history_by_id = {deal_id: history_by_id_raw[deal_id] for deal_id in all_candidate_ids if deal_id in history_by_id_raw}
    source_overrides = source_overrides_raw
    telemarketing_lead_allowed = telemarketing_lead_allowed_raw
    telemarketing_meeting_stats = telemarketing_meeting_stats_raw
    telemarketing_control = {
        **telemarketing_control_raw,
        "deals_overridden_after_spam_filter": len(source_overrides),
        "deal_ids_after_spam_filter": sorted(source_overrides),
        "deals_with_first_meeting_held_after_spam_filter": sum(1 for deal_id in source_overrides if telemarketing_lead_allowed.get(deal_id, False)),
        "deals_without_held_first_meeting_after_spam_filter": sum(1 for deal_id in source_overrides if not telemarketing_lead_allowed.get(deal_id, False)),
        "lead_allowed_deal_ids_after_spam_filter": sorted(deal_id for deal_id in source_overrides if telemarketing_lead_allowed.get(deal_id, False)),
        "lead_denied_deal_ids_after_spam_filter": sorted(deal_id for deal_id in source_overrides if not telemarketing_lead_allowed.get(deal_id, False)),
    }
    log(f"Спамных отказов найдено, обращения сохранены в рабочих слоях: {len(spam_deal_ids)}")
    log(f"Sales-only когорта с учётом спам-обращений: {len(cohort_ids)}")
    log(f"Кандидатов для событийного слоя с учётом спам-обращений: {len(all_candidate_ids)}")

    assigned_ids = [deal.assigned_id for deal in deal_by_id.values() if deal.assigned_id]
    manager_map = list_users_by_ids(auth, assigned_ids)

    spam_control = {
        "rejection_reason_field": REJECTION_REASON_FIELD,
        "spam_match_rule": "trim + lower + collapse spaces; values: Спам / Spam / Вход: нет связи / Нет связи",
        "spam_enum_values": [
            {"id": item_id, "value": value}
            for item_id, value in sorted(rejection_reason_map.items())
            if normalize_reason(value) in SPAM_REJECTION_REASONS
        ],
        "created_deals_before": len(created_deals_raw),
        "created_deals_after": len(created_deals),
        "sales_only_created_before": len(cohort_ids_raw),
        "sales_only_created_after": len(cohort_ids),
        "event_candidates_before": len(all_candidate_ids_raw),
        "event_candidates_after": len(all_candidate_ids),
        "spam_deals_found": len(spam_deal_ids),
        "spam_deal_ids": spam_deal_ids,
        "cohort_leads_before": count_cohort_leads(cohort_ids_raw, history_by_id_raw, {}, rejection_reason_map),
        "cohort_leads_after": count_cohort_leads(cohort_ids, history_by_id, deal_by_id, rejection_reason_map),
        "event_leads_before": count_event_leads(all_candidate_ids_raw, history_by_id_raw, {}, rejection_reason_map, end_dt),
        "event_leads_after": count_event_leads(all_candidate_ids, history_by_id, deal_by_id, rejection_reason_map, end_dt),
        "spam_leads_by_source": spam_lead_sources(spam_deal_ids, deal_by_id, history_by_id_raw, source_map, source_overrides_raw, end_dt),
    }
    spam_control["cohort_leads_excluded"] = spam_control["cohort_leads_before"] - spam_control["cohort_leads_after"]
    spam_control["event_leads_excluded"] = spam_control["event_leads_before"] - spam_control["event_leads_after"]
    spam_source_rows = build_spam_source_rows(spam_deal_ids, deal_by_id, history_by_id_raw, brand_map, source_map, source_overrides_raw, telemarketing_meeting_stats_raw, rejection_reason_map, end_dt)
    spam_control["spam_source_rows"] = len(spam_source_rows)

    non_lead_deal_ids = sorted(
        deal_id
        for deal_id in all_candidate_ids
        if is_non_lead_rejection(deal_by_id.get(deal_id, DealCard("", "", None, "", "", "", "", 0.0, "", "")).rejection_reason_raw, rejection_reason_map)
    )
    non_lead_deal_id_set = set(non_lead_deal_ids)
    lead_exclusion_control = {
        "rejection_reason_field": REJECTION_REASON_FIELD,
        "lead_exclusion_rule": "disabled; Вход: нет связи / Нет связи обрабатываются как spam_filter",
        "non_lead_enum_values": [
            {"id": item_id, "value": value}
            for item_id, value in sorted(rejection_reason_map.items())
            if normalize_reason(value) in NON_LEAD_REJECTION_REASONS
        ],
        "non_lead_deals_found": len(non_lead_deal_ids),
        "non_lead_deal_ids": non_lead_deal_ids,
        "cohort_leads_before": count_cohort_leads(cohort_ids, history_by_id, {}, rejection_reason_map),
        "cohort_leads_after": count_cohort_leads(cohort_ids, history_by_id, deal_by_id, rejection_reason_map),
        "event_leads_before": count_event_leads(all_candidate_ids, history_by_id, {}, rejection_reason_map, end_dt),
        "event_leads_after": count_event_leads(all_candidate_ids, history_by_id, deal_by_id, rejection_reason_map, end_dt),
    }
    lead_exclusion_control["cohort_leads_excluded"] = lead_exclusion_control["cohort_leads_before"] - lead_exclusion_control["cohort_leads_after"]
    lead_exclusion_control["event_leads_excluded"] = lead_exclusion_control["event_leads_before"] - lead_exclusion_control["event_leads_after"]
    log(f"Лидов с отказом 'Вход: нет связи' исключено из метрики lead: {len(non_lead_deal_id_set)}")

    cohort_deal_ids = dedupe(cohort_ids + sorted(source_overrides))
    cohort_deals = [deal_by_id[deal_id] for deal_id in cohort_deal_ids if deal_id in deal_by_id]
    detail_rows = build_detail_rows(cohort_deals, history_by_id, brand_map, source_map, source_overrides, telemarketing_lead_allowed, telemarketing_meeting_stats, stage_maps, category_map, manager_map, rejection_reason_map, end_dt)
    dashboard_by_brand, cohort_by_brand, cohort_by_source = build_cohort_metrics(detail_rows)

    event_rows, sales_rows, event_by_source, event_months = build_event_rows(
        deal_by_id=deal_by_id,
        history_by_id=history_by_id,
        brand_map=brand_map,
        source_map=source_map,
        source_overrides=source_overrides,
        telemarketing_lead_allowed=telemarketing_lead_allowed,
        telemarketing_meeting_stats=telemarketing_meeting_stats,
        reason_map=rejection_reason_map,
        end_dt=end_dt,
    )
    wins_payload = build_wins_payload(
        auth=auth,
        deal_by_id=deal_by_id,
        history_by_id=history_by_id,
        brand_map=brand_map,
        source_map=source_map,
        source_overrides=source_overrides,
        stage_maps=stage_maps,
        category_map=category_map,
        manager_map=manager_map,
        end_dt=end_dt,
    )

    meta = {
        "period": f"{START_DT.date()}..{end_dt.date()}",
        "updated_at": fmt_date(end_dt),
        "timezone": "Europe/Moscow",
        "sales_category_id": SALES_CATEGORY_ID,
        "created_in_period": len(created_deals),
        "sales_only_created": len(cohort_ids),
        "event_candidates": len(all_candidate_ids),
        "event_months": event_months,
        "spam_filter": spam_control,
        "lead_exclusion": lead_exclusion_control,
        "telemarketing_source_override": telemarketing_control,
    }
    cohort_payload = {
        "meta": meta,
        "dashboard_by_brand": dashboard_by_brand,
        "cohort_by_brand": cohort_by_brand,
        "cohort_by_source": cohort_by_source,
        "detail_rows": detail_rows,
        "spam_source_rows": spam_source_rows,
    }
    events_payload = {
        "meta": meta,
        "event_rows": event_rows,
        "event_by_source": event_by_source,
        "sales_rows": sales_rows,
        "spam_source_rows": spam_source_rows,
    }
    wins_payload = {"meta": meta, **wins_payload}

    write_json(TMP_DIR / "cohort_slice_3.json", cohort_payload)
    write_json(TMP_DIR / "sales_only_q1_2026_details.json", cohort_payload)
    write_json(TMP_DIR / "true_events_q1_2026.json", events_payload)
    write_json(TMP_DIR / "wins_ytd_2026.json", wins_payload)

    summary = {
        "meta": meta,
        "dashboard_by_brand": dashboard_by_brand,
        "event_rows": event_rows,
        "wins": {
            "deals": len(wins_payload["deal_rows"]),
            "services": len(wins_payload["service_rows"]),
        },
        "quality": {
            "no_brand": sum(1 for row in detail_rows if row["brand"] == "Без бренда"),
            "no_source": sum(1 for row in detail_rows if row["source"] == "Без источника"),
        },
        "spam_filter": spam_control,
        "lead_exclusion": lead_exclusion_control,
        "telemarketing_source_override": telemarketing_control,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
