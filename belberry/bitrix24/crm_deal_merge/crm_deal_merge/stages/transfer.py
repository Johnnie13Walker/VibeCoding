"""WRITE-стадия transfer — перенос связей LOSER на WINNER."""
from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError

from ..bitrix_client import BitrixClient, BitrixError
from ..config import BACKUP_DIR, TAB_INVENTORY
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
    "REST_APP",
}
SHEETS_FLUSH_RETRY_DELAYS = (5, 15, 45)
SHEETS_FLUSH_TIMEOUT_MESSAGE = "Sheets flush timeout after Bitrix write"


def _provider_id(details_json: str) -> str:
    try:
        data = json.loads(details_json)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("PROVIDER_ID") or "")


def _is_not_transferable(details_json: str) -> bool:
    return _provider_id(details_json) in NOT_TRANSFERABLE_PROVIDERS


def _is_task_activity(details_json: str) -> bool:
    return _provider_id(details_json) in TASK_ACTIVITY_PROVIDERS


def run(
    bx: BitrixClient,
    sheets: SheetsClient,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    group_key: str | None = None,
    batch_mode: bool = False,
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
            result = _transfer_group(bx, sheets, headers, inventory, group, now,
                                     dry_run=dry_run, batch_mode=batch_mode)
            totals.update(result)
            if not dry_run:
                updated = replace(
                    group,
                    status=Status.TRANSFERRED,
                    backup_sheet=group.backup_sheet,
                    last_action_at=now,
                    error_message=None,
                )
                update_group(sheets, row_number, updated)
        except BitrixError as exc:
            totals["failed"] += 1
            if not dry_run:
                status = Status.MANUAL if "MANUAL review" in str(exc) else Status.FAILED
                update_group(
                    sheets,
                    row_number,
                    replace(group, status=status, last_action_at=now, error_message=str(exc)[:500]),
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
    batch_mode: bool = False,
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
            if row.get("entity_type", "") == "activity" and _is_not_transferable(row.get("details", "")):
                continue
            planned[row.get("entity_type", "")] += 1
        print(f"[transfer dry-run] {group.company_id}:{group.domain} -> winner #{group.winner_id}: {dict(planned)}")
        return planned

    # 1. Backup перед записью. Новая стратегия — локальный JSON, чтобы не упираться
    # в лимит Google Sheets workbook 10M cells.
    backup_losers = []
    for loser_id in group.loser_ids:
        deal = bx.get_deal(loser_id)
        if not deal:
            continue
        _assert_title_matches_domain(deal, group.domain)
        backup_losers.append({"loser_id": loser_id, "raw": deal})
    group.backup_sheet = str(_write_local_backup(group, backup_losers, now))

    current_contacts = {str(c.get("CONTACT_ID") or c.get("ID") or "")
                        for c in bx.list_deal_contacts(group.winner_id)}

    if batch_mode:
        return _transfer_group_batch(bx, sheets, headers, inventory, group, now, current_contacts)
    return _transfer_group_sequential(bx, sheets, headers, inventory, group, now, current_contacts)


def _transfer_group_sequential(bx, sheets, headers, inventory, group, now, current_contacts):
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
            details = row.get("details", "")
            if _is_not_transferable(details):
                note = "not_transferable"
            elif _is_task_activity(details):
                try:
                    transferred = bx.reassign_task_activity(child_id, loser_id, group.winner_id)
                except BitrixError as exc:
                    if "HTTP 400" not in str(exc):
                        raise
                    note = "not_transferable_dynamic"
                    transferred = False
            else:
                try:
                    transferred = bx.reassign_activity(child_id, group.winner_id)
                except BitrixError as exc:
                    if "HTTP 400" not in str(exc):
                        raise
                    note = "not_transferable_dynamic"
                    transferred = False
        elif entity_type == "timeline":
            data = _json(row.get("details", ""))
            text = str(data.get("COMMENT") or row.get("child_subject") or "")
            bx.add_deal_timeline_comment(
                group.winner_id,
                f"[crm_deal_merge: перенесено из сделки #{loser_id}, "
                f"{now.isoformat(timespec='seconds')}]\n{text}",
            )
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


def _transfer_group_batch(bx, sheets, headers, inventory, group, now, current_contacts):
    """Batch-режим: группирует API-операции в Bitrix batch и Sheets batchUpdate.

    TASKS-активности остаются sequential (reassign_task_activity сложен для batch).
    SP оставлены sequential (мало штук, простая логика, FORBIDDEN check проще).
    """
    counters: Counter[str] = Counter({"groups": 1})

    activity_batch: list[tuple[int, dict[str, str]]] = []
    task_activities: list[tuple[int, dict[str, str]]] = []
    timeline_batch: list[tuple[int, dict[str, str]]] = []
    contact_to_add: list[tuple[int, dict[str, str]]] = []
    sp_rows: list[tuple[int, dict[str, str]]] = []
    direct_updates: list[tuple[int, dict[str, str], bool, str]] = []
    # direct_updates содержит уже-решённые: телеметрия (transferred=True), VOXI (False),
    # already_linked contact (True), unknown (False).

    for row_number, row in _group_inventory(inventory, group):
        if row.get("transferred") == "1":
            continue
        entity_type = row.get("entity_type", "")
        if entity_type in FORBIDDEN_SP_TELEMETRY:
            direct_updates.append((row_number, row, True, "skipped_sp_telemetry"))
            counters[entity_type] += 1
            continue
        if entity_type == "activity":
            details = row.get("details", "")
            if _is_not_transferable(details):
                direct_updates.append((row_number, row, False, "not_transferable"))
                counters["activity"] += 1
            elif _is_task_activity(details):
                task_activities.append((row_number, row))
            else:
                activity_batch.append((row_number, row))
            continue
        if entity_type == "timeline":
            timeline_batch.append((row_number, row))
            continue
        if entity_type == "contact":
            child_id = row.get("child_id", "")
            if child_id in current_contacts:
                direct_updates.append((row_number, row, True, "already_linked"))
                counters["contact"] += 1
            else:
                contact_to_add.append((row_number, row))
                current_contacts.add(child_id)
            continue
        if entity_type.startswith("sp:"):
            sp_rows.append((row_number, row))
            continue
        direct_updates.append((row_number, row, False, "unknown_entity_type"))
        counters[entity_type] += 1

    _flush_inventory_updates(sheets, headers, direct_updates, now)

    # TASKS — sequential (как раньше), но с отдельным flush сразу после стадии.
    task_updates: list[tuple[int, dict[str, str], bool, str]] = []
    for row_number, row in task_activities:
        try:
            ok = bx.reassign_task_activity(row.get("child_id", ""), row.get("loser_id", ""), group.winner_id)
            note = ""
        except BitrixError as exc:
            if "HTTP 400" not in str(exc):
                raise
            ok = False
            note = "not_transferable_dynamic"
        task_updates.append((row_number, row, ok, note))
        counters["activity"] += 1
    _flush_inventory_updates(sheets, headers, task_updates, now)

    # Activity batch
    if activity_batch:
        activity_updates = []
        commands = {
            f"a{idx}": (
                "crm.activity.update",
                {"id": row.get("child_id", ""),
                 "fields": {"OWNER_TYPE_ID": "2", "OWNER_ID": group.winner_id}},
            )
            for idx, (_, row) in enumerate(activity_batch)
        }
        batch_error = False
        try:
            result = bx.batch(commands)
        except BitrixError:
            batch_error = True
            result = {}
        for idx, (row_number, row) in enumerate(activity_batch):
            ok = bool(result.get(f"a{idx}"))
            note = "" if ok else ("not_transferable_dynamic" if batch_error else "batch_failed")
            activity_updates.append((row_number, row, ok, note))
            counters["activity"] += 1
        _flush_inventory_updates(sheets, headers, activity_updates, now)

    # Timeline batch
    if timeline_batch:
        commands = {}
        for idx, (_, row) in enumerate(timeline_batch):
            data = _json(row.get("details", ""))
            text = str(data.get("COMMENT") or row.get("child_subject") or "")
            commands[f"tl{idx}"] = (
                "crm.timeline.comment.add",
                {"fields": {"ENTITY_TYPE": "deal", "ENTITY_ID": group.winner_id,
                            "COMMENT": f"[crm_deal_merge: перенесено из сделки #{row.get('loser_id','')}, "
                                       f"{now.isoformat(timespec='seconds')}]\n{text}"}},
            )
        try:
            result = bx.batch(commands)
            batch_error = False
        except BitrixError:
            result = {}
            batch_error = True
        timeline_updates = []
        for idx, (row_number, row) in enumerate(timeline_batch):
            ok = bool(result.get(f"tl{idx}"))
            note = "" if ok else ("batch_error" if batch_error else "batch_failed")
            timeline_updates.append((row_number, row, ok, note))
            counters["timeline"] += 1
        _flush_inventory_updates(sheets, headers, timeline_updates, now)

    # Contact batch
    if contact_to_add:
        commands = {
            f"c{idx}": (
                "crm.deal.contact.add",
                {"id": group.winner_id, "fields": {"CONTACT_ID": row.get("child_id", "")}},
            )
            for idx, (_, row) in enumerate(contact_to_add)
        }
        try:
            result = bx.batch(commands)
            batch_error = False
        except BitrixError:
            result = {}
            batch_error = True
        contact_updates = []
        for idx, (row_number, row) in enumerate(contact_to_add):
            ok = bool(result.get(f"c{idx}"))
            note = "" if ok else ("batch_error" if batch_error else "batch_failed")
            contact_updates.append((row_number, row, ok, note))
            counters["contact"] += 1
        _flush_inventory_updates(sheets, headers, contact_updates, now)

    # SP — sequential (мало, простая логика)
    sp_updates = []
    for row_number, row in sp_rows:
        entity_type_id = int(row.get("entity_type", "").split(":", 1)[1])
        try:
            ok = bx.relink_smart_item(entity_type_id, row.get("child_id", ""), group.winner_id)
        except BitrixError:
            ok = False
        sp_updates.append((row_number, row, ok, ""))
        counters[row.get("entity_type", "")] += 1
    _flush_inventory_updates(sheets, headers, sp_updates, now)

    return counters


def _flush_inventory_updates(sheets, headers, updates_list, now):
    """Bulk update inventory rows. Группирует в contiguous chunks и шлёт batchUpdate."""
    if not updates_list:
        return
    sorted_updates = sorted(updates_list, key=lambda x: x[0])
    # Применяем мутации
    for _, row, transferred, note in sorted_updates:
        row["transferred"] = "1" if transferred else "0"
        row["transferred_at"] = now.isoformat(timespec="seconds") if transferred else ""
        row["note"] = note

    # Группируем в contiguous chunks (rows c row_number подряд)
    chunks: list[list[tuple[int, dict[str, str]]]] = []
    current: list[tuple[int, dict[str, str]]] = []
    for row_number, row, _, _ in sorted_updates:
        if current and row_number == current[-1][0] + 1:
            current.append((row_number, row))
        else:
            if current:
                chunks.append(current)
            current = [(row_number, row)]
    if current:
        chunks.append(current)

    def write() -> None:
        if len(chunks) == 1:
            chunk = chunks[0]
            start, end = chunk[0][0], chunk[-1][0]
            payload = [[r.get(h, "") for h in headers] for _, r in chunk]
            sheets.update(TAB_INVENTORY, f"A{start}:I{end}", payload)
        else:
            data = []
            for chunk in chunks:
                start, end = chunk[0][0], chunk[-1][0]
                values = [[r.get(h, "") for h in headers] for _, r in chunk]
                data.append({"range": f"{TAB_INVENTORY}!A{start}:I{end}", "values": values})
            sheets.batch_update(data)

    for attempt in range(len(SHEETS_FLUSH_RETRY_DELAYS) + 1):
        try:
            write()
            return
        except Exception as exc:
            if not _is_retryable_sheets_flush_error(exc):
                raise
            if attempt >= len(SHEETS_FLUSH_RETRY_DELAYS):
                raise BitrixError(f"{SHEETS_FLUSH_TIMEOUT_MESSAGE}: {exc}") from exc
            delay = SHEETS_FLUSH_RETRY_DELAYS[attempt]
            print(f"[transfer] Sheets flush retry {attempt + 1}/{len(SHEETS_FLUSH_RETRY_DELAYS)} after {exc}")
            time.sleep(delay)


def _is_retryable_sheets_flush_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, OSError) and "timed out" in str(exc).lower():
        return True
    if isinstance(exc, HttpError):
        status = getattr(exc.resp, "status", 0)
        return status in {429, 500, 502, 503, 504}
    return False


def _inventory_by_group(rows: list[tuple[int, dict[str, str]]]) -> dict[str, list[tuple[int, dict[str, str]]]]:
    out: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for row_number, row in rows:
        out[row.get("company_id", "")].append((row_number, row))
    return out


def _group_inventory(inventory: dict[str, list[tuple[int, dict[str, str]]]], group) -> list[tuple[int, dict[str, str]]]:
    losers = set(group.loser_ids)
    return [(row_number, row) for row_number, row in inventory.get(group.company_id, []) if row.get("loser_id") in losers]


def _write_local_backup(group, losers: list[dict], now: datetime) -> Path:
    backup_dir = BACKUP_DIR / now.strftime("%Y%m%d")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file = backup_dir / f"{group.company_id}_{_safe_domain(group.domain)}.json"
    backup_data = {
        "ts_msk": now.isoformat(timespec="seconds"),
        "company_id": group.company_id,
        "domain": group.domain,
        "losers": losers,
    }
    backup_file.write_text(json.dumps(backup_data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return backup_file


def _safe_domain(domain: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", domain or "no_domain")[:40]


def _parse_group_key(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise ValueError("--group должен быть в формате COMPANY_ID:DOMAIN")
    company_id, domain = value.split(":", 1)
    return company_id, domain


def _assert_title_matches_domain(deal: dict, expected_domain: str | None) -> None:
    if expected_domain is None:
        return
    title = str(deal.get("TITLE") or "")
    if not title.strip():
        raise BitrixError(f"TITLE deal #{deal.get('ID')} пустой — MANUAL review")
    actual = normalize_domain(title)
    if actual != expected_domain:
        raise BitrixError(f"TITLE safety check failed for deal #{deal.get('ID')}: {actual} != {expected_domain}")


def _json(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
