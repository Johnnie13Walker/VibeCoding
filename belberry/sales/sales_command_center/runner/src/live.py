"""Лёгкий сбор «Сегодня» (live): только быстрые метрики текущего дня —
звонки, встречи, брифы, КП, созданные сделки. БЕЗ Wazzup/транскриптов/LLM,
чтобы гонять часто (cron каждые ~20 мин). Имена резолвит веб по таблице users."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .collect import SEL_1048, _fetch_all, _range, collect_voximplant
from .service_maps import BRIEF_SERVICE_FIELD, KP_SERVICE_FIELD, brief_service, kp_service
from .transform import aggregate_calls, parse_dt, _to_int, _meeting_type
from .timeutil import MSK

# Годовая выручка компании пишется обогащением на сделку (3 формы поля). Берём первую
# непустую: число → деньги (amount|CUR) → строка. Нужна для ТМ-брифингов на /today.
DEAL_REVENUE_FIELDS = ("UF_CRM_1774971054", "UF_CRM_67B35193BAFB4", "UF_CRM_5E79DD26CB010")


def _parse_revenue(deal: dict[str, Any]) -> float | None:
    for key in DEAL_REVENUE_FIELDS:
        val = deal.get(key)
        if val in (None, "", 0, "0"):
            continue
        s = str(val).split("|", 1)[0]  # money: "amount|RUB"
        cleaned = "".join(ch for ch in s if ch.isdigit() or ch == ".")
        try:
            num = float(cleaned)
        except ValueError:
            continue
        if num > 0:
            return num
    return None


# СПАМ-сделка: причина отказа UF_CRM_1771495464 = 8588 (как в дневном отчёте).
SPAM_REASON_FIELD = "UF_CRM_1771495464"
SPAM_REASON_ID = "8588"


def _deal_is_spam(deal: dict[str, Any]) -> bool:
    value = deal.get(SPAM_REASON_FIELD)
    if isinstance(value, (list, tuple)):
        return SPAM_REASON_ID in [str(x) for x in value]
    return str(value) == SPAM_REASON_ID


def kp_status(stage_id: Any) -> str:
    """Статус КП (1106) по стадии: SUCCESS=Готово (получено), FAIL=Не актуально
    (отклонено), иначе в работе."""
    code = str(stage_id or "").rsplit(":", 1)[-1].upper()
    if code == "SUCCESS":
        return "success"
    if code == "FAIL":
        return "rejected"
    return "progress"


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
    # Встречи, НАЗНАЧЕННЫЕ сегодня (по дате создания) — даже если сама встреча на
    # будущую дату. Без этого «назначено сегодня на потом» не видно в /today.
    meetings_set = _fetch_all(
        bx, "crm.item.list",
        {"entityTypeId": 1048, "filter": {">=createdTime": d0, "<=createdTime": d1}, "select": SEL_1048},
        idfield="id",
    )
    # Встречи, ТРОНУТЫЕ сегодня (по дате обновления) — ловим перенесённые: встреча
    # существовала раньше и сегодня её передвинули на другую дату. Без этого запроса
    # такая встреча выпадает из /today (не сегодня по дате, не создана сегодня).
    meetings_upd = _fetch_all(
        bx, "crm.item.list",
        {"entityTypeId": 1048, "filter": {">=updatedTime": d0, "<=updatedTime": d1}, "select": SEL_1048},
        idfield="id",
    )
    deals_created = _fetch_all(
        bx, "crm.deal.list",
        {"filter": {">=DATE_CREATE": d0, "<=DATE_CREATE": d1},
         "select": ["ID", "TITLE", "ASSIGNED_BY_ID", "CATEGORY_ID", "OPPORTUNITY", "DATE_CREATE", SPAM_REASON_FIELD]},
    )
    kp = _fetch_all(
        bx, "crm.item.list",
        {"entityTypeId": 1106, "filter": {">=updatedTime": d0, "<=updatedTime": d1},
         "select": ["id", "title", "assignedById", "parentId2", "stageId", KP_SERVICE_FIELD, "updatedTime"]},
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
    # Годовая выручка компании по сделкам встреч (нужна для ТМ-брифингов).
    deal_ids = sorted({
        did for m in [*meetings, *meetings_set, *meetings_upd]
        if (did := _to_int(m.get("parentId2")))
    })
    meeting_deal_revenue: dict[int, float] = {}
    if deal_ids:
        rev_rows = _fetch_all(
            bx, "crm.deal.list",
            {"filter": {"@ID": deal_ids}, "select": ["ID", *DEAL_REVENUE_FIELDS]},
        )
        for d in rev_rows:
            did = _to_int(d.get("ID"))
            rev = _parse_revenue(d)
            if did and rev:
                meeting_deal_revenue[did] = rev
    return {"calls": calls, "meetings": meetings, "meetings_set": meetings_set,
            "meetings_upd": meetings_upd,
            "deals_created": deals_created, "kp": kp, "briefs": briefs, "activities": activities,
            "meeting_deal_revenue": meeting_deal_revenue}


def build_live_payload(today: date, raw: dict[str, Any], now: datetime) -> dict[str, Any]:
    call_stats = aggregate_calls(raw.get("calls") or [])
    meetings = raw.get("meetings") or []
    deals = raw.get("deals_created") or []
    kp = raw.get("kp") or []
    briefs = raw.get("briefs") or []
    revenue_map = raw.get("meeting_deal_revenue") or {}

    per: dict[int, dict[str, Any]] = {}

    def slot(uid: int | None) -> dict[str, Any] | None:
        if not uid:
            return None
        return per.setdefault(
            uid,
            {"manager_id": uid, "dials": 0, "answered": 0, "calls60": 0, "meetings": 0,
             "m_held": 0, "m_scheduled": 0, "m_cancelled": 0, "m_set": 0, "briefs": 0, "deals": 0, "kp": 0, "emails": 0},
        )

    for uid, s in call_stats.items():
        slot(uid).update(dials=s.get("dials_total", 0), answered=s.get("calls_answered", 0), calls60=s.get("calls_60s_plus", 0))

    # meetings = встречи с датой=сегодня (проведено/отменено сегодня);
    # meetings_set = встречи, СОЗДАННЫЕ сегодня (назначено сегодня, дата любая);
    # meetings_upd = встречи, ОБНОВЛЁННЫЕ сегодня (ловим перенесённые).
    meetings_set = raw.get("meetings_set") or []
    meetings_upd = raw.get("meetings_upd") or []
    today_ids = {_to_int(m.get("id")) for m in meetings}
    set_ids = {_to_int(m.get("id")) for m in meetings_set}
    upd_ids = {_to_int(m.get("id")) for m in meetings_upd}
    merged: dict[Any, dict[str, Any]] = {}
    for m in [*meetings, *meetings_set, *meetings_upd]:
        merged.setdefault(_to_int(m.get("id")), m)

    meetings_list = []
    for mid, m in merged.items():
        conductor = _to_int(m.get("assignedById"))   # кто проводит встречу
        creator = _to_int(m.get("createdBy"))          # кто назначил встречу
        st = meeting_status(m.get("stageId"))  # held / scheduled / cancelled
        set_today = mid in set_ids
        # «Тронута сегодня» = пришла только из апдейт-запроса (не из сегодняшних/созданных).
        upd_only = mid in upd_ids and mid not in set_ids and mid not in today_ids
        m_dt = parse_dt(m.get("ufCrm16_1751009238"))
        m_date = m_dt.astimezone(MSK).date() if m_dt else None
        # Перенесена сегодня: тронута сегодня И её (новая) дата ≥ сегодня — актуальный
        # перенос вперёд. Прошлую проведённую встречу, которую сегодня просто
        # отредактировали (дата < сегодня), переносом НЕ считаем — иначе «перенесена
        # на <её же прошлая дата>» (эвристика: Bitrix не отдаёт историю даты по REST).
        moved_today = upd_only and m_date is not None and m_date >= today
        # Тронутая сегодня прошлая встреча (правка, не перенос) к /today не относится —
        # не показываем и не учитываем в счётчиках дня.
        if upd_only and not moved_today:
            continue
        # «Назначено сегодня (ещё не проведено)» засчитываем СОЗДАТЕЛЮ (телемаркетолог),
        # проведено/отменено — ответственному (продавец, кто реально провёл).
        scheduled_today = set_today and st == "scheduled" and mid not in today_ids
        owner = creator if scheduled_today else conductor
        cell = slot(owner)
        if cell:
            cell["meetings"] += 1
            if mid in today_ids and st == "held":
                cell["m_held"] += 1
            elif mid in today_ids and st == "cancelled":
                cell["m_cancelled"] += 1
            elif scheduled_today:
                cell["m_scheduled"] += 1  # назначено сегодня (ещё не проведено)
        # «Назначено за день» — все встречи, СОЗДАННЫЕ сегодня, в зачёт создателю
        # (вкл. проведённые в тот же день); по роли создателя считаем «назначено ТМ».
        if set_today and creator:
            cset = slot(creator)
            if cset:
                cset["m_set"] += 1
        deal_id = _to_int(m.get("parentId2"))
        meetings_list.append(
            {"id": mid, "title": m.get("title") or "Встреча", "manager_id": owner,
             "at": str(m.get("ufCrm16_1751009238") or ""), "status": st,
             "deal_id": deal_id, "set_today": set_today, "moved_today": moved_today,
             "type": _meeting_type(m), "created_by": creator,
             "company_revenue": revenue_map.get(deal_id)}
        )

    briefs_list = []
    for b in briefs:
        uid = _to_int(b.get("assignedById"))
        cell = slot(uid)
        if cell:
            cell["briefs"] += 1
        service = brief_service(b)
        briefs_list.append(
            {"id": _to_int(b.get("id")), "title": b.get("title") or "Бриф", "manager_id": uid,
             "deal_id": _to_int(b.get("parentId2")), "service": service}
        )

    kp_list = []
    for k in kp:
        uid = _to_int(k.get("assignedById"))
        service = kp_service(k)
        kp_list.append(
            {"id": _to_int(k.get("id")), "title": k.get("title") or "КП", "manager_id": uid,
             "deal_id": _to_int(k.get("parentId2")), "service": service,
             "status": kp_status(k.get("stageId"))}
        )

    # СПАМ-сделки в «создано» не считаем (как в дневном отчёте).
    deals_real = [d for d in deals if not _deal_is_spam(d)]
    deals_spam = len(deals) - len(deals_real)
    for d in deals_real:
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
        "meetings": len(merged),
        "meetings_held": sum(x["m_held"] for x in managers),
        "meetings_scheduled": sum(x["m_scheduled"] for x in managers),
        "meetings_cancelled": sum(x["m_cancelled"] for x in managers),
        "briefs": len(briefs),
        "kp": len(kp),
        "deals": len(deals_real),
        "deals_spam": deals_spam,
        "emails": sum(x["emails"] for x in managers),
    }

    # Лента активности: встречи + брифы + КП + созданные сделки (события с временем).
    feed: list[dict[str, Any]] = []
    for m in meetings:
        feed.append({"kind": "meeting", "id": _to_int(m.get("id")), "manager_id": _to_int(m.get("assignedById")),
                     "title": m.get("title") or "Встреча", "at": str(m.get("ufCrm16_1751009238") or "")})
    for b in briefs:
        feed.append({"kind": "brief", "id": _to_int(b.get("id")), "manager_id": _to_int(b.get("assignedById")),
                     "title": b.get("title") or "Бриф", "at": str(b.get("createdTime") or "")})
    for k in kp:
        feed.append({"kind": "kp", "id": _to_int(k.get("id")), "manager_id": _to_int(k.get("assignedById")),
                     "title": k.get("title") or "КП", "at": str(k.get("updatedTime") or "")})
    for d in deals_real:
        feed.append({"kind": "deal", "id": _to_int(d.get("ID")), "manager_id": _to_int(d.get("ASSIGNED_BY_ID")),
                     "title": d.get("TITLE") or "Сделка", "at": str(d.get("DATE_CREATE") or "")})
    feed.sort(key=lambda e: e["at"], reverse=True)

    meetings_list.sort(key=lambda e: e["at"], reverse=True)

    return {
        "report_date": today.isoformat(),
        "totals": totals,
        "managers": managers,
        "meetings_list": meetings_list,
        "briefs_list": briefs_list,
        "kp_list": kp_list,
        "feed": feed[:200],  # не режем агрессивно: фильтры Ленты (КП/Брифы/…) клиентские
    }
