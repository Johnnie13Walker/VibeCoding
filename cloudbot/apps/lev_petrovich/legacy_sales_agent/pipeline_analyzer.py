"""Нормализация live-данных Bitrix для управленческого Sales Copilot."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from cloudbot.business_day import MOSCOW_TZ, report_day_flags

from .bitrix_links import build_deal_url, build_dynamic_item_url, build_lead_url
from .sales_team_scope import sales_allowlist_user_ids
QUALIFIED_MARKERS = ("qual", "квали", "appointment", "meeting", "demo", "proposal", "in work")
WON_MARKERS = ("won", "успеш", "оплач", "converted", "sale")
LOST_MARKERS = ("lost", "lose", "junk", "некаче", "отказ", "fail")
DEFERRED_MARKERS = ("отлож", "defer", "postpon", "pause", "hold", "later")
RETURNABLE_REASON_MARKERS = (
    "будет актуально",
    "верн",
    "позже",
    "позднее",
    "перезвон",
    "напомн",
    "не сейчас",
    "после сезона",
    "после отпуска",
    "в следующем месяце",
    "в следующем квартале",
)
LATE_STAGE_MARKERS = (
    "proposal",
    "invoice",
    "contract",
    "negoti",
    "final",
    "offer",
    "коммер",
    "договор",
    "счет",
    "оплат",
    "соглас",
    "кп",
)
LEADER_FIELD_MARKERS = ("HEAD", "ESCAL", "DIRECTOR", "RUK", "CONTROL", "BOSS")
STAGE_NAME_MAP = {
    "NEW": "Новая",
    "PREPARATION": "Подготовка",
    "EXECUTING": "В работе",
    "FINAL_INVOICE": "Финальный счет",
    "PREPAYMENT_INVOICE": "Предоплата",
    "WON": "Успешно",
    "LOSE": "Потеряна",
}
GENERIC_LOST_REASON_VALUES = {
    "",
    "0",
    "1",
    "отвал",
    "lose",
    "c10:lose",
    "новая",
    "квалификация",
    "подготовка кп",
    "подготовка договора",
    "подготовка брифа",
    "догрев и переговоры",
}
HOT_STAGE_STAGE_ID = "C10:UC_KC7195"
HOT_STAGE_STAGE_NAME = "Подготовка договора"
BRIEF_PREP_STAGE_ID = "C10:PREPAYMENT_INVOIC"
BRIEF_PREP_STAGE_NAME = "Подготовка БРИФа"
TASK_DEADLINE_CHANGE_KEYS = {
    "changeddeadlinecount",
    "deadlinechangecount",
    "deadlinechangescount",
    "deadlinemovecount",
    "deadlinemovescount",
    "deadlinepostponecount",
    "deadlinereschedulecount",
    "deadlineshiftcount",
    "deadlineshiftscount",
    "postponecount",
    "postponescount",
    "reschedulecount",
    "reschedulescount",
}
TASK_DEADLINE_CHANGED_AT_KEYS = {
    "activitydate",
    "changedat",
    "changeddate",
    "deadlinechangedat",
    "deadlinemovedat",
    "deadlinepostponedat",
    "deadlinerescheduledat",
    "deadlineshiftat",
    "lastdeadlinechangedat",
    "lastdeadlinemovedat",
    "lastdeadlinepostponedat",
    "lastdeadlinerescheduledat",
    "lastdeadlineshiftat",
    "postponedat",
    "rescheduledat",
    "statuschangeddate",
    "updatedat",
}
DYNAMIC_ITEM_PARENT_DEAL_KEYS = {"parentid2"}
DYNAMIC_ITEM_SCHEDULE_IGNORED_KEYS = {
    "id",
    "xmlid",
    "title",
    "createdtime",
    "updatedtime",
    "movedtime",
    "lastactivitytime",
    "lastcommunicationtime",
    "lastcommunicationcalltime",
    "lastcommunicationemailtime",
    "lastcommunicationimoltime",
    "lastcommunicationwebformtime",
    "assignedbyid",
    "createdby",
    "updatedby",
    "movedby",
    "lastactivityby",
    "categoryid",
    "stageid",
    "previousstageid",
    "opened",
    "entitytypeid",
    "companyid",
    "contactid",
    "opportunity",
    "ismanualopportunity",
    "taxvalue",
    "currencyid",
    "mycompanyid",
    "sourceid",
    "sourcedescription",
    "webformid",
    "parentid2",
}
NEXT_STEP_FIELD_INCLUDE_MARKERS = (
    "дата встречи",
    "защита кп",
    "бриф",
    "брифф",
)
NEXT_STEP_FIELD_EXCLUDE_MARKERS = (
    "ссылка",
    "запись",
    "коммент",
    "комментар",
)
TIMELINE_TOUCH_INCLUDE_MARKERS = (
    "wazzup24.com/images/bitrix/",
    "telegram.png",
    "whatsapp",
    "написал",
    "написала",
    "ответил",
    "ответила",
    "позвонил",
    "позвонила",
    "созвон",
    "в почте",
    "по почте",
    "email",
    "отправил",
    "отправила",
)
TIMELINE_TOUCH_EXCLUDE_MARKERS = (
    "выбран новый ответственный",
    "причина отказа:",
)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "y", "yes", "true", "t", "да"}


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except ValueError:
        return 0.0


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=MOSCOW_TZ)
        return value.astimezone(MOSCOW_TZ)

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).astimezone(MOSCOW_TZ)

    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        parsed = None

    if parsed is None:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%Y %H:%M",
            "%d.%m.%Y",
        ):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MOSCOW_TZ)
    return parsed.astimezone(MOSCOW_TZ)


def _timeline_touch_at(comments: list[dict[str, Any]] | None) -> datetime | None:
    latest: datetime | None = None
    for item in comments or []:
        comment = str(item.get("comment") or item.get("COMMENT") or "").strip()
        if not comment:
            continue
        lowered = comment.casefold()
        if any(marker in lowered for marker in TIMELINE_TOUCH_EXCLUDE_MARKERS):
            continue
        if not any(marker in lowered for marker in TIMELINE_TOUCH_INCLUDE_MARKERS):
            continue
        created_at = _parse_datetime(item.get("created_at") or item.get("CREATED"))
        if created_at is None:
            continue
        if latest is None or created_at > latest:
            latest = created_at
    return latest


def _normalized_lookup_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _task_nested_value(
    payload: Any,
    *,
    candidate_keys: set[str],
    parser: callable,
    max_depth: int = 3,
) -> Any:
    stack: list[tuple[Any, int]] = [(payload, 0)]
    while stack:
        current, depth = stack.pop(0)
        if depth > max_depth:
            continue
        if isinstance(current, dict):
            for key, value in current.items():
                if _normalized_lookup_key(key) in candidate_keys:
                    parsed = parser(value)
                    if parsed is not None:
                        return parsed
                if isinstance(value, (dict, list, tuple)):
                    stack.append((value, depth + 1))
        elif isinstance(current, (list, tuple)):
            for value in current:
                if isinstance(value, (dict, list, tuple)):
                    stack.append((value, depth + 1))
    return None


def _parse_int_like(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw.replace(" ", "")
    if raw.isdigit():
        return int(raw)
    match = re.search(r"-?\d+", raw)
    if match:
        return int(match.group(0))
    return None


def _extract_task_deadline_change_count(task: dict[str, Any]) -> int:
    count = _task_nested_value(task, candidate_keys=TASK_DEADLINE_CHANGE_KEYS, parser=_parse_int_like)
    return max(int(count or 0), 0)


def _extract_task_deadline_changed_at(task: dict[str, Any]) -> datetime | None:
    return _task_nested_value(task, candidate_keys=TASK_DEADLINE_CHANGED_AT_KEYS, parser=_parse_datetime)


def _today_flags(dt: datetime | None, now: datetime) -> tuple[bool, bool]:
    return report_day_flags(dt, now)


def _semantic_is_won(value: str) -> bool:
    return str(value or "").strip().upper() == "S"


def _semantic_is_lost(value: str) -> bool:
    return str(value or "").strip().upper() == "F"


def _status_haystack(*parts: Any) -> str:
    return " ".join(str(part or "").strip() for part in parts if str(part or "").strip()).lower()


def _is_qualified_status(status_id: str, status_name: str, semantic_id: str) -> bool:
    if _semantic_is_won(semantic_id):
        return True
    haystack = _status_haystack(status_id, status_name, semantic_id)
    return any(marker in haystack for marker in QUALIFIED_MARKERS)


def _is_won_status(status_id: str, status_name: str, semantic_id: str) -> bool:
    if _semantic_is_won(semantic_id):
        return True
    haystack = _status_haystack(status_id, status_name, semantic_id)
    return any(marker in haystack for marker in WON_MARKERS)


def _is_lost_status(status_id: str, status_name: str, semantic_id: str) -> bool:
    if _semantic_is_lost(semantic_id):
        return True
    haystack = _status_haystack(status_id, status_name, semantic_id)
    return any(marker in haystack for marker in LOST_MARKERS)


def _is_deferred_reason(reason: str | None) -> bool:
    lowered = str(reason or "").strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in RETURNABLE_REASON_MARKERS)


def _is_deferred_status(status_id: str, status_name: str, semantic_id: str, *, reason: str | None = None) -> bool:
    haystack = _status_haystack(status_id, status_name, semantic_id)
    if any(marker in haystack for marker in DEFERRED_MARKERS):
        return True
    return _is_deferred_reason(reason)


def _friendly_stage_name(stage_id: str, status_name: str | None = None) -> str:
    explicit_name = str(status_name or "").strip()
    if explicit_name and explicit_name != stage_id:
        return explicit_name

    raw = str(stage_id or "").strip()
    if not raw:
        return "Без стадии"
    token = raw.split(":", 1)[-1].strip().upper()
    if token in STAGE_NAME_MAP:
        return STAGE_NAME_MAP[token]
    humanized = token.replace("_", " ").strip().title()
    return humanized or raw


def _is_late_stage(stage_id: str, stage_name: str, probability: float) -> bool:
    haystack = _status_haystack(stage_id, stage_name)
    if any(marker in haystack for marker in LATE_STAGE_MARKERS):
        return True
    return probability >= 70.0


def _explicit_leader_flag(item: dict[str, Any]) -> bool:
    for key, value in item.items():
        key_upper = str(key).upper()
        if any(marker in key_upper for marker in LEADER_FIELD_MARKERS) and _truthy(value):
            return True
    for field in (
        "UF_CRM_NEEDS_HEAD",
        "UF_CRM_ESCALATE",
        "UF_CRM_DIRECTOR_CONTROL",
        "NEEDS_ATTENTION",
    ):
        if _truthy(item.get(field)):
            return True
    return False


def _effective_probability(probability: float, *, late_stage: bool, inactive_days: int | None) -> float:
    if probability > 0.0:
        return probability
    if late_stage:
        return 75.0 if (inactive_days or 0) <= 5 else 55.0
    if inactive_days in (None, 0, 1):
        return 45.0
    return 25.0


def _user_name(user: dict[str, Any]) -> str:
    last_name = str(user.get("last_name") or "").strip()
    name = str(user.get("name") or "").strip()
    if last_name and name:
        return f"{last_name} {name}"
    raw_full_name = " ".join(str(user.get("full_name") or "").split()).strip()
    if raw_full_name:
        parts = raw_full_name.split()
        if len(parts) >= 2:
            return f"{parts[0]} {parts[1]}"
        return raw_full_name
    return str(user.get("email") or "Не назначен").strip()


def _assigned_name(user_map: dict[str, str], assigned_id: str) -> str:
    value = user_map.get(str(assigned_id or "").strip(), "").strip()
    if value:
        return value
    assigned_id = str(assigned_id or "").strip()
    if assigned_id:
        return f"ID {assigned_id}"
    return "без ответственного"


def _dedupe_entities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        entity_id = str(item.get("id") or "").strip()
        if not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        result.append(item)
    return result


def _company_contact_suffix(
    company_map: dict[str, str],
    contact_map: dict[str, str],
    company_id: str | None,
    contact_id: str | None,
) -> str:
    company_title = company_map.get(str(company_id or "").strip(), "")
    contact_title = contact_map.get(str(contact_id or "").strip(), "")
    relation = company_title or contact_title
    return relation.strip()


def _significant_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-zA-Zа-яА-Я0-9]+", str(text or "").lower())
        if len(token) >= 4
    }


def _meeting_matches(entity_title: str, relation_suffix: str, meeting_title: str) -> bool:
    meeting_lc = str(meeting_title or "").lower()
    if not meeting_lc:
        return False

    for probe in (entity_title, relation_suffix):
        probe_lc = str(probe or "").lower().strip()
        if probe_lc and (probe_lc in meeting_lc or meeting_lc in probe_lc):
            return True

    entity_tokens = _significant_tokens(entity_title) | _significant_tokens(relation_suffix)
    meeting_tokens = _significant_tokens(meeting_title)
    return bool(entity_tokens and meeting_tokens and entity_tokens.intersection(meeting_tokens))


def _status_name_map(items: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items or []:
        status_id = str(item.get("STATUS_ID") or item.get("status_id") or "").strip()
        if not status_id:
            continue
        result[status_id] = str(item.get("NAME") or item.get("name") or status_id).strip()
    return result


def _source_name_map(items: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items or []:
        source_id = str(item.get("STATUS_ID") or item.get("status_id") or "").strip()
        if not source_id:
            continue
        result[source_id] = str(item.get("NAME") or item.get("name") or source_id).strip()
    return result


def _looks_like_text_reason(value: str, *, title: str, relation_suffix: str) -> bool:
    cleaned = str(value or "").strip()
    if len(cleaned) < 12 or len(cleaned) > 280:
        return False
    lowered = cleaned.lower()
    if lowered in GENERIC_LOST_REASON_VALUES:
        return False
    if "@" in cleaned or "http://" in lowered or "https://" in lowered or ".ru" in lowered:
        return False
    if re.match(r"^\d{4}[./-]\d{2}[./-]\d{2}", cleaned) or re.match(r"^\d{2}[./-]\d{2}[./-]\d{4}", cleaned):
        return False
    if re.fullmatch(r"[0-9 .:+-]+", cleaned):
        return False
    if lowered == str(title or "").strip().lower():
        return False
    if relation_suffix and lowered == str(relation_suffix).strip().lower():
        return False
    word_count = len([part for part in re.split(r"\s+", cleaned) if part])
    return bool(
        re.search(r"[a-zа-я]", cleaned, flags=re.IGNORECASE)
        and " " in cleaned
        and (word_count >= 3 or bool(re.search(r"[,.!?;:]", cleaned)))
    )


def _field_reason_label(meta: dict[str, Any]) -> str:
    for key in ("formLabel", "listLabel", "filterLabel", "title"):
        label = str(meta.get(key) or "").strip()
        if label:
            return label
    return ""


def _is_lost_reason_field(field_name: str, meta: dict[str, Any]) -> bool:
    if not str(field_name).startswith("UF_CRM_"):
        return False
    label = _field_reason_label(meta).lower()
    return "причин" in label or "причина" in label or "reason" in label


def _clean_explicit_reason_text(value: Any) -> str | None:
    cleaned = " ".join(str(value or "").split()).strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered in GENERIC_LOST_REASON_VALUES:
        return None
    if re.fullmatch(r"[0-9 .:+-]+", cleaned):
        return None
    return cleaned


def _extract_lost_reason_from_fields(raw: dict[str, Any], field_meta: dict[str, Any]) -> str | None:
    for field_name, meta in field_meta.items():
        if not _is_lost_reason_field(field_name, meta):
            continue
        value = raw.get(field_name)
        if value in (None, "", [], {}):
            continue

        field_type = str(meta.get("type") or "").strip().lower()
        if field_type == "enumeration":
            items_map = {
                str(item.get("ID") or "").strip(): str(item.get("VALUE") or "").strip()
                for item in meta.get("items") or []
                if str(item.get("ID") or "").strip() and str(item.get("VALUE") or "").strip()
            }
            raw_values = value if isinstance(value, list) else [value]
            resolved = []
            for raw_value in raw_values:
                label = items_map.get(str(raw_value or "").strip()) or str(raw_value or "").strip()
                cleaned = _clean_explicit_reason_text(label)
                if cleaned:
                    resolved.append(cleaned)
            if resolved:
                return "; ".join(dict.fromkeys(resolved))
            continue

        cleaned = _clean_explicit_reason_text(value)
        if cleaned:
            return cleaned
    return None


def _extract_explicit_lost_reason(
    raw: dict[str, Any],
    *,
    title: str,
    relation_suffix: str,
    field_meta: dict[str, Any] | None = None,
) -> str | None:
    if field_meta:
        reason_from_fields = _extract_lost_reason_from_fields(raw, field_meta)
        if reason_from_fields:
            return reason_from_fields

    standard_keys = ("COMMENTS", "COMMENT", "DESCRIPTION")
    for key in standard_keys:
        value = str(raw.get(key) or "").strip()
        if _looks_like_text_reason(value, title=title, relation_suffix=relation_suffix):
            return value

    for key, value in raw.items():
        if not str(key).startswith("UF_CRM_"):
            continue
        candidate = str(value or "").strip()
        if _looks_like_text_reason(candidate, title=title, relation_suffix=relation_suffix):
            return candidate
    return None


def _dynamic_item_payload(raw_item: dict[str, Any]) -> dict[str, Any]:
    payload = raw_item.get("raw") if isinstance(raw_item.get("raw"), dict) else raw_item
    return payload if isinstance(payload, dict) else {}


def _extract_dynamic_parent_deal_id(raw_item: dict[str, Any]) -> str | None:
    for payload in (raw_item, _dynamic_item_payload(raw_item)):
        if not isinstance(payload, dict):
            continue
        explicit = str(payload.get("parent_deal_id") or "").strip()
        if explicit:
            return explicit
        for key, value in payload.items():
            if _normalized_lookup_key(key) not in DYNAMIC_ITEM_PARENT_DEAL_KEYS:
                continue
            resolved = str(value or "").strip()
            if resolved and resolved != "0":
                return resolved
    return None


def _extract_dynamic_schedule_at(raw_item: dict[str, Any]) -> datetime | None:
    candidates: list[datetime] = []
    payload = _dynamic_item_payload(raw_item)
    if not isinstance(payload, dict):
        return None
    for key, value in payload.items():
        if _normalized_lookup_key(key) in DYNAMIC_ITEM_SCHEDULE_IGNORED_KEYS:
            continue
        if not isinstance(value, (str, datetime)):
            continue
        parsed = _parse_datetime(value)
        if parsed is not None:
            candidates.append(parsed)
    return max(candidates) if candidates else None


def _extract_next_step_from_deal_fields(
    raw_item: dict[str, Any],
    *,
    deal_fields_meta: dict[str, Any] | None,
    now: datetime,
) -> tuple[datetime | None, str | None]:
    payload = raw_item.get("raw") if isinstance(raw_item.get("raw"), dict) else raw_item
    if not isinstance(payload, dict) or not isinstance(deal_fields_meta, dict):
        return None, None

    future_candidates: list[tuple[datetime, str]] = []
    fallback_candidates: list[tuple[datetime, str]] = []
    for field_name, meta in deal_fields_meta.items():
        field_key = str(field_name or "").strip()
        if not field_key:
            continue
        value = payload.get(field_key)
        if value in (None, "", [], {}):
            continue

        label_parts = [
            str(meta.get(key) or "").strip()
            for key in ("title", "formLabel", "listLabel", "name")
            if str(meta.get(key) or "").strip()
        ]
        label = " ".join(label_parts).strip() or field_key
        lowered = label.casefold()
        if not any(marker in lowered for marker in NEXT_STEP_FIELD_INCLUDE_MARKERS):
            continue
        if any(marker in lowered for marker in NEXT_STEP_FIELD_EXCLUDE_MARKERS):
            continue

        parsed = _parse_datetime(value)
        if parsed is None:
            continue
        if parsed >= now:
            future_candidates.append((parsed, label))
        else:
            fallback_candidates.append((parsed, label))

    if future_candidates:
        return min(future_candidates, key=lambda item: item[0])
    if fallback_candidates:
        return max(fallback_candidates, key=lambda item: item[0])
    return None, None


def _normalize_dynamic_item(
    raw_item: dict[str, Any],
    *,
    now: datetime,
    user_map: dict[str, str],
    stage_name_map: dict[str, str],
    portal_base_url: str,
    entity_type_id: int,
) -> dict[str, Any]:
    item_id = str(raw_item.get("id") or raw_item.get("ID") or "").strip()
    stage_id = str(raw_item.get("stage_id") or raw_item.get("stageId") or raw_item.get("STAGE_ID") or "").strip()
    moved_at = _parse_datetime(raw_item.get("moved_at") or raw_item.get("movedTime"))
    updated_at = _parse_datetime(raw_item.get("updated_at") or raw_item.get("updatedTime"))
    created_at = _parse_datetime(raw_item.get("created_at") or raw_item.get("createdTime"))
    effective_at = moved_at or updated_at or created_at
    today_moved, yesterday_moved = _today_flags(effective_at, now)
    assigned_id = str(raw_item.get("assigned_id") or raw_item.get("assignedById") or "").strip()
    category_id = str(raw_item.get("category_id") or raw_item.get("categoryId") or "").strip()
    parent_deal_id = _extract_dynamic_parent_deal_id(raw_item)
    scheduled_at = _extract_dynamic_schedule_at(raw_item)
    return {
        "id": item_id,
        "title": str(raw_item.get("title") or raw_item.get("TITLE") or item_id).strip(),
        "card_url": build_dynamic_item_url(
            portal_base_url,
            entity_type_id,
            item_id,
            category_id=category_id,
        ),
        "assigned_id": assigned_id,
        "assigned_name": _assigned_name(user_map, assigned_id),
        "stage_id": stage_id,
        "stage_name": stage_name_map.get(stage_id) or stage_id or "Без стадии",
        "category_id": category_id,
        "parent_deal_id": parent_deal_id,
        "scheduled_at": scheduled_at,
        "created_at": created_at,
        "updated_at": updated_at,
        "moved_at": effective_at,
        "today_moved": today_moved,
        "yesterday_moved": yesterday_moved,
        "raw": raw_item.get("raw") if isinstance(raw_item.get("raw"), dict) else raw_item,
    }


def _link_planned_meetings_to_deals(
    deals: list[dict[str, Any]],
    meetings: list[dict[str, Any]],
    *,
    now: datetime,
) -> None:
    if not deals or not meetings:
        return

    for deal in deals:
        deal_id = str(deal.get("id") or "").strip()
        if not deal_id:
            continue
        matched_meetings = [
            item
            for item in meetings
            if (
                str(item.get("parent_deal_id") or "").strip() == deal_id
                or (
                    not str(item.get("parent_deal_id") or "").strip()
                    and _meeting_matches(
                        str(deal.get("title") or "").strip(),
                        str(deal.get("relation_suffix") or "").strip(),
                        str(item.get("title") or "").strip(),
                    )
                )
            )
        ]
        if not matched_meetings:
            continue

        matched_meetings.sort(
            key=lambda item: (
                0 if isinstance(item.get("scheduled_at"), datetime) else 1,
                item.get("scheduled_at") or item.get("updated_at") or item.get("created_at") or item.get("moved_at") or now,
            )
        )
        deal["meeting_titles"] = list(
            dict.fromkeys(
                str(item.get("title") or "").strip()
                for item in matched_meetings
                if str(item.get("title") or "").strip()
            )
        )
        deal["meeting_today"] = any(
            _today_flags(
                item.get("scheduled_at") or item.get("updated_at") or item.get("created_at") or item.get("moved_at"),
                now,
            )[0]
            for item in matched_meetings
            if item.get("scheduled_at") or item.get("updated_at") or item.get("created_at") or item.get("moved_at")
        )
        future_meetings = [
            item
            for item in matched_meetings
            if isinstance(item.get("scheduled_at"), datetime) and item.get("scheduled_at") >= now
        ]
        if future_meetings:
            deal["upcoming_meeting_at"] = min(item.get("scheduled_at") for item in future_meetings)
        meeting_communication_at = max(
            (
                item.get("updated_at") or item.get("created_at") or item.get("moved_at")
                for item in matched_meetings
                if item.get("updated_at") or item.get("created_at") or item.get("moved_at")
            ),
            default=None,
        )
        current_last_communication_at = deal.get("last_communication_at")
        if isinstance(meeting_communication_at, datetime) and (
            current_last_communication_at is None
            or (isinstance(current_last_communication_at, datetime) and current_last_communication_at < meeting_communication_at)
        ):
            deal["last_communication_at"] = meeting_communication_at
            deal["last_client_touch_at"] = meeting_communication_at
            deal["communication_gap_days"] = max(int((now - meeting_communication_at).total_seconds() // 86400), 0)
            signal_points = [
                value
                for value in (
                    meeting_communication_at,
                    deal.get("last_activity_at"),
                    deal.get("modified_at"),
                    deal.get("created_at"),
                )
                if isinstance(value, datetime)
            ]
            if signal_points:
                last_signal_at = max(signal_points)
                deal["last_signal_at"] = last_signal_at
                deal["inactive_days"] = max(int((now - last_signal_at).total_seconds() // 86400), 0)
        deal["engaged_in_last_week"] = bool(
            (
                isinstance(deal.get("last_client_touch_at"), datetime)
                and deal.get("last_client_touch_at") >= (now - timedelta(days=7))
            )
            or isinstance(deal.get("upcoming_meeting_at"), datetime)
        )

        best_meeting = matched_meetings[0]
        meeting_next_step_at = (
            best_meeting.get("scheduled_at")
            or best_meeting.get("updated_at")
            or best_meeting.get("created_at")
            or best_meeting.get("moved_at")
        )
        current_next_step_at = deal.get("next_step_at")
        if deal.get("missing_next_step"):
            deal["missing_next_step"] = False
        if meeting_next_step_at and (
            current_next_step_at is None
            or (isinstance(current_next_step_at, datetime) and current_next_step_at < now)
        ):
            deal["next_step_at"] = meeting_next_step_at
            deal["next_step_subject"] = (
                str(best_meeting.get("title") or "").strip()
                or str(deal.get("next_step_subject") or "").strip()
                or None
            )
            deal["next_step_source"] = "crm.item.list:meeting"
            deal["next_step_activity_id"] = str(best_meeting.get("id") or "").strip() or None
            deal["next_step_provider_id"] = "CRM_DYNAMIC_1048"
            deal["next_step_provider_type_id"] = "MEETING"
            deal["missing_next_step"] = False


def _filter_sales_owned_entities(
    items: list[dict[str, Any]],
    *,
    allowlist_user_ids: set[str],
    source: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not allowlist_user_ids:
        return list(items), []

    filtered: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for item in items:
        assigned_id = str(item.get("assigned_id") or "").strip()
        if assigned_id and assigned_id in allowlist_user_ids:
            filtered.append(item)
            continue
        excluded.append(
            {
                "source": source,
                "entity_id": str(item.get("id") or "").strip(),
                "title": str(item.get("title") or "").strip() or "Без названия",
                "assigned_id": assigned_id,
                "assigned_name": str(item.get("assigned_name") or "").strip() or "без ответственного",
                "reason": "outside_sales_scope" if assigned_id else "missing_assignee",
            }
        )
    return filtered, excluded


def _filter_sales_related_dynamic_items(
    items: list[dict[str, Any]],
    *,
    allowlist_user_ids: set[str],
    scoped_deal_ids: set[str],
    source: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not allowlist_user_ids and not scoped_deal_ids:
        return list(items), []

    filtered: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for item in items:
        assigned_id = str(item.get("assigned_id") or "").strip()
        parent_deal_id = str(item.get("parent_deal_id") or "").strip()
        if (assigned_id and assigned_id in allowlist_user_ids) or (parent_deal_id and parent_deal_id in scoped_deal_ids):
            filtered.append(item)
            continue
        excluded.append(
            {
                "source": source,
                "entity_id": str(item.get("id") or "").strip(),
                "title": str(item.get("title") or "").strip() or "Без названия",
                "assigned_id": assigned_id,
                "assigned_name": str(item.get("assigned_name") or "").strip() or "без ответственного",
                "reason": "outside_sales_scope" if assigned_id else "missing_assignee",
            }
        )
    return filtered, excluded


def _scope_summary(
    *,
    department_filter: Mapping[str, Any] | None,
    excluded_entities: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    unique_users: dict[tuple[str, str], dict[str, str]] = {}
    for items in excluded_entities.values():
        for item in items:
            key = (str(item.get("assigned_id") or "").strip(), str(item.get("assigned_name") or "").strip())
            if key not in unique_users:
                unique_users[key] = {
                    "assigned_id": key[0],
                    "assigned_name": key[1] or "без ответственного",
                    "reason": str(item.get("reason") or "outside_sales_scope"),
                }
    return {
        "allowlist_users": sorted(sales_allowlist_user_ids(department_filter)),
        "allowlist_user_names": sorted((department_filter or {}).get("allowlist_user_names") or []),
        "excluded_entity_counts": {
            key: len(value)
            for key, value in excluded_entities.items()
            if value
        },
        "excluded_users": sorted(
            unique_users.values(),
            key=lambda item: (item["assigned_name"], item["assigned_id"]),
        ),
    }


def _build_stage_stats(active_deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for deal in active_deals:
        key = str(deal.get("stage_name") or "Без стадии").strip()
        item = stats.setdefault(key, {"stage_name": key, "count": 0, "amount": 0.0})
        item["count"] += 1
        item["amount"] += float(deal.get("amount") or 0.0)
    return sorted(
        stats.values(),
        key=lambda item: (float(item["amount"]), int(item["count"])),
        reverse=True,
    )[:3]


def _build_owner_stats(active_deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for deal in active_deals:
        key = str(deal.get("assigned_name") or "Не назначен").strip()
        item = stats.setdefault(
            key,
            {"assigned_name": key, "count": 0, "amount": 0.0, "stuck_count": 0},
        )
        item["count"] += 1
        item["amount"] += float(deal.get("amount") or 0.0)
        if int(deal.get("inactive_days") or 0) >= 5:
            item["stuck_count"] += 1
    return sorted(
        stats.values(),
        key=lambda item: (float(item["amount"]), int(item["count"]), -int(item["stuck_count"])),
        reverse=True,
    )[:3]


def _is_hot_stage_deal(deal: dict[str, Any]) -> bool:
    stage_id = str(deal.get("stage_id") or "").strip()
    if stage_id == HOT_STAGE_STAGE_ID:
        return True
    stage_name = str(deal.get("stage_name") or "").strip().lower()
    return stage_name == HOT_STAGE_STAGE_NAME.lower()


def _is_brief_prep_deal(deal: dict[str, Any]) -> bool:
    stage_id = str(deal.get("stage_id") or "").strip()
    if stage_id == BRIEF_PREP_STAGE_ID:
        return True
    stage_name = str(deal.get("stage_name") or "").strip().lower()
    return stage_name == BRIEF_PREP_STAGE_NAME.lower()


def _aggregate_sources(deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for deal in deals:
        source_name = str(deal.get("source_name") or "Источник не указан").strip()
        item = stats.setdefault(source_name, {"source_name": source_name, "count": 0, "amount": 0.0})
        item["count"] += 1
        item["amount"] += float(deal.get("amount") or 0.0)
    return sorted(stats.values(), key=lambda item: (int(item["count"]), float(item["amount"])), reverse=True)


def _closed_task_statuses(task_status_map: dict[str, str]) -> set[str]:
    closed = {
        str(status_id).strip()
        for status_id, status_name in (task_status_map or {}).items()
        if "заверш" in str(status_name or "").strip().lower()
    }
    return closed or {"5"}


def _extract_task_deal_ids(task: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for binding in task.get("crm_bindings") or []:
        raw = str(binding or "").strip()
        if raw.startswith("D_"):
            deal_id = raw.split("_", 1)[-1].strip()
            if deal_id:
                result.append(deal_id)
    return result


def _task_signal_at(task: dict[str, Any], *, now: datetime) -> datetime:
    deadline = _parse_datetime(task.get("deadline"))
    if isinstance(deadline, datetime):
        return deadline

    raw = task.get("raw") if isinstance(task.get("raw"), dict) else {}
    for key in (
        "activityDate",
        "activity_date",
        "changedDate",
        "changed_date",
        "createdDate",
        "created_date",
    ):
        value = _parse_datetime(raw.get(key))
        if isinstance(value, datetime):
            return value

    return now


def _build_overdue_task_stats(
    tasks: list[dict[str, Any]],
    *,
    active_deals_by_id: dict[str, dict[str, Any]],
    now: datetime,
    task_status_map: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    closed_statuses = _closed_task_statuses(task_status_map)
    overdue_tasks: list[dict[str, Any]] = []
    by_manager: dict[str, dict[str, Any]] = {}

    for task in tasks:
        deadline = _parse_datetime(task.get("deadline"))
        if deadline is None or deadline >= now:
            continue
        status = str(task.get("status") or "").strip()
        if status in closed_statuses:
            continue

        linked_deals = [
            active_deals_by_id[deal_id]
            for deal_id in _extract_task_deal_ids(task)
            if deal_id in active_deals_by_id
        ]
        if not linked_deals:
            continue

        deal = sorted(linked_deals, key=lambda item: float(item.get("amount") or 0.0), reverse=True)[0]
        days_overdue = max(int((now - deadline).total_seconds() // 86400), 0)
        item = {
            "task_id": str(task.get("id") or "").strip(),
            "task_title": str(task.get("title") or "").strip() or "Без названия",
            "task_status": status,
            "deadline": deadline,
            "days_overdue": days_overdue,
            "deal_id": deal.get("id"),
            "deal_title": deal.get("title"),
            "deal_card_url": deal.get("card_url"),
            "deal_amount": float(deal.get("amount") or 0.0),
            "deal_stage_name": deal.get("stage_name"),
            "manager_id": deal.get("assigned_id"),
            "manager_name": deal.get("assigned_name"),
        }
        overdue_tasks.append(item)

        manager_id = str(deal.get("assigned_id") or "").strip()
        manager_key = manager_id or str(deal.get("assigned_name") or "").strip()
        manager_row = by_manager.setdefault(
            manager_key,
            {
                "manager_id": manager_id or None,
                "manager_name": deal.get("assigned_name") or "без ответственного",
                "count": 0,
                "deals": [],
                "max_days_overdue": 0,
            },
        )
        manager_row["count"] += 1
        manager_row["max_days_overdue"] = max(manager_row["max_days_overdue"], days_overdue)
        manager_row["deals"].append(
            {
                "deal_id": deal.get("id"),
                "deal_title": deal.get("title"),
                "deal_card_url": deal.get("card_url"),
                "task_title": item["task_title"],
                "deadline": deadline,
                "days_overdue": days_overdue,
            }
        )

    overdue_tasks.sort(key=lambda item: (int(item["days_overdue"]), float(item["deal_amount"])), reverse=True)
    manager_rows = sorted(
        by_manager.values(),
        key=lambda item: (int(item["count"]), int(item["max_days_overdue"])),
        reverse=True,
    )
    return overdue_tasks, manager_rows


def _build_deadline_reschedule_focus_tasks(
    tasks: list[dict[str, Any]],
    *,
    active_deals_by_id: dict[str, dict[str, Any]],
    now: datetime,
    task_status_map: dict[str, str],
) -> list[dict[str, Any]]:
    closed_statuses = _closed_task_statuses(task_status_map)
    items: list[dict[str, Any]] = []

    for task in tasks:
        if str(task.get("status") or "").strip() in closed_statuses:
            continue

        deadline_change_count = _extract_task_deadline_change_count(task)
        if deadline_change_count <= 2:
            continue

        linked_deals = [
            active_deals_by_id[deal_id]
            for deal_id in _extract_task_deal_ids(task)
            if deal_id in active_deals_by_id
        ]
        if not linked_deals:
            continue

        deal = sorted(linked_deals, key=lambda item: float(item.get("amount") or 0.0), reverse=True)[0]
        manager_id = str(deal.get("assigned_id") or "").strip()
        manager_name = str(deal.get("assigned_name") or "").strip()
        if not manager_id or not manager_name:
            continue

        deadline = _parse_datetime(task.get("deadline"))
        days_overdue = max(int((now - deadline).total_seconds() // 86400), 0) if deadline and deadline < now else 0
        deadline_changed_at = _extract_task_deadline_changed_at(task)
        last_shift_age_days = (
            max(int((now - deadline_changed_at).total_seconds() // 86400), 0)
            if deadline_changed_at is not None and deadline_changed_at <= now
            else 0
        )

        items.append(
            {
                "task_id": str(task.get("id") or "").strip(),
                "task_title": str(task.get("title") or "").strip() or "Без названия",
                "deadline": deadline,
                "days_overdue": days_overdue,
                "deadline_change_count": deadline_change_count,
                "deadline_changed_at": deadline_changed_at,
                "last_shift_age_days": last_shift_age_days,
                "deal_id": deal.get("id"),
                "deal_title": deal.get("title"),
                "deal_card_url": deal.get("card_url"),
                "deal_amount": float(deal.get("amount") or 0.0),
                "manager_id": manager_id,
                "manager_name": manager_name,
            }
        )

    items.sort(
        key=lambda item: (
            int(item.get("deadline_change_count") or 0),
            int(int(item.get("days_overdue") or 0) > 0),
            int(item.get("days_overdue") or 0) or int(item.get("last_shift_age_days") or 0),
            float(item.get("deal_amount") or 0.0),
        ),
        reverse=True,
    )
    return items


def _link_open_tasks_to_deals(
    deals: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    *,
    now: datetime,
    task_status_map: dict[str, str],
) -> None:
    if not deals or not tasks:
        return

    closed_statuses = _closed_task_statuses(task_status_map)
    tasks_by_deal_id: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        status = str(task.get("status") or "").strip()
        if status in closed_statuses:
            continue
        signal_at = _task_signal_at(task, now=now)
        if signal_at < now and _parse_datetime(task.get("deadline")) is not None:
            continue
        for deal_id in _extract_task_deal_ids(task):
            tasks_by_deal_id.setdefault(deal_id, []).append(task)

    for deal in deals:
        deal_id = str(deal.get("id") or "").strip()
        if not deal_id or not deal.get("missing_next_step"):
            continue
        linked_tasks = tasks_by_deal_id.get(deal_id) or []
        if not linked_tasks:
            continue
        best_task = sorted(
            linked_tasks,
            key=lambda item: (
                _task_signal_at(item, now=now),
                str(item.get("id") or "").strip(),
            ),
        )[0]
        deal["next_step_at"] = _task_signal_at(best_task, now=now)
        deal["next_step_subject"] = str(best_task.get("title") or "").strip() or None
        deal["next_step_source"] = "tasks.task.list"
        deal["next_step_activity_id"] = str(best_task.get("id") or "").strip() or None
        deal["next_step_provider_id"] = "TASKS_TASK"
        deal["next_step_provider_type_id"] = "TASK"
        deal["missing_next_step"] = False


def _normalize_deal(
    raw_deal: dict[str, Any],
    *,
    now: datetime,
    user_map: dict[str, str],
    stage_name_map: dict[str, str],
    deal_fields_meta: dict[str, Any] | None,
    source_name_map: dict[str, str],
    company_map: dict[str, str],
    contact_map: dict[str, str],
    department_heads: set[str],
    large_deal_amount: float,
    portal_base_url: str,
    timeline_comments_map: Mapping[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    deal_id = str(raw_deal.get("id") or raw_deal.get("ID") or "").strip()
    stage_id = str(raw_deal.get("stage_id") or raw_deal.get("STAGE_ID") or "").strip()
    stage_name = stage_name_map.get(stage_id) or _friendly_stage_name(stage_id, raw_deal.get("stage_description"))
    semantic_id = str(raw_deal.get("semantic_id") or raw_deal.get("STAGE_SEMANTIC_ID") or "").strip()
    created_at = _parse_datetime(raw_deal.get("created_at") or raw_deal.get("DATE_CREATE"))
    modified_at = _parse_datetime(raw_deal.get("updated_at") or raw_deal.get("DATE_MODIFY"))
    moved_at = _parse_datetime(raw_deal.get("moved_at") or raw_deal.get("MOVED_TIME"))
    last_activity_at = _parse_datetime(raw_deal.get("last_activity_at") or raw_deal.get("LAST_ACTIVITY_TIME"))
    last_communication_at = _parse_datetime(
        raw_deal.get("last_communication_at") or raw_deal.get("LAST_COMMUNICATION_TIME")
    )
    timeline_touch_at = _timeline_touch_at((timeline_comments_map or {}).get(deal_id) or [])
    if timeline_touch_at is not None and (
        last_communication_at is None or last_communication_at < timeline_touch_at
    ):
        last_communication_at = timeline_touch_at
    last_signal_at = last_communication_at or last_activity_at or modified_at or created_at
    last_communication_signal_at = last_communication_at or created_at
    inactive_days = (
        max(int((now - last_signal_at).total_seconds() // 86400), 0)
        if last_signal_at is not None
        else None
    )
    communication_gap_days = (
        max(int((now - last_communication_signal_at).total_seconds() // 86400), 0)
        if last_communication_signal_at is not None
        else None
    )
    today_created, yesterday_created = _today_flags(created_at, now)
    today_moved, yesterday_moved = _today_flags(moved_at, now)
    moved_in_last_week = bool(moved_at and moved_at >= (now - timedelta(days=7)))
    amount = _to_float(raw_deal.get("amount") or raw_deal.get("OPPORTUNITY"))
    probability = _to_float(raw_deal.get("probability") or raw_deal.get("PROBABILITY"))
    late_stage = _is_late_stage(stage_id, stage_name, probability)
    effective_probability = _effective_probability(
        probability,
        late_stage=late_stage,
        inactive_days=inactive_days,
    )
    won = _is_won_status(stage_id, stage_name, semantic_id)
    raw_lost = _is_lost_status(stage_id, stage_name, semantic_id)
    assigned_id = str(raw_deal.get("assigned_id") or raw_deal.get("ASSIGNED_BY_ID") or "").strip()
    relation_suffix = _company_contact_suffix(
        company_map,
        contact_map,
        raw_deal.get("company_id"),
        raw_deal.get("contact_id"),
    )
    title = str(raw_deal.get("title") or raw_deal.get("TITLE") or "").strip()
    if not title:
        title = f"Сделка {raw_deal.get('id') or raw_deal.get('ID') or ''}".strip()
    source_id = str(raw_deal.get("source_id") or raw_deal.get("SOURCE_ID") or "").strip()
    source_description = str(raw_deal.get("source_description") or raw_deal.get("SOURCE_DESCRIPTION") or "").strip()
    large_deal = amount >= float(large_deal_amount)
    leader_flag = _explicit_leader_flag(raw_deal.get("raw") if isinstance(raw_deal.get("raw"), dict) else raw_deal)

    raw_payload = raw_deal.get("raw") if isinstance(raw_deal.get("raw"), dict) else raw_deal
    next_step_at = _parse_datetime(raw_deal.get("next_step_at"))
    next_step_subject = str(raw_deal.get("next_step_subject") or "").strip() or None
    next_step_source = str(raw_deal.get("next_step_source") or "").strip() or None
    field_next_step_at, field_next_step_subject = _extract_next_step_from_deal_fields(
        raw_payload,
        deal_fields_meta=deal_fields_meta,
        now=now,
    )
    if field_next_step_at is not None and (
        next_step_at is None or (isinstance(next_step_at, datetime) and next_step_at < now)
    ):
        next_step_at = field_next_step_at
        next_step_subject = field_next_step_subject or next_step_subject
        next_step_source = "deal.field:meeting_date"
    missing_next_step = next_step_at is None
    lost_reason = (
        _extract_explicit_lost_reason(
            raw_payload,
            title=title,
            relation_suffix=relation_suffix,
            field_meta=deal_fields_meta,
        )
        if raw_lost
        else None
    )
    deferred = _is_deferred_status(stage_id, stage_name, semantic_id, reason=lost_reason)
    lost = raw_lost and not deferred
    closed = bool(raw_deal.get("closed")) or won or raw_lost or deferred

    return {
        "kind": "deal",
        "id": deal_id,
        "title": title,
        "card_url": build_deal_url(portal_base_url, deal_id),
        "assigned_id": assigned_id,
        "assigned_name": _assigned_name(user_map, assigned_id),
        "assigned_is_department_head": assigned_id in department_heads,
        "stage_id": stage_id,
        "stage_name": stage_name,
        "semantic_id": semantic_id,
        "amount": amount,
        "probability": probability,
        "effective_probability": effective_probability,
        "created_at": created_at,
        "modified_at": modified_at,
        "moved_at": moved_at,
        "last_activity_at": last_activity_at,
        "last_communication_at": last_communication_at,
        "timeline_touch_at": timeline_touch_at,
        "last_client_touch_at": last_communication_at,
        "last_signal_at": last_signal_at,
        "inactive_days": inactive_days,
        "communication_gap_days": communication_gap_days,
        "next_step_at": next_step_at,
        "next_step_subject": next_step_subject,
        "next_step_source": next_step_source,
        "next_step_activity_id": str(raw_deal.get("next_step_activity_id") or "").strip() or None,
        "next_step_provider_id": str(raw_deal.get("next_step_provider_id") or "").strip() or None,
        "next_step_provider_type_id": str(raw_deal.get("next_step_provider_type_id") or "").strip() or None,
        "next_step_supported": True,
        "missing_next_step": missing_next_step,
        "today_created": today_created,
        "yesterday_created": yesterday_created,
        "today_moved": today_moved,
        "yesterday_moved": yesterday_moved,
        "moved_in_last_week": moved_in_last_week,
        "meeting_today": False,
        "meeting_titles": [],
        "upcoming_meeting_at": None,
        "engaged_in_last_week": bool(
            isinstance(last_communication_at, datetime) and last_communication_at >= (now - timedelta(days=7))
        ),
        "active": not closed,
        "won": won,
        "lost": lost,
        "deferred": deferred,
        "late_stage": late_stage and not closed,
        "high_probability": (effective_probability >= 70.0) or (late_stage and effective_probability >= 55.0),
        "large_deal": large_deal,
        "leader_flag": leader_flag,
        "needs_leader": leader_flag or (large_deal and ((inactive_days or 0) >= 5 or late_stage)),
        "source_id": source_id or None,
        "source_name": source_name_map.get(source_id) or source_id or "Источник не указан",
        "source_description": source_description or None,
        "lost_reason": lost_reason,
        "company_id": str(raw_deal.get("company_id") or "").strip() or None,
        "contact_id": str(raw_deal.get("contact_id") or "").strip() or None,
        "relation_suffix": relation_suffix,
        "raw": raw_payload,
    }


def _normalize_lead(
    raw_lead: dict[str, Any],
    *,
    now: datetime,
    user_map: dict[str, str],
    company_map: dict[str, str],
    contact_map: dict[str, str],
    portal_base_url: str,
) -> dict[str, Any]:
    status_id = str(raw_lead.get("stage_id") or raw_lead.get("status_id") or raw_lead.get("STATUS_ID") or "").strip()
    status_name = _friendly_stage_name(status_id, raw_lead.get("stage_description") or raw_lead.get("STATUS_DESCRIPTION"))
    semantic_id = str(raw_lead.get("semantic_id") or raw_lead.get("STATUS_SEMANTIC_ID") or "").strip()
    created_at = _parse_datetime(raw_lead.get("created_at") or raw_lead.get("DATE_CREATE"))
    modified_at = _parse_datetime(raw_lead.get("updated_at") or raw_lead.get("DATE_MODIFY"))
    last_activity_at = _parse_datetime(raw_lead.get("last_activity_at") or raw_lead.get("LAST_ACTIVITY_TIME"))
    last_communication_at = _parse_datetime(
        raw_lead.get("last_communication_at") or raw_lead.get("LAST_COMMUNICATION_TIME")
    )
    last_signal_at = last_communication_at or last_activity_at or modified_at or created_at
    inactive_days = (
        max(int((now - last_signal_at).total_seconds() // 86400), 0)
        if last_signal_at is not None
        else None
    )
    today_created, yesterday_created = _today_flags(created_at, now)
    assigned_id = str(raw_lead.get("assigned_id") or raw_lead.get("ASSIGNED_BY_ID") or "").strip()
    qualified = _is_qualified_status(status_id, status_name, semantic_id)
    won = _is_won_status(status_id, status_name, semantic_id)
    lost = _is_lost_status(status_id, status_name, semantic_id)
    relation_suffix = _company_contact_suffix(
        company_map,
        contact_map,
        raw_lead.get("company_id"),
        raw_lead.get("contact_id"),
    )
    title = str(raw_lead.get("title") or raw_lead.get("TITLE") or raw_lead.get("NAME") or "").strip()
    if not title:
        title = f"Лид {raw_lead.get('id') or raw_lead.get('ID') or ''}".strip()

    next_step_at = last_communication_at or last_activity_at
    missing_next_step = next_step_at is None

    return {
        "kind": "lead",
        "id": str(raw_lead.get("id") or raw_lead.get("ID") or "").strip(),
        "title": title,
        "card_url": build_lead_url(portal_base_url, raw_lead.get("id") or raw_lead.get("ID")),
        "assigned_id": assigned_id,
        "assigned_name": _assigned_name(user_map, assigned_id),
        "status_id": status_id,
        "status_name": status_name,
        "semantic_id": semantic_id,
        "created_at": created_at,
        "modified_at": modified_at,
        "last_activity_at": last_activity_at,
        "last_communication_at": last_communication_at,
        "last_signal_at": last_signal_at,
        "inactive_days": inactive_days,
        "next_step_at": next_step_at,
        "next_step_supported": True,
        "missing_next_step": missing_next_step,
        "today_created": today_created,
        "yesterday_created": yesterday_created,
        "qualified": qualified,
        "won": won,
        "lost": lost,
        "active": not (won or lost),
        "company_id": str(raw_lead.get("company_id") or "").strip() or None,
        "contact_id": str(raw_lead.get("contact_id") or "").strip() or None,
        "relation_suffix": relation_suffix,
        "raw": raw_lead.get("raw") if isinstance(raw_lead.get("raw"), dict) else raw_lead,
    }


def analyze_pipeline(
    snapshot: dict[str, Any],
    *,
    now: datetime | None = None,
    large_deal_amount: float = 150000.0,
    inactivity_days: int = 5,
    stale_communication_days: int = 14,
    department_filter: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(MOSCOW_TZ)).astimezone(MOSCOW_TZ)

    limitations = list(snapshot.get("limitations") or [])
    if snapshot.get("source") == "not_configured":
        limitations.append("Bitrix CRM не настроен: отсутствует BITRIX_WEBHOOK_URL.")
    if not snapshot.get("next_step_source"):
        limitations.append("Следующий шаг не найден: нет подтверждённого источника next step в Bitrix.")
    portal_base_url = str(snapshot.get("portal_base_url") or "").strip()

    user_map = {
        user_id: _user_name(user)
        for user_id, user in (snapshot.get("responsibles") or {}).items()
        if str(user_id).strip()
    }
    company_map = {
        str(item.get("id") or "").strip(): str(item.get("title") or "").strip()
        for item in snapshot.get("companies") or []
        if str(item.get("id") or "").strip()
    }
    contact_map = {
        str(item.get("id") or "").strip(): str(item.get("full_name") or "").strip()
        for item in snapshot.get("contacts") or []
        if str(item.get("id") or "").strip()
    }
    department_heads = {
        str(item.get("head_user_id") or "").strip()
        for item in snapshot.get("departments") or []
        if str(item.get("head_user_id") or "").strip()
    }
    deal_stage_name_map = _status_name_map(snapshot.get("deal_stage_map") or [])
    deal_source_name_map = _source_name_map(snapshot.get("deal_source_map") or [])
    deal_fields_meta = dict(snapshot.get("deal_fields_meta") or {})
    meeting_stage_name_map = _status_name_map(snapshot.get("meeting_stage_map") or [])
    brief_stage_name_map = _status_name_map(snapshot.get("brief_stage_map") or [])
    timeline_comments_map = dict(snapshot.get("deal_timeline_comments") or {})

    recent_deals = _dedupe_entities(
        [
            _normalize_deal(
                raw_deal,
                now=now,
                user_map=user_map,
                stage_name_map=deal_stage_name_map,
                deal_fields_meta=deal_fields_meta,
                source_name_map=deal_source_name_map,
                company_map=company_map,
                contact_map=contact_map,
                department_heads=department_heads,
                large_deal_amount=large_deal_amount,
                portal_base_url=portal_base_url,
                timeline_comments_map=timeline_comments_map,
            )
            for raw_deal in snapshot.get("recent_deals") or []
        ]
    )
    active_deals = _dedupe_entities(
        [
            _normalize_deal(
                raw_deal,
                now=now,
                user_map=user_map,
                stage_name_map=deal_stage_name_map,
                deal_fields_meta=deal_fields_meta,
                source_name_map=deal_source_name_map,
                company_map=company_map,
                contact_map=contact_map,
                department_heads=department_heads,
                large_deal_amount=large_deal_amount,
                portal_base_url=portal_base_url,
                timeline_comments_map=timeline_comments_map,
            )
            for raw_deal in snapshot.get("active_deals") or []
        ]
    )
    active_deals = [deal for deal in active_deals if deal.get("active")]
    allowlist_user_ids = sales_allowlist_user_ids(department_filter)
    active_deals, excluded_active_deals = _filter_sales_owned_entities(
        active_deals,
        allowlist_user_ids=allowlist_user_ids,
        source="active_deals",
    )
    recent_deals, excluded_recent_deals = _filter_sales_owned_entities(
        recent_deals,
        allowlist_user_ids=allowlist_user_ids,
        source="recent_deals",
    )
    meetings = [
        _normalize_dynamic_item(
            item,
            now=now,
            user_map=user_map,
            stage_name_map=meeting_stage_name_map,
            portal_base_url=portal_base_url,
            entity_type_id=1048,
        )
        for item in snapshot.get("meetings") or []
    ]
    closed_deals = _dedupe_entities(
        [
            _normalize_deal(
                raw_deal,
                now=now,
                user_map=user_map,
                stage_name_map=deal_stage_name_map,
                deal_fields_meta=deal_fields_meta,
                source_name_map=deal_source_name_map,
                company_map=company_map,
                contact_map=contact_map,
                department_heads=department_heads,
                large_deal_amount=large_deal_amount,
                portal_base_url=portal_base_url,
                timeline_comments_map=timeline_comments_map,
            )
            for raw_deal in snapshot.get("closed_deals") or []
        ]
    )
    closed_deals, excluded_closed_deals = _filter_sales_owned_entities(
        closed_deals,
        allowlist_user_ids=allowlist_user_ids,
        source="closed_deals",
    )
    recent_leads: list[dict[str, Any]] = []
    active_leads: list[dict[str, Any]] = []
    recent_leads, excluded_recent_leads = _filter_sales_owned_entities(
        recent_leads,
        allowlist_user_ids=allowlist_user_ids,
        source="recent_leads",
    )
    active_leads, excluded_active_leads = _filter_sales_owned_entities(
        active_leads,
        allowlist_user_ids=allowlist_user_ids,
        source="active_leads",
    )
    scoped_deal_ids = {
        str(item.get("id") or "").strip()
        for item in active_deals + recent_deals + closed_deals
        if str(item.get("id") or "").strip()
    }
    meetings, excluded_meetings = _filter_sales_related_dynamic_items(
        meetings,
        allowlist_user_ids=allowlist_user_ids,
        scoped_deal_ids=scoped_deal_ids,
        source="meetings",
    )
    conducted_meetings = [
        _normalize_dynamic_item(
            item,
            now=now,
            user_map=user_map,
            stage_name_map=meeting_stage_name_map,
            portal_base_url=portal_base_url,
            entity_type_id=1048,
        )
        for item in snapshot.get("conducted_meetings") or []
    ]
    conducted_meetings, excluded_conducted_meetings = _filter_sales_related_dynamic_items(
        conducted_meetings,
        allowlist_user_ids=allowlist_user_ids,
        scoped_deal_ids=scoped_deal_ids,
        source="conducted_meetings",
    )
    conducted_meeting_ids = {str(item.get("id") or "").strip() for item in conducted_meetings if str(item.get("id") or "").strip()}
    planned_meetings = [item for item in meetings if str(item.get("id") or "").strip() not in conducted_meeting_ids]
    _link_planned_meetings_to_deals(active_deals, planned_meetings, now=now)
    accepted_briefs = [
        _normalize_dynamic_item(
            item,
            now=now,
            user_map=user_map,
            stage_name_map=brief_stage_name_map,
            portal_base_url=portal_base_url,
            entity_type_id=1056,
        )
        for item in snapshot.get("accepted_briefs") or []
    ]
    accepted_briefs, excluded_accepted_briefs = _filter_sales_related_dynamic_items(
        accepted_briefs,
        allowlist_user_ids=allowlist_user_ids,
        scoped_deal_ids=scoped_deal_ids,
        source="accepted_briefs",
    )

    postponed_deals_now = [
        deal
        for deal in closed_deals
        if deal.get("deferred")
    ]
    postponed_deals_yesterday = [
        deal
        for deal in postponed_deals_now
        if deal.get("deferred") and deal.get("yesterday_moved")
    ]
    lost_deals_yesterday = [
        deal
        for deal in closed_deals
        if deal.get("lost") and deal.get("yesterday_moved") and str(deal.get("lost_reason") or "").strip()
    ]
    new_deals_yesterday = sorted(
        [
            deal
            for deal in active_deals
            if deal.get("yesterday_moved") and _is_brief_prep_deal(deal)
        ],
        key=lambda item: (
            _parse_datetime(item.get("moved_at")) or datetime.min.replace(tzinfo=MOSCOW_TZ),
            float(item.get("amount") or 0.0),
        ),
        reverse=True,
    )
    source_stats_yesterday = _aggregate_sources(new_deals_yesterday)
    deals_without_next_step = [deal for deal in active_deals if deal.get("missing_next_step")]
    hot_stage_deals = [
        deal
        for deal in active_deals
        if _is_hot_stage_deal(deal)
    ]
    stale_communication_deals = [
        deal
        for deal in active_deals
        if int(deal.get("communication_gap_days") or 0) >= int(stale_communication_days)
        and not isinstance(deal.get("upcoming_meeting_at"), datetime)
    ]
    moving_deals = [
        deal
        for deal in active_deals
        if int(deal.get("inactive_days") or 0) < int(inactivity_days)
    ]
    active_deals_by_id = {
        str(deal.get("id") or "").strip(): deal
        for deal in active_deals
        if str(deal.get("id") or "").strip()
    }
    overdue_tasks, overdue_tasks_by_manager = _build_overdue_task_stats(
        list(snapshot.get("tasks") or []),
        active_deals_by_id=active_deals_by_id,
        now=now,
        task_status_map=dict(snapshot.get("task_status_map") or {}),
    )
    overdue_task_deal_ids = {
        str(item.get("deal_id") or "").strip()
        for item in overdue_tasks
        if str(item.get("deal_id") or "").strip()
    }
    deadline_reschedule_focus_tasks = _build_deadline_reschedule_focus_tasks(
        list(snapshot.get("tasks") or []),
        active_deals_by_id=active_deals_by_id,
        now=now,
        task_status_map=dict(snapshot.get("task_status_map") or {}),
    )
    _link_open_tasks_to_deals(
        active_deals,
        list(snapshot.get("tasks") or []),
        now=now,
        task_status_map=dict(snapshot.get("task_status_map") or {}),
    )
    deals_without_next_step = [deal for deal in active_deals if deal.get("missing_next_step")]

    stage_stats = _build_stage_stats(active_deals)
    owner_stats = _build_owner_stats(active_deals)

    metrics = {
        "new_deals_today": sum(
            1
            for deal in active_deals
            if deal.get("today_moved") and _is_brief_prep_deal(deal)
        ),
        "new_deals_yesterday": len(new_deals_yesterday),
        "conducted_meetings_today": sum(1 for item in conducted_meetings if item.get("today_moved")),
        "conducted_meetings_yesterday": sum(1 for item in conducted_meetings if item.get("yesterday_moved")),
        "accepted_briefs_today": sum(1 for item in accepted_briefs if item.get("today_moved")),
        "accepted_briefs_yesterday": sum(1 for item in accepted_briefs if item.get("yesterday_moved")),
        "postponed_deals_yesterday": len(postponed_deals_yesterday),
        "postponed_deals_yesterday_amount": sum(float(deal.get("amount") or 0.0) for deal in postponed_deals_yesterday),
        "postponed_deals_now": len(postponed_deals_now),
        "postponed_deals_now_amount": sum(float(deal.get("amount") or 0.0) for deal in postponed_deals_now),
        "lost_deals_yesterday": len(lost_deals_yesterday),
        "lost_deals_yesterday_amount": sum(float(deal.get("amount") or 0.0) for deal in lost_deals_yesterday),
        "deals_in_work": len(active_deals),
        "moving_deals": len(moving_deals),
        "moving_deals_last_week": sum(
            1 for deal in active_deals if deal.get("moved_in_last_week") or deal.get("engaged_in_last_week")
        ),
        "stagnant_deals_last_week": sum(
            1 for deal in active_deals if not deal.get("moved_in_last_week") and not deal.get("engaged_in_last_week")
        ),
        "pipeline_amount": sum(float(deal.get("amount") or 0.0) for deal in active_deals),
        "hot_stage_deals": len(hot_stage_deals),
        "hot_stage_amount": sum(float(deal.get("amount") or 0.0) for deal in hot_stage_deals),
        "high_probability_deals": sum(1 for deal in active_deals if deal.get("high_probability")),
        "high_probability_amount": sum(
            float(deal.get("amount") or 0.0)
            for deal in active_deals
            if deal.get("high_probability")
        ),
        "deals_without_next_step": len(deals_without_next_step),
        "deals_without_next_step_amount": sum(float(deal.get("amount") or 0.0) for deal in deals_without_next_step),
        "deals_without_next_step_late_stage": sum(1 for deal in deals_without_next_step if deal.get("late_stage")),
        "stuck_deals": sum(1 for deal in active_deals if int(deal.get("inactive_days") or 0) >= int(inactivity_days)),
        "stale_communication_deals": len(stale_communication_deals),
        "stale_communication_amount": sum(float(deal.get("amount") or 0.0) for deal in stale_communication_deals),
        "overdue_deal_tasks": len(overdue_tasks),
        "overdue_deal_task_deals": len(overdue_task_deal_ids),
        "overdue_deal_task_amount": sum(
            float(active_deals_by_id[deal_id].get("amount") or 0.0)
            for deal_id in overdue_task_deal_ids
            if deal_id in active_deals_by_id
        ),
        "expected_forecast_amount": sum(
            float(deal.get("amount") or 0.0) * max(float(deal.get("effective_probability") or 0.0), 0.0) / 100.0
            for deal in active_deals
        ),
    }

    return {
        "now": now,
        "timezone": "Europe/Moscow",
        "source": snapshot.get("source") or "unknown",
        "portal_base_url": portal_base_url,
        "limitations": list(dict.fromkeys(limitations)),
        "users": user_map,
        "deals": recent_deals,
        "active_deals": active_deals,
        "closed_deals": closed_deals,
        "postponed_deals_now": postponed_deals_now,
        "postponed_deals_yesterday": postponed_deals_yesterday,
        "lost_deals_yesterday": lost_deals_yesterday,
        "new_deals_yesterday": new_deals_yesterday,
        "new_deal_sources_yesterday": source_stats_yesterday,
        "leads": recent_leads,
        "active_leads": active_leads,
        "meetings": meetings,
        "conducted_meetings": conducted_meetings,
        "accepted_briefs": accepted_briefs,
        "hot_stage_deals": sorted(
            hot_stage_deals,
            key=lambda item: float(item.get("amount") or 0.0),
            reverse=True,
        ),
        "deals_without_next_step_items": sorted(
            deals_without_next_step,
            key=lambda item: (
                int(bool(item.get("late_stage"))),
                float(item.get("amount") or 0.0),
                int(item.get("inactive_days") or 0),
            ),
            reverse=True,
        ),
        "stale_communication_deals": sorted(
            stale_communication_deals,
            key=lambda item: (int(item.get("communication_gap_days") or 0), float(item.get("amount") or 0.0)),
            reverse=True,
        ),
        "overdue_deal_tasks": overdue_tasks,
        "overdue_deal_tasks_by_manager": overdue_tasks_by_manager,
        "deadline_reschedule_focus_tasks": deadline_reschedule_focus_tasks,
        "stage_stats": stage_stats,
        "owner_stats": owner_stats,
        "metrics": metrics,
        "sales_scope": _scope_summary(
            department_filter=department_filter,
            excluded_entities={
                "active_deals": excluded_active_deals,
                "recent_deals": excluded_recent_deals,
                "closed_deals": excluded_closed_deals,
                "recent_leads": excluded_recent_leads,
                "active_leads": excluded_active_leads,
                "meetings": excluded_meetings,
                "conducted_meetings": excluded_conducted_meetings,
                "accepted_briefs": excluded_accepted_briefs,
            },
        ),
    }
