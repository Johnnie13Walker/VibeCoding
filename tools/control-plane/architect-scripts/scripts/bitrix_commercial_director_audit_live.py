#!/usr/bin/env python3
"""Read-only аудит Bitrix24 для контура коммерческого директора."""

from __future__ import annotations

import importlib.util
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path("/Users/pro2kuror/Desktop/architect")
BASE_SCRIPT = ROOT / "scripts" / "bitrix_field_audit_gd324.py"
OUT_DIR = ROOT / "docs" / "architecture"
TMP_DIR = ROOT / "tmp" / "bitrix_commercial_director_audit"
REPORT_MD = OUT_DIR / "bitrix24_commercial_director_audit_2026-05-01.md"
REPORT_JSON = TMP_DIR / "bitrix24_commercial_director_audit_2026-05-01.json"

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
NOW = datetime.now(MOSCOW_TZ)
YEAR_START = datetime(2026, 1, 1, 0, 0, 0, tzinfo=MOSCOW_TZ)
THREE_MONTHS_START = NOW - timedelta(days=92)
SIX_MONTHS_START = NOW - timedelta(days=183)
ACTIVITY_LOOKBACK_START = NOW - timedelta(days=220)

REJECTION_REASON_FIELD = "UF_CRM_1771495464"
BRAND_FIELD = "UF_CRM_1721661506"
DEAL_ENTITY_TYPE_ID = 2
DEAL_OWNER_TYPE_ID = 2

DEAL_SELECT = [
    "ID",
    "TITLE",
    "DATE_CREATE",
    "DATE_MODIFY",
    "DATE_CLOSED",
    "CATEGORY_ID",
    "STAGE_ID",
    "STAGE_SEMANTIC_ID",
    "SOURCE_ID",
    "ASSIGNED_BY_ID",
    "OPPORTUNITY",
    "COMPANY_ID",
    "CONTACT_ID",
    "CLOSED",
    "IS_RETURN_CUSTOMER",
    BRAND_FIELD,
    REJECTION_REASON_FIELD,
]

HISTORY_SELECT = ["ID", "OWNER_ID", "CATEGORY_ID", "STAGE_ID", "CREATED_TIME", "STAGE_SEMANTIC_ID"]
ACTIVITY_SELECT = [
    "ID",
    "OWNER_ID",
    "OWNER_TYPE_ID",
    "TYPE_ID",
    "PROVIDER_ID",
    "PROVIDER_TYPE_ID",
    "SUBJECT",
    "COMPLETED",
    "DEADLINE",
    "CREATED",
    "LAST_UPDATED",
    "RESPONSIBLE_ID",
]


def load_base():
    spec = importlib.util.spec_from_file_location("bitrix_field_audit_gd324", BASE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base = load_base()


def log(message: str) -> None:
    print(message, flush=True)


def parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MOSCOW_TZ)
    return parsed.astimezone(MOSCOW_TZ)


def iso(dt: datetime) -> str:
    return dt.astimezone(MOSCOW_TZ).isoformat(timespec="seconds")


def fmt_dt(dt: datetime | None) -> str:
    return dt.astimezone(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M") if dt else ""


def fmt_days(hours: float | None) -> str:
    if hours is None:
        return "нет данных"
    return f"{round(hours / 24, 1)} дн."


def as_float(value: Any) -> float:
    try:
        return float(str(value or "0").replace(" ", ""))
    except ValueError:
        return 0.0


def pct(part: int, total: int) -> float:
    return round(part * 100 / total, 1) if total else 0.0


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def average(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("ё", "е").split())


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


@dataclass
class Deal:
    id: str
    title: str
    created_at: datetime | None
    updated_at: datetime | None
    closed_at: datetime | None
    category_id: str
    stage_id: str
    semantic_id: str
    source_id: str
    assigned_id: str
    amount: float
    company_id: str
    contact_id: str
    closed: bool
    is_return_customer: str
    brand_raw: str
    rejection_reason_raw: str


def make_deal(row: dict[str, Any]) -> Deal:
    return Deal(
        id=str(row.get("ID") or "").strip(),
        title=str(row.get("TITLE") or "").strip(),
        created_at=parse_dt(row.get("DATE_CREATE")),
        updated_at=parse_dt(row.get("DATE_MODIFY")),
        closed_at=parse_dt(row.get("DATE_CLOSED")),
        category_id=str(row.get("CATEGORY_ID") or "0").strip(),
        stage_id=str(row.get("STAGE_ID") or "").strip(),
        semantic_id=str(row.get("STAGE_SEMANTIC_ID") or "").strip(),
        source_id=str(row.get("SOURCE_ID") or "").strip(),
        assigned_id=str(row.get("ASSIGNED_BY_ID") or "").strip(),
        amount=as_float(row.get("OPPORTUNITY")),
        company_id=str(row.get("COMPANY_ID") or "").strip(),
        contact_id=str(row.get("CONTACT_ID") or "").strip(),
        closed=str(row.get("CLOSED") or "").upper() == "Y",
        is_return_customer=str(row.get("IS_RETURN_CUSTOMER") or "").strip(),
        brand_raw=str(row.get(BRAND_FIELD) or "").strip(),
        rejection_reason_raw=str(row.get(REJECTION_REASON_FIELD) or "").strip(),
    )


def payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        result = payload.get("result")
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict):
            for key in ("items", "types", "categories", "result"):
                value = result.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
    return []


