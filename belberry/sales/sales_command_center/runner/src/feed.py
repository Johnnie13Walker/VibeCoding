"""Общие data-хелперы (НЕ отчёт): лента дня для архивного /today и отказы дня.

Раньше жили в report_author.py / render.py вместе с генерацией дневного отчёта.
Отчёт удалён (атавизм), а эти функции остались нужны: extract_rejections — для
build_extras и блока «Отказы», build_day_feed — для summary_json (/today).
"""

from typing import Any

from .transform import manager_name

# Стадии отвала (Продажи [10] и Телемаркетинг [50]).
REJECTION_STAGES = {"C10:LOSE", "C50:APOLOGY"}
# СПАМ-причина (UF_CRM_1771495464 = 8588) — такие сделки исключаем из ленты.
REASON_FIELD = "UF_CRM_1771495464"
SPAM_REASON_ID = "8588"
# Скоуп ленты: отдел продаж + телемаркетинг.
_SALES_TM_ROLE_KEYS = ("продаж", "телемаркет", "роп")


def extract_rejections(raw: dict[str, Any], users: dict[Any, str] | None = None) -> list[dict[str, Any]]:
    users = users or raw.get("users") or {}
    deal_index = {
        str(deal.get("ID")): deal
        for deal in [
            *raw.get("deals_created", []),
            *raw.get("deals_open", []),
            *raw.get("rejected_deals", []),
        ]
    }
    rejections = []
    for item in raw.get("stagehistory", []):
        if item.get("STAGE_ID") not in REJECTION_STAGES:
            continue
        deal_id = str(item.get("OWNER_ID"))
        deal = deal_index.get(deal_id, {})
        manager_id = deal.get("ASSIGNED_BY_ID")
        rejections.append(
            {
                "deal_id": deal_id,
                "title": deal.get("TITLE") or f"Сделка {deal_id}",
                "manager": manager_name(users, manager_id) if manager_id else "не назначен",
                "stage": item.get("STAGE_ID"),
                "reason": item.get("STAGE_SEMANTIC_ID") or item.get("STAGE_ID"),
                "created_time": item.get("CREATED_TIME"),
            }
        )
    return rejections


def _feed_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _deal_is_spam(deal: dict[str, Any]) -> bool:
    """Сделка помечена причиной отказа «СПАМ» (UF_CRM_1771495464 = 8588)."""
    value = deal.get(REASON_FIELD)
    if isinstance(value, (list, tuple)):
        return SPAM_REASON_ID in [str(x) for x in value]
    return str(value) == SPAM_REASON_ID


def build_day_feed(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Лента событий дня (встречи/брифы/КП/созданные сделки) для summary_json —
    чтобы архивный /today показывал ленту за прошлый день. Скоуп ОП+ТМ, СПАМ
    исключаются. Имена резолвит веб по manager_id."""
    roles = raw.get("user_roles") or {}

    def in_scope(uid: int | None) -> bool:
        role = (roles.get(str(uid)) or "").lower()
        return any(k in role for k in _SALES_TM_ROLE_KEYS)

    feed: list[dict[str, Any]] = []
    for m in raw.get("meet_day") or []:
        uid = _feed_int(m.get("assignedById"))
        if in_scope(uid):
            feed.append({"kind": "meeting", "manager_id": uid, "title": m.get("title") or "Встреча", "at": str(m.get("ufCrm16_1751009238") or "")})
    for b in raw.get("briefs") or []:
        uid = _feed_int(b.get("assignedById"))
        if in_scope(uid):
            feed.append({"kind": "brief", "manager_id": uid, "title": b.get("title") or "Бриф", "at": str(b.get("createdTime") or "")})
    for k in raw.get("kp") or []:
        uid = _feed_int(k.get("assignedById"))
        if in_scope(uid):
            feed.append({"kind": "kp", "manager_id": uid, "title": k.get("title") or "КП", "at": str(k.get("updatedTime") or "")})
    for d in raw.get("deals_created") or []:
        if _deal_is_spam(d):
            continue
        uid = _feed_int(d.get("ASSIGNED_BY_ID"))
        if in_scope(uid):
            feed.append({"kind": "deal", "manager_id": uid, "title": d.get("TITLE") or "Сделка", "at": str(d.get("DATE_CREATE") or "")})
    feed.sort(key=lambda e: e["at"], reverse=True)
    return feed
