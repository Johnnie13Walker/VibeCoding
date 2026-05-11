from __future__ import annotations

import dataclasses
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from crm_company_merge.bitrix_client import BitrixClient
from crm_company_merge.config import Config
from crm_company_merge.models import (
    CONFLICT_HEADERS,
    GROUP_HEADERS,
    LOG_ENTRY_HEADERS,
    Conflict,
    Group,
    LogEntry,
)
from crm_company_merge.notifications import send_telegram
from crm_company_merge.sheets_client import SheetsClient
from crm_company_merge.state import Status

QUEUE_SHEET = "Очередь merge"
CONFLICTS_SHEET = "Конфликты полей"
MERGE_LOG_SHEET = "Лог merge"
MULTIFIELD_KEYS = {"PHONE", "EMAIL", "WEB", "IM", "LINK"}


def run(args, config=None) -> None:
    """
    Запускается через CLI: `crm-company-merge merge --limit N [--dry-run]`.
    Обрабатывает группы со статусом TRANSFERRED.
    """
    config = _resolve_config(args, config)
    pause_flag = Path(config.pause_flag_path)
    if pause_flag.exists():
        print(f"Paused since {_format_mtime(pause_flag, config.timezone)}")
        return

    bitrix = BitrixClient(config.bitrix_state_path)
    sheets = SheetsClient(config.sheet_id, config.google_service_account_json)
    queue_items = _parse_queue_rows(sheets.read(QUEUE_SHEET))
    targets = [item for item in queue_items if item.group.status == Status.TRANSFERRED][
        : args.limit
    ]
    if not targets:
        print("Merge: нет групп TRANSFERRED для обработки")
        return

    conflict_index = _build_conflict_index(sheets.read(CONFLICTS_SHEET))
    now = datetime.now(ZoneInfo(config.timezone))
    company_cache: dict[str, dict | None] = {}
    updated_groups: list[tuple[int, Group]] = []
    total_field_updates = 0
    total_deletes = 0
    total_failed = 0
    merge_log_ready = False

    for item in targets:
        result = _merge_group(
            bitrix=bitrix,
            group=item.group,
            conflicts=conflict_index.get(item.group.inn, []),
            company_cache=company_cache,
            now=now,
            dry_run=args.dry_run,
        )
        updated_groups.append((item.row_number, result.group))
        total_field_updates += result.field_updates
        total_deletes += result.deletes
        if result.group.status == Status.FAILED:
            total_failed += 1

        if not args.dry_run:
            if result.log_entries:
                if not merge_log_ready:
                    _ensure_sheet_header(sheets, MERGE_LOG_SHEET, LOG_ENTRY_HEADERS)
                    merge_log_ready = True
                sheets.append(
                    MERGE_LOG_SHEET,
                    [entry.to_sheet_row() for entry in result.log_entries],
                )
            sheets.update(
                QUEUE_SHEET,
                f"A{item.row_number}:O{item.row_number}",
                [result.group.to_sheet_row()],
            )

    if args.dry_run:
        print(
            f"[dry-run] would merge {len(targets)} groups: "
            f"{total_field_updates} field updates, {total_deletes} deletes"
        )
        return

    print(
        f"Merge: обработано {len(targets)} групп. "
        f"Обновлений полей: {total_field_updates}. Удалений: {total_deletes}. "
        f"Сбоев: {total_failed}"
    )
    groups_after = _groups_after_updates(queue_items, updated_groups)
    status_counts = _status_counts(groups_after)
    text = (
        f"Merge: {len(targets)} групп. Обновлений полей: {total_field_updates}. "
        f"Удалений: {total_deletes}. Сбоев: {total_failed}. Очередь: "
        f"{status_counts[Status.TRANSFERRED]} TRANSFERRED / "
        f"{status_counts[Status.MERGED]} MERGED / {status_counts[Status.FAILED]} FAILED"
    )
    if config.telegram_bot_token and config.telegram_chat_id is not None:
        send_telegram(config.telegram_bot_token, config.telegram_chat_id, text)


@dataclass(frozen=True)
class QueueItem:
    row_number: int
    group: Group


@dataclass
class GroupMergeResult:
    group: Group
    log_entries: list[LogEntry]
    field_updates: int
    deletes: int


@dataclass(frozen=True)
class OperationResult:
    action: str
    api_method: str
    ok: bool
    summary: str


def _resolve_config(args, config: Config | None) -> Config:
    resolved = config or Config.from_env()
    if getattr(args, "sheet", None):
        resolved = dataclasses.replace(resolved, sheet_id=args.sheet)
    return resolved


