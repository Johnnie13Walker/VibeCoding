"""Тонкий adapter Bitrix для Sales Copilot."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

from cloudbot.providers.bitrix.bitrix_app_auth import BitrixAPIError as BitrixAppAuthError, BitrixAppAuth
from cloudbot.providers.bitrix_provider import BitrixAPIError, BitrixProvider

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
SALES_DEAL_CATEGORY_ID = 10
MEETING_ENTITY_TYPE_ID = 1048
MEETING_CATEGORY_ID = 24
BRIEF_ENTITY_TYPE_ID = 1056
BRIEF_CATEGORY_ID = 28
MEETING_DONE_STAGE_NAME = "Встреча проведена"
BRIEF_ACCEPTED_STAGE_NAME = "Бриф принят производством"
DEAL_SELECT_FIELDS = [
    "ID",
    "TITLE",
    "ASSIGNED_BY_ID",
    "DATE_CREATE",
    "DATE_MODIFY",
    "MOVED_TIME",
    "LAST_ACTIVITY_TIME",
    "LAST_COMMUNICATION_TIME",
    "STAGE_ID",
    "STAGE_SEMANTIC_ID",
    "OPPORTUNITY",
    "PROBABILITY",
    "CLOSED",
    "COMPANY_ID",
    "CONTACT_ID",
    "CATEGORY_ID",
    "IS_NEW",
    "SOURCE_ID",
    "SOURCE_DESCRIPTION",
    "COMMENTS",
    "UF_*",
]
LEAD_SELECT_FIELDS = [
    "ID",
    "TITLE",
    "NAME",
    "STATUS_ID",
    "STATUS_DESCRIPTION",
    "STATUS_SEMANTIC_ID",
    "ASSIGNED_BY_ID",
    "DATE_CREATE",
    "DATE_MODIFY",
    "MOVED_TIME",
    "LAST_ACTIVITY_TIME",
    "LAST_COMMUNICATION_TIME",
    "OPPORTUNITY",
    "COMPANY_ID",
    "CONTACT_ID",
    "IS_RETURN_CUSTOMER",
]
COMPANY_SELECT_FIELDS = [
    "ID",
    "TITLE",
    "ASSIGNED_BY_ID",
    "DATE_CREATE",
    "DATE_MODIFY",
    "LAST_ACTIVITY_TIME",
]
CONTACT_SELECT_FIELDS = [
    "ID",
    "NAME",
    "LAST_NAME",
    "SECOND_NAME",
    "ASSIGNED_BY_ID",
    "COMPANY_ID",
    "DATE_CREATE",
    "DATE_MODIFY",
    "LAST_ACTIVITY_TIME",
]
ACTIVITY_SELECT_FIELDS = [
    "ID",
    "TYPE_ID",
    "OWNER_ID",
    "OWNER_TYPE_ID",
    "PROVIDER_ID",
    "PROVIDER_TYPE_ID",
    "SUBJECT",
    "RESPONSIBLE_ID",
    "AUTHOR_ID",
    "CREATED",
    "LAST_UPDATED",
    "DEADLINE",
    "START_TIME",
    "END_TIME",
    "COMPLETED",
    "DIRECTION",
    "COMMUNICATIONS",
    "SETTINGS",
    "DESCRIPTION",
]
DYNAMIC_ITEM_SELECT_FIELDS = [
    "id",
    "title",
    "createdTime",
    "updatedTime",
    "movedTime",
    "categoryId",
    "stageId",
    "assignedById",
    "lastActivityTime",
    "lastCommunicationTime",
    "begindate",
    "closedate",
    "parentId2",
    "uf*",
]

BITRIX_RUNTIME_ERRORS = (BitrixAPIError, BitrixAppAuthError)
BITRIX_OAUTH_HOSTS = {
    "oauth.bitrix24.tech",
    "oauth.bitrix.info",
}


def _to_moscow_iso(dt: datetime) -> str:
    return dt.astimezone(MOSCOW_TZ).replace(microsecond=0).isoformat()


def _normalize_datetime(value: Any) -> str | None:
    raw = str(value or "").strip()
    return raw or None


def _normalize_active_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().upper()
    if not raw:
        return True
    return raw in {"Y", "YES", "TRUE", "1"}


def _duration_seconds(start_value: Any, end_value: Any) -> int:
    start_raw = str(start_value or "").strip()
    end_raw = str(end_value or "").strip()
    if not start_raw or not end_raw:
        return 0

    try:
        start_dt = datetime.fromisoformat(start_raw)
        end_dt = datetime.fromisoformat(end_raw)
    except ValueError:
        return 0

    return max(int((end_dt - start_dt).total_seconds()), 0)


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("items", "tasks", "events"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def _dedupe_ids(ids: Sequence[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in ids:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _chunked(items: Sequence[str], size: int) -> list[list[str]]:
    return [list(items[index : index + size]) for index in range(0, len(items), size)]


def _normalize_id_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        return _dedupe_ids(value)
    raw = str(value).strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    parts = [item.strip() for item in raw.replace(";", ",").split(",")]
    return _dedupe_ids(parts)


def _normalize_portal_base_candidate(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    hostname = str(parsed.hostname or "").strip().lower()
    if not parsed.scheme or not parsed.netloc or not hostname:
        return ""
    if hostname in BITRIX_OAUTH_HOSTS or hostname.startswith("oauth."):
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")


def _flatten_query_params(prefix: str, value: Any) -> list[tuple[str, str]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        items: list[tuple[str, str]] = []
        for key, nested_value in value.items():
            key_name = f"{prefix}[{key}]" if prefix else str(key)
            items.extend(_flatten_query_params(key_name, nested_value))
        return items
    if isinstance(value, (list, tuple, set)):
        items: list[tuple[str, str]] = []
        for nested_value in value:
            items.extend(_flatten_query_params(f"{prefix}[]", nested_value))
        return items
    return [(prefix, str(value))]


def _next_step_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("deadline") or ""),
        str(item.get("start_time") or ""),
        str(item.get("id") or ""),
    )


def _build_next_step_payload(deal_id: str, activities: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not activities:
        return None
    next_item = sorted(activities, key=_next_step_sort_key)[0]
    return {
        "next_step_at": next_item.get("deadline") or next_item.get("start_time"),
        "next_step_subject": next_item.get("subject"),
        "next_step_source": "crm.activity.list",
        "next_step_activity_id": next_item.get("id"),
        "next_step_provider_id": next_item.get("provider_id"),
        "next_step_provider_type_id": next_item.get("provider_type_id"),
        "next_step_type_id": next_item.get("type_id"),
    }


class BitrixSalesAdapter:
    """Нормализованный слой чтения данных из Bitrix через безопасный provider."""

    def __init__(
        self,
        provider: BitrixProvider | None = None,
        *,
        app_auth: BitrixAppAuth | None = None,
    ) -> None:
        self.provider = provider or BitrixProvider.from_env()
        self.app_auth = app_auth or BitrixAppAuth.from_env()

    @classmethod
    def from_env(cls, env: Mapping[str, Any] | None = None) -> "BitrixSalesAdapter":
        return cls(
            BitrixProvider.from_env(env=env),
            app_auth=BitrixAppAuth.from_env(env=env),
        )

    def is_configured(self) -> bool:
        return self.provider.is_configured() or self.app_auth.is_configured()

    def sales_read_mode(self) -> str:
        if self.provider.mode() == "fixture":
            return "fixture"
        if self.app_auth.is_configured():
            return "app_oauth"
        return self.provider.mode()

    def portal_base_url(self) -> str:
        portal_base = _normalize_portal_base_candidate(self.provider.portal_base_url())
        if portal_base:
            return portal_base
        try:
            state = self.app_auth.load_state()
        except BITRIX_RUNTIME_ERRORS:
            return ""
        client_endpoint_base = _normalize_portal_base_candidate(state.client_endpoint)
        if client_endpoint_base:
            return client_endpoint_base
        if state.domain:
            domain_base = _normalize_portal_base_candidate(state.domain)
            if domain_base:
                return domain_base
        return ""

    def _call_list_page(
        self,
        method: str,
        *,
        fixture_key: str,
        params: Mapping[str, Any] | None = None,
        limit: int | None = None,
        use_sales_app: bool = False,
    ) -> list[dict[str, Any]]:
        if use_sales_app and self.sales_read_mode() == "app_oauth":
            return self.app_auth.list_method(method, params=params, limit=limit)

        payload = self.provider.call_method(
            method,
            params=params,
            fixture_key=fixture_key,
            default=[],
        )
        return _extract_items(payload)

    def _normalize_status_name(self, value: Any) -> str:
        return str(value or "").strip().replace("ё", "е").lower()

    def _get_status_map(self, entity_id: str) -> list[dict[str, Any]]:
        if self.sales_read_mode() == "app_oauth":
            items = self.app_auth.list_method(
                "crm.status.list",
                params={"filter": {"ENTITY_ID": entity_id}},
            )
            return [item for item in items if isinstance(item, dict)]

        payload = self.provider.call_method("crm.status.list", params={"filter": {"ENTITY_ID": entity_id}}, default=[])
        items = payload if isinstance(payload, list) else []
        return [item for item in items if isinstance(item, dict)]

    def _resolve_status_id(self, entity_id: str, stage_name: str) -> str | None:
        probe = self._normalize_status_name(stage_name)
        for item in self._get_status_map(entity_id):
            if self._normalize_status_name(item.get("NAME")) == probe:
                return str(item.get("STATUS_ID") or "").strip() or None
        return None

    def get_profile(self) -> dict[str, Any]:
        if self.sales_read_mode() == "app_oauth":
            raw_payload = self.app_auth.call_method("user.current", default={})
            raw = raw_payload if isinstance(raw_payload, dict) else {}
        else:
            raw = self.provider.get_profile()
        return {
            "id": str(raw.get("ID") or raw.get("id") or "").strip(),
            "name": str(raw.get("NAME") or raw.get("name") or "").strip(),
            "last_name": str(raw.get("LAST_NAME") or raw.get("last_name") or "").strip(),
            "email": str(raw.get("EMAIL") or raw.get("email") or "").strip() or None,
            "admin": str(raw.get("ADMIN") or raw.get("IS_ADMIN") or "").strip(),
            "raw": raw,
        }

    def _list_users_raw(self, *, limit: int | None = None, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        if self.sales_read_mode() == "app_oauth":
            return self.app_auth.list_method("user.get", params=params, limit=limit)
        return self.provider.list_users(limit=limit, params=params)

    def _list_departments_raw(self) -> list[dict[str, Any]]:
        if self.sales_read_mode() == "app_oauth":
            return self.app_auth.list_method("department.get")
        return self.provider.list_departments()

    def _normalize_user_item(self, item: dict[str, Any]) -> dict[str, Any]:
        department_ids = _normalize_id_list(
            item.get("UF_DEPARTMENT")
            or item.get("uf_department")
            or item.get("department_ids")
        )
        return {
            "id": str(item.get("ID") or item.get("id") or "").strip(),
            "name": str(item.get("NAME") or item.get("name") or "").strip(),
            "last_name": str(item.get("LAST_NAME") or item.get("last_name") or "").strip(),
            "full_name": " ".join(
                part
                for part in (
                    str(item.get("LAST_NAME") or item.get("last_name") or "").strip(),
                    str(item.get("NAME") or item.get("name") or "").strip(),
                    str(item.get("SECOND_NAME") or item.get("second_name") or "").strip(),
                )
                if part
            ).strip(),
            "email": str(item.get("EMAIL") or item.get("email") or "").strip() or None,
            "position": str(item.get("WORK_POSITION") or item.get("work_position") or "").strip() or None,
            "active": _normalize_active_flag(item.get("ACTIVE") if "ACTIVE" in item else item.get("active")),
            "department_ids": department_ids,
            "raw": item,
        }

    def get_users(
        self,
        limit: int = 200,
        *,
        user_ids: Sequence[Any] | None = None,
        department_ids: Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        ids = _dedupe_ids(user_ids or [])
        dept_ids = _dedupe_ids(department_ids or [])
        users_by_id: dict[str, dict[str, Any]] = {}

        if ids and self.provider.mode() == "fixture":
            for item in self.provider.list_users(limit=max(limit, len(ids) + 20), params=None):
                normalized = self._normalize_user_item(item)
                user_id = str(normalized.get("id") or "").strip()
                if user_id and user_id in ids:
                    users_by_id[user_id] = normalized
            rows = [users_by_id[user_id] for user_id in ids if user_id in users_by_id]
            if dept_ids:
                rows = [
                    user
                    for user in rows
                    if set(user.get("department_ids") or []).intersection(dept_ids)
                ]
            return rows

        if ids:
            # В live Belberry bulk FILTER[ID] для user.get периодически возвращает пустой список.
            # Для критичного manager-resolve используем малые чанки по одному ID: это стабильнее,
            # а уникальных ответственных в sales snapshot немного.
            for chunk in _chunked(ids[:limit], 1):
                chunk_params = {"FILTER": {"ID": chunk}}
                for item in self._list_users_raw(limit=1, params=chunk_params):
                    normalized = self._normalize_user_item(item)
                    user_id = str(normalized.get("id") or "").strip()
                    if user_id:
                        users_by_id[user_id] = normalized
            rows = [users_by_id[user_id] for user_id in ids if user_id in users_by_id]
            if dept_ids:
                rows = [
                    user
                    for user in rows
                    if set(user.get("department_ids") or []).intersection(dept_ids)
                ]
            return rows

        if dept_ids:
            if self.provider.mode() == "fixture":
                for item in self.provider.list_users(limit=max(limit, 500), params=None):
                    normalized = self._normalize_user_item(item)
                    user_id = str(normalized.get("id") or "").strip()
                    if user_id and set(normalized.get("department_ids") or []).intersection(dept_ids):
                        users_by_id[user_id] = normalized
                return list(users_by_id.values())[:limit]

            for dept_id in dept_ids:
                params = {"FILTER": {"UF_DEPARTMENT": dept_id}}
                for item in self._list_users_raw(limit=limit, params=params):
                    normalized = self._normalize_user_item(item)
                    user_id = str(normalized.get("id") or "").strip()
                    if user_id:
                        users_by_id[user_id] = normalized
            return list(users_by_id.values())[:limit]

        for item in self._list_users_raw(limit=limit, params=None):
            normalized = self._normalize_user_item(item)
            user_id = str(normalized.get("id") or "").strip()
            if user_id:
                users_by_id[user_id] = normalized
        return list(users_by_id.values())

    def get_departments(self) -> list[dict[str, Any]]:
        departments = []
        for item in self._list_departments_raw():
            departments.append(
                {
                    "id": str(item.get("ID") or item.get("id") or "").strip(),
                    "name": str(item.get("NAME") or item.get("name") or "").strip(),
                    "head_user_id": str(item.get("UF_HEAD") or item.get("head_user_id") or "").strip() or None,
                    "parent_id": str(item.get("PARENT") or item.get("PARENT_ID") or item.get("parent_id") or "").strip()
                    or None,
                    "sort": str(item.get("SORT") or item.get("sort") or "").strip() or None,
                    "raw": item,
                }
            )
        return departments

    def _normalize_crm_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for item in items:
            normalized.append(
                {
                    "id": str(item.get("ID") or item.get("id") or "").strip(),
                    "title": str(
                        item.get("TITLE")
                        or item.get("NAME")
                        or item.get("COMPANY_TITLE")
                        or item.get("FULL_NAME")
                        or ""
                    ).strip(),
                    "assigned_id": str(item.get("ASSIGNED_BY_ID") or item.get("assigned_by_id") or "").strip() or None,
                    "created_at": _normalize_datetime(item.get("DATE_CREATE") or item.get("CREATED_TIME")),
                    "updated_at": _normalize_datetime(item.get("DATE_MODIFY") or item.get("UPDATED_TIME")),
                    "stage_id": str(item.get("STAGE_ID") or item.get("STATUS_ID") or "").strip() or None,
                    "semantic_id": str(
                        item.get("STAGE_SEMANTIC_ID")
                        or item.get("STATUS_SEMANTIC_ID")
                        or item.get("semantic_id")
                        or ""
                    ).strip()
                    or None,
                    "stage_description": str(item.get("STATUS_DESCRIPTION") or item.get("stage_description") or "").strip()
                    or None,
                    "amount": str(item.get("OPPORTUNITY") or item.get("AMOUNT") or "").strip() or None,
                    "probability": str(item.get("PROBABILITY") or item.get("probability") or "").strip() or None,
                    "company_id": str(item.get("COMPANY_ID") or "").strip() or None,
                    "contact_id": str(item.get("CONTACT_ID") or "").strip() or None,
                    "category_id": str(item.get("CATEGORY_ID") or item.get("categoryId") or "").strip() or None,
                    "moved_at": _normalize_datetime(item.get("MOVED_TIME")),
                    "source_id": str(item.get("SOURCE_ID") or "").strip() or None,
                    "source_description": str(item.get("SOURCE_DESCRIPTION") or "").strip() or None,
                    "comments": str(item.get("COMMENTS") or "").strip() or None,
                    "last_activity_at": _normalize_datetime(
                        item.get("LAST_ACTIVITY_TIME")
                        or item.get("LAST_COMMUNICATION_TIME")
                        or item.get("DATE_MODIFY")
                    ),
                    "last_communication_at": _normalize_datetime(item.get("LAST_COMMUNICATION_TIME")),
                    "closed": str(item.get("CLOSED") or "").strip().upper() == "Y",
                    "raw": item,
                }
            )
        return normalized

    def get_leads(
        self,
        limit: int = 50,
        *,
        filter_params: Mapping[str, Any] | None = None,
        order: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": LEAD_SELECT_FIELDS}
        if filter_params:
            params["filter"] = dict(filter_params)
        if order:
            params["order"] = dict(order)
        items = self._call_list_page("crm.lead.list", fixture_key="leads", params=params)
        return self._normalize_crm_items(items[:limit])

    def get_recent_leads(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.get_leads(limit=limit, order={"DATE_CREATE": "DESC"})

    def get_active_leads(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.get_leads(
            limit=limit,
            filter_params={"!STATUS_ID": "CONVERTED"},
            order={"DATE_MODIFY": "DESC"},
        )

    def get_deals(
        self,
        limit: int = 50,
        *,
        category_id: int | str | None = None,
        filter_params: Mapping[str, Any] | None = None,
        order: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": DEAL_SELECT_FIELDS}
        filter_data = dict(filter_params or {})
        if category_id not in (None, ""):
            filter_data["CATEGORY_ID"] = str(category_id)
        if filter_data:
            params["filter"] = filter_data
        if order:
            params["order"] = dict(order)
        items = self._call_list_page(
            "crm.deal.list",
            fixture_key="deals",
            params=params,
            limit=limit,
            use_sales_app=True,
        )
        return self._normalize_crm_items(items[:limit])

    def get_recent_deals(
        self,
        limit: int = 50,
        *,
        category_id: int | str | None = None,
    ) -> list[dict[str, Any]]:
        return self.get_deals(limit=limit, category_id=category_id, order={"DATE_CREATE": "DESC"})

    def get_active_deals(
        self,
        limit: int = 50,
        *,
        category_id: int | str | None = None,
    ) -> list[dict[str, Any]]:
        return self.get_deals(
            limit=limit,
            category_id=category_id,
            filter_params={"CLOSED": "N"},
            order={"DATE_MODIFY": "DESC"},
        )

    def get_closed_deals(
        self,
        limit: int = 100,
        *,
        category_id: int | str | None = None,
    ) -> list[dict[str, Any]]:
        return self.get_deals(
            limit=limit,
            category_id=category_id,
            filter_params={"CLOSED": "Y"},
            order={"MOVED_TIME": "DESC"},
        )

    def get_deal_stage_map(self, category_id: int | str = SALES_DEAL_CATEGORY_ID) -> list[dict[str, Any]]:
        return self._get_status_map(f"DEAL_STAGE_{int(category_id)}")

    def get_deal_source_map(self) -> list[dict[str, Any]]:
        return self._get_status_map("SOURCE")

    def get_deal_fields_meta(self) -> dict[str, Any]:
        try:
            if self.sales_read_mode() == "app_oauth":
                payload = self.app_auth.call_payload("crm.deal.fields", default={})
            else:
                payload = self.provider.call_method("crm.deal.fields", default={})
        except BITRIX_RUNTIME_ERRORS:
            return {}

        result = payload.get("result") if isinstance(payload, dict) else payload
        return result if isinstance(result, dict) else {}

    def _normalize_dynamic_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or item.get("ID") or "").strip(),
            "title": str(item.get("title") or item.get("TITLE") or "").strip(),
            "created_at": _normalize_datetime(item.get("createdTime") or item.get("created_at")),
            "updated_at": _normalize_datetime(item.get("updatedTime") or item.get("updated_at")),
            "moved_at": _normalize_datetime(item.get("movedTime") or item.get("moved_at")),
            "last_activity_at": _normalize_datetime(item.get("lastActivityTime") or item.get("last_activity_at")),
            "last_communication_at": _normalize_datetime(
                item.get("lastCommunicationTime") or item.get("last_communication_at")
            ),
            "category_id": str(item.get("categoryId") or item.get("CATEGORY_ID") or "").strip() or None,
            "stage_id": str(item.get("stageId") or item.get("STAGE_ID") or "").strip() or None,
            "assigned_id": str(item.get("assignedById") or item.get("ASSIGNED_BY_ID") or "").strip() or None,
            "parent_deal_id": str(item.get("parentId2") or item.get("PARENT_ID_2") or "").strip() or None,
            "raw": item,
        }

    def get_dynamic_items(
        self,
        *,
        entity_type_id: int,
        category_id: int | str,
        limit: int = 100,
        filter_params: Mapping[str, Any] | None = None,
        order: Mapping[str, Any] | None = None,
        select_fields: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        items = self._call_list_page(
            "crm.item.list",
            fixture_key="items",
            params={
                "entityTypeId": int(entity_type_id),
                "select": list(select_fields or DYNAMIC_ITEM_SELECT_FIELDS),
                "filter": {"categoryId": int(category_id), **dict(filter_params or {})},
                "order": dict(order or {"updatedTime": "DESC"}),
            },
            limit=limit,
            use_sales_app=True,
        )
        return [self._normalize_dynamic_item(item) for item in items[:limit]]

    def get_dynamic_stage_map(self, *, entity_type_id: int, category_id: int | str) -> list[dict[str, Any]]:
        return self._get_status_map(f"DYNAMIC_{int(entity_type_id)}_STAGE_{int(category_id)}")

    def resolve_dynamic_stage_id(
        self,
        *,
        entity_type_id: int,
        category_id: int | str,
        stage_name: str,
    ) -> str | None:
        return self._resolve_status_id(
            f"DYNAMIC_{int(entity_type_id)}_STAGE_{int(category_id)}",
            stage_name,
        )

    def get_meetings(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.get_dynamic_items(
            entity_type_id=MEETING_ENTITY_TYPE_ID,
            category_id=MEETING_CATEGORY_ID,
            limit=limit,
        )

    def get_briefs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.get_dynamic_items(
            entity_type_id=BRIEF_ENTITY_TYPE_ID,
            category_id=BRIEF_CATEGORY_ID,
            limit=limit,
        )

    def get_conducted_meetings(self, limit: int = 100) -> list[dict[str, Any]]:
        stage_id = self.resolve_dynamic_stage_id(
            entity_type_id=MEETING_ENTITY_TYPE_ID,
            category_id=MEETING_CATEGORY_ID,
            stage_name=MEETING_DONE_STAGE_NAME,
        )
        if not stage_id:
            return []
        return self.get_dynamic_items(
            entity_type_id=MEETING_ENTITY_TYPE_ID,
            category_id=MEETING_CATEGORY_ID,
            limit=limit,
            filter_params={"stageId": stage_id},
        )

    def get_accepted_briefs(self, limit: int = 100) -> list[dict[str, Any]]:
        stage_id = self.resolve_dynamic_stage_id(
            entity_type_id=BRIEF_ENTITY_TYPE_ID,
            category_id=BRIEF_CATEGORY_ID,
            stage_name=BRIEF_ACCEPTED_STAGE_NAME,
        )
        if not stage_id:
            return []
        return self.get_dynamic_items(
            entity_type_id=BRIEF_ENTITY_TYPE_ID,
            category_id=BRIEF_CATEGORY_ID,
            limit=limit,
            filter_params={"stageId": stage_id},
        )

    def get_companies(
        self,
        limit: int = 50,
        *,
        company_ids: Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": COMPANY_SELECT_FIELDS, "order": {"DATE_MODIFY": "DESC"}}
        ids = _dedupe_ids(company_ids or [])
        if ids:
            params["filter"] = {"ID": ids[:limit]}
        items = self._call_list_page(
            "crm.company.list",
            fixture_key="companies",
            params=params,
            limit=limit,
            use_sales_app=True,
        )
        return self._normalize_crm_items(items[:limit])

    def get_contacts(
        self,
        limit: int = 50,
        *,
        contact_ids: Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": CONTACT_SELECT_FIELDS, "order": {"DATE_MODIFY": "DESC"}}
        ids = _dedupe_ids(contact_ids or [])
        if ids:
            params["filter"] = {"ID": ids[:limit]}

        contacts = []
        for item in self._call_list_page(
            "crm.contact.list",
            fixture_key="contacts",
            params=params,
            limit=limit,
            use_sales_app=True,
        )[:limit]:
            contacts.append(
                {
                    "id": str(item.get("ID") or item.get("id") or "").strip(),
                    "full_name": " ".join(
                        part
                        for part in (
                            str(item.get("LAST_NAME") or "").strip(),
                            str(item.get("NAME") or "").strip(),
                            str(item.get("SECOND_NAME") or "").strip(),
                        )
                        if part
                    ).strip()
                    or str(item.get("TITLE") or "").strip(),
                    "assigned_id": str(item.get("ASSIGNED_BY_ID") or "").strip() or None,
                    "company_id": str(item.get("COMPANY_ID") or "").strip() or None,
                    "created_at": _normalize_datetime(item.get("DATE_CREATE")),
                    "updated_at": _normalize_datetime(item.get("DATE_MODIFY")),
                    "last_activity_at": _normalize_datetime(item.get("LAST_ACTIVITY_TIME") or item.get("DATE_MODIFY")),
                    "raw": item,
                }
            )
        return contacts

    def get_calendar_events(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        if date_from is None or date_to is None:
            now = datetime.now(MOSCOW_TZ)
            start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=MOSCOW_TZ)
            end = start + timedelta(days=1) - timedelta(seconds=1)
            date_from = date_from or _to_moscow_iso(start)
            date_to = date_to or _to_moscow_iso(end)

        owner_id = self.get_profile().get("id") or None
        events = []
        for item in self.provider.list_calendar_events(
            date_from=date_from,
            date_to=date_to,
            owner_id=owner_id,
        ):
            events.append(
                {
                    "id": str(item.get("ID") or item.get("id") or "").strip(),
                    "title": str(item.get("NAME") or item.get("TITLE") or "").strip(),
                    "date_from": _normalize_datetime(item.get("DATE_FROM") or item.get("DATE_FROM_TS")),
                    "date_to": _normalize_datetime(item.get("DATE_TO") or item.get("DATE_TO_TS")),
                    "owner_id": owner_id,
                    "attendees": item.get("ATTENDEES") or [],
                    "raw": item,
                }
            )
        return events

    def get_activities(
        self,
        limit: int = 200,
        *,
        filter_params: Mapping[str, Any] | None = None,
        order: Mapping[str, Any] | None = None,
        select_fields: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": list(select_fields or ACTIVITY_SELECT_FIELDS)}
        if filter_params:
            params["filter"] = dict(filter_params)
        if order:
            params["order"] = dict(order)

        raw_items = (
            self.app_auth.list_method("crm.activity.list", params=params, limit=limit)
            if self.sales_read_mode() == "app_oauth"
            else self.provider.list_activities(limit=limit, params=params)
        )
        return [self._normalize_activity_item(item) for item in raw_items]

    def _normalize_activity_item(self, item: dict[str, Any]) -> dict[str, Any]:
        communications = item.get("COMMUNICATIONS")
        settings = item.get("SETTINGS")
        return {
            "id": str(item.get("ID") or item.get("id") or "").strip(),
            "type_id": str(item.get("TYPE_ID") or item.get("type_id") or "").strip() or None,
            "provider_id": str(item.get("PROVIDER_ID") or item.get("provider_id") or "").strip() or None,
            "provider_type_id": str(item.get("PROVIDER_TYPE_ID") or item.get("provider_type_id") or "").strip()
            or None,
            "subject": str(item.get("SUBJECT") or item.get("subject") or "").strip(),
            "responsible_id": str(
                item.get("RESPONSIBLE_ID")
                or item.get("responsible_id")
                or (settings.get("RESPONSIBLE_ID") if isinstance(settings, dict) else "")
                or ""
            ).strip()
            or None,
            "author_id": str(item.get("AUTHOR_ID") or item.get("author_id") or "").strip() or None,
            "created_at": _normalize_datetime(item.get("CREATED")),
            "last_updated_at": _normalize_datetime(item.get("LAST_UPDATED") or item.get("UPDATED")),
            "deadline": _normalize_datetime(item.get("DEADLINE")),
            "start_time": _normalize_datetime(item.get("START_TIME")),
            "end_time": _normalize_datetime(item.get("END_TIME")),
            "completed": str(item.get("COMPLETED") or "").strip().upper() == "Y",
            "direction": str(item.get("DIRECTION") or "").strip() or None,
            "duration_sec": _duration_seconds(item.get("START_TIME"), item.get("END_TIME")),
            "communications": communications if isinstance(communications, list) else [],
            "settings": settings if isinstance(settings, dict) else {},
            "description": str(item.get("DESCRIPTION") or "").strip(),
            "raw": item,
        }

    def get_call_activities(
        self,
        limit: int = 50,
        *,
        filter_params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        activities = self.get_activities(
            limit=limit,
            filter_params=filter_params,
            order={"CREATED": "DESC"},
        )
        return [
            item
            for item in activities
            if (
                str(item.get("type_id") or "").strip() == "2"
                and (
                    str(item.get("provider_type_id") or "").strip().upper() == "CALL"
                    or "CALL" in str(item.get("provider_id") or "").strip().upper()
                )
            )
        ]

    def get_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.get_tasks_bundle(limit=limit).get("items") or []

    def _normalize_task_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tasks = []
        for item in items:
            task = item.get("task") if isinstance(item.get("task"), dict) else item
            tasks.append(
                {
                    "id": str(task.get("id") or task.get("ID") or "").strip(),
                    "title": str(task.get("title") or task.get("TITLE") or "").strip(),
                    "status": str(task.get("status") or task.get("STATUS") or "").strip() or None,
                    "created_by": str(
                        task.get("createdBy")
                        or task.get("CREATED_BY")
                        or task.get("created_by")
                        or ""
                    ).strip()
                    or None,
                    "responsible_id": str(
                        task.get("responsibleId")
                        or task.get("RESPONSIBLE_ID")
                        or task.get("responsible_id")
                        or ""
                    ).strip()
                    or None,
                    "deadline": _normalize_datetime(task.get("deadline") or task.get("DEADLINE")),
                    "closed_at": _normalize_datetime(task.get("closedDate") or task.get("CLOSED_DATE")),
                    "crm_bindings": _normalize_id_list(task.get("ufCrmTask") or task.get("UF_CRM_TASK")),
                    "raw": task,
                }
            )
        return tasks

    def get_task_status_map(self) -> dict[str, str]:
        try:
            if self.sales_read_mode() == "app_oauth":
                payload = self.app_auth.call_payload("tasks.task.getFields", default={})
            else:
                payload = self.provider.call_method("tasks.task.getFields", default={})
        except BITRIX_RUNTIME_ERRORS:
            return {}

        result = payload.get("result") if isinstance(payload, dict) else payload
        fields = result.get("fields") if isinstance(result, dict) else {}
        status_meta = fields.get("STATUS") if isinstance(fields, dict) else {}
        values = status_meta.get("values") if isinstance(status_meta, dict) else {}
        if not isinstance(values, dict):
            return {}
        return {
            str(status_id).strip(): str(status_name).strip()
            for status_id, status_name in values.items()
            if str(status_id).strip()
        }

    def get_tasks_bundle(self, limit: int = 50) -> dict[str, Any]:
        try:
            webhook_items = self.provider.list_tasks(limit=limit)
            return {
                "available": True,
                "source": "webhook:tasks.task.list",
                "items": self._normalize_task_items(webhook_items),
                "error": None,
            }
        except BITRIX_RUNTIME_ERRORS as error:
            webhook_error = {
                "status": error.to_status(),
                "code": error.code or None,
                "message": error.message,
                "http_status": error.http_status,
            }

        try:
            app_items = self.app_auth.list_method(
                "tasks.task.list",
                params={
                    "select": [
                        "ID",
                        "TITLE",
                        "STATUS",
                        "CREATED_BY",
                        "RESPONSIBLE_ID",
                        "DEADLINE",
                        "CLOSED_DATE",
                        "UF_CRM_TASK",
                    ],
                    "order": {"ID": "desc"},
                },
                limit=limit,
            )
            return {
                "available": True,
                "source": "app_oauth:tasks.task.list",
                "items": self._normalize_task_items(app_items),
                "error": None,
            }
        except BITRIX_RUNTIME_ERRORS as error:
            return {
                "available": False,
                "source": "tasks.task.list",
                "items": [],
                "error": {
                    "webhook": webhook_error,
                    "app_oauth": {
                        "status": error.to_status(),
                        "code": error.code or None,
                        "message": error.message,
                        "http_status": error.http_status,
                    },
                },
            }

    def get_deal_next_steps(
        self,
        deal_ids: Sequence[Any],
        *,
        limit_per_deal: int = 10,
    ) -> dict[str, dict[str, Any]]:
        deduped_ids = _dedupe_ids(deal_ids)
        if not deduped_ids:
            return {}

        result: dict[str, dict[str, Any]] = {}
        unresolved_ids = list(deduped_ids)
        if self.sales_read_mode() == "app_oauth":
            result, unresolved_ids = self._get_deal_next_steps_batch(
                deduped_ids,
                limit_per_deal=limit_per_deal,
            )
        if unresolved_ids:
            result.update(self._get_deal_next_steps_sequential(unresolved_ids, limit_per_deal=limit_per_deal))
        return result

    def get_deal_product_rows(
        self,
        deal_ids: Sequence[Any],
    ) -> dict[str, list[dict[str, Any]]]:
        deduped_ids = _dedupe_ids(deal_ids)
        if not deduped_ids:
            return {}
        if self.provider.mode() == "fixture":
            return {}

        result: dict[str, list[dict[str, Any]]] = {}
        unresolved_ids = list(deduped_ids)
        if self.sales_read_mode() == "app_oauth":
            result, unresolved_ids = self._get_deal_product_rows_batch(deduped_ids)
        for deal_id in unresolved_ids:
            rows: Any
            if self.sales_read_mode() == "app_oauth":
                rows = self.app_auth.call_method("crm.deal.productrows.get", params={"id": deal_id}, default=[])
            else:
                rows = self.provider.call_method(
                    "crm.deal.productrows.get",
                    params={"id": deal_id},
                    fixture_key="deal_product_rows",
                    default=[],
                )
            if not isinstance(rows, list):
                continue
            result[deal_id] = [dict(item) for item in rows if isinstance(item, Mapping)]
        return result

    def _get_deal_product_rows_batch(
        self,
        deal_ids: Sequence[str],
    ) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
        result: dict[str, list[dict[str, Any]]] = {}
        unresolved_ids: list[str] = []

        for chunk in _chunked(_dedupe_ids(deal_ids), 25):
            commands: dict[str, str] = {}
            command_to_deal: dict[str, str] = {}
            for deal_id in chunk:
                command_id = f"deal_{deal_id}"
                commands[command_id] = "crm.deal.productrows.get?" + urlencode({"id": deal_id})
                command_to_deal[command_id] = deal_id

            try:
                payload = self.app_auth.call_payload(
                    "batch",
                    params={"halt": 0, "cmd": commands},
                    default={},
                )
            except BITRIX_RUNTIME_ERRORS:
                unresolved_ids.extend(chunk)
                continue

            raw_result = payload.get("result") if isinstance(payload, dict) else {}
            batch_results = raw_result.get("result") if isinstance(raw_result, dict) else {}
            batch_errors = raw_result.get("result_error") if isinstance(raw_result, dict) else {}

            for command_id, deal_id in command_to_deal.items():
                if isinstance(batch_errors, Mapping) and batch_errors.get(command_id):
                    unresolved_ids.append(deal_id)
                    continue
                raw_rows = batch_results.get(command_id) if isinstance(batch_results, Mapping) else None
                if not isinstance(raw_rows, list):
                    continue
                result[deal_id] = [dict(item) for item in raw_rows if isinstance(item, Mapping)]

        return result, unresolved_ids

    def get_deal_timeline_comments(
        self,
        deal_ids: Sequence[str | int],
        *,
        since: datetime | None = None,
        limit_per_deal: int = 20,
    ) -> dict[str, list[dict[str, Any]]]:
        deduped_ids = _dedupe_ids(deal_ids)
        result: dict[str, list[dict[str, Any]]] = {}
        unresolved_ids = list(deduped_ids)
        if self.sales_read_mode() == "app_oauth":
            result, unresolved_ids = self._get_deal_timeline_comments_batch(
                deduped_ids,
                since=since,
                limit_per_deal=limit_per_deal,
            )
        if unresolved_ids:
            result.update(
                self._get_deal_timeline_comments_sequential(
                    unresolved_ids,
                    since=since,
                    limit_per_deal=limit_per_deal,
                )
            )
        return result

    def _normalize_timeline_comment_items(
        self,
        raw_items: Sequence[dict[str, Any]],
        *,
        since: datetime | None = None,
        limit_per_deal: int = 20,
    ) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            created_at = _normalize_datetime(item.get("CREATED") or item.get("created_at"))
            if since is not None and created_at:
                try:
                    created_dt = datetime.fromisoformat(created_at)
                except ValueError:
                    created_dt = None
                if created_dt is not None and created_dt < since:
                    continue
            comments.append(
                {
                    "id": str(item.get("ID") or item.get("id") or "").strip(),
                    "created_at": created_at,
                    "author_id": str(item.get("AUTHOR_ID") or item.get("author_id") or "").strip() or None,
                    "comment": str(item.get("COMMENT") or item.get("comment") or "").strip(),
                    "raw": item,
                }
            )
        if limit_per_deal > 0:
            comments = comments[-limit_per_deal:]
        return comments

    def _get_deal_timeline_comments_batch(
        self,
        deal_ids: Sequence[str],
        *,
        since: datetime | None,
        limit_per_deal: int,
    ) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
        result: dict[str, list[dict[str, Any]]] = {}
        unresolved_ids: list[str] = []

        for chunk in _chunked(_dedupe_ids(deal_ids), 25):
            commands: dict[str, str] = {}
            command_to_deal: dict[str, str] = {}
            for deal_id in chunk:
                command_id = f"deal_{deal_id}"
                command_params = {
                    "filter": {
                        "ENTITY_TYPE": "deal",
                        "ENTITY_ID": deal_id,
                    },
                    "order": {"CREATED": "ASC"},
                }
                commands[command_id] = "crm.timeline.comment.list?" + urlencode(
                    _flatten_query_params("", command_params)
                )
                command_to_deal[command_id] = deal_id

            try:
                payload = self.app_auth.call_payload(
                    "batch",
                    params={"halt": 0, "cmd": commands},
                    default={},
                )
            except BITRIX_RUNTIME_ERRORS:
                unresolved_ids.extend(chunk)
                continue

            raw_result = payload.get("result") if isinstance(payload, dict) else {}
            batch_results = raw_result.get("result") if isinstance(raw_result, dict) else {}
            batch_errors = raw_result.get("result_error") if isinstance(raw_result, dict) else {}

            for command_id, deal_id in command_to_deal.items():
                if isinstance(batch_errors, Mapping) and batch_errors.get(command_id):
                    unresolved_ids.append(deal_id)
                    continue
                raw_items = _extract_items(batch_results.get(command_id) if isinstance(batch_results, Mapping) else None)
                result[deal_id] = self._normalize_timeline_comment_items(
                    raw_items,
                    since=since,
                    limit_per_deal=limit_per_deal,
                )

        return result, unresolved_ids

    def _get_deal_timeline_comments_sequential(
        self,
        deal_ids: Sequence[str],
        *,
        since: datetime | None,
        limit_per_deal: int,
    ) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for deal_id in _dedupe_ids(deal_ids):
            raw_items = self.app_auth.call_method(
                "crm.timeline.comment.list",
                params={
                    "filter": {
                        "ENTITY_TYPE": "deal",
                        "ENTITY_ID": deal_id,
                    },
                    "order": {"CREATED": "ASC"},
                },
                default=[],
            )
            comments: list[dict[str, Any]] = []
            if isinstance(raw_items, list):
                comments = self._normalize_timeline_comment_items(
                    raw_items,
                    since=since,
                    limit_per_deal=limit_per_deal,
                )
            result[str(deal_id)] = comments
        return result

    def _get_deal_next_steps_batch(
        self,
        deal_ids: Sequence[str],
        *,
        limit_per_deal: int,
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        result: dict[str, dict[str, Any]] = {}
        unresolved_ids: list[str] = []
        order = {"DEADLINE": "ASC", "START_TIME": "ASC", "ID": "ASC"}

        for chunk in _chunked(_dedupe_ids(deal_ids), 25):
            commands: dict[str, str] = {}
            command_to_deal: dict[str, str] = {}
            for deal_id in chunk:
                command_id = f"deal_{deal_id}"
                command_params = {
                    "select": ACTIVITY_SELECT_FIELDS,
                    "filter": {"OWNER_TYPE_ID": 2, "OWNER_ID": deal_id, "COMPLETED": "N"},
                    "order": order,
                    "start": 0,
                }
                commands[command_id] = "crm.activity.list?" + urlencode(_flatten_query_params("", command_params))
                command_to_deal[command_id] = deal_id

            try:
                payload = self.app_auth.call_payload(
                    "batch",
                    params={"halt": 0, "cmd": commands},
                    default={},
                )
            except BITRIX_RUNTIME_ERRORS:
                unresolved_ids.extend(chunk)
                continue

            raw_result = payload.get("result") if isinstance(payload, dict) else {}
            batch_results = raw_result.get("result") if isinstance(raw_result, dict) else {}
            batch_errors = raw_result.get("result_error") if isinstance(raw_result, dict) else {}

            for command_id, deal_id in command_to_deal.items():
                if isinstance(batch_errors, Mapping) and batch_errors.get(command_id):
                    unresolved_ids.append(deal_id)
                    continue
                normalized = [
                    self._normalize_activity_item(item)
                    for item in _extract_items(batch_results.get(command_id) if isinstance(batch_results, Mapping) else None)
                ]
                payload_item = _build_next_step_payload(deal_id, normalized)
                if payload_item:
                    result[deal_id] = payload_item

        return result, unresolved_ids

    def _get_deal_next_steps_sequential(
        self,
        deal_ids: Sequence[str],
        *,
        limit_per_deal: int,
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for deal_id in _dedupe_ids(deal_ids):
            activities = self.get_activities(
                limit=limit_per_deal,
                filter_params={"OWNER_TYPE_ID": 2, "OWNER_ID": deal_id, "COMPLETED": "N"},
                order={"DEADLINE": "ASC", "START_TIME": "ASC", "ID": "ASC"},
            )
            payload = _build_next_step_payload(deal_id, activities)
            if payload:
                result[deal_id] = payload
        return result

    def _probe(self, key: str, label: str, loader: Callable[[], Any]) -> dict[str, Any]:
        try:
            payload = loader()
        except BITRIX_RUNTIME_ERRORS as error:
            return {
                "key": key,
                "label": label,
                "ok": False,
                "status": error.to_status(),
                "message": error.message,
                "code": error.code or None,
            }
        except Exception as error:  # noqa: BLE001
            return {
                "key": key,
                "label": label,
                "ok": False,
                "status": "error",
                "message": str(error),
                "code": None,
            }

        size = len(payload) if isinstance(payload, list) else 1
        return {
            "key": key,
            "label": label,
            "ok": True,
            "status": "ok",
            "message": f"OK ({size})",
            "code": None,
        }

    def check_access(self) -> list[dict[str, Any]]:
        access = [
            self._probe("profile", "профиль", self.get_profile),
            self._probe("users", "пользователи", lambda: self.get_users(limit=1)),
            self._probe("deals", "сделки category 10", lambda: self.get_deals(limit=5, category_id=SALES_DEAL_CATEGORY_ID)),
            self._probe("companies", "компании", lambda: self.get_companies(limit=5)),
            self._probe("contacts", "контакты", lambda: self.get_contacts(limit=5)),
            self._probe("meetings", "встречи type 1048", lambda: self.get_meetings(limit=5)),
            self._probe("briefs", "брифы type 1056", lambda: self.get_briefs(limit=5)),
            self._probe("telephony", "телефония (crm.activity.list CALL)", lambda: self.get_call_activities(limit=5)),
            self._probe("departments", "департаменты", self.get_departments),
        ]
        tasks_bundle = self.get_tasks_bundle(limit=5)
        if tasks_bundle.get("available"):
            access.append(
                {
                    "key": "tasks",
                    "label": "задачи",
                    "ok": True,
                    "status": "ok",
                    "message": f"OK ({len(tasks_bundle.get('items') or [])}) [{tasks_bundle.get('source')}]",
                    "code": None,
                }
            )
        else:
            error = tasks_bundle.get("error") or {}
            webhook_error = error.get("webhook") or {}
            app_error = error.get("app_oauth") or {}
            access.append(
                {
                    "key": "tasks",
                    "label": "задачи",
                    "ok": False,
                    "status": app_error.get("status") or webhook_error.get("status") or "error",
                    "message": (
                        f"webhook: {webhook_error.get('message') or '-'}; "
                        f"app_oauth: {app_error.get('message') or '-'}"
                    ),
                    "code": app_error.get("code") or webhook_error.get("code"),
                }
            )
        return access
