"""Экстрактор звонков из voximplant.statistic.get.

ВАЖНО: voximplant.statistic.get использует фильтр по CALL_START_DATE и
пагинацию через start/next (не filter[>ID]). Лаг ~1-2 мин от реального
звонка до появления в API.
"""
from __future__ import annotations

from datetime import datetime

from ..bitrix_client import BitrixClient
from ..config import MOSCOW_TZ

HEADER = [
    "call_id",
    "call_type",            # 1=исходящий, 2=входящий, 3=пропущенный, 4=входящий не отвеч.
    "call_type_label",
    "call_start_date",
    "call_duration",        # секунды (включая ожидание)
    "talk_duration",        # секунды (только разговор) — если есть
    "call_failed_code",
    "call_failed_reason",
    "phone_number",
    "portal_user_id",       # менеджер
    "manager",              # ← join из users
    "crm_activity_id",
    "crm_entity_type",
    "crm_entity_id",
    "cost",
    "cost_currency",
    "call_record_url",
    "date",                 # YYYY-MM-DD в MSK для группировки
    "hour",                 # 0..23 MSK
    "is_answered",          # Y/N — Y если call_duration > 0 и call_failed_code = "200"
]

CALL_TYPE_LABELS = {
    "1": "outgoing",
    "2": "incoming",
    "3": "missed",          # incoming missed by manager
    "4": "incoming_redirect",
}


def extract_calls(
    client: BitrixClient,
    since: datetime,
    until: datetime | None = None,
    user_names: dict[int, str] | None = None,
) -> list[list]:
    """Тянем все звонки за окно [since, until]. until=None → до настоящего."""
    flt: dict = {
        ">=CALL_START_DATE": since.astimezone(MOSCOW_TZ).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if until is not None:
        flt["<CALL_START_DATE"] = until.astimezone(MOSCOW_TZ).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

    params = {
        "filter": flt,
        "sort": "CALL_START_DATE",
        "order": "ASC",
    }

    rows: list[list] = []
    for c in client.paginate_by_start("voximplant.statistic.get", params):
        rows.append(_to_row(c, user_names or {}))
    return rows


def _to_row(c: dict, user_names: dict[int, str]) -> list:
    call_type = str(c.get("CALL_TYPE") or "")
    start = c.get("CALL_START_DATE") or ""
    date_part = ""
    hour = ""
    if start:
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            dt_msk = dt.astimezone(MOSCOW_TZ)
            date_part = dt_msk.strftime("%Y-%m-%d")
            hour = dt_msk.hour
        except ValueError:
            pass

    duration = _as_int(c.get("CALL_DURATION"))
    failed_code = c.get("CALL_FAILED_CODE") or ""
    is_answered = (
        "Y" if isinstance(duration, int) and duration > 0 and failed_code == "200" else "N"
    )
    portal_user_id = _as_int(c.get("PORTAL_USER_ID"))

    return [
        c.get("ID") or "",
        call_type,
        CALL_TYPE_LABELS.get(call_type, ""),
        start,
        duration,
        duration,
        failed_code,
        c.get("CALL_FAILED_REASON") or "",
        c.get("PHONE_NUMBER") or "",
        portal_user_id,
        user_names.get(portal_user_id, "") if isinstance(portal_user_id, int) else "",
        _as_int(c.get("CRM_ACTIVITY_ID")) if c.get("CRM_ACTIVITY_ID") else "",
        c.get("CRM_ENTITY_TYPE") or "",
        _as_int(c.get("CRM_ENTITY_ID")) if c.get("CRM_ENTITY_ID") else "",
        _as_float(c.get("COST")),
        c.get("COST_CURRENCY") or "",
        c.get("CALL_RECORD_URL") or "",
        date_part,
        hour,
        is_answered,
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
