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

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
CLOSED_STAGES = {LOSE_STAGE_38, "C50:LOSE", "C50:APOLOGY"}
ALLOWED_RESIDUAL_PROVIDERS = {
    "VOXIMPLANT_CALL",
    "CRM_SMS",
    "IMOPENLINES_SESSION",
    "CRM_OPENLINES",
    "CRM_TODO",
    "REST_APP",
}


def run(bx: BitrixClient, sheets: SheetsClient) -> dict:
    now = datetime.now(MOSCOW_TZ)
    ok = 0
    failed = 0
    _, inventory_rows = read_inventory(sheets)
    transferred_activity_ids = _transferred_activity_ids(inventory_rows)
    for row_number, group in read_groups(sheets):
        if group.status != Status.MERGED:
            continue
        errors = _verify_group(bx, group, transferred_activity_ids, inventory_rows)
        if errors:
            failed += 1
            update_group(sheets, row_number, replace(group, status=Status.FAILED, last_action_at=now, error_message="; ".join(errors)[:500]))
        else:
            ok += 1
            update_group(sheets, row_number, replace(group, status=Status.DONE, last_action_at=now, error_message=None))
    print(f"[verify] DONE: {ok}; FAILED: {failed}")
    return {"done": ok, "failed": failed}


def _verify_group(
    bx: BitrixClient,
    group,
    transferred_activity_ids: set[str],
    inventory_rows: list[tuple[int, dict[str, str]]] | None = None,
) -> list[str]:
    errors: list[str] = []
    winner_contacts = len(bx.list_deal_contacts(group.winner_id)) if group.winner_id else 0
    winner_timeline = bx.list_deal_timeline_comments(group.winner_id) if group.winner_id else []
    if group.n_timeline_planned > 0 and not any(
        TIMELINE_TRANSFER_MARKER in str(c.get("COMMENT") or "")
        for c in winner_timeline
    ):
        errors.append("у WINNER нет timeline-маркера переноса")
    expected_new_contacts = (
        _expected_new_contacts(group, inventory_rows)
        if inventory_rows is not None
        else group.n_contacts_planned
    )
    if winner_contacts < expected_new_contacts:
        errors.append(
            f"контактов на WINNER {winner_contacts} меньше реально перенесённых {expected_new_contacts}"
        )
    for loser_id in group.loser_ids:
        deal = bx.get_deal(loser_id)
        if not deal:
            errors.append(f"LOSER #{loser_id} не найден")
            continue
        if deal.get("STAGE_ID") not in CLOSED_STAGES:
            errors.append(f"LOSER #{loser_id} не закрыт в дубль/закрытую стадию")
        active = [
            a for a in bx.list_deal_activities(loser_id)
            if not _allowed_residual_activity(a, transferred_activity_ids)
        ]
        if active:
            errors.append(f"LOSER #{loser_id} имеет неперенесённые активности: {len(active)}")
    return errors


def _transferred_activity_ids(rows: list[tuple[int, dict[str, str]]]) -> set[str]:
    return {
        row.get("child_id", "")
        for _, row in rows
        if row.get("entity_type") == "activity" and row.get("transferred") == "1"
    }


def _expected_new_contacts(group, rows: list[tuple[int, dict[str, str]]]) -> int:
    losers = set(group.loser_ids)
    return sum(
        1
        for _, row in rows
        if row.get("company_id") == group.company_id
        and row.get("loser_id") in losers
        and row.get("entity_type") == "contact"
        and row.get("transferred") == "1"
        and row.get("note") != "already_linked"
    )


def _allowed_residual_activity(activity: dict, transferred_activity_ids: set[str]) -> bool:
    provider_id = str(activity.get("PROVIDER_ID") or "")
    if provider_id in ALLOWED_RESIDUAL_PROVIDERS:
        return True
    if (
        provider_id in {"TASKS", "CRM_TASKS_TASK"}
        and str(activity.get("COMPLETED") or "").upper() == "Y"
        and str(activity.get("ID") or "") in transferred_activity_ids
    ):
        return True
    return False
