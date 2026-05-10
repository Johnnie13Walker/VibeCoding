"""Append-only JSONL ledger merge операций.

Контракт:
- одна строка JSON на событие;
- operation_key — канонический из policies.operation_key;
- несколько строк с одним operation_key допустимы (state transitions);
- read-API всегда возвращает last по operation_key;
- перед apply обязательна проверка `is_operation_already_applied`.

State machine:
    apply_started
        → crm_applied_sheet_pending
            → crm_applied_archive_appended
                → crm_applied_sheet_archived  (terminal success)
        → manual_review_sheet_pending
            → manual_review_marked  (terminal manual)
        → merge_conflict_sheet_pending
            → merge_conflict_marked  (terminal conflict)
        → apply_unknown_needs_reconcile  (terminal degraded)
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

TERMINAL_CRM_APPLIED_STATUSES = frozenset({
    "crm_applied_sheet_pending",
    "crm_applied_archive_appended",
    "crm_applied_sheet_archived",
})

TERMINAL_NON_RETRYABLE_STATUSES = frozenset({
    *TERMINAL_CRM_APPLIED_STATUSES,
    "apply_unknown_needs_reconcile",
})


def _now_msk() -> str:
    return datetime.now(MOSCOW_TZ).isoformat(timespec="seconds")


@dataclass(frozen=True)
class MergeLedgerRecord:
    operation_key: str
    sheet_id: str
    domain: str
    target_id: str
    deal_ids: tuple[str, ...]
    policy_version: str
    status: str
    crm_status: str
    sheet_status: str
    run_id: str = ""
    dry_run_artifact: str = ""
    crm_backup_path: str = ""
    manual_merge_url: str = ""
    applied_at_msk: str = ""
    recorded_at_msk: str = field(default_factory=_now_msk)
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["deal_ids"] = list(self.deal_ids)
        return payload


def classify_result(result: Mapping[str, Any] | None) -> tuple[str, str, str]:
    """Маппит исходный CRM-result в (status, crm_status, sheet_status).

    Используется на старте для perception текущего состояния.
    """
    if result is None:
        return ("apply_unknown_needs_reconcile", "unknown_after_apply", "not_ready")

    crm_status = str(result.get("status") or "unknown")
    if bool(result.get("ok")) and crm_status in {"applied", "merged", "success"}:
        return ("crm_applied_sheet_pending", crm_status, "pending_archive")

    if crm_status.startswith("manual_review"):
        return ("manual_review_sheet_pending", crm_status, "pending_manual_review_mark")

    return ("merge_conflict_sheet_pending", crm_status, "pending_conflict_mark")


def _atomic_append(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def append_record(ledger_path: Path, record: MergeLedgerRecord) -> None:
    """Атомарная append-only запись одной строки."""
    line = json.dumps(record.to_json(), ensure_ascii=False, sort_keys=True)
    _atomic_append(Path(ledger_path), line)


def append_records(ledger_path: Path, records: Iterable[MergeLedgerRecord]) -> int:
    count = 0
    for record in records:
        append_record(ledger_path, record)
        count += 1
    return count


def iter_records(ledger_path: Path) -> Iterable[dict[str, Any]]:
    path = Path(ledger_path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def latest_by_operation_key(ledger_path: Path) -> dict[str, dict[str, Any]]:
    """Map operation_key → last record. Поздняя строка перебивает раннюю."""
    result: dict[str, dict[str, Any]] = {}
    for record in iter_records(ledger_path):
        key = str(record.get("operation_key") or "")
        if not key:
            continue
        result[key] = record
    return result


def find_latest(ledger_path: Path, operation_key: str) -> dict[str, Any] | None:
    return latest_by_operation_key(ledger_path).get(operation_key)


def is_operation_already_applied(ledger_path: Path, operation_key: str) -> bool:
    """True если operation_key достиг любого CRM-applied статуса.

    Используется как safety gate перед apply: блокирует повторный merge
    после успешного crm.entity.mergeBatch даже если sheet sync не завершен.
    """
    latest = find_latest(ledger_path, operation_key)
    if latest is None:
        return False
    status = str(latest.get("status") or "")
    return status in TERMINAL_CRM_APPLIED_STATUSES


def is_operation_locked_for_retry(ledger_path: Path, operation_key: str) -> bool:
    """True если повторный apply запрещен (применен или unknown-degraded)."""
    latest = find_latest(ledger_path, operation_key)
    if latest is None:
        return False
    return str(latest.get("status") or "") in TERMINAL_NON_RETRYABLE_STATUSES


def transition(
    ledger_path: Path,
    operation_key: str,
    *,
    status: str,
    sheet_status: str | None = None,
    crm_status: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Записывает state transition: новая строка с тем же operation_key.

    Не редактирует историю, просто append. last-reader подхватит новый статус.
    """
    previous = find_latest(ledger_path, operation_key)
    if previous is None:
        raise ValueError(f"Cannot transition unknown operation_key: {operation_key}")

    new_record = dict(previous)
    new_record["status"] = status
    if sheet_status is not None:
        new_record["sheet_status"] = sheet_status
    if crm_status is not None:
        new_record["crm_status"] = crm_status
    new_record["recorded_at_msk"] = _now_msk()
    if note:
        new_record["note"] = note

    line = json.dumps(new_record, ensure_ascii=False, sort_keys=True)
    _atomic_append(Path(ledger_path), line)
    return new_record


def summarize(ledger_path: Path) -> dict[str, int]:
    summary: dict[str, int] = {}
    for record in latest_by_operation_key(ledger_path).values():
        status = str(record.get("status") or "unknown")
        summary[status] = summary.get(status, 0) + 1
    return dict(sorted(summary.items()))
