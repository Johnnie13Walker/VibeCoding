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

        buckets[stage_label].append(
            {
                "stage_label": stage_label,
                "deal_id": _to_int(deal_id),
                "title": deal.get("TITLE") or str(deal_id),
                "manager_id": _to_int(deal.get("ASSIGNED_BY_ID")),
                "opportunity": float(deal.get("OPPORTUNITY") or 0),
                "age": age,
                "age_unit": "раб.дн" if mode == "w" else "кал.дн",
                "last_contact_days": min(activity_days, wazzup_days),
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
        if duration >= 120:
            stats[uid]["calls_120s_plus"] += 1
    return {uid: dict(counter) for uid, counter in stats.items()}


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
    manager_ids = set(calls)
    for key in ["meet_day", "meet_created_day", "briefs", "kp"]:
        manager_ids.update(_to_int(item.get("assignedById")) for item in raw.get(key, []))
    manager_ids.discard(None)

    meetings_set = Counter(_to_int(item.get("assignedById")) for item in raw.get("meet_created_day", []))
    meetings_held = Counter(_to_int(item.get("assignedById")) for item in raw.get("meet_day", []))
    briefs_created = Counter(_to_int(item.get("assignedById")) for item in raw.get("briefs", []))
    kp_sent = Counter(_to_int(item.get("assignedById")) for item in raw.get("kp", []))

    manager_activity = []
    for manager_id in sorted(manager_ids):
        call_stats = calls.get(manager_id, {})
        manager_activity.append(
            {
                "report_date": report_date,
                "manager_id": manager_id,
                "calls_total": call_stats.get("calls_total", 0),
                "calls_answered": call_stats.get("calls_answered", 0),
                "calls_120s_plus": call_stats.get("calls_120s_plus", 0),
                "dials_total": call_stats.get("dials_total", 0),
                "meetings_set": meetings_set[manager_id],
                "meetings_held": meetings_held[manager_id],
                "briefs_created": briefs_created[manager_id],
                "kp_sent": kp_sent[manager_id],
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
                    "manager_id": _to_int(item.get("assignedById")),
                    "amount": _to_float(
                        item.get("opportunity") or item.get("ufCrm20_1754044185200")
                    ),
                }
            )

    return {
        "deals_snapshot": deals_snapshot,
        "meetings": meetings,
        "manager_activity": manager_activity,
        "kp_briefs": kp_briefs,
    }


def _meeting_type(item: dict[str, Any]) -> str | None:
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
