"""Read-only детектор застрявших сделок телемаркетинга."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import TELEMARKETING_CATEGORY_ID

PREPARATION_ALERT_DAYS = 21
WZ4KQE_ALERT_DAYS_AFTER_MEETING = 14
PREPARATION_STAGE_ID = "C50:PREPARATION"
WZ4KQE_STAGE_ID = "C50:UC_WZ4KQE"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


@dataclass
class StuckDeal:
    deal_id: str
    title: str
    assignee: str
    stage_id: str
    days_stuck: int
    reason: str


def find_stuck_preparation(
    bx: Any,
    *,
    threshold_days: int = PREPARATION_ALERT_DAYS,
    today: date | None = None,
) -> list[StuckDeal]:
    today = today or datetime.now(MOSCOW_TZ).date()
    deals = _list_open_stage(bx, PREPARATION_STAGE_ID)
    out = []
    for deal in deals:
        basis = _parse_date(deal.get("LAST_COMMUNICATION_TIME")) or _parse_date(deal.get("DATE_MODIFY"))
        if not basis:
            continue
        days = (today - basis).days
        if days > threshold_days:
            out.append(_stuck_deal(deal, days, "no_communication_21d"))
    return out


def find_stuck_wz4kqe(
    bx: Any,
    *,
    threshold_days: int = WZ4KQE_ALERT_DAYS_AFTER_MEETING,
    today: date | None = None,
) -> list[StuckDeal]:
    today = today or datetime.now(MOSCOW_TZ).date()
    deals = _list_open_stage(bx, WZ4KQE_STAGE_ID)
    out = []
    for deal in deals:
        meeting_date = _parse_date(deal.get("MEETING_DATE")) or _parse_date(deal.get("CLOSEDATE"))
        if not meeting_date:
            continue
        days = (today - meeting_date).days
        if days > threshold_days:
            out.append(_stuck_deal(deal, days, "meeting_overdue_14d"))
    return out


def run(bx: Any, *, dry_run: bool = True, today: date | None = None) -> dict[str, Any]:
    prep = find_stuck_preparation(bx, today=today)
    wz4 = find_stuck_wz4kqe(bx, today=today)
    return {
        "dry_run": dry_run,
        "preparation_stuck_count": len(prep),
        "wz4kqe_stuck_count": len(wz4),
        "preparation_stuck": [asdict(deal) for deal in prep],
        "wz4kqe_stuck": [asdict(deal) for deal in wz4],
    }


def _list_open_stage(bx: Any, stage_id: str) -> list[dict[str, Any]]:
    if not hasattr(bx, "list_deals_by_stages"):
        return []
    return list(
        bx.list_deals_by_stages(
            category_id=int(TELEMARKETING_CATEGORY_ID),
            stage_ids=[stage_id],
            closed="N",
            select=[
                "ID",
                "TITLE",
                "STAGE_ID",
                "ASSIGNED_BY_ID",
                "DATE_MODIFY",
                "LAST_COMMUNICATION_TIME",
                "CLOSEDATE",
                "MEETING_DATE",
            ],
        )
    )


def _stuck_deal(deal: dict[str, Any], days: int, reason: str) -> StuckDeal:
    return StuckDeal(
        deal_id=str(deal.get("ID") or ""),
        title=str(deal.get("TITLE") or ""),
        assignee=str(deal.get("ASSIGNED_BY_ID") or ""),
        stage_id=str(deal.get("STAGE_ID") or ""),
        days_stuck=days,
        reason=reason,
    )


def _parse_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:10]).date()
    except ValueError:
        return None