def list_categories(auth: Any) -> dict[str, str]:
    payload = auth.call_payload("crm.category.list", params={"entityTypeId": DEAL_ENTITY_TYPE_ID}, default={})
    rows = payload_items(payload)
    categories = {"0": "Общая"}
    for row in rows:
        cid = str(row.get("id") or row.get("ID") or "").strip()
        name = str(row.get("name") or row.get("NAME") or "").strip()
        if cid:
            categories[cid] = name or cid
    return categories


def list_statuses(auth: Any) -> list[dict[str, Any]]:
    return auth.list_method("crm.status.list")


def build_stage_maps(statuses: list[dict[str, Any]], categories: dict[str, str]) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, int]]]:
    names: dict[str, dict[str, str]] = {}
    sorts: dict[str, dict[str, int]] = {}
    for category_id in categories:
        entity_id = f"DEAL_STAGE_{category_id}"
        names[category_id] = {}
        sorts[category_id] = {}
        for row in statuses:
            if str(row.get("ENTITY_ID") or "") != entity_id:
                continue
            stage_id = str(row.get("STATUS_ID") or "").strip()
            if not stage_id:
                continue
            names[category_id][stage_id] = str(row.get("NAME") or stage_id).strip()
            try:
                sorts[category_id][stage_id] = int(row.get("SORT") or 0)
            except ValueError:
                sorts[category_id][stage_id] = 0
    return names, sorts