def _merge_group(
    *,
    bitrix: BitrixClient,
    group: Group,
    conflicts: list[Conflict],
    company_cache: dict[str, dict | None],
    now: datetime,
    dry_run: bool,
) -> GroupMergeResult:
    log_entries: list[LogEntry] = []
    field_updates = 0
    deletes = 0

    winner_id = group.winner_id
    winner = _get_company_cached(bitrix, company_cache, winner_id) if winner_id else None
    if winner is None:
        updated = replace(
            group,
            status=Status.FAILED,
            last_action_at=now,
            error_message="winner gone during merge",
        )
        log_entries.append(
            _log_entry(now, group.inn, OperationResult("winner_gone", "crm.company.get", False, "winner gone during merge"), _hash("winner", winner_id or ""), 0)
        )
        return GroupMergeResult(updated, log_entries, 0, 0)

    update_fields, conflict_logs = _build_update_fields(
        bitrix, winner_id, winner, group.loser_ids, conflicts, company_cache
    )
    log_entries.extend(_log_entry(now, group.inn, item, _hash(item.action, item.summary), 0) for item in conflict_logs)
    field_updates = len(update_fields)

    if update_fields and not dry_run:
        started = perf_counter()
        ok = bitrix.update_company(winner_id, update_fields)
        duration_ms = int((perf_counter() - started) * 1000)
        result = OperationResult(
            "update_company",
            "crm.company.update",
            ok,
            f"fields:{','.join(sorted(update_fields))}" if ok else "winner_update_failed",
        )
        log_entries.append(
            _log_entry(now, group.inn, result, _hash("update_company", update_fields), duration_ms)
        )
        if not ok:
            updated = replace(
                group,
                status=Status.FAILED,
                last_action_at=now,
                error_message="winner update failed",
            )
            return GroupMergeResult(updated, log_entries, field_updates, deletes)

    for loser_id in group.loser_ids:
        loser = _get_company_cached(bitrix, company_cache, loser_id)
        if loser is None:
            log_entries.append(
                _log_entry(
                    now,
                    group.inn,
                    OperationResult("loser_already_deleted", "crm.company.get", True, f"loser:{loser_id}"),
                    _hash("loser_already_deleted", loser_id),
                    0,
                )
            )
            continue

        orphan_deals = bitrix.list_deals(loser_id)
        if orphan_deals:
            updated = replace(
                group,
                status=Status.FAILED,
                last_action_at=now,
                error_message=f"orphan deals on {loser_id}",
            )
            log_entries.append(
                _log_entry(
                    now,
                    group.inn,
                    OperationResult("orphan_deals_blocked", "crm.deal.list", False, f"orphan deals on {loser_id}"),
                    _hash("orphan_deals", loser_id),
                    0,
                )
            )
            return GroupMergeResult(updated, log_entries, field_updates, deletes)

        requisite_rows = bitrix.list_requisites(loser_id)
        for requisite in requisite_rows:
            requisite_id = str(requisite.get("ID") or requisite.get("id") or "")
            if not requisite_id:
                continue
            bank_details = bitrix.list_bank_details(requisite_id)
            for bank_detail in bank_details:
                bank_detail_id = str(bank_detail.get("ID") or bank_detail.get("id") or "")
                if not bank_detail_id:
                    continue
                deletes += 1
                if not dry_run:
                    result = _delete_bank_detail(bitrix, bank_detail_id)
                    log_entries.append(_log_entry(now, group.inn, result, _hash("bank", bank_detail_id), 0))
                    if not result.ok:
                        return GroupMergeResult(
                            replace(group, status=Status.FAILED, last_action_at=now, error_message=result.summary),
                            log_entries,
                            field_updates,
                            deletes,
                        )
            deletes += 1
            if not dry_run:
                result = _delete_requisite(bitrix, requisite_id)
                log_entries.append(_log_entry(now, group.inn, result, _hash("req", requisite_id), 0))
                if not result.ok:
                    return GroupMergeResult(
                        replace(group, status=Status.FAILED, last_action_at=now, error_message=result.summary),
                        log_entries,
                        field_updates,
                        deletes,
                    )

        deletes += 1
        if not dry_run:
            result = _delete_company(bitrix, loser_id)
            log_entries.append(_log_entry(now, group.inn, result, _hash("company", loser_id), 0))
            if not result.ok:
                return GroupMergeResult(
                    replace(group, status=Status.FAILED, last_action_at=now, error_message=result.summary),
                    log_entries,
                    field_updates,
                    deletes,
                )

    if dry_run:
        return GroupMergeResult(group, log_entries, field_updates, deletes)

    updated = replace(
        group,
        status=Status.MERGED,
        last_action_at=now,
        error_message=None,
    )
    return GroupMergeResult(updated, log_entries, field_updates, deletes)


