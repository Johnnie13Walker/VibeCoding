"""Автовозврат отложенных LOSE-сделок в телемаркетинг."""
from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import (
    HOLD_MARKER_FLAG_FIELD,
    HOLD_REASON_COMMENT_FIELD,
    LOG_DIR,
    REVIVE_AUDIT_FIELD,
    REVIVE_NEXT_COMMUNICATION_FIELD,
    TELEMARKETING_ASSIGNEES,
    TELEMARKETING_REVIVE_MAX_PER_DEAL,
    TELEMARKETING_REVIVE_SOURCE_ID,
    TELEMARKETING_REVIVE_TARGET_STAGE,
    TELEMARKETING_REVIVED_FROM_LOSE_STAGE,
)
from .telemarketing_dedupe import _active_user_ids

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
DEAL_OWNER_TYPE_ID = 2
CSV_HEADERS = [
    "timestamp",
    "deal_id",
    "company_id",
    "old_assignee",
    "new_assignee",
    "due_date",
    "revive_count",
    "status",
    "error",
]


@dataclass
class ReviveOutcome:
    deal_id: str
    company_id: str
    old_assignee: str
    new_assignee: str
    due_date: str
    status: str
    skipped_reason: str = ""
    error: str = ""


def run(
    bx: BitrixClient,
    *,
    dry_run: bool = True,
    due_before: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Вернуть LOSE-сделки в NEW, если наступила дата следующей коммуникации."""
    due_before = due_before or _today_iso()
    candidates = [
        deal for deal in bx.list_revive_candidates(due_before=due_before)
        if _is_due(deal.get(REVIVE_NEXT_COMMUNICATION_FIELD), due_before)
    ]
    if limit:
        candidates = candidates[:limit]

    active_users = _active_user_ids(bx)
    outcomes: list[ReviveOutcome] = []
    rotation_index = 0

    for deal in candidates:
        outcome, used_rotation = _process_deal(
            bx,
            deal,
            dry_run=dry_run,
            due_before=due_before,
            active_user_ids=active_users,
            rotation_index=rotation_index,
        )
        if used_rotation:
            rotation_index += 1
        outcomes.append(outcome)

    summary = _summary(outcomes, dry_run=dry_run, due_before=due_before)
    summary["old_assignee_breakdown"] = dict(Counter(o.old_assignee for o in outcomes if o.old_assignee))
    summary["outcomes"] = [outcome.__dict__ for outcome in outcomes]
    return summary


def _process_deal(
    bx: BitrixClient,
    deal: dict[str, Any],
    *,
    dry_run: bool,
    due_before: str,
    active_user_ids: set[str],
    rotation_index: int,
) -> tuple[ReviveOutcome, bool]:
    deal_id = str(deal.get("ID") or "")
    company_id = str(deal.get("COMPANY_ID") or "")
    old_assignee = str(deal.get("ASSIGNED_BY_ID") or "")
    due_date = str(deal.get(REVIVE_NEXT_COMMUNICATION_FIELD) or "")

    if str(deal.get("STAGE_ID") or "") != TELEMARKETING_REVIVED_FROM_LOSE_STAGE:
        return ReviveOutcome(deal_id, company_id, old_assignee, "", due_date, "SKIPPED", "not_lose_stage"), False
    if _is_auto_rejected(deal):
        return ReviveOutcome(deal_id, company_id, old_assignee, "", due_date, "SKIPPED", "auto_rejected_skip"), False

    revive_count = _revive_count(deal)
    if revive_count >= TELEMARKETING_REVIVE_MAX_PER_DEAL:
        return (
            ReviveOutcome(
                deal_id,
                company_id,
                old_assignee,
                "",
                due_date,
                "LIMIT_REACHED",
                f"revived {TELEMARKETING_REVIVE_MAX_PER_DEAL}+ times",
            ),
            False,
        )

    new_assignee, used_rotation = _resolve_revive_assignee(old_assignee, active_user_ids, rotation_index)
    if dry_run:
        return ReviveOutcome(deal_id, company_id, old_assignee, new_assignee, due_date, "DRY_RUN"), used_rotation

    try:
        _apply_revive(bx, deal, new_assignee)
        outcome = ReviveOutcome(deal_id, company_id, old_assignee, new_assignee, due_date, "REVIVED")
        _append_audit_row(outcome, revive_count=_revive_count(deal) + 1)
        return outcome, used_rotation
    except Exception as exc:  # noqa: BLE001
        return ReviveOutcome(deal_id, company_id, old_assignee, new_assignee, due_date, "FAILED", error=str(exc)[:200]), used_rotation


def _apply_revive(bx: BitrixClient, deal: dict[str, Any], new_assignee: str) -> None:
    fields = {
        "STAGE_ID": TELEMARKETING_REVIVE_TARGET_STAGE,
        "CLOSED": "N",
        "SOURCE_ID": TELEMARKETING_REVIVE_SOURCE_ID,
        "ASSIGNED_BY_ID": new_assignee,
        REVIVE_AUDIT_FIELD: _build_audit_text(deal),
    }
    bx.update_deal(str(deal.get("ID") or ""), fields, params={"REGISTER_SONET_EVENT": "Y"})
    reason = str(deal.get(HOLD_REASON_COMMENT_FIELD) or "").strip()[:200]
    due = str(deal.get(REVIVE_NEXT_COMMUNICATION_FIELD) or "").strip()
    bx.add_timeline_comment(
        owner_type_id=DEAL_OWNER_TYPE_ID,
        owner_id=str(deal.get("ID") or ""),
        text=f"[auto-revive] возврат из ОТЛОЖЕНО (дата касания {due}). Причина: {reason or '—'}",
    )


def _resolve_revive_assignee(old_assignee: str, active_user_ids: set[str], rotation_index: int) -> tuple[str, bool]:
    assignee_ids = [str(item[0]) for item in TELEMARKETING_ASSIGNEES]
    active = active_user_ids or set(assignee_ids)
    current = str(old_assignee or "").strip()
    if current in assignee_ids:
        for assignee_id in assignee_ids:
            if assignee_id != current and assignee_id in active:
                return assignee_id, False
    available = [assignee_id for assignee_id in assignee_ids if assignee_id in active] or assignee_ids
    if not available:
        return "", True
    return available[rotation_index % len(available)], True


def _is_auto_rejected(deal: dict[str, Any]) -> bool:
    value = deal.get(HOLD_MARKER_FLAG_FIELD)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().upper() in {"1", "Y", "TRUE"}


def _revive_count(deal: dict[str, Any]) -> int:
    desc = str(deal.get(REVIVE_AUDIT_FIELD) or "")
    matches = re.findall(r"#(\d+)", desc)
    return int(matches[-1]) if matches else 0


def _build_audit_text(deal: dict[str, Any]) -> str:
    prev = str(deal.get(REVIVE_AUDIT_FIELD) or "").strip()
    new_line = f"auto-revive {_today_iso()} #{_revive_count(deal) + 1}"
    return f"{prev}; {new_line}" if prev else new_line


def _is_due(raw_due: Any, due_before: str) -> bool:
    due = _date_from_value(raw_due)
    if not due:
        return False
    return due <= date.fromisoformat(due_before)


def _date_from_value(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def _today_iso() -> str:
    return datetime.now(MOSCOW_TZ).date().isoformat()


def _summary(outcomes: list[ReviveOutcome], *, dry_run: bool, due_before: str) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "due_before": due_before,
        "examined": len(outcomes),
        "revived": sum(1 for outcome in outcomes if outcome.status == "REVIVED"),
        "dry_run_updates": sum(1 for outcome in outcomes if outcome.status == "DRY_RUN"),
        "skipped": sum(1 for outcome in outcomes if outcome.status == "SKIPPED"),
        "limit_reached": sum(1 for outcome in outcomes if outcome.status == "LIMIT_REACHED"),
        "failed": sum(1 for outcome in outcomes if outcome.status == "FAILED"),
    }


def _append_audit_row(outcome: ReviveOutcome, *, revive_count: int) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "auto_revive_lose.csv"
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(MOSCOW_TZ).isoformat(timespec="seconds"),
                "deal_id": outcome.deal_id,
                "company_id": outcome.company_id,
                "old_assignee": outcome.old_assignee,
                "new_assignee": outcome.new_assignee,
                "due_date": outcome.due_date,
                "revive_count": str(revive_count),
                "status": outcome.status,
                "error": outcome.error,
            }
        )

