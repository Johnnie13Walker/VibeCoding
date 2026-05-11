from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo

from crm_company_merge.bitrix_client import BitrixClient
from crm_company_merge.config import Config
from crm_company_merge.models import (
    GROUP_HEADERS,
    INVENTORY_HEADERS,
    LOG_ENTRY_HEADERS,
    Group,
    InventoryRecord,
    LogEntry,
)
from crm_company_merge.notifications import send_telegram
from crm_company_merge.sheets_client import SheetsClient
from crm_company_merge.state import Status

QUEUE_SHEET = "Очередь merge"
INVENTORY_SHEET = "Inventory"
MERGE_LOG_SHEET = "Лог merge"
BACKUP_HEADERS = ["timestamp", "inn", "entity_type", "entity_id", "raw_json"]
TRANSFERABLE_TYPES = {"Deal", "Contact", "Activity", "Lead", "TimelineComment"}
SMART_ITEM_PREFIX = "SmartItem:"
SKIP_TYPES = {"Company", "Requisite", "BankDetail"}


def run(args, config=None) -> None:
    """
    Запускается через CLI: `crm-company-merge transfer --limit N [--dry-run]`.
    Обрабатывает группы со статусом PLAN_READY где approved=True.
    """
    config = _resolve_config(args, config)
    pause_flag = Path(config.pause_flag_path)
    if pause_flag.exists():
        print(f"Paused since {_format_mtime(pause_flag, config.timezone)}")
        return

    bitrix = BitrixClient(config.bitrix_state_path)
    sheets = SheetsClient(config.sheet_id, config.google_service_account_json)
    queue_items = _parse_queue_rows(sheets.read(QUEUE_SHEET))
    targets = _approved_targets(queue_items, args.limit)

    if not targets:
        print("Transfer: нет approved PLAN_READY групп для обработки")
        return

    inventory_index = _build_inventory_index(sheets.read(INVENTORY_SHEET))
    now = datetime.now(ZoneInfo(config.timezone))
    backup_sheet = f"Backup merge {now.strftime('%Y-%m-%d %H-%M')}"
    company_cache: dict[str, dict | None] = {}
    updated_groups: list[tuple[int, Group]] = []
    backup_rows: list[list[str]] = []
    log_entries: list[LogEntry] = []
    total_transferred = 0
    total_failed = 0
    dry_run_counts: Counter[str] = Counter()
    dry_run_actions = 0

    for item in targets:
        group_result = _transfer_group(
            bitrix=bitrix,
            group=item.group,
            inventory_index=inventory_index,
            company_cache=company_cache,
            now=now,
            backup_sheet=backup_sheet,
            dry_run=args.dry_run,
        )
        updated_groups.append((item.row_number, group_result.group))
        backup_rows.extend(group_result.backup_rows)
        log_entries.extend(group_result.log_entries)
        total_transferred += group_result.transferred
        total_failed += group_result.failed
        dry_run_counts.update(group_result.dry_run_counts)
        dry_run_actions += group_result.dry_run_actions

    if args.dry_run:
        print(
            f"[dry-run] would transfer {dry_run_actions} actions across {len(targets)} groups: "
            f"deals={dry_run_counts['deals']}, contacts={dry_run_counts['contacts']}, "
            f"activities={dry_run_counts['activities']}, leads={dry_run_counts['leads']}, "
            f"smart_items={dry_run_counts['smart_items']}, "
            f"timeline_comments={dry_run_counts['timeline_comments']}"
        )
        return

    sheets.ensure_sheet(backup_sheet)
    sheets.update(backup_sheet, "A1", [BACKUP_HEADERS])
    if backup_rows:
        sheets.append(backup_sheet, backup_rows)

    _ensure_sheet_header(sheets, MERGE_LOG_SHEET, LOG_ENTRY_HEADERS)
    if log_entries:
        sheets.append(MERGE_LOG_SHEET, [entry.to_sheet_row() for entry in log_entries])

    groups_after = _groups_after_updates(queue_items, updated_groups)
    sheets.update(
        QUEUE_SHEET,
        f"A1:O{len(groups_after) + 1}",
        [GROUP_HEADERS, *[group.to_sheet_row() for group in groups_after]],
    )

    print(
        f"Transfer: обработано {len(targets)} групп. "
        f"Перенесено: {total_transferred}. Сбоев: {total_failed}"
    )
    status_counts = _status_counts(groups_after)
    text = (
        f"Transfer: {len(targets)} групп. Перенесено: {total_transferred}. "
        f"Сбоев: {total_failed}. Очередь: {status_counts[Status.PLAN_READY]} PLAN_READY / "
        f"{status_counts[Status.TRANSFERRED]} TRANSFERRED / {status_counts[Status.FAILED]} FAILED"
    )
    if config.telegram_bot_token and config.telegram_chat_id is not None:
        send_telegram(config.telegram_bot_token, config.telegram_chat_id, text)


