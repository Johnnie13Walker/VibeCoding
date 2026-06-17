"""Безопасная сборка Bitrix24-ссылок для Telegram-отчётов."""

from __future__ import annotations

from urllib.parse import urlencode


def _normalize_portal_base_url(portal_base_url: str | None) -> str:
    return str(portal_base_url or "").strip().rstrip("/")


def _normalize_id(value: object) -> str:
    return str(value or "").strip()


def build_deal_url(portal_base_url: str | None, deal_id: object) -> str:
    base = _normalize_portal_base_url(portal_base_url)
    entity_id = _normalize_id(deal_id)
    if not base or not entity_id:
        return ""
    return f"{base}/crm/deal/details/{entity_id}/"


def build_lead_url(portal_base_url: str | None, lead_id: object) -> str:
    base = _normalize_portal_base_url(portal_base_url)
    entity_id = _normalize_id(lead_id)
    if not base or not entity_id:
        return ""
    return f"{base}/crm/lead/details/{entity_id}/"


def build_dynamic_item_url(
    portal_base_url: str | None,
    entity_type_id: object,
    item_id: object,
    *,
    category_id: object | None = None,
) -> str:
    base = _normalize_portal_base_url(portal_base_url)
    type_id = _normalize_id(entity_type_id)
    entity_id = _normalize_id(item_id)
    if not base or not type_id or not entity_id:
        return ""
    query = urlencode({"categoryId": str(category_id).strip()}) if str(category_id or "").strip() else ""
    suffix = f"?{query}" if query else ""
    return f"{base}/crm/type/{type_id}/details/{entity_id}/{suffix}"
