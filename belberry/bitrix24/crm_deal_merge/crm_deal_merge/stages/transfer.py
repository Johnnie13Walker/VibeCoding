"""WRITE-стадия transfer — перенос связей LOSER на WINNER."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from ..bitrix_client import BitrixClient, BitrixError
from ..config import TAB_BACKUP_PREFIX
from ..domain import normalize_domain
from ..sheet_store import read_groups, read_inventory, update_group, update_inventory_row
from ..sheets_client import SheetsClient
from ..state import Status

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
BACKUP_HEADERS = ["ts_msk", "company_id", "domain", "loser_id", "raw_json"]
FORBIDDEN_SP_TELEMETRY = {"sp:1040", "sp:1044", "sp:1052"}
# Bitrix-activity PROVIDER_ID для задач:
#   "TASKS"           — классические task-activity
#   "CRM_TASKS_TASK"  — task-activity, созданная через CRM-deal context (новый стиль)
# Обоим нужен путь reassign_task_activity (через tasks.task.update UF_CRM_TASK).
# Обычный crm.activity.update OWNER_ID для них отдаёт HTTP 400.
TASK_ACTIVITY_PROVIDERS = {"TASKS", "CRM_TASKS_TASK"}
NOT_TRANSFERABLE_PROVIDERS = {
    "VOXIMPLANT_CALL",
    "CRM_SMS",
    "IMOPENLINES_SESSION",
    "CRM_OPENLINES",
    "CRM_TODO",
    "REST_APP",
}


def _provider_id(details_json: str) -> str:
    try:
        data = json.loads(details_json)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("PROVIDER_ID") or "")


def _is_task_activity(details_json: str) -> bool:
    return _provider_id(details_json) in TASK_ACTIVITY_PROVIDERS


def _is_not_transferable(details_json: str) -> bool:
    return _provider_id(details_json) in NOT_TRANSFERABLE_PROVIDERS


def run(
    bx: BitrixClient,
    sheets: SheetsClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    group_key: str | None = None,
) -> dict:
    groups = [(row, g) for row, g in read_groups(sheets) if g.status == Status.APPROVED and g.approved]
    if group_key:
        company_id, domain = _parse_group_key(group_key)
        groups = [(row, g) for row, g in groups if g.company_id == company_id and (g.domain or "") == domain]
    if limit:
        groups = groups[:limit]
    if not groups:
        print("[transfer] нет APPROVED групп")
        return {"processed": 0}

    headers, inventory_rows = read_inventory(sheets)
    inventory = _inventory_by_group(inventory_rows)
    now = datetime.now(MOSCOW_TZ)
    totals: Counter[str] = Counter()

    for row_number, group in groups:
        try:
            result = _transfer_group(bx, sheets, headers, inventory, group, now, dry_run=dry_run)
            totals.update(result)
            if not dry_run:
                updated = replace(
                    group,
                    status=Status.TRANSFERRED,
                    backup_sheet=_backup_sheet_name(group.company_id, group.domain),
                    last_action_at=now,
                    error_message=None,
                )
                update_group(sheets, row_number, updated)
        except BitrixError as exc:
            totals["failed"] += 1
            if not dry_run:
                update_group(
                    sheets,
                    row_number,
                    replace(group, status=Status.FAILED, last_action_at=now, error_message=str(exc)[:500]),
                )
            print(f"[transfer] FAILED {group.company_id}:{group.domain}: {exc}")
    if dry_run:
        print(f"[transfer dry-run] план: {dict(totals)}")
    else:
        print(f"[transfer] готово: {dict(totals)}")
    return dict(totals)


def _transfer_group(
    bx: BitrixClient,
    sheets: SheetsClient,
    headers: list[str],
    inventory: dict[str, list[tuple[int, dict[str, str]]]],
    group,
    now: datetime,
    *,
    dry_run: bool,
) -> Counter[str]:
    if not group.winner_id:
        raise BitrixError("winner_id пустой")
    if dry_run:
        planned = Counter({"groups": 1})
        for _, row in _group_inventory(inventory, group):
            if row.get("transferred") == "1":
                continue
            if row.get("entity_type", "") in FORBIDDEN_SP_TELEMETRY:
                continue
            planned[row.get("entity_type", "")] += 1
        print(f"[transfer dry-run] {group.company_id}:{group.domain} -> winner #{group.winner_id}: {dict(planned)}")
        return planned

    backup_sheet = _backup_sheet_name(group.company_id, group.domain)
    sheets.ensure_sheet(backup_sheet)
    sheets.update(backup_sheet, "A1", [BACKUP_HEADERS])
    backup_rows = []
    for loser_id in group.loser_ids:
        deal = bx.get_deal(loser_id)
        if not deal:
            continue
        _assert_title_matches_domain(deal, group.domain)
        backup_rows.append([now.isoformat(timespec="seconds"), group.company_id, group.domain or "", loser_id, json.dumps(deal, ensure_ascii=False, sort_keys=True)])
    if backup_rows:
        sheets.append(backup_sheet, backup_rows)

    current_contacts = {str(c.get("CONTACT_ID") or c.get("ID") or "") for c in bx.list_deal_contacts(group.winner_id)}
    counters: Counter[str] = Counter({"groups": 1})
    for row_number, row in _group_inventory(inventory, group):
        if row.get("transferred") == "1":
            continue
        entity_type = row.get("entity_type", "")
        child_id = row.get("child_id", "")
        loser_id = row.get("loser_id", "")
        note = ""
        transferred = False
        if entity_type in FORBIDDEN_SP_TELEMETRY:
            note = "skipped_sp_telemetry"
            transferred = True
        elif entity_type == "activity":
            if _is_not_transferable(row.get("details", "")):
                note = "not_transferable"
            elif _is_task_activity(row.get("details", "")):
                try:
                    transferred = bx.reassign_task_activity(child_id, loser_id, group.winner_id)
                except BitrixError as exc:
                    if "HTTP 400" in str(exc):
                        note = "not_transferable_dynamic"
                    else:
                        raise
            else:
                try:
                    transferred = bx.reassign_activity(child_id, group.winner_id)
                except BitrixError as exc:
                    if "HTTP 400" in str(exc):
                        note = "not_transferable_dynamic"
                    else:
                        raise
        elif entity_type == "timeline":
            data = _json(row.get("details", ""))
            text = str(data.get("COMMENT") or row.get("child_subject") or "")
            bx.add_deal_timeline_comment(group.winner_id, f"[crm_deal_merge: перенесено из сделки #{loser_id}, {now.isoformat(timespec='seconds')}]\n{text}")
            transferred = True
        elif entity_type == "contact":
            if child_id in current_contacts:
                note = "already_linked"
                transferred = True
            else:
                transferred = bx.add_deal_contact(group.winner_id, child_id)
                if transferred:
                    current_contacts.add(child_id)
        elif entity_type.startswith("sp:"):
            entity_type_id = int(entity_type.split(":", 1)[1])
            transferred = bx.relink_smart_item(entity_type_id, child_id, group.winner_id)
        else:
            note = "unknown_entity_type"
        update_inventory_row(
            sheets,
            row_number,
            headers,
            row,
            transferred=transferred,
            transferred_at=now if transferred else None,
            note=note,
        )
        counters[entity_type] += 1
    return counters


def _inventory_by_group(rows: list[tuple[int, dict[str, str]]]) -> dict[str, list[tuple[int, dict[str, str]]]]:
    out: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for row_number, row in rows:
        out[row.get("company_id", "")].append((row_number, row))
    return out


def _group_inventory(inventory: dict[str, list[tuple[int, dict[str, str]]]], group) -> list[tuple[int, dict[str, str]]]:
    losers = set(group.loser_ids)
    return [(row_number, row) for row_number, row in inventory.get(group.company_id, []) if row.get("loser_id") in losers]


def _backup_sheet_name(company_id: str, domain: str | None) -> str:
    safe_domain = re.sub(r"[^A-Za-z0-9_.-]+", "_", domain or "no_domain")[:40]
    return f"{TAB_BACKUP_PREFIX}{company_id}_{safe_domain}"[:99]


def _parse_group_key(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise ValueError("--group должен быть в формате COMPANY_ID:DOMAIN")
    company_id, domain = value.split(":", 1)
    return company_id, domain


def _assert_title_matches_domain(deal: dict, expected_domain: str | None) -> None:
    if expected_domain is None:
        return
    actual = normalize_domain(str(deal.get("TITLE") or ""))
    if actual != expected_domain:
        raise BitrixError(f"TITLE safety check failed for deal #{deal.get('ID')}: {actual} != {expected_domain}")


def _json(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
