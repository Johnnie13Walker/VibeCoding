from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from sales_dashboard.bitrix_client import BitrixClient


class BitrixReader:
    def __init__(self, client: BitrixClient | None = None):
        self.client = client or BitrixClient()
        self._stage_cache: dict[int, list[dict]] = {}

    def profile(self) -> dict:
        return self.client.call("profile").get("result") or {}

    def list_active_users(self) -> list[dict]:
        rows: list[dict] = []
        start = 0
        while True:
            body = self.client.call("user.get", {"filter": {"ACTIVE": True}, "start": start})
            page = _result_rows(body)
            rows.extend(page)
            next_start = body.get("next")
            if next_start is None or not page:
                return rows
            start = int(next_start)

    def resolve_role_users(self, regex: re.Pattern) -> dict[int, str]:
        users: dict[int, str] = {}
        for user in self.list_active_users():
            position = str(user.get("WORK_POSITION") or "")
            if not regex.search(position):
                continue
            user_id = _to_int(user.get("ID"))
            if user_id is None:
                continue
            users[user_id] = _user_name(user)
        return users

    def list_deals_won_in_period(self, start: date, end: date) -> list[dict]:
        return list(
            self.client.paginate(
                "crm.deal.list",
                {
                    "filter": {
                        "STAGE_SEMANTIC_ID": "S",
                        ">=CLOSEDATE": _date_value(start),
                        "<CLOSEDATE": _date_value(end + timedelta(days=1)),
                    },
                    "select": [
                        "ID",
                        "TITLE",
                        "OPPORTUNITY",
                        "ASSIGNED_BY_ID",
                        "STAGE_ID",
                        "CATEGORY_ID",
                        "CLOSEDATE",
                        "DATE_CLOSED",
                    ],
                    "start": -1,
                },
            )
        )

    def list_deals_open_in_pre_final(self, category_id: int) -> list[dict]:
        stages = self.deal_stages(category_id)
        stage_ids = [
            stage_id
            for stage in stages
            if (stage_id := stage.get("STATUS_ID") or stage.get("ID"))
            and str(stage.get("SEMANTICS") or "").upper() not in {"S", "F"}
            and "WON" not in str(stage_id).upper()
            and "LOSE" not in str(stage_id).upper()
        ]
        if not stage_ids:
            return []
        return list(
            self.client.paginate(
                "crm.deal.list",
                {
                    "filter": {
                        "CATEGORY_ID": category_id,
                        "STAGE_ID": stage_ids,
                        "CLOSED": "N",
                    },
                    "select": ["ID", "TITLE", "OPPORTUNITY", "ASSIGNED_BY_ID", "STAGE_ID", "CATEGORY_ID"],
                    "start": -1,
                },
            )
        )

    def productrows_for_deals(self, deal_ids: list[int]) -> dict[int, list[dict]]:
        unique_ids = list(dict.fromkeys(int(deal_id) for deal_id in deal_ids if deal_id))
        if not unique_ids:
            return {}
        rows_by_deal: dict[int, list[dict]] = {deal_id: [] for deal_id in unique_ids}
        for chunk in _chunks(unique_ids, 50):
            try:
                body = self.client.call(
                    "batch",
                    {
                        "halt": 0,
                        "cmd": {
                            str(deal_id): f"crm.deal.productrows.get?id={deal_id}"
                            for deal_id in chunk
                        },
                    },
                )
                result = body.get("result", {}).get("result", {})
                for deal_id in chunk:
                    rows_by_deal[deal_id] = _result_rows(result.get(str(deal_id)) or [])
            except Exception:
                for deal_id in chunk:
                    rows_by_deal[deal_id] = _result_rows(
                        self.client.call("crm.deal.productrows.get", {"id": deal_id})
                    )
        return rows_by_deal

    def list_meetings_in_period(self, start: date, end: date) -> list[dict]:
        activities = list(
            self.client.paginate_by_start(
                "crm.activity.list",
                {
                    "order": {"CREATED": "ASC"},
                    "filter": {
                        "TYPE_ID": 1,
                        "COMPLETED": "Y",
                        ">=CREATED": _date_value(start),
                        "<CREATED": _date_value(end + timedelta(days=1)),
                    },
                    "select": [
                        "ID",
                        "SUBJECT",
                        "OWNER_ID",
                        "OWNER_TYPE_ID",
                        "DEAL_ID",
                        "COMPANY_ID",
                        "COMPLETED",
                        "CREATED",
                        "CREATED_BY_ID",
                        "RESPONSIBLE_ID",
                    ],
                },
            )
        )
        return activities + self._list_meeting_sp_items(start, end)

    def list_calls_in_period(self, start: date, end: date) -> list[dict]:
        return list(
            self.client.paginate_by_start(
                "voximplant.statistic.get",
                {
                    "order": {"CALL_START_DATE": "ASC"},
                    "filter": {
                        ">=CALL_START_DATE": _date_value(start),
                        "<CALL_START_DATE": _date_value(end + timedelta(days=1)),
                    },
                },
            )
        )

    def count_sp_items(
        self,
        entity_type_id: int,
        stage_id: str,
        period_start: date,
        assigned_id: int | None = None,
    ) -> int:
        params: dict[str, Any] = {
            "entityTypeId": entity_type_id,
            "filter": {
                "stageId": stage_id,
                ">=movedTime": _date_value(period_start),
            },
        }
        if assigned_id is not None:
            params["filter"]["assignedById"] = assigned_id
        return self._count_start_pages("crm.item.list", params)

    def count_tasks_closed(self, user_id: int, period_start: date) -> int:
        return self._count_start_pages(
            "tasks.task.list",
            {
                "filter": {
                    "STATUS": 5,
                    "RESPONSIBLE_ID": user_id,
                    ">=CLOSED_DATE": _date_value(period_start),
                },
                "select": ["ID"],
            },
        )

    def deal_stages(self, category_id: int = 10) -> list[dict]:
        if category_id not in self._stage_cache:
            body = self.client.call("crm.dealcategory.stage.list", {"id": category_id})
            self._stage_cache[category_id] = _result_rows(body)
        return self._stage_cache[category_id]

    def _count_start_pages(self, method: str, params: dict[str, Any]) -> int:
        return len(self._list_start_pages(method, params))

    def _list_start_pages(self, method: str, params: dict[str, Any]) -> list[dict]:
        rows: list[dict] = []
        start = 0
        while True:
            page_params = _deep(params)
            page_params["start"] = start
            body = self.client.call(method, page_params)
            page_rows = _result_rows(body)
            rows.extend(page_rows)
            next_start = body.get("next")
            if next_start is None or not page_rows:
                return rows
            start = int(next_start)

    def _list_meeting_sp_items(self, start: date, end: date) -> list[dict]:
        rows = self._list_start_pages(
            "crm.item.list",
            {
                "entityTypeId": 1048,
                "filter": {
                    "stageId": "DT1048_24:SUCCESS",
                    ">=ufCrm16_1751009238": _date_value(start),
                    "<ufCrm16_1751009238": _date_value(end + timedelta(days=1)),
                },
            },
        )
        return [_normalize_meeting_sp_item(row) for row in rows]