def _build_update_fields(
    bitrix: BitrixClient,
    winner_id: str,
    winner: dict,
    loser_ids: list[str],
    conflicts: list[Conflict],
    company_cache: dict[str, dict | None],
) -> tuple[dict[str, Any], list[OperationResult]]:
    update_fields: dict[str, Any] = {}
    logs: list[OperationResult] = []
    for conflict in conflicts:
        if conflict.resolution == "winner_wins":
            logs.append(OperationResult("conflict_winner_wins", "", True, f"{conflict.field}:winner_wins"))
            continue
        if conflict.resolution == "loser_wins":
            update_fields[conflict.field] = conflict.loser_value
            logs.append(OperationResult("conflict_loser_wins", "", True, f"{conflict.field}:loser_wins"))
            continue
        if conflict.resolution == "union" and conflict.field in MULTIFIELD_KEYS:
            update_fields[conflict.field] = _union_multifield(
                winner.get(conflict.field),
                [
                    loser_company.get(conflict.field)
                    for loser_company in (
                        _get_company_cached(bitrix, company_cache, loser_id)
                        for loser_id in loser_ids
                    )
                    if loser_company is not None
                ],
            )
            logs.append(OperationResult("conflict_union", "", True, f"{conflict.field}:union"))
            continue
        if conflict.resolution == "manual":
            logs.append(
                OperationResult(
                    "manual_conflict_skipped",
                    "",
                    True,
                    f"manual_conflict_skipped:{conflict.field}",
                )
            )
            continue
        logs.append(
            OperationResult(
                "conflict_skipped",
                "",
                True,
                f"unsupported_resolution:{conflict.resolution}:{conflict.field}",
            )
        )
    return update_fields, logs


def _union_multifield(winner_value: Any, loser_values: list[Any]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for value in [winner_value, *loser_values]:
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            key = (str(item.get("VALUE_TYPE", "")), str(item.get("VALUE", "")))
            if not key[1] or key in seen:
                continue
            seen.add(key)
            payload = {k: v for k, v in item.items() if k != "ID"}
            merged.append(payload)
    return merged


def _delete_bank_detail(bitrix: BitrixClient, bank_detail_id: str) -> OperationResult:
    ok = bitrix.delete_bank_detail(bank_detail_id)
    return OperationResult("delete_bank_detail", "crm.requisite.bankdetail.delete", ok, f"bank_detail_deleted:{bank_detail_id}" if ok else f"bank_detail_delete_failed:{bank_detail_id}")


def _delete_requisite(bitrix: BitrixClient, requisite_id: str) -> OperationResult:
    ok = bitrix.delete_requisite(requisite_id)
    return OperationResult("delete_requisite", "crm.requisite.delete", ok, f"requisite_deleted:{requisite_id}" if ok else f"requisite_delete_failed:{requisite_id}")


def _delete_company(bitrix: BitrixClient, company_id: str) -> OperationResult:
    ok = bitrix.delete_company(company_id)
    return OperationResult("delete_company", "crm.company.delete", ok, f"company_deleted:{company_id}" if ok else f"company_delete_failed:{company_id}")


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
    if headers[: len(GROUP_HEADERS)] != GROUP_HEADERS:
        raise ValueError("Лист 'Очередь merge' должен начинаться с GROUP_HEADERS")
    return [
        QueueItem(
            index,
            Group.from_sheet_row(
                [str(value) for value in row[: len(GROUP_HEADERS)]], GROUP_HEADERS
            ),
        )
        for index, row in enumerate(rows[1:], start=2)
        if row
    ]


def _build_conflict_index(rows: list[list]) -> dict[str, list[Conflict]]:
    if not rows:
        return {}
    headers = [str(value) for value in rows[0]]
    if headers != CONFLICT_HEADERS:
        raise ValueError("Лист 'Конфликты полей' должен начинаться с CONFLICT_HEADERS")
    index: dict[str, list[Conflict]] = defaultdict(list)
    for row in rows[1:]:
        if not row:
            continue
        conflict = _conflict_from_row([str(value) for value in row], headers)
        index[conflict.inn].append(conflict)
    return index


def _conflict_from_row(row: list[str], headers: list[str]) -> Conflict:
    values = {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
    return Conflict(
        inn=values.get("inn", ""),
        field=values.get("field", ""),
        kind=values.get("kind", ""),
        winner_value=values.get("winner_value", ""),
        loser_value=values.get("loser_value", ""),
        resolution=values.get("resolution", ""),
        applied=str(values.get("applied", "")).strip().lower() in {"1", "true", "yes", "y", "да", "✓"},
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
    now: datetime,
    inn: str,
    result: OperationResult,
    request_hash: str,
    duration_ms: int,
) -> LogEntry:
    return LogEntry(
        ts=now,
        inn=inn,
        stage="merge",
        action=result.action,
        api_method=result.api_method,
        request_hash=request_hash,
        response_summary=result.summary,
        ok=result.ok,
        duration_ms=duration_ms,
    )


def _hash(prefix: str, payload: Any) -> str:
    raw = f"{prefix}:{payload}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _format_mtime(path: Path, timezone: str) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo(timezone)).isoformat(
        timespec="seconds"
    )