@dataclass(frozen=True)
class QueueItem:
    row_number: int
    group: Group


@dataclass
class GroupTransferResult:
    group: Group
    backup_rows: list[list[str]]
    log_entries: list[LogEntry]
    transferred: int
    failed: int
    dry_run_actions: int
    dry_run_counts: Counter[str]


@dataclass(frozen=True)
class OperationResult:
    action: str
    api_method: str
    ok: bool
    summary: str
    critical: bool = False


def _resolve_config(args, config: Config | None) -> Config:
    resolved = config or Config.from_env()
    if getattr(args, "sheet", None):
        resolved = dataclasses.replace(resolved, sheet_id=args.sheet)
    return resolved


def _approved_targets(queue_items: list[QueueItem], limit: int) -> list[QueueItem]:
    targets: list[QueueItem] = []
    for item in queue_items:
        group = item.group
        if group.status != Status.PLAN_READY:
            continue
        if not group.approved:
            print(f"Skip {group.inn}: not approved")
            continue
        targets.append(item)
        if len(targets) >= limit:
            break
    return targets


def _transfer_group(
    *,
    bitrix: BitrixClient,
    group: Group,
    inventory_index: dict[str, dict[str, list[InventoryRecord]]],
    company_cache: dict[str, dict | None],
    now: datetime,
    backup_sheet: str,
    dry_run: bool,
) -> GroupTransferResult:
    backup_rows: list[list[str]] = []
    log_entries: list[LogEntry] = []
    transferred = 0
    failed = 0
    critical_failed = False
    dry_run_counts: Counter[str] = Counter()
    dry_run_actions = 0

    winner_id = group.winner_id
    if not winner_id or _get_company_cached(bitrix, company_cache, winner_id) is None:
        updated = replace(
            group,
            status=Status.FAILED,
            backup_sheet=backup_sheet,
            last_action_at=now,
            error_message="winner disappeared",
        )
        return GroupTransferResult(updated, backup_rows, log_entries, 0, 0, 0, dry_run_counts)

    live_losers: list[str] = []
    for loser_id in group.loser_ids:
        loser_company = _get_company_cached(bitrix, company_cache, loser_id)
        if loser_company is None:
            continue
        live_losers.append(loser_id)
        backup_rows.append(
            [
                now.isoformat(timespec="seconds"),
                group.inn,
                "Company",
                loser_id,
                json.dumps(loser_company, ensure_ascii=False, sort_keys=True),
            ]
        )

    if not live_losers:
        updated = replace(
            group,
            status=Status.DONE,
            backup_sheet=backup_sheet,
            last_action_at=now,
            error_message=None,
        )
        return GroupTransferResult(updated, backup_rows, log_entries, 0, 0, 0, dry_run_counts)

    records_to_transfer: list[InventoryRecord] = []
    for loser_id in live_losers:
        records_to_transfer.extend(inventory_index.get(group.inn, {}).get(loser_id, []))

    for record in records_to_transfer:
        if not _is_transferable(record):
            continue
        dry_run_counts[_counter_key(record)] += 1
        dry_run_actions += 1
        if dry_run:
            _touch_read_for_dry_run(bitrix, record)
            continue

        started = perf_counter()
        result = _execute_transfer(bitrix, record, winner_id, now)
        duration_ms = int((perf_counter() - started) * 1000)
        log_entries.append(
            _log_entry(
                now=now,
                inn=group.inn,
                result=result,
                request_hash=_request_hash(record, winner_id),
                duration_ms=duration_ms,
            )
        )
        if result.ok:
            transferred += 1
        else:
            failed += 1
            critical_failed = critical_failed or result.critical

    if dry_run:
        return GroupTransferResult(group, backup_rows, log_entries, 0, 0, dry_run_actions, dry_run_counts)

    has_transferable = any(_is_transferable(record) for record in records_to_transfer)
    if critical_failed:
        status = Status.FAILED
        error = "critical transfer failed"
    elif has_transferable and transferred == 0:
        status = Status.FAILED
        error = "no transfers succeeded"
    else:
        status = Status.TRANSFERRED
        error = None

    updated = replace(
        group,
        status=status,
        backup_sheet=backup_sheet,
        last_action_at=now,
        error_message=error,
    )
    return GroupTransferResult(
        updated, backup_rows, log_entries, transferred, failed, dry_run_actions, dry_run_counts
    )


