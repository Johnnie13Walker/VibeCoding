from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

from .timeutil import MSK, prev_working_day

STAGE_RULES = {
    "C10:NEW": ("Квалификация", 2, "w"),
    "C10:PREPAYMENT_INVOIC": ("Подготовка БРИФа", 3, "w"),
    "C10:EXECUTING": ("Подготовка КП", 4, "w"),
    "C10:UC_KC7195": ("Подготовка договора", 5, "w"),
    "C10:FINAL_INVOICE": ("Догрев и переговоры", 14, "c"),
}
STAGE_ORDER = [
    "Квалификация",
    "Подготовка БРИФа",
    "Подготовка КП",
    "Догрев и переговоры",
    "Подготовка договора",
]


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=MSK)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=MSK)


def resolve_target_date(arg: str | None) -> date:
    return date.fromisoformat(arg) if arg else prev_working_day()


def working_days_between(a: date | datetime | None, b: date | datetime) -> int:
    if a is None:
        return 999
    start = a.date() if isinstance(a, datetime) else a
    end = b.date() if isinstance(b, datetime) else b
    days = 0
    current = start
    while current < end:
        if current.weekday() < 5:
            days += 1
        current = date.fromordinal(current.toordinal() + 1)
    return days


def calendar_days_between(a: date | datetime | None, b: date | datetime) -> int:
    if a is None:
        return 999
    start = a.date() if isinstance(a, datetime) else a
    end = b.date() if isinstance(b, datetime) else b
    return (end - start).days


def max_wazzup_date(comments: list[dict[str, Any]] | None) -> datetime | None:
    dates = [
        parse_dt(comment.get("CREATED") or comment.get("created") or comment.get("createdTime"))
        for comment in comments or []
    ]
    dates = [item for item in dates if item is not None]
    return max(dates) if dates else None


def last_comm_date(
    deal_id: Any,
    wazzup: dict[Any, list[dict[str, Any]]] | None,
    last_calls: dict[Any, str] | None,
) -> str | None:
    """Дата последней КОММУНИКАЦИИ С КЛИЕНТОМ по сделке (ISO YYYY-MM-DD) или None.

    Источник — только переписка с клиентом: звонки (обе стороны) + Wazzup. Внутренние
    комментарии/задачи не учитываем. Берём максимум из последнего звонка и последнего
    Wazzup-сообщения. Используется блоком «Тишина» (нет коммуникации >14 дней)."""
    key = str(deal_id)
    candidates: list[datetime] = []
    call_dt = parse_dt((last_calls or {}).get(key) or (last_calls or {}).get(deal_id))
    if call_dt is not None:
        candidates.append(call_dt)
    wz_dt = max_wazzup_date((wazzup or {}).get(key) or (wazzup or {}).get(deal_id))
    if wz_dt is not None:
        candidates.append(wz_dt)
    if not candidates:
        return None
    return max(candidates).date().isoformat()


def risk_reason(opportunity: float, age: int, threshold: int, last_contact_days: int) -> str:
    # У зависшей сделки age всегда > threshold (иначе она не попала бы в stale),
    # поэтому различаем причины по бюджету и давности касания, а «застрял» —
    # дефолт для сделок со свежим контактом, но без движения по стадии.
    if opportunity <= 0:
        return "нет бюджета"
    if last_contact_days >= 30:
        return "нет контакта"
    if last_contact_days >= 7:
        return f"молчит {last_contact_days} дн"
    return "застрял на стадии"


def age_level(age: int, threshold: int) -> str:
    if age >= 31:
        return "critical"
    if age >= threshold * 2:
        return "warning"
    return "normal"


