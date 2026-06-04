"""Лёгкий сбор «Сегодня» (live): только быстрые метрики текущего дня —
звонки, встречи, КП, созданные сделки. БЕЗ Wazzup/транскриптов/LLM, чтобы
гонять часто (cron каждые ~20 мин). Имена резолвит веб по таблице users."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .collect import SEL_1048, _fetch_all, _range, collect_voximplant
from .transform import aggregate_calls, _to_int, parse_dt


def collect_live(today: date, bx=None) -> dict[str, Any]:
    d0, d1 = _range(today)
    calls = collect_voximplant(today, bx)
    meetings = _fetch_all(
        bx,
        "crm.item.list",
        {"entityTypeId": 1048, "filter": {">=ufCrm16_1751009238": d0, "<=ufCrm16_1751009238": d1}, "select": SEL_1048},
        idfield="id",
    )
    deals_created = _fetch_all(
        bx,
        "crm.deal.list",
        {
            "filter": {">=DATE_CREATE": d0, "<=DATE_CREATE": d1},
            "select": ["ID", "TITLE", "ASSIGNED_BY_ID", "CATEGORY_ID", "OPPORTUNITY", "DATE_CREATE"],
        },
    )
    kp = _fetch_all(
        bx,
        "crm.item.list",
        {"entityTypeId": 1106, "filter": {">=updatedTime": d0, "<=updatedTime": d1}, "select": ["id", "title", "assignedById", "updatedTime"]},
        idfield="id",
    )
    return {"calls": calls, "meetings": meetings, "deals_created": deals_created, "kp": kp}


def build_live_payload(today: date, raw: dict[str, Any], now: datetime) -> dict[str, Any]:
    call_stats = aggregate_calls(raw.get("calls") or [])
    meetings = raw.get("meetings") or []
    deals = raw.get("deals_created") or []
    kp = raw.get("kp") or []

    per: dict[int, dict[str, Any]] = {}

    def slot(uid: int | None) -> dict[str, Any] | None:
        if not uid:
            return None
        return per.setdefault(
            uid,
            {"manager_id": uid, "dials": 0, "answered": 0, "calls120": 0, "meetings": 0, "deals": 0, "kp": 0},
        )

    for uid, s in call_stats.items():
        slot(uid).update(
            dials=s.get("dials_total", 0), answered=s.get("calls_answered", 0), calls120=s.get("calls_120s_plus", 0)
        )
    meetings_done = 0
    for m in meetings:
        cell = slot(_to_int(m.get("assignedById")))
        if cell:
            cell["meetings"] += 1
        dt = parse_dt(m.get("ufCrm16_1751009238"))
        if dt and dt <= now:
            meetings_done += 1
    for d in deals:
        cell = slot(_to_int(d.get("ASSIGNED_BY_ID")))
        if cell:
            cell["deals"] += 1
    for k in kp:
        cell = slot(_to_int(k.get("assignedById")))
        if cell:
            cell["kp"] += 1

    managers = sorted(per.values(), key=lambda x: (x["meetings"], x["dials"]), reverse=True)
    totals = {
        "dials": sum(x["dials"] for x in managers),
        "answered": sum(x["answered"] for x in managers),
        "calls120": sum(x["calls120"] for x in managers),
        "meetings": len(meetings),
        "meetings_done": meetings_done,
        "kp": len(kp),
        "deals": len(deals),
    }

    # Лента активности: встречи + КП + созданные сделки (события с временем).
    feed: list[dict[str, Any]] = []
    for m in meetings:
        feed.append(
            {"kind": "meeting", "manager_id": _to_int(m.get("assignedById")), "title": m.get("title") or "Встреча",
             "at": str(m.get("ufCrm16_1751009238") or "")}
        )
    for k in kp:
        feed.append(
            {"kind": "kp", "manager_id": _to_int(k.get("assignedById")), "title": k.get("title") or "КП",
             "at": str(k.get("updatedTime") or "")}
        )
    for d in deals:
        feed.append(
            {"kind": "deal", "manager_id": _to_int(d.get("ASSIGNED_BY_ID")), "title": d.get("TITLE") or "Сделка",
             "at": str(d.get("DATE_CREATE") or "")}
        )
    feed.sort(key=lambda e: e["at"], reverse=True)

    return {"report_date": today.isoformat(), "totals": totals, "managers": managers, "feed": feed[:12]}