def _execute_transfer(
    bitrix: BitrixClient, record: InventoryRecord, winner_id: str, now: datetime
) -> OperationResult:
    try:
        if record.entity_type == "Deal":
            deal = bitrix.get_deal(record.child_id) or {}
            old_comments = str(deal.get("COMMENTS") or "")
            note = f"\n\n[Перенесена с дубля company_id={record.loser_id} ({now.date()})]"
            ok = bitrix.update_deal(
                record.child_id,
                {"COMPANY_ID": winner_id, "COMMENTS": (old_comments + note).strip()},
            )
            return OperationResult("transfer_deal", "crm.deal.update", ok, "deal_transferred" if ok else "deal_update_failed")

        if record.entity_type == "Contact":
            ok = bitrix.update_contact(record.child_id, {"COMPANY_ID": winner_id})
            return OperationResult("transfer_contact", "crm.contact.update", ok, "contact_transferred" if ok else "contact_update_failed")

        if record.entity_type == "Activity":
            ok = bitrix.update_activity(record.child_id, {"OWNER_ID": winner_id})
            if ok:
                return OperationResult("transfer_activity", "crm.activity.update", True, "activity_transferred")
            return OperationResult(
                "activity_not_transferable",
                "crm.activity.update",
                False,
                f"activity_not_transferable: provider={_provider_from_details(record.details)}",
            )

        if record.entity_type == "Lead":
            ok = bitrix.update_lead(record.child_id, {"COMPANY_ID": winner_id})
            return OperationResult("transfer_lead", "crm.lead.update", ok, "lead_transferred" if ok else "lead_update_failed")

        if record.entity_type.startswith(SMART_ITEM_PREFIX):
            entity_type_id = int(record.entity_type.removeprefix(SMART_ITEM_PREFIX))
            ok = bitrix.update_smart_item(entity_type_id, record.child_id, {"companyId": winner_id})
            return OperationResult(
                "transfer_smart_item",
                "crm.item.update",
                ok,
                "smart_item_transferred" if ok else "smart_item_update_failed",
                critical=not ok,
            )

        if record.entity_type == "TimelineComment":
            comment_id = bitrix.add_timeline_comment(
                "company",
                winner_id,
                f"[Перенесено из дубля company_id={record.loser_id} ({now.date()})]\n{record.child_name}",
            )
            return OperationResult(
                "copy_timeline_comment",
                "crm.timeline.comment.add",
                bool(comment_id),
                f"timeline_comment_added:{comment_id}" if comment_id else "timeline_comment_add_failed",
            )
    except Exception as exc:  # noqa: BLE001 - перенос одной сущности не должен валить группу
        return OperationResult(
            f"transfer_{record.entity_type}",
            _method_for_type(record.entity_type),
            False,
            f"exception:{type(exc).__name__}:{exc}",
            critical=record.entity_type.startswith(SMART_ITEM_PREFIX),
        )

    return OperationResult("skip", "", True, "skipped")


def _touch_read_for_dry_run(bitrix: BitrixClient, record: InventoryRecord) -> None:
    if record.entity_type == "Deal":
        bitrix.get_deal(record.child_id)
    elif record.entity_type == "Contact":
        bitrix.get_contact(record.child_id)
    elif record.entity_type == "Lead":
        bitrix.get_lead(record.child_id)
    elif record.entity_type.startswith(SMART_ITEM_PREFIX):
        entity_type_id = int(record.entity_type.removeprefix(SMART_ITEM_PREFIX))
        bitrix.get_smart_item(entity_type_id, record.child_id)


def _is_transferable(record: InventoryRecord) -> bool:
    return record.entity_type in TRANSFERABLE_TYPES or record.entity_type.startswith(SMART_ITEM_PREFIX)


