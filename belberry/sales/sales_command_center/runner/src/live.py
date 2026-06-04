"""Лёгкий сбор «Сегодня» (live): только быстрые метрики текущего дня —
звонки, встречи, брифы, КП, созданные сделки. БЕЗ Wazzup/транскриптов/LLM,
чтобы гонять часто (cron каждые ~20 мин). Имена резолвит веб по таблице users."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .collect import SEL_1048, _fetch_all, _range, collect_voximplant
from .transform import aggregate_calls, _to_int

# Поле брифа (1056) «Список услуг» — enumeration ufCrm20_1753290430.
BRIEF_SERVICE_FIELD = "ufCrm20_1753290430"
SERVICE_MAP = {
    2722: "Дзен", 2724: "Копирайтинг", 2726: "Контекстная реклама", 2728: "GEO",
    2730: "SEO", 2732: "ORM", 2734: "SMM", 2736: "Разработка сайта",
    2738: "Техподдержка", 2740: "Лендинг", 2742: "Фирменный стиль", 9538: "AEO",
}


def meeting_status(stage_id: Any) -> str:
    """Статус встречи (1048) по стадии: SUCCESS→проведена, FAIL→отменена, иначе назначена."""
    code = str(stage_id or "").rsplit(":", 1)[-1].upper()
    if code == "SUCCESS":
        return "held"
    if code == "FAIL":
        return "cancelled"
    return "scheduled"


def collect_live(today: date, bx=None) -> dict[str, Any]:
    d0, d1 = _range(today)
    calls = collect_voximplant(today, bx)
    meetings = _fetch_all(
        bx, "crm.item.list",
        {"entityTypeId": 1048, "filter": {">=ufCrm16_1751009238": d0, "<=ufCrm16_1751009238": d1}, "select": SEL_1048},
        idfield="id",
    )
    deals_created = _fetch_all(
        bx, "crm.deal.list",
        {"filter": {">=DATE_CREATE": d0, "<=DATE_CREATE": d1},
         "select": ["ID", "TITLE", "ASSIGNED_BY_ID", "CATEGORY_ID", "OPPORTUNITY", "DATE_CREATE"]},
    )
    kp = _fetch_all(
        bx, "crm.item.list",
        {"entityTypeId": 1106, "filter": {">=updatedTime": d0, "<=updatedTime": d1},
         "select": ["id", "title", "assignedById", "updatedTime"]},
        idfield="id",
    )
    briefs = _fetch_all(
        bx, "crm.item.list",
        {"entityTypeId": 1056, "filter": {">=createdTime": d0, "<=createdTime": d1},
         "select": ["id", "title", "assignedById", "parentId2", BRIEF_SERVICE_FIELD, "createdTime"]},
        idfield="id",
    )
    activities = _fetch_all(
        bx, "crm.activity.list",
        {"filter": {">=CREATED": d0, "<=CREATED": d1},
         "select": ["ID", "TYPE_ID", "PROVIDER_ID", "DIRECTION", "RESPONSIBLE_ID", "AUTHOR_ID"]},
    )
    return {"calls": calls, "meetings": meetings, "deals_created": deals_created, "kp": kp, "briefs": briefs, "activities": activities}


def build_live_payload(today: date, raw: dict[str, Any], now: datetime) -> dict[str, Any]:
    call_stats = aggregate_calls(raw.get("calls") or [])
    meetings = raw.get("meetings") or []
    deals = raw.get("deals_created") or []
    kp = raw.get("kp") or []
    briefs = raw.get("briefs") or []

    per: dict[int, dict[str, Any]] = {}

    def slot(uid: int | None) -> dict[str, Any] | None:
        if not uid:
            return None
        return per.setdefault(
            uid,
            {"manager_id": uid, "dials": 0, "answered": 0, "calls60": 0, "meetings": 0,
             "m_held": 0, "m_scheduled": 0, "m_cancelled": 0, "briefs": 0, "deals": 0, "kp": 0, "emails": 0},
        )

    for uid, s in call_stats.items():
        slot(uid).update(dials=s.get("dials_total", 0), answered=s.get("calls_answered", 0), calls60=s.get("calls_60s_plus", 0))

    meetings_list = []
    for m in meetings:
        uid = _to_int(m.get("assignedById"))
        cell = slot(uid)
        st = meeting_status(m.get("stageId"))  # held / scheduled / cancelled
        if cell:
            cell["meetings"] += 1
            cell[f"m_{st}"] += 1
        meetings_list.append(
            {"id": _to_int(m.get("id")), "title": m.get("title") or "Встреча", "manager_id": uid,
             "at": str(m.get("ufCrm16_1751009238") or ""), "status": st, "deal_id": _to_int(m.get("parentId2"))}
        )

    briefs_list = []
    for b in briefs:
        uid = _to_int(b.get("assignedById"))
        cell = slot(uid)
        if cell:
            cell["briefs"] += 1
        service = SERVICE_MAP.get(_to_int(b.get(BRIEF_SERVICE_FIELD)) or 0, "")
        briefs_list.append(
            {"id": _to_int(b.get("id")), "title": b.get("title") or "Бриф", "manager_id": uid,
             "deal_id": _to_int(b.get("parentId2")), "service": service}
        )

    for d in deals:
        cell = slot(_to_int(d.get("ASSIGNED_BY_ID")))
        if cell:
            cell["deals"] += 1
    for k in kp:
        cell = slot(_to_int(k.get("assignedById")))
        if cell:
            cell["kp"] += 1

    # Отправленные письма — исходящие активности CRM_EMAIL (атрибуция автору письма).
    for a in raw.get("activities") or []:
        if str(a.get("PROVIDER_ID")) == "CRM_EMAIL" and str(a.get("DIRECTION")) in ("2", "O"):
            cell = slot(_to_int(a.get("AUTHOR_ID")) or _to_int(a.get("RESPONSIBLE_ID")))
            if cell:
                cell["emails"] += 1

    managers = sorted(per.values(), key=lambda x: (x["meetings"], x["briefs"], x["dials"]), reverse=True)
    totals = {
        "dials": sum(x["dials"] for x in managers),
        "answered": sum(x["answered"] for x in managers),
        "calls60": sum(x["calls60"] for x in managers),
        "meetings": len(meetings),
        "meetings_held": sum(x["m_held"] for x in managers),
        "meetings_scheduled": sum(x["m_scheduled"] for x in managers),
        "meetings_cancelled": sum(x["m_cancelled"] for x in managers),
        "briefs": len(briefs),
        "kp": len(kp),
        "deals": len(deals),
        "emails": sum(x["emails"] for x in managers),
    }

    # Лента активности: встречи + брифы + КП + созданные сделки (события с временем).
    feed: list[dict[str, Any]] = []
    for m in meetings:
        feed.append({"kind": "meeting", "manager_id": _to_int(m.get("assignedById")),
                     "title": m.get("title") or "Встреча", "at": str(m.get("ufCrm16_1751009238") or "")})
    for b in briefs:
        feed.append({"kind": "brief", "manager_id": _to_int(b.get("assignedById")),
                     "title": b.get("title") or "Бриф", "at": str(b.get("createdTime") or "")})
    for k in kp:
        feed.append({"kind": "kp", "manager_id": _to_int(k.get("assignedById")),
                     "title": k.get("title") or "КП", "at": str(k.get("updatedTime") or "")})
    for d in deals:
        feed.append({"kind": "deal", "manager_id": _to_int(d.get("ASSIGNED_BY_ID")),
                     "title": d.get("TITLE") or "Сделка", "at": str(d.get("DATE_CREATE") or "")})
    feed.sort(key=lambda e: e["at"], reverse=True)

    meetings_list.sort(key=lambda e: e["at"], reverse=True)

    return {
        "report_date": today.isoformat(),
        "totals": totals,
        "managers": managers,
        "meetings_list": meetings_list,
        "briefs_list": briefs_list,
        "feed": feed[:15],
    }
