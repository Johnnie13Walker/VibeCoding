"""Live reconcile сделок Bitrix24 в read-only backup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo

from belberry.bitrix24.providers.bitrix_oauth import BitrixOAuthError

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
DEAL_ENTITY_TYPE_ID = 2

ACTIVITY_SELECT_DEFAULT = (
    "ID",
    "OWNER_ID",
    "OWNER_TYPE_ID",
    "TYPE_ID",
    "PROVIDER_ID",
    "PROVIDER_TYPE_ID",
    "SUBJECT",
    "DESCRIPTION",
    "CREATED",
    "LAST_UPDATED",
    "DEADLINE",
    "START_TIME",
    "END_TIME",
    "COMPLETED",
    "RESPONSIBLE_ID",
    "AUTHOR_ID",
    "COMMUNICATIONS",
    "SETTINGS",
)

READ_METHODS = (
    "crm.deal.get",
    "crm.deal.productrows.get",
    "crm.deal.contact.items.get",
    "crm.activity.list",
    "crm.timeline.comment.list",
    "crm.category.list",
    "crm.status.list",
)


class BitrixReadClient(Protocol):
    call_method: Callable[..., Any]
    call_payload: Callable[..., dict[str, Any]]
    list_method: Callable[..., list[dict[str, Any]]]


@dataclass(frozen=True)
class ReconcileSettings:
    portal_base_url: str
    activity_select: tuple[str, ...] = ACTIVITY_SELECT_DEFAULT


class BitrixReconcileError(RuntimeError):
    """Ошибка read-only reconcile, которая делает merge decision небезопасным."""


def _now_msk() -> str:
    return datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")


def _string_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.isdigit() else ""


def _text_id(value: Any) -> str:
    return str(value or "").strip()


def _normalize_deal_ids(deal_ids: Sequence[Any], *, target_id: str) -> tuple[str, ...]:
    target = _string_id(target_id)
    if not target:
        raise ValueError("target_id must be a numeric id")
    ordered: list[str] = []
    for raw in (target, *deal_ids):
        deal_id = _string_id(raw)
        if deal_id and deal_id not in ordered:
            ordered.append(deal_id)
    if len(ordered) < 2:
        raise ValueError("deal_ids must contain target and at least one duplicate")
    return tuple(ordered)


def _error_payload(error: Exception) -> dict[str, Any]:
    if isinstance(error, BitrixOAuthError):
        return error.to_payload()
    return {"ok": False, "status": "error", "message": str(error or "unknown error")}


def _read_optional_status_list(oauth: BitrixReadClient, entity_id: str) -> list[Any]:
    try:
        result = oauth.call_method("crm.status.list", {"filter": {"ENTITY_ID": entity_id}}, default=[])
    except Exception:  # noqa: BLE001
        return []
    return result if isinstance(result, list) else []


def _read_required_call_list(
    oauth: BitrixReadClient,
    method: str,
    params: Mapping[str, Any],
    *,
    deal_id: str,
) -> list[Any]:
    try:
        result = oauth.call_method(method, params, default=[])
    except Exception as error:  # noqa: BLE001
        raise BitrixReconcileError(f"child read failed: {method} for deal {deal_id}") from error
    if not isinstance(result, list):
        raise BitrixReconcileError(f"child read returned non-list: {method} for deal {deal_id}")
    return result


def _read_required_list_method(
    oauth: BitrixReadClient,
    method: str,
    params: Mapping[str, Any],
    *,
    deal_id: str,
) -> list[dict[str, Any]]:
    try:
        result = oauth.list_method(method, params)
    except Exception as error:  # noqa: BLE001
        raise BitrixReconcileError(f"child read failed: {method} for deal {deal_id}") from error
    if not isinstance(result, list):
        raise BitrixReconcileError(f"child read returned non-list: {method} for deal {deal_id}")
    return result


def _category_map(oauth: BitrixReadClient) -> dict[str, str]:
    try:
        payload = oauth.call_payload("crm.category.list", {"entityTypeId": DEAL_ENTITY_TYPE_ID}, default={})
    except Exception:  # noqa: BLE001
        return {}
    raw = payload.get("result") if isinstance(payload, Mapping) else {}
    categories = raw.get("categories") if isinstance(raw, Mapping) else raw
    if not isinstance(categories, list):
        return {}
    result: dict[str, str] = {}
    for item in categories:
        if not isinstance(item, Mapping):
            continue
        category_id = _string_id(item.get("id") or item.get("ID"))
        name = str(item.get("name") or item.get("NAME") or "").strip()
        if category_id:
            result[category_id] = name or category_id
    return result


def _status_map(oauth: BitrixReadClient, entity_id: str) -> dict[str, str]:
    items = _read_optional_status_list(oauth, entity_id)
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        status_id = _text_id(item.get("STATUS_ID") or item.get("ID"))
        name = str(item.get("NAME") or item.get("TITLE") or "").strip()
        if status_id:
            result[status_id] = name or status_id
    return result


def _stage_entity_id(category_id: str) -> str:
    return f"DEAL_STAGE_{category_id}" if category_id and category_id != "0" else "DEAL_STAGE"


def _deal_url(deal_id: str, *, portal_base_url: str) -> str:
    return f"{portal_base_url.rstrip('/')}/crm/deal/details/{deal_id}/"


def _deal_summary(
    deal: Mapping[str, Any],
    *,
    categories: Mapping[str, str],
    stages: Mapping[str, Mapping[str, str]],
    sources: Mapping[str, str],
    portal_base_url: str,
) -> dict[str, Any]:
    deal_id = _string_id(deal.get("ID"))
    category_id = _string_id(deal.get("CATEGORY_ID"))
    stage_id = _text_id(deal.get("STAGE_ID"))
    source_id = _text_id(deal.get("SOURCE_ID"))
    return {
        "id": deal_id,
        "title": str(deal.get("TITLE") or "").strip(),
        "category_id": category_id,
        "category_name": categories.get(category_id, category_id),
        "stage_id": stage_id,
        "stage_name": stages.get(category_id, {}).get(stage_id, stage_id),
        "source_id": source_id,
        "source_name": sources.get(source_id, source_id),
        "assigned_by_id": _string_id(deal.get("ASSIGNED_BY_ID")),
        "company_id": _string_id(deal.get("COMPANY_ID")),
        "contact_id": _string_id(deal.get("CONTACT_ID")),
        "date_create": str(deal.get("DATE_CREATE") or "").strip(),
        "date_modify": str(deal.get("DATE_MODIFY") or "").strip(),
        "url": _deal_url(deal_id, portal_base_url=portal_base_url),
    }


def _deal_backup(oauth: BitrixReadClient, deal_id: str, *, settings: ReconcileSettings) -> dict[str, Any]:
    try:
        deal = oauth.call_method("crm.deal.get", {"id": deal_id}, default={})
    except Exception as error:  # noqa: BLE001
        return {"id": deal_id, "exists": False, "deal": {}, "error": _error_payload(error)}
    if not isinstance(deal, Mapping) or not deal:
        return {"id": deal_id, "exists": False, "deal": deal}

    return {
        "id": deal_id,
        "exists": True,
        "deal": dict(deal),
        "product_rows": _read_required_call_list(
            oauth,
            "crm.deal.productrows.get",
            {"id": deal_id},
            deal_id=deal_id,
        ),
        "contacts": _read_required_call_list(
            oauth,
            "crm.deal.contact.items.get",
            {"id": deal_id},
            deal_id=deal_id,
        ),
        "activities": _read_required_list_method(
            oauth,
            "crm.activity.list",
            {
                "filter": {"OWNER_TYPE_ID": DEAL_ENTITY_TYPE_ID, "OWNER_ID": deal_id},
                "order": {"CREATED": "ASC"},
                "select": settings.activity_select,
            },
            deal_id=deal_id,
        ),
        "timeline_comments": _read_required_call_list(
            oauth,
            "crm.timeline.comment.list",
            {
                "filter": {"ENTITY_TYPE": "deal", "ENTITY_ID": deal_id},
                "order": {"CREATED": "ASC"},
            },
            deal_id=deal_id,
        ),
    }


def crm_methods_used() -> tuple[str, ...]:
    """Декларация read-only Bitrix methods для audit/documentation."""
    return READ_METHODS


def live_reconcile(
    *,
    oauth: BitrixReadClient,
    deal_ids: Sequence[str],
    target_id: str,
    settings: ReconcileSettings,
) -> dict[str, Any]:
    """Возвращает read-only backup сделок для policy/risk/dry-run."""
    ordered_ids = _normalize_deal_ids(deal_ids, target_id=target_id)
    target = ordered_ids[0]
    categories = _category_map(oauth)
    category_ids = set(categories.keys())
    category_ids.add("0")
    sources = _status_map(oauth, "SOURCE")
    stages = {
        category_id: _status_map(oauth, _stage_entity_id(category_id))
        for category_id in sorted(category_ids, key=int)
    }
    deals = [_deal_backup(oauth, deal_id, settings=settings) for deal_id in ordered_ids]
    summaries = [
        _deal_summary(
            item.get("deal") if isinstance(item.get("deal"), Mapping) else {},
            categories=categories,
            stages=stages,
            sources=sources,
            portal_base_url=settings.portal_base_url,
        )
        for item in deals
        if item.get("exists")
    ]
    return {
        "created_at_msk": _now_msk(),
        "target_id": target,
        "entity_ids_for_merge": list(ordered_ids),
        "summaries": summaries,
        "deals": deals,
    }