def compute_stale_deals(
    deals_open: list[dict[str, Any]],
    now: datetime,
    wazzup: dict[Any, list[dict[str, Any]]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {label: [] for label in STAGE_ORDER}
    wazzup = wazzup or {}

    for deal in deals_open:
        stage = deal.get("STAGE_ID")
        if stage not in STAGE_RULES:
            continue
        stage_label, threshold, mode = STAGE_RULES[stage]
        moved_at = parse_dt(deal.get("MOVED_TIME"))
        age = (
            working_days_between(moved_at, now)
            if mode == "w"
            else calendar_days_between(moved_at, now)
        )
        if age <= threshold:
            continue

        deal_id = deal.get("ID")
        if not deal_id:
            continue
        activity_days = calendar_days_between(parse_dt(deal.get("LAST_ACTIVITY_TIME")), now)
        wazzup_dt = max_wazzup_date(wazzup.get(str(deal_id)) or wazzup.get(deal_id))
        wazzup_days = calendar_days_between(wazzup_dt, now)
        last_contact_days = min(activity_days, wazzup_days)
        opportunity = float(deal.get("OPPORTUNITY") or 0)

        buckets[stage_label].append(
            {
                "stage_label": stage_label,
                "deal_id": _to_int(deal_id),
                "title": deal.get("TITLE") or str(deal_id),
                "manager_id": _to_int(deal.get("ASSIGNED_BY_ID")),
                "opportunity": opportunity,
                "age": age,
                "age_unit": "раб.дн" if mode == "w" else "кал.дн",
                "last_contact_days": last_contact_days,
                "stage_threshold": threshold,
                "risk_reason": risk_reason(opportunity, age, threshold, last_contact_days),
                "age_level": age_level(age, threshold),
                "stage": stage,
            }
        )

    return {
        label: sorted(rows, key=lambda row: row["opportunity"], reverse=True)
        for label, rows in buckets.items()
        if rows
    }


def aggregate_calls(calls: list[dict[str, Any]]) -> dict[int, dict[str, int]]:
    stats: dict[int, Counter] = defaultdict(Counter)
    for call in calls:
        uid = _to_int(call.get("PORTAL_USER_ID"))
        if not uid:
            continue
        duration = _to_int(call.get("CALL_DURATION")) or 0
        stats[uid]["dials_total"] += 1
        stats[uid]["calls_total"] += 1
        stats[uid]["talk_seconds"] += duration
        if duration > 0:
            stats[uid]["calls_answered"] += 1
        if duration >= 60:
            stats[uid]["calls_60s_plus"] += 1
        if duration >= 120:
            stats[uid]["calls_120s_plus"] += 1
    return {uid: dict(counter) for uid, counter in stats.items()}


def aggregate_calls_hourly(calls: list[dict[str, Any]]) -> dict[tuple[int, int], dict[str, int]]:
    """Звонки по (PORTAL_USER_ID, час МСК): наборы/ответы/дозвоны ≥60с — для heatmap
    «когда берут трубку». Час берём из CALL_START_DATE (offset +03:00 = МСК)."""
    stats: dict[tuple[int, int], Counter] = defaultdict(Counter)
    for call in calls:
        uid = _to_int(call.get("PORTAL_USER_ID"))
        if not uid:
            continue
        dt = parse_dt(call.get("CALL_START_DATE"))
        if dt is None:
            continue
        duration = _to_int(call.get("CALL_DURATION")) or 0
        key = (uid, dt.hour)
        stats[key]["dials"] += 1
        if duration > 0:
            stats[key]["answered"] += 1
        if duration >= 60:
            stats[key]["calls60"] += 1
    return {key: dict(counter) for key, counter in stats.items()}


def aggregate_emails(activities: list[dict[str, Any]]) -> dict[int, int]:
    """Исходящие письма (CRM_EMAIL) по автору — для «Опер» (письмо = 5 мин)."""
    counts: Counter = Counter()
    for act in activities or []:
        if str(act.get("PROVIDER_ID")) != "CRM_EMAIL":
            continue
        if str(act.get("DIRECTION")) not in ("2", "O"):  # 2/O — исходящее
            continue
        uid = _to_int(act.get("AUTHOR_ID")) or _to_int(act.get("RESPONSIBLE_ID"))
        if uid:
            counts[uid] += 1
    return dict(counts)


def manager_name(users: dict[Any, str], uid: Any) -> str:
    return users.get(str(uid)) or users.get(uid) or str(uid)


def build_db_rows(raw: dict[str, Any], target_date: date, now: datetime) -> dict[str, list[dict[str, Any]]]:
    report_date = target_date.isoformat()
    stale = compute_stale_deals(raw.get("deals_open", []), now, raw.get("wazzup"))
    stale_by_deal = {
        item["deal_id"]: item
        for rows in stale.values()
        for item in rows
    }

    deals_snapshot = []
    for deal in raw.get("deals_open", []):
        deal_id = _to_int(deal.get("ID"))
        moved_at = parse_dt(deal.get("MOVED_TIME"))
        deals_snapshot.append(
            {
                "report_date": report_date,
                "deal_id": deal_id,
                "category_id": _to_int(deal.get("CATEGORY_ID")),
                "stage": deal.get("STAGE_ID"),
                "opportunity": _to_float(deal.get("OPPORTUNITY")),
                "manager_id": _to_int(deal.get("ASSIGNED_BY_ID")),
                "stuck_days": stale_by_deal.get(deal_id, {}).get("age"),
                "stage_entered": moved_at.date().isoformat() if moved_at else None,
                "last_comm_at": last_comm_date(deal_id, raw.get("wazzup"), raw.get("last_calls")),
                "title": deal.get("TITLE"),
                "company_id": _to_int(deal.get("COMPANY_ID")),
            }
        )

    meetings = [
        {
            "report_date": report_date,
            "meeting_id": _to_int(item.get("id")),
            "deal_id": _to_int(item.get("parentId2")),
            "meeting_type": _meeting_type(item),
            "status": item.get("stageId"),
            "manager_id": _to_int(item.get("assignedById")),
            # Создатель встречи (ТМ-телемаркетолог) — для событийных метрик ТМ:
            # «встречу назначил ТМ и она состоялась» считается запросом по этой таблице.
            "created_by": _to_int(item.get("createdBy")),
            "scheduled_at": parse_dt(item.get("ufCrm16_1751009238")),
            "analysis_json": None,
            "transcript_url": None,
            "transcript_text": None,
            "transcript_ok": None,
            "analysis_status": None,
        }
        for item in raw.get("meet_day", [])
    ]

    calls = aggregate_calls(raw.get("calls", []))
    emails_sent = aggregate_emails(raw.get("activities", []))

    # Брифы/КП засчитываем ОТВЕТСТВЕННОМУ ПО СДЕЛКЕ (а не исполнителю элемента брифа/КП):
    # элемент SP может висеть на другом человеке/быть переназначен, а кредит за бриф/КП
    # принадлежит владельцу сделки. Резолвим parentId2 → deal.ASSIGNED_BY_ID из открытых
    # сделок; если сделка не найдена (закрыта/вне выборки) — фолбэк на assignedById.
    deal_owner: dict[int, int | None] = {}
    for d in [*raw.get("deals_open", []), *raw.get("deals_created", [])]:
        did = _to_int(d.get("ID"))
        if did is not None:
            deal_owner[did] = _to_int(d.get("ASSIGNED_BY_ID"))
    # Явная карта владельцев родительских сделок брифов/КП (вкл. закрытые) — приоритет.
    for did, owner in (raw.get("deal_owners") or {}).items():
        di = _to_int(did)
        if di is not None:
            deal_owner[di] = _to_int(owner)

    def _deal_resp(item: dict[str, Any]) -> int | None:
        deal = _to_int(item.get("parentId2"))
        return deal_owner.get(deal) or _to_int(item.get("assignedById"))

    manager_ids = set(calls)
    manager_ids.update(emails_sent)
    for item in [*raw.get("meet_day", []), *raw.get("meet_created_day", [])]:
        manager_ids.add(_to_int(item.get("assignedById")))
    for item in [*raw.get("briefs", []), *raw.get("kp", [])]:
        manager_ids.add(_deal_resp(item))
    # Создатели встреч (ТМ) тоже должны получить строку активности.
    manager_ids.update(_to_int(item.get("createdBy")) for item in raw.get("meet_created_day", []))
    manager_ids.update(_to_int(item.get("createdBy")) for item in raw.get("meet_day", []))
    manager_ids.update(_to_int(d.get("ASSIGNED_BY_ID")) for d in raw.get("won_deals", []))
    manager_ids.discard(None)

    # Назначенную встречу засчитываем СОЗДАТЕЛЮ (createdBy), а не ответственному:
    # телемаркетолог создаёт встречу и ставит ответственным продавца — иначе работа
    # ТМ по назначению встреч уходит в зачёт ОП.
    meetings_set = Counter(_to_int(item.get("createdBy")) for item in raw.get("meet_created_day", []))
    meetings_held = Counter(_to_int(item.get("assignedById")) for item in raw.get("meet_day", []))
    briefs_created = Counter(_deal_resp(item) for item in raw.get("briefs", []))
    kp_sent = Counter(_deal_resp(item) for item in raw.get("kp", []))

    # «Сделки» = ВОШЕДШИЕ в воронку Продажи (запись C10:NEW в истории стадий за день).
    # История стадий неизменна и дата-точна (в отличие от текущего CATEGORY_ID сделки).
    #   вход   — сделка СОЗДАНА в этот же день (DATE_CREATE = день входа) → прямой вход в Продажи;
    #   холод  — создана раньше (переведена из ТМ в Продажи).
    deals_incoming_cnt: Counter = Counter()
    deals_cold_cnt: Counter = Counter()
    for d in raw.get("entered_deals", []):
        mid = _to_int(d.get("ASSIGNED_BY_ID"))
        if mid is None:
            continue
        created = parse_dt(d.get("DATE_CREATE"))
        if created is not None and created.date().isoformat() == report_date:
            deals_incoming_cnt[mid] += 1
        else:
            deals_cold_cnt[mid] += 1
    deals_created_cnt: Counter = Counter()
    for mid, n in deals_incoming_cnt.items():
        deals_created_cnt[mid] += n
    for mid, n in deals_cold_cnt.items():
        deals_created_cnt[mid] += n
    manager_ids.update(k for k in deals_created_cnt if k is not None)

    # Оплаты (выигранные сделки C10:WON) — шт и сумма по ответственному.
    deals_won_cnt: Counter = Counter()
    deals_won_amount: dict[int, float] = defaultdict(float)
    for d in raw.get("won_deals", []):
        mid = _to_int(d.get("ASSIGNED_BY_ID"))
        deals_won_cnt[mid] += 1
        deals_won_amount[mid] += _to_float(d.get("OPPORTUNITY")) or 0.0

    # Чаты Wazzup (messenger_dialogs) — посчитаны в collect_day, лежат в raw.
    # Сохраняем их в дневную статистику, чтобы они были видны в архиве за прошлый день.
    messenger: dict[int, int] = {}
    for mk, mv in (raw.get("messenger_dialogs") or {}).items():
        ki = _to_int(mk)
        if ki is not None:
            messenger[ki] = messenger.get(ki, 0) + int(mv or 0)
    manager_ids.update(messenger.keys())

    manager_activity = []
    for manager_id in sorted(manager_ids):
        call_stats = calls.get(manager_id, {})
        manager_activity.append(
            {
                "report_date": report_date,
                "manager_id": manager_id,
                "calls_total": call_stats.get("calls_total", 0),
                "calls_answered": call_stats.get("calls_answered", 0),
                "calls_60s_plus": call_stats.get("calls_60s_plus", 0),
                "calls_120s_plus": call_stats.get("calls_120s_plus", 0),
                "dials_total": call_stats.get("dials_total", 0),
                "talk_seconds": call_stats.get("talk_seconds", 0),
                "emails_sent": emails_sent.get(manager_id, 0),
                "messenger_dialogs": messenger.get(manager_id, 0),
                "meetings_set": meetings_set[manager_id],
                "meetings_held": meetings_held[manager_id],
                "briefs_created": briefs_created[manager_id],
                "kp_sent": kp_sent[manager_id],
                "deals_created_count": deals_created_cnt[manager_id],
                "deals_cold_count": deals_cold_cnt[manager_id],
                "deals_incoming_count": deals_incoming_cnt[manager_id],
                "deals_won_count": deals_won_cnt[manager_id],
                "deals_won_amount": round(deals_won_amount[manager_id], 2),
            }
        )

    kp_briefs = []
    for item_type, key in [("brief", "briefs"), ("kp", "kp")]:
        for item in raw.get(key, []):
            kp_briefs.append(
                {
                    "report_date": report_date,
                    "item_id": _to_int(item.get("id")),
                    "deal_id": _to_int(item.get("parentId2")),
                    "title": item.get("title"),
                    "item_type": item_type,
                    "stage": item.get("stageId"),
                    "manager_id": _deal_resp(item),  # ответственный по сделке, не исполнитель элемента
                    "amount": _to_float(
                        item.get("opportunity") or item.get("ufCrm20_1754044185200")
                    ),
                }
            )

    call_hourly = [
        {
            "report_date": report_date,
            "manager_id": uid,
            "hour": hour,
            "dials": s.get("dials", 0),
            "answered": s.get("answered", 0),
            "calls60": s.get("calls60", 0),
        }
        for (uid, hour), s in aggregate_calls_hourly(raw.get("calls", [])).items()
    ]

    return {
        "deals_snapshot": deals_snapshot,
        "meetings": meetings,
        "manager_activity": manager_activity,
        "kp_briefs": kp_briefs,
        "call_hourly": call_hourly,
    }


def build_post_meeting_comms(
    meet_day: list[dict[str, Any]] | None,
    wazzup: dict[Any, list[dict[str, Any]]] | None,
    activities: list[dict[str, Any]] | None,
) -> dict[str, str]:
    """Пост-встречная коммуникация по каждой встрече: Wazzup-сообщения и исходящие
    письма по сделке, отправленные ПОСЛЕ времени встречи. По ней LLM судит, отправлены
    ли клиенту итоги встречи. Ключ — meeting_id (str), как ждёт analyze_day."""
    emails_by_deal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for act in activities or []:
        if str(act.get("PROVIDER_ID")) != "CRM_EMAIL":
            continue
        if str(act.get("DIRECTION")) not in ("2", "O"):  # исходящее
            continue
        if str(act.get("OWNER_TYPE_ID")) != "2":  # сделка
            continue
        emails_by_deal[str(act.get("OWNER_ID"))].append(act)

    out: dict[str, str] = {}
    for item in meet_day or []:
        mid = item.get("id")
        if mid is None:
            continue
        deal = str(item.get("parentId2") or "")
        mtime = str(item.get("ufCrm16_1751009238") or "")
        parts: list[str] = []
        for c in (wazzup or {}).get(deal, []) or []:
            created = str(c.get("CREATED") or c.get("created") or "")
            if mtime and created <= mtime:
                continue
            body = str(c.get("COMMENT") or "").strip()
            if body:
                parts.append(f"[Wazzup {created}] {body}")
        for e in emails_by_deal.get(deal, []):
            created = str(e.get("CREATED") or "")
            if mtime and created <= mtime:
                continue
            parts.append(f"[Письмо {created}] тема: {e.get('SUBJECT') or ''}")
        out[str(mid)] = "\n".join(parts)[:4000]
    return out


# Структурное поле «тип встречи» в карточке SP 1048 (enum). Надёжнее названия:
# до марта 2026 встречи назывались доменом клиента, но поле заполнялось всегда.
MEETING_TYPE_FIELD = "ufCrm16_1751006460"
_MEETING_TYPE_BY_FIELD = {"2638": "briefing", "2640": "defense"}


def _meeting_type(item: dict[str, Any]) -> str | None:
    by_field = _MEETING_TYPE_BY_FIELD.get(str(item.get(MEETING_TYPE_FIELD)))
    if by_field:
        return by_field
    # Fallback на название, если структурное поле пустое/нестандартное.
    title = (item.get("title") or "").lower()
    if "защ" in title:
        return "defense"
    if "бриф" in title or "брифф" in title:
        return "briefing"
    return "other"


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