def _result_rows(value: Any) -> list[dict]:
    if isinstance(value, dict) and "result" in value:
        return _result_rows(value["result"])
    if isinstance(value, dict):
        for key in ("items", "tasks"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return []
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return []


def _user_name(user: dict) -> str:
    first_name = str(user.get("NAME") or "").strip()
    last_name = str(user.get("LAST_NAME") or "").strip()
    return f"{last_name} {first_name}".strip() or str(user.get("ID") or "")


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _date_value(value: date) -> str:
    return value.isoformat()


def _normalize_meeting_sp_item(row: dict) -> dict:
    return {
        "ID": f"SP1048:{row.get('id')}",
        "SUBJECT": row.get("title") or "",
        "OWNER_ID": row.get("parentId2") or 0,
        "OWNER_TYPE_ID": "2",
        "DEAL_ID": row.get("parentId2") or 0,
        "COMPANY_ID": row.get("companyId") or 0,
        "COMPLETED": "Y",
        "CREATED": row.get("ufCrm16_1751009238") or row.get("createdTime") or "",
        "CREATED_BY_ID": row.get("createdBy") or 0,
        "RESPONSIBLE_ID": row.get("assignedById") or 0,
    }


def _chunks(values: list[int], size: int) -> list[list[int]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _deep(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep(item) for item in value]
    return value
