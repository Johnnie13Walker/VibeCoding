"""Read-only verify — проверка инвариантов после merge."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient
from ..config import LOSE_STAGE_38, TIMELINE_TRANSFER_MARKER
from ..sheet_store import read_groups, read_inventory, update_group
from ..sheets_client import SheetsClient
from ..state import Status
from .transfer import NOT_TRANSFERABLE_PROVIDERS

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
CLOSED_STAGES = {LOSE_STAGE_38, "C50:LOSE", "C50:APOLOGY"}


def run(bx: BitrixClient, sheets: SheetsClient) -> dict:
    now = datetime.now(MOSCOW_TZ)
    ok = 0
    failed = 0
    _, inventory_rows = read_inventory(sheets)
    allowed_residual_activity_ids = _allowed_residual_activity_ids(inventory_rows)
    for row_number, group in read_groups(sheets):
        if group.status != Status.MERGED:
            continue
        errors = _verify_group(bx, group, allowed_residual_activity_ids, inventory_rows)
        if errors:
            failed += 1
            update_group(sheets, row_number, replace(group, status=Status.FAILED, last_action_at=now, error_message="; ".join(errors)[:500]))
        else:
            ok += 1
            update_group(sheets, row_number, replace(group, status=Status.DONE, last_action_at=now, error_message=None))
    print(f"[verify] DONE: {ok}; FAILED: {failed}")
    return {"done": ok, "failed": failed}


def _verify_group(bx: BitrixClient, group, allowed_residual_activity_ids: set[str], inventory_rows) -> list[str]:
    errors: list[str] = []
    winner_contacts = len(bx.list_deal_contacts(group.winner_id)) if group.winner_id else 0
    winner_timeline = bx.list_deal_timeline_comments(group.winner_id) if group.winner_id else []
    if group.n_timeline_planned > 0 and not any(
        TIMELINE_TRANSFER_MARKER in str(c.get("COMMENT") or "") for c in winner_timeline
    ):
        errors.append("у WINNER нет timeline-маркера переноса")
    expected_new_contacts = _expected_new_contacts(inventory_rows, group)
    if winner_contacts < expected_new_contacts:
        errors.append(f"контактов на WINNER {winner_contacts} меньше реально перенесённых {expected_new_contacts}")
    for loser_id in group.loser_ids:
        deal = bx.get_deal(loser_id)
        if not deal:
            errors.append(f"LOSER #{loser_id} не найден")
            continue
        if deal.get("STAGE_ID") not in CLOSED_STAGES:
            errors.append(f"LOSER #{loser_id} не закрыт в дубль/закрытую стадию")
        active = [
            a for a in bx.list_deal_activities(loser_id)
            if not _allowed_residual_activity(a, allowed_residual_activity_ids)
        ]
        if active:
            errors.append(f"LOSER #{loser_id} имеет неперенесённые активности: {len(active)}")
    return errors


def _expected_new_contacts(inventory_rows, group) -> int:
    expected_new = 0
    loser_ids = set(group.loser_ids)
    for _, row in inventory_rows:
        if row.get("company_id") != group.company_id:
            continue
        if row.get("loser_id") not in loser_ids:
            continue
        if row.get("entity_type") != "contact":
            continue
        if row.get("transferred") == "1" and row.get("note") != "already_linked":
            expected_new += 1
    return expected_new


def _allowed_residual_activity_ids(rows) -> set[str]:
    return {
        row.get("child_id", "")
        for _, row in rows
        if row.get("entity_type") == "activity"
        and (row.get("transferred") == "1" or row.get("note") in {"not_transferable", "not_transferable_dynamic"})
    }


def _allowed_residual_activity(activity: dict, allowed_residual_activity_ids: set[str]) -> bool:
    provider_id = str(activity.get("PROVIDER_ID") or "")
    if provider_id in NOT_TRANSFERABLE_PROVIDERS:
        return True
    if (
        provider_id in {"TASKS", "CRM_TASKS_TASK"}
        and str(activity.get("COMPLETED") or "").upper() == "Y"
        and str(activity.get("ID") or "") in allowed_residual_activity_ids
    ):
        return True
    if str(activity.get("ID") or "") in allowed_residual_activity_ids:
        return True
    return False