def source_map(statuses: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in statuses:
        if str(row.get("ENTITY_ID") or "") != "SOURCE":
            continue
        sid = str(row.get("STATUS_ID") or "").strip()
        name = str(row.get("NAME") or sid).strip()
        if sid:
            mapping[sid] = name
    return mapping


def enum_map(auth: Any, field_code: str) -> dict[str, str]:
    payload = auth.call_payload("crm.deal.fields", default={})
    fields = payload.get("result") if isinstance(payload, dict) else {}
    meta = fields.get(field_code) if isinstance(fields, dict) else {}
    items = meta.get("items") if isinstance(meta, dict) else []
    result: dict[str, str] = {}
    for item in items if isinstance(items, list) else []:
        iid = str(item.get("ID") or "").strip()
        value = str(item.get("VALUE") or "").strip()
        if iid:
            result[iid] = value or iid
    return result


def list_all_deals(auth: Any) -> list[Deal]:
    rows = auth.list_method("crm.deal.list", params={"select": DEAL_SELECT, "order": {"ID": "ASC"}})
    return [make_deal(row) for row in rows if isinstance(row, dict)]


def list_stage_history(auth: Any, category_id: str, start_dt: datetime) -> list[dict[str, Any]]:
    params = {
        "entityTypeId": DEAL_ENTITY_TYPE_ID,
        "select": HISTORY_SELECT,
        "filter": {">=CREATED_TIME": iso(start_dt), "CATEGORY_ID": int(category_id)},
        "order": {"CREATED_TIME": "ASC"},
    }
    return auth.list_method("crm.stagehistory.list", params=params)


def list_activities(auth: Any) -> tuple[list[dict[str, Any]], str]:
    try:
        rows = auth.list_method(
            "crm.activity.list",
            params={
                "select": ACTIVITY_SELECT,
                "filter": {
                    "OWNER_TYPE_ID": DEAL_OWNER_TYPE_ID,
                    ">=LAST_UPDATED": iso(ACTIVITY_LOOKBACK_START),
                },
                "order": {"LAST_UPDATED": "ASC"},
            },
        )
        return rows, ""
    except Exception as error:  # noqa: BLE001
        return [], str(error)


def probe_automation(auth: Any, categories: dict[str, str]) -> dict[str, Any]:
    probes: list[dict[str, Any]] = []
    candidates = [
        ("crm.automation.robot.list", {"entityTypeId": DEAL_ENTITY_TYPE_ID}),
        ("crm.automation.trigger.list", {"entityTypeId": DEAL_ENTITY_TYPE_ID}),
        ("bizproc.workflow.template.list", {"MODULE_ID": "crm", "ENTITY": "CCrmDocumentDeal"}),
    ]
    for method, params in candidates:
        try:
            payload = auth.call_payload(method, params=params, default={})
            items = payload_items(payload)
            probes.append({"method": method, "ok": True, "items_count": len(items), "sample": items[:3]})
        except Exception as error:  # noqa: BLE001
            probes.append({"method": method, "ok": False, "error": str(error)[:400]})

    per_category: list[dict[str, Any]] = []
    for category_id, name in categories.items():
        try:
            payload = auth.call_payload(
                "crm.automation.robot.list",
                params={"entityTypeId": DEAL_ENTITY_TYPE_ID, "categoryId": int(category_id)},
                default={},
            )
            items = payload_items(payload)
            per_category.append({"category_id": category_id, "category": name, "ok": True, "items_count": len(items), "sample": items[:5]})
        except Exception as error:  # noqa: BLE001
            per_category.append({"category_id": category_id, "category": name, "ok": False, "error": str(error)[:250]})
    return {"global_probes": probes, "per_category": per_category}


def user_names(auth: Any, user_ids: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for user_id in sorted(set(uid for uid in user_ids if uid)):
        try:
            rows = auth.list_method("user.get", params={"FILTER": {"ID": [user_id]}}, limit=1)
        except Exception:  # noqa: BLE001
            continue
        for row in rows:
            uid = str(row.get("ID") or "").strip()
            name = " ".join(part for part in [str(row.get("LAST_NAME") or "").strip(), str(row.get("NAME") or "").strip()] if part)
            if uid:
                result[uid] = name or uid
    return result


def stage_label(stage_maps: dict[str, dict[str, str]], category_id: str, stage_id: str) -> str:
    return stage_maps.get(category_id, {}).get(stage_id, stage_id or "Без стадии")


def source_label(mapping: dict[str, str], source_id: str) -> str:
    return mapping.get(source_id, source_id or "Без источника")


def reason_label(mapping: dict[str, str], reason_id: str) -> str:
    return mapping.get(reason_id, reason_id or "")


def period_count(deals: list[Deal], start_dt: datetime) -> int:
    return sum(1 for deal in deals if deal.created_at and deal.created_at >= start_dt)


def build_history_by_owner(history_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in history_rows:
        owner_id = str(row.get("OWNER_ID") or "").strip()
        if owner_id:
            by_owner[owner_id].append(row)
    for owner_id in by_owner:
        by_owner[owner_id].sort(key=lambda row: str(row.get("CREATED_TIME") or ""))
    return by_owner


def stage_duration_hours(
    category_deals: list[Deal],
    history_by_owner: dict[str, list[dict[str, Any]]],
    stage_sorts: dict[str, dict[str, int]],
) -> tuple[dict[str, list[float]], Counter[str], Counter[str], Counter[str]]:
    durations: dict[str, list[float]] = defaultdict(list)
    reached: Counter[str] = Counter()
    backward: Counter[str] = Counter()
    category_transfers: Counter[str] = Counter()
    current_by_id = {deal.id: deal for deal in category_deals}

    for deal in category_deals:
        rows = history_by_owner.get(deal.id, [])
        events: list[tuple[datetime, str, str]] = []
        for row in rows:
            dt = parse_dt(row.get("CREATED_TIME"))
            stage_id = str(row.get("STAGE_ID") or "").strip()
            category_id = str(row.get("CATEGORY_ID") or deal.category_id or "0").strip()
            if dt and stage_id:
                events.append((dt, category_id, stage_id))
        if not events:
            if deal.stage_id:
                reached[deal.stage_id] += 1
            continue
        seen_stage: set[str] = set()
        seen_category: set[str] = set()
        previous: tuple[datetime, str, str] | None = None
        for event in events:
            dt, category_id, stage_id = event
            seen_stage.add(stage_id)
            seen_category.add(category_id)
            if previous is not None:
                prev_dt, prev_category, prev_stage = previous
                if dt >= prev_dt:
                    durations[prev_stage].append((dt - prev_dt).total_seconds() / 3600)
                prev_sort = stage_sorts.get(prev_category, {}).get(prev_stage, 0)
                next_sort = stage_sorts.get(category_id, {}).get(stage_id, 0)
                if prev_category == category_id and next_sort and prev_sort and next_sort < prev_sort:
                    backward[deal.id] += 1
            previous = event
        if previous is not None and not deal.closed:
            prev_dt, _prev_category, prev_stage = previous
            if NOW >= prev_dt:
                durations[prev_stage].append((NOW - prev_dt).total_seconds() / 3600)
        for stage_id in seen_stage:
            reached[stage_id] += 1
        if len(seen_category) > 1:
            category_transfers[deal.id] += len(seen_category) - 1

    for deal in current_by_id.values():
        if deal.stage_id and deal.stage_id not in reached:
            reached[deal.stage_id] += 1
    return durations, reached, backward, category_transfers


def build_activity_index(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], Counter[str]]:
    index: dict[str, dict[str, Any]] = defaultdict(lambda: {"future": 0, "overdue": 0, "completed": 0, "last_touch": None, "auto_subjects": Counter()})
    type_counter: Counter[str] = Counter()
    for row in rows:
        deal_id = str(row.get("OWNER_ID") or "").strip()
        if not deal_id:
            continue
        deadline = parse_dt(row.get("DEADLINE"))
        created = parse_dt(row.get("CREATED"))
        updated = parse_dt(row.get("LAST_UPDATED"))
        completed = str(row.get("COMPLETED") or "").upper() == "Y"
        subject = str(row.get("SUBJECT") or "").strip()
        provider = str(row.get("PROVIDER_ID") or row.get("PROVIDER_TYPE_ID") or row.get("TYPE_ID") or "").strip()
        type_counter[provider or "unknown"] += 1
        bucket = index[deal_id]
        touch = max([dt for dt in [deadline, created, updated] if dt], default=None)
        if touch and (bucket["last_touch"] is None or touch > bucket["last_touch"]):
            bucket["last_touch"] = touch
        if completed:
            bucket["completed"] += 1
        elif deadline and deadline >= NOW:
            bucket["future"] += 1
        elif deadline and deadline < NOW:
            bucket["overdue"] += 1
        if subject:
            bucket["auto_subjects"][subject] += 1
    return dict(index), type_counter


def classify_activity_gaps(active_deals: list[Deal], activity_index: dict[str, dict[str, Any]], users: dict[str, str]) -> dict[str, Any]:
    without_future = []
    no_touch_7 = []
    no_touch_14 = []
    no_touch_30 = []
    overdue = []
    by_manager: dict[str, Counter[str]] = defaultdict(Counter)
    for deal in active_deals:
        info = activity_index.get(deal.id, {})
        manager = users.get(deal.assigned_id, deal.assigned_id or "Без ответственного")
        future = int(info.get("future") or 0)
        overdue_count = int(info.get("overdue") or 0)
        last_touch = info.get("last_touch")
        if future <= 0:
            without_future.append(deal)
            by_manager[manager]["без будущей задачи"] += 1
        if overdue_count > 0:
            overdue.append(deal)
            by_manager[manager]["с просрочками"] += 1
        if not isinstance(last_touch, datetime):
            last_touch = deal.updated_at or deal.created_at
        if last_touch:
            age_days = (NOW - last_touch).days
            if age_days >= 7:
                no_touch_7.append(deal)
                by_manager[manager]["без коммуникации 7+"] += 1
            if age_days >= 14:
                no_touch_14.append(deal)
                by_manager[manager]["без коммуникации 14+"] += 1
            if age_days >= 30:
                no_touch_30.append(deal)
                by_manager[manager]["без коммуникации 30+"] += 1
    return {
        "without_future": without_future,
        "no_touch_7": no_touch_7,
        "no_touch_14": no_touch_14,
        "no_touch_30": no_touch_30,
        "overdue": overdue,
        "by_manager": by_manager,
    }


def top_counter(counter: Counter[str], limit: int = 10) -> list[tuple[str, int]]:
    return counter.most_common(limit)


def generic_source(name: str) -> bool:
    norm = normalize(name)
    return norm in {"не выяснено", "прочее", "другое", "без источника", "неизвестно", "other", "unknown"} or "проч" in norm


def build_category_audit(
    categories: dict[str, str],
    deals: list[Deal],
    history_by_category: dict[str, list[dict[str, Any]]],
    stage_maps: dict[str, dict[str, str]],
    stage_sorts: dict[str, dict[str, int]],
    sources: dict[str, str],
    reason_map_data: dict[str, str],
    users: dict[str, str],
    activity_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    by_category: dict[str, Any] = {}
    deals_by_category: dict[str, list[Deal]] = defaultdict(list)
    for deal in deals:
        deals_by_category[deal.category_id].append(deal)

    all_history = []
    for rows in history_by_category.values():
        all_history.extend(rows)
    history_by_owner = build_history_by_owner(all_history)

    for category_id, category_name in categories.items():
        category_deals = deals_by_category.get(category_id, [])
        active_deals = [deal for deal in category_deals if not deal.closed]
        durations, reached, backward, transfers = stage_duration_hours(category_deals, history_by_owner, stage_sorts)
        current_stage = Counter(deal.stage_id for deal in category_deals if deal.stage_id)
        lost_deals = [deal for deal in category_deals if deal.semantic_id == "F" or "LOSE" in deal.stage_id or "FAIL" in deal.stage_id]
        won_deals = [deal for deal in category_deals if deal.semantic_id == "S" or "WON" in deal.stage_id]
        sources_counter = Counter(source_label(sources, deal.source_id) for deal in category_deals)
        generic_sources = sum(count for name, count in sources_counter.items() if generic_source(name))
        missing_source = sum(1 for deal in category_deals if not deal.source_id)
        missing_company = sum(1 for deal in category_deals if not deal.company_id)
        missing_amount = sum(1 for deal in category_deals if deal.amount <= 0)
        lost_without_reason = sum(1 for deal in lost_deals if not deal.rejection_reason_raw)
        reasons_counter = Counter(reason_label(reason_map_data, deal.rejection_reason_raw) or "Без причины" for deal in lost_deals)
        spam_lost = sum(count for name, count in reasons_counter.items() if normalize(name) == "спам")
        activity_gaps = classify_activity_gaps(active_deals, activity_index, users)
        stage_rows = []
        for stage_id, stage_name in stage_maps.get(category_id, {}).items():
            duration_values = durations.get(stage_id, [])
            current_count = current_stage.get(stage_id, 0)
            reached_count = reached.get(stage_id, 0)
            stage_rows.append(
                {
                    "stage_id": stage_id,
                    "stage": stage_name,
                    "current": current_count,
                    "reached": reached_count,
                    "avg_hours": average(duration_values),
                    "median_hours": median(duration_values),
                    "max_hours": max(duration_values) if duration_values else None,
                    "activity": "не используется" if current_count == 0 and reached_count == 0 else ("низкая" if current_count <= 2 and reached_count <= 3 else "используется"),
                }
            )

        by_category[category_id] = {
            "category": category_name,
            "deals_total": len(category_deals),
            "active_total": len(active_deals),
            "created_3m": period_count(category_deals, THREE_MONTHS_START),
            "created_6m": period_count(category_deals, SIX_MONTHS_START),
            "created_ytd": period_count(category_deals, YEAR_START),
            "won_total": len(won_deals),
            "lost_total": len(lost_deals),
            "stages_count": len(stage_maps.get(category_id, {})),
            "stage_rows": stage_rows,
            "dead_stages": [row for row in stage_rows if row["activity"] == "не используется"],
            "low_stages": [row for row in stage_rows if row["activity"] == "низкая"],
            "top_current_stages": [(stage_label(stage_maps, category_id, sid), count) for sid, count in top_counter(current_stage)],
            "top_reached_stages": [(stage_label(stage_maps, category_id, sid), count) for sid, count in top_counter(reached)],
            "longest_stages": sorted([row for row in stage_rows if row["median_hours"] is not None], key=lambda row: row["median_hours"] or 0, reverse=True)[:5],
            "lost_by_stage": [(stage_label(stage_maps, category_id, deal_stage), count) for deal_stage, count in Counter(deal.stage_id for deal in lost_deals).most_common(8)],
            "reasons": reasons_counter,
            "lost_without_reason": lost_without_reason,
            "spam_lost": spam_lost,
            "sources": sources_counter,
            "missing_source": missing_source,
            "generic_sources": generic_sources,
            "missing_company": missing_company,
            "missing_amount": missing_amount,
            "backward_deals": len(backward),
            "backward_events": sum(backward.values()),
            "category_transfer_deals": len(transfers),
            "category_transfer_events": sum(transfers.values()),
            "activity": {
                "without_future": len(activity_gaps["without_future"]),
                "no_touch_7": len(activity_gaps["no_touch_7"]),
                "no_touch_14": len(activity_gaps["no_touch_14"]),
                "no_touch_30": len(activity_gaps["no_touch_30"]),
                "overdue": len(activity_gaps["overdue"]),
                "by_manager": {
                    manager: dict(counter)
                    for manager, counter in sorted(activity_gaps["by_manager"].items(), key=lambda item: sum(item[1].values()), reverse=True)[:10]
                },
            },
        }
    return by_category


def recommendation_rows(audit: dict[str, Any], automation: dict[str, Any]) -> list[dict[str, str]]:
    rows = [
        {
            "name": "Зафиксировать единую карту коммерческих контуров",
            "problem": "В сделках смешаны продажи, телемаркетинг, реанимация, аккаунтинг, retention, delivery и архивы.",
            "effect": "Коммерческий директор получает одну понятную картину new business и отдельную картину клиентского развития.",
            "complexity": "средняя",
            "priority": "высокий",
            "risk": "Без этого pipeline и конверсия продолжат считаться вместе с не-продажными процессами.",
        },
        {
            "name": "Сократить и пересобрать Реанимацию",
            "problem": "Реанимация работает как контейнер сегментов, а не как управляемая воронка.",
            "effect": "Появится контроль SLA, конверсии и качества реактивации.",
            "complexity": "высокая",
            "priority": "высокий",
            "risk": "Большой массив открытых карточек останется складом без управленческой ответственности.",
        },
        {
            "name": "Перестать перезаписывать первичный маркетинговый источник внутренними источниками",
            "problem": "Внутренние контуры и ручные действия могут загрязнять SOURCE_ID, особенно если телемаркетинг используется как источник.",
            "effect": "Маркетинговая аналитика перестанет терять первичный канал привлечения.",
            "complexity": "средняя",
            "priority": "высокий",
            "risk": "Реклама и SDR будут спорить за один источник, а ROI каналов останется недостоверным.",
        },
        {
            "name": "Ввести обязательный следующий шаг для активных коммерческих сделок",
            "problem": "Активные сделки без будущей активности невозможно контролировать по SLA.",
            "effect": "РОП видит сделки без движения и может управлять фокусом менеджеров.",
            "complexity": "низкая",
            "priority": "высокий",
            "risk": "Сделки продолжат зависать без явного владельца следующего действия.",
        },
        {
            "name": "Нормализовать причины отказа",
            "problem": "Причины отказа должны быть управленческим классификатором, а не способом закрыть карточку.",
            "effect": "Отказы можно будет разбирать по продукту, цене, срокам, конкурентам, нецелевым и спаму.",
            "complexity": "низкая",
            "priority": "высокий",
            "risk": "Проигрыши будут копиться без качественной обратной связи для продаж и маркетинга.",
        },
        {
            "name": "Вынести delivery-процессы из сделочных воронок",
            "problem": "Проекты и производственные процессы искажают коммерческий pipeline.",
            "effect": "Продажи считаются до оплаты/передачи, delivery живёт в отдельной операционной сущности.",
            "complexity": "высокая",
            "priority": "средний",
            "risk": "Длина сделки и конверсия будут смешиваться с производственным циклом.",
        },
        {
            "name": "Закрыть или скрыть пустые и архивные контуры из рабочей навигации",
            "problem": "Пустые и архивные воронки создают шум и риск ошибочного заведения сделок.",
            "effect": "Менеджеры видят только актуальные рабочие процессы.",
            "complexity": "низкая",
            "priority": "средний",
            "risk": "Новые карточки будут появляться в старых контурах по привычке или ошибке.",
        },
        {
            "name": "Сделать поля Компания, сумма, источник и причина отказа обязательными по ключевым переходам",
            "problem": "Пустые поля ломают отчётность, автоматизации и передачу клиента между командами.",
            "effect": "Управленческие отчёты станут сопоставимыми, а роботы будут запускаться предсказуемо.",
            "complexity": "средняя",
            "priority": "высокий",
            "risk": "CRM останется заполненной частично, а автоматизации будут работать только на части карточек.",
        },
    ]
    if not any(probe.get("ok") and probe.get("items_count", 0) for probe in automation.get("global_probes", [])):
        rows.append(
            {
                "name": "Провести ручную инвентаризацию роботов в интерфейсе Bitrix24",
                "problem": "REST API не дал полного подтверждённого списка роботов и бизнес-процессов.",
                "effect": "Можно будет безопасно найти дубли задач, конфликтующие уведомления и перезапись источников.",
                "complexity": "средняя",
                "priority": "высокий",
                "risk": "Автоматизации останутся чёрным ящиком, а изменения воронок могут сломать скрытые сценарии.",
            }
        )
    return rows


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("\n", "<br>") for value in row) + " |")
    return "\n".join(lines)


def render_report(
    categories: dict[str, str],
    audit: dict[str, Any],
    sources: dict[str, str],
    reason_map_data: dict[str, str],
    activities_error: str,
    activity_type_counter: Counter[str],
    automation: dict[str, Any],
    recommendations: list[dict[str, str]],
) -> str:
    total_deals = sum(item["deals_total"] for item in audit.values())
    total_active = sum(item["active_total"] for item in audit.values())
    total_without_future = sum(item["activity"]["without_future"] for item in audit.values())
    total_overdue = sum(item["activity"]["overdue"] for item in audit.values())
    total_missing_source = sum(item["missing_source"] for item in audit.values())
    total_lost_without_reason = sum(item["lost_without_reason"] for item in audit.values())

    funnel_rows = []
    for category_id, item in sorted(audit.items(), key=lambda pair: pair[1]["deals_total"], reverse=True):
        if item["deals_total"] == 0:
            activity = "не используется"
        elif item["created_6m"] == 0 and item["active_total"] == 0:
            activity = "архив/заморожена"
        elif item["created_6m"] <= 3:
            activity = "низкая"
        else:
            activity = "активная"
        problems = []
        if item["active_total"] > item["deals_total"] * 0.7 and item["deals_total"] > 30:
            problems.append("много открытых")
        if item["dead_stages"]:
            problems.append(f"мертвые этапы: {len(item['dead_stages'])}")
        if item["missing_source"]:
            problems.append(f"без источника: {item['missing_source']}")
        if item["activity"]["without_future"]:
            problems.append(f"без след. шага: {item['activity']['without_future']}")
        if item["backward_deals"]:
            problems.append(f"возвраты назад: {item['backward_deals']}")
        funnel_rows.append(
            [
                item["category"],
                infer_purpose(item["category"]),
                item["stages_count"],
                activity,
                "; ".join(problems[:4]) or "критичных признаков не видно",
                f"создано 3м/6м/год: {item['created_3m']}/{item['created_6m']}/{item['created_ytd']}",
            ]
        )

    lines = [
        "# Аудит Bitrix24: воронки, сделки, автоматизации",
        "",
        f"Дата подготовки: `{fmt_dt(NOW)} МСК`",
        "",
        "## 1. Краткий вывод",
        "",
        f"- В CRM найдено `{len(categories)}` сделочных воронок и `{total_deals}` сделок, из них `{total_active}` открытых.",
        "- Система используется активно, но коммерческий контур смешан с аккаунтингом, retention, delivery, архивами и техническими процессами.",
        f"- Ключевые операционные риски: `{total_without_future}` активных сделок без будущей активности, `{total_overdue}` сделок с просроченными активностями, `{total_missing_source}` сделок без источника, `{total_lost_without_reason}` проигранных сделок без причины отказа.",
        "- Самый большой управленческий риск: часть стадий и воронок описывает не бизнес-решение клиента, а внутреннее состояние, архив или сегмент базы.",
        "",
        "## 2. Список воронок",
        "",
        md_table(["Воронка", "Назначение", "Количество этапов", "Активность", "Основные проблемы", "Комментарий"], funnel_rows),
        "",
        "## 3. Движение сделок",
        "",
    ]

    for category_id, item in sorted(audit.items(), key=lambda pair: pair[1]["deals_total"], reverse=True):
        lines.extend(
            [
                f"### {item['category']}",
                "",
                f"- Сделок всего: `{item['deals_total']}`, открытых: `{item['active_total']}`, создано за 3 месяца: `{item['created_3m']}`, за 6 месяцев: `{item['created_6m']}`, с начала 2026 года: `{item['created_ytd']}`.",
                f"- Выиграно: `{item['won_total']}`, проиграно: `{item['lost_total']}`.",
                f"- Возвраты назад: `{item['backward_events']}` событий по `{item['backward_deals']}` сделкам; переходы между воронками по истории стадий: `{item['category_transfer_events']}` событий по `{item['category_transfer_deals']}` сделкам.",
                f"- Текущие накопители: {', '.join(f'{name} ({count})' for name, count in item['top_current_stages'][:5]) or 'нет данных'}.",
                f"- Максимальные зависания по медиане: {longest_stage_text(item['longest_stages'])}.",
            ]
        )
        if item["dead_stages"] or item["low_stages"]:
            unused = [row["stage"] for row in item["dead_stages"][:6]]
            low = [row["stage"] for row in item["low_stages"][:6]]
            lines.append(f"- Неиспользуемые/слабо используемые этапы: {', '.join(unused + low) or 'не выявлены'}.")
        lines.append("")

    lines.extend(
        [
            "## 4. Источники и причины отказов",
            "",
            f"- В справочнике источников: `{len(sources)}` значений.",
            f"- В справочнике причин отказа по полю `{REJECTION_REASON_FIELD}`: `{len(reason_map_data)}` значений.",
            f"- Сделок без источника: `{total_missing_source}`; сделок с общими источниками типа `прочее/не выяснено`: `{sum(item['generic_sources'] for item in audit.values())}`.",
            f"- Проигранных сделок без причины отказа: `{total_lost_without_reason}`.",
            "- Спам нужно исключать из маркетинговых конверсий отдельным правилом: это не коммерческий отказ и не качество канала продаж.",
            "- Первичный маркетинговый источник нельзя перезаписывать внутренними источниками вроде телемаркетинга. Для внутреннего канала обработки нужно отдельное поле `канал обработки/команда`, а не замена `SOURCE_ID`.",
            "",
        ]
    )
    source_rows = []
    for item in audit.values():
        source_rows.append([item["category"], ", ".join(f"{name} ({count})" for name, count in item["sources"].most_common(5))])
    lines.append(md_table(["Воронка", "Топ источников"], source_rows))

    reason_rows = []
    for item in audit.values():
        if item["lost_total"]:
            reason_rows.append([item["category"], item["lost_without_reason"], item["spam_lost"], ", ".join(f"{name} ({count})" for name, count in item["reasons"].most_common(5))])
    lines.extend(["", md_table(["Воронка", "Без причины", "Спам", "Топ причин"], reason_rows or [["Нет проигранных", 0, 0, ""]]), ""])

    lines.extend(
        [
            "## 5. Поля и качество заполнения",
            "",
            md_table(
                ["Воронка", "Без компании", "Без суммы", "Без источника", "Проиграно без причины"],
                [[item["category"], item["missing_company"], item["missing_amount"], item["missing_source"], item["lost_without_reason"]] for item in audit.values()],
            ),
            "",
            "- Обязательными по ключевым переходам стоит сделать: компания/контакт, сумма, источник, услуга/направление, следующий шаг, дата следующего контакта, причина отказа для проигрыша.",
            "- Перед включением обязательности нужно проверить роботов и карточки в интерфейсе, чтобы не заблокировать рабочий процесс на исторических карточках.",
            "",
            "## 6. Задачи и следующий шаг",
            "",
        ]
    )
    if activities_error:
        lines.append(f"- Активности не удалось выгрузить полностью: `{activities_error}`.")
    else:
        lines.append(f"- Активности выгружены за период с `{fmt_dt(ACTIVITY_LOOKBACK_START)}`; типов/провайдеров активности найдено: `{len(activity_type_counter)}`.")
    lines.extend(
        [
            f"- Активные сделки без будущей активности: `{total_without_future}`.",
            f"- Сделки с просроченными активностями: `{total_overdue}`.",
            f"- Без коммуникации 7/14/30 дней: `{sum(item['activity']['no_touch_7'] for item in audit.values())}` / `{sum(item['activity']['no_touch_14'] for item in audit.values())}` / `{sum(item['activity']['no_touch_30'] for item in audit.values())}`.",
            "",
        ]
    )
    manager_rows = []
    for item in audit.values():
        for manager, counters in item["activity"]["by_manager"].items():
            manager_rows.append([item["category"], manager, counters.get("без будущей задачи", 0), counters.get("с просрочками", 0), counters.get("без коммуникации 14+", 0)])
    lines.append(md_table(["Воронка", "Менеджер", "Без следующего шага", "С просрочками", "Без коммуникации 14+"], manager_rows[:30] or [["-", "-", 0, 0, 0]]))

    automation_rows = []
    for probe in automation["global_probes"]:
        automation_rows.append([probe["method"], "да" if probe.get("ok") else "нет", probe.get("items_count", 0), probe.get("error", "")])
    lines.extend(
        [
            "",
            "## 7. Автоматизации",
            "",
            md_table(["Метод проверки", "Доступен", "Найдено элементов", "Комментарий"], automation_rows),
            "",
            "- По REST удалось/не удалось проверить только то, что доступно текущему OAuth-приложению. Это не заменяет ручную инвентаризацию роботов в интерфейсе Bitrix24.",
            "- Особо проверить вручную: автосоздание задач, уведомления РОПу, смену источника, смену ответственного, перенос между воронками, создание встреч/брифов/договоров.",
            "",
            "## 8. Дубли и мусор",
            "",
            "- Явные структурные дубли уже видны на уровне воронок: параллельные аккаунтинг/retention-контуры, архивные контуры, пустые или почти пустые рабочие контуры.",
            "- Сделки без компании и компании без нормального идентификатора должны попадать в отдельную очередь чистки, иначе повторные сделки не связываются с историей клиента.",
            "- Для защиты от дублей нужно правило поиска по ИНН, телефону, email, домену и активной открытой сделке перед автосозданием карточки из звонка/чата.",
            "",
            "## 9. Рекомендации",
            "",
            md_table(["Рекомендация", "Проблема", "Эффект", "Сложность", "Приоритет"], [[row["name"], row["problem"], row["effect"], row["complexity"], row["priority"]] for row in recommendations]),
            "",
        ]
    )
    for row in recommendations:
        lines.extend(
            [
                f"### Рекомендация: {row['name']}",
                "",
                "Проблема:",
                f"- {row['problem']}",
                "",
                "Что сделать:",
                f"- {action_for(row['name'])}",
                "",
                "Обоснование:",
                f"- {row['risk']}",
                "",
                "Ожидаемый эффект:",
                f"- {row['effect']}",
                "",
                "Сложность внедрения:",
                f"- {row['complexity']}",
                "",
                "Приоритет:",
                f"- {row['priority']}",
                "",
            ]
        )

    quick = [row["name"] for row in recommendations if row["complexity"] == "низкая"]
    medium = [row["name"] for row in recommendations if row["complexity"] == "средняя"]
    large = [row["name"] for row in recommendations if row["complexity"] == "высокая"]
    lines.extend(
        [
            "## 10. План внедрения",
            "",
            "### Быстрые победы",
            "",
            *[f"- {name}" for name in quick],
            "",
            "### Среднесрочные улучшения",
            "",
            *[f"- {name}" for name in medium],
            "",
            "### Крупные изменения",
            "",
            *[f"- {name}" for name in large],
            "",
            "## 11. Что требует ручного решения",
            "",
            "- Подтвердить owner каждой коммерческой воронки: Sales, SDR, Реанимация, Account Management, Retention.",
            "- Решить, какая воронка является единственным источником правды по новым деньгам.",
            "- В интерфейсе Bitrix24 вручную выгрузить/проверить роботов, потому что REST-доступ к ним ограничен.",
            "- Утвердить справочник причин отказа и правило исключения спама из маркетинговой аналитики.",
            "- Утвердить правило сохранения первичного источника и отдельное поле для внутреннего канала обработки.",
            "",
            "Финальный вывод:",
            "",
            "В первую очередь нужно зафиксировать карту коммерческих контуров, запретить перезапись первичного источника, нормализовать причины отказа и включить контроль следующего шага. Максимальный эффект дадут чистая основная воронка продаж, короткая управляемая реанимация и единый post-sale/accounting контур. Наибольший риск сейчас создают смешанные воронки, активные карточки без следующего действия и автоматизации, которые могут менять источник, ответственного или маршрут сделки без прозрачного owner.",
            "",
            "## Ограничения аудита",
            "",
            "- Никакие изменения в Bitrix24 не выполнялись.",
            "- Метрики по движению построены по `crm.deal.list`, `crm.stagehistory.list`, `crm.status.list` и `crm.activity.list` в доступном OAuth-контуре.",
            "- Историю изменения `SOURCE_ID` и полный список роботов текущий REST-доступ может не раскрывать; эти зоны помечены как требующие ручной проверки.",
        ]
    )
    return "\n".join(lines)


def infer_purpose(name: str) -> str:
    norm = normalize(name)
    if "продаж" in norm:
        return "new business продажи"
    if "теле" in norm:
        return "первичный обзвон / SDR"
    if "реаним" in norm:
        return "реактивация базы"
    if "аккаунт" in norm:
        return "аккаунтинг / развитие клиентов"
    if "retention" in norm:
        return "retention / возврат клиентов"
    if "проект" in norm:
        return "delivery / проекты"
    if "архив" in norm:
        return "архивный контур"
    return "требует подтверждения owner"


def action_for(name: str) -> str:
    actions = {
        "Зафиксировать единую карту коммерческих контуров": "Утвердить список рабочих коммерческих воронок, назначение каждой, owner и правило, где создаётся новая выручка.",
        "Сократить и пересобрать Реанимацию": "Перенести сегменты из стадий в поля и оставить короткий процесс: база, взят в работу, контакт, интерес, передано в продажи, отказ/неактуально.",
        "Перестать перезаписывать первичный маркетинговый источник внутренними источниками": "Разделить `первичный источник` и `внутренний канал обработки`; запретить роботам менять источник, если он уже заполнен.",
        "Ввести обязательный следующий шаг для активных коммерческих сделок": "На активных стадиях требовать будущую задачу или дату следующего контакта; РОПу дать ежедневный список нарушений.",
        "Нормализовать причины отказа": "Сократить справочник отказов, объединить дубли, сделать причину обязательной при проигрыше и вынести `Спам` в технический отказ.",
        "Вынести delivery-процессы из сделочных воронок": "После выигрыша создавать/связывать delivery smart-process, а сделку закрывать коммерческим результатом.",
        "Закрыть или скрыть пустые и архивные контуры из рабочей навигации": "Сначала заморозить создание новых карточек, затем закрыть остатки и скрыть контуры после согласования.",
        "Сделать поля Компания, сумма, источник и причина отказа обязательными по ключевым переходам": "Настроить обязательность не на всей карточке сразу, а на переходах между ключевыми стадиями.",
        "Провести ручную инвентаризацию роботов в интерфейсе Bitrix24": "Собрать таблицу по каждой воронке: робот, стадия, действие, поле/задача/уведомление, owner, риск конфликта.",
    }
    return actions.get(name, "Описать изменение в отдельной карте внедрения и согласовать с владельцем процесса.")


def longest_stage_text(rows: list[dict[str, Any]]) -> str:
    text = ", ".join("{} - {}".format(row["stage"], fmt_days(row["median_hours"])) for row in rows[:5])
    return text or "нет данных"


def json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return iso(value)
    if isinstance(value, Counter):
        return dict(value)
    if isinstance(value, defaultdict):
        return dict(value)
    if isinstance(value, dict):
        return {key: json_safe(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def main() -> None:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    auth = base.make_auth()

    log("Загружаю справочники Bitrix24")
    categories = list_categories(auth)
    statuses = list_statuses(auth)
    stage_maps, stage_sorts = build_stage_maps(statuses, categories)
    sources = source_map(statuses)
    reason_map_data = enum_map(auth, REJECTION_REASON_FIELD)

    log("Загружаю сделки")
    deals = list_all_deals(auth)
    log(f"Сделок загружено: {len(deals)}")

    log("Загружаю историю стадий")
    history_by_category: dict[str, list[dict[str, Any]]] = {}
    for category_id, name in categories.items():
        rows = list_stage_history(auth, category_id, SIX_MONTHS_START)
        history_by_category[category_id] = rows
        log(f"История стадий: {name} ({category_id}) = {len(rows)}")

    log("Загружаю активности")
    activities, activities_error = list_activities(auth)
    activity_index, activity_type_counter = build_activity_index(activities)
    log(f"Активностей загружено: {len(activities)}")

    user_ids = [deal.assigned_id for deal in deals if deal.assigned_id]
    user_ids.extend(str(row.get("RESPONSIBLE_ID") or "") for row in activities if row.get("RESPONSIBLE_ID"))
    users = user_names(auth, user_ids)

    log("Проверяю доступность API автоматизаций")
    automation = probe_automation(auth, categories)

    log("Считаю метрики")
    audit = build_category_audit(
        categories,
        deals,
        history_by_category,
        stage_maps,
        stage_sorts,
        sources,
        reason_map_data,
        users,
        activity_index,
    )
    recommendations = recommendation_rows(audit, automation)
    report = render_report(categories, audit, sources, reason_map_data, activities_error, activity_type_counter, automation, recommendations)

    REPORT_MD.write_text(report, encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps(
            json_safe(
                {
                    "generated_at_msk": iso(NOW),
                    "periods": {
                        "three_months_start": iso(THREE_MONTHS_START),
                        "six_months_start": iso(SIX_MONTHS_START),
                        "year_start": iso(YEAR_START),
                    },
                    "categories": categories,
                    "audit": audit,
                    "sources": sources,
                    "rejection_reasons": reason_map_data,
                    "activities_error": activities_error,
                    "activity_type_counter": activity_type_counter,
                    "automation": automation,
                    "recommendations": recommendations,
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(REPORT_MD)
    print(REPORT_JSON)


if __name__ == "__main__":
    main()