def _counter_key(record: InventoryRecord) -> str:
    if record.entity_type == "Deal":
        return "deals"
    if record.entity_type == "Contact":
        return "contacts"
    if record.entity_type == "Activity":
        return "activities"
    if record.entity_type == "Lead":
        return "leads"
    if record.entity_type.startswith(SMART_ITEM_PREFIX):
        return "smart_items"
    if record.entity_type == "TimelineComment":
        return "timeline_comments"
    return "other"


def _method_for_type(entity_type: str) -> str:
    if entity_type == "Deal":
        return "crm.deal.update"
    if entity_type == "Contact":
        return "crm.contact.update"
    if entity_type == "Activity":
        return "crm.activity.update"
    if entity_type == "Lead":
        return "crm.lead.update"
    if entity_type.startswith(SMART_ITEM_PREFIX):
        return "crm.item.update"
    if entity_type == "TimelineComment":
        return "crm.timeline.comment.add"
    return ""


def _provider_from_details(details: str) -> str:
    for part in str(details).split(","):
        key, _, value = part.strip().partition("=")
        if key == "provider":
            return value
    return ""


def _get_company_cached(
    bitrix: BitrixClient, company_cache: dict[str, dict | None], company_id: str
) -> dict | None:
    if company_id not in company_cache:
        company_cache[company_id] = bitrix.get_company(company_id)
    return company_cache[company_id]


def _parse_queue_rows(rows: list[list]) -> list[QueueItem]:
    if not rows:
        return []
    headers = [str(value) for value in rows[0]]
    if headers != GROUP_HEADERS:
        raise ValueError("Лист 'Очередь merge' должен начинаться с GROUP_HEADERS")
    return [
        QueueItem(index, Group.from_sheet_row([str(value) for value in row], headers))
        for index, row in enumerate(rows[1:], start=2)
        if row
    ]


def _build_inventory_index(rows: list[list]) -> dict[str, dict[str, list[InventoryRecord]]]:
    if not rows:
        return {}
    headers = [str(value) for value in rows[0]]
    if headers != INVENTORY_HEADERS:
        raise ValueError("Лист 'Inventory' должен начинаться с INVENTORY_HEADERS")
    index: dict[str, dict[str, list[InventoryRecord]]] = defaultdict(lambda: defaultdict(list))
    for row in rows[1:]:
        if not row:
            continue
        record = _inventory_record_from_row([str(value) for value in row], headers)
        index[record.inn][record.loser_id].append(record)
    return index


def _inventory_record_from_row(row: list[str], headers: list[str]) -> InventoryRecord:
    values = {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
    return InventoryRecord(
        inn=values.get("inn", ""),
        loser_id=values.get("loser_id", ""),
        entity_type=values.get("entity_type", ""),
        child_id=values.get("child_id", ""),
        child_name=values.get("child_name", ""),
        owner=values.get("owner", ""),
        details=values.get("details", ""),
        transferred=str(values.get("transferred", "")).strip() == "1",
        transferred_at=None,
    )


def _ensure_sheet_header(sheets: SheetsClient, sheet: str, headers: list[str]) -> None:
    sheets.ensure_sheet(sheet)
    rows = sheets.read(sheet, "A1:Z1")
    if not rows:
        sheets.update(sheet, "A1", [headers])


def _groups_after_updates(
    queue_items: list[QueueItem], updates: list[tuple[int, Group]]
) -> list[Group]:
    by_row = {row_number: group for row_number, group in updates}
    return [by_row.get(item.row_number, item.group) for item in queue_items]


def _status_counts(groups: list[Group]) -> dict[Status, int]:
    counts = {status: 0 for status in Status}
    for group in groups:
        counts[group.status] += 1
    return counts


def _log_entry(
    *,
    now: datetime,
    inn: str,
    result: OperationResult,
    request_hash: str,
    duration_ms: int,
) -> LogEntry:
    return LogEntry(
        ts=now,
        inn=inn,
        stage="transfer",
        action=result.action,
        api_method=result.api_method,
        request_hash=request_hash,
        response_summary=result.summary,
        ok=result.ok,
        duration_ms=duration_ms,
    )


def _request_hash(record: InventoryRecord, winner_id: str) -> str:
    payload = f"{record.entity_type}:{record.child_id}:{record.loser_id}:{winner_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _format_mtime(path: Path, timezone: str) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo(timezone)).isoformat(
        timespec="seconds"
    )
