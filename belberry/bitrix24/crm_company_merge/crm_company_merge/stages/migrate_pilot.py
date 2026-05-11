from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from crm_company_merge.bitrix_client import BitrixClient
from crm_company_merge.config import Config
from crm_company_merge.models import GROUP_HEADERS, Group
from crm_company_merge.sheets_client import SheetsClient
from crm_company_merge.state import Status

QUEUE_SHEET = "Очередь merge"
PILOT_INNS = {
    "1661042280",
    "2372028320",
    "5001044465",
    "5010025719",
    "5034004041",
    "5040146453",
    "6312069182",
    "6671276329",
    "7022013581",
    "1003001854",
    "1215157275",
}
PILOT_WINNERS = {
    "1003001854": "4822",
    "1215157275": "9040",
}
PILOT_BACKUP_MARKERS = ("11-47", "11-51")


@dataclass(frozen=True)
class QueueItem:
    row_number: int
    group: Group


def run(args, config=None) -> None:
    config = _resolve_config(args, config)
    pause_flag = Path(config.pause_flag_path)
    if pause_flag.exists():
        print(f"Paused since {_format_mtime(pause_flag, config.timezone)}")
        return

    bitrix = BitrixClient(config.bitrix_state_path)
    sheets = SheetsClient(config.sheet_id, config.google_service_account_json)
    items = _parse_queue_rows(sheets.read(QUEUE_SHEET))
    by_inn = {item.group.inn: item for item in items}
    backup_losers = _read_pilot_backup_losers(sheets)
    now = datetime.now(ZoneInfo(config.timezone))

    found = 0
    missing: list[str] = []
    updated: list[QueueItem] = []

    for inn in sorted(PILOT_INNS):
        item = by_inn.get(inn)
        if item is None:
            missing.append(inn)
            continue
        found += 1
        winner_id = PILOT_WINNERS.get(inn) or _single_company_id(bitrix, inn) or item.group.winner_id
        loser_ids = [cid for cid in backup_losers.get(inn, item.group.loser_ids) if cid != winner_id]
        group = replace(
            item.group,
            status=Status.DONE,
            winner_id=winner_id,
            loser_ids=loser_ids,
            approved=True,
            last_action_at=now,
            error_message="migrated from pre-workflow pilot",
        )
        updated.append(QueueItem(item.row_number, group))

    if args.dry_run:
        print(
            f"[dry-run] migrate-pilot: found={found}, missing={len(missing)}, "
            f"would_update={len(updated)}"
        )
        if missing:
            print(f"[dry-run] missing inns: {', '.join(missing)}")
        return

    for item in updated:
        sheets.update(QUEUE_SHEET, f"A{item.row_number}:O{item.row_number}", [item.group.to_sheet_row()])
    print(f"Migrate pilot: обновлено {len(updated)} групп, не найдено {len(missing)}")


def _resolve_config(args, config):
    if config is not None:
        return config
    loaded = Config.from_env()
    if getattr(args, "sheet", None):
        return replace(loaded, sheet_id=args.sheet)
    return loaded


def _parse_queue_rows(rows: list[list]) -> list[QueueItem]:
    if not rows:
        return []
    headers = [str(value) for value in rows[0]]
    if headers[: len(GROUP_HEADERS)] != GROUP_HEADERS:
        raise ValueError("Лист 'Очередь merge' должен начинаться с GROUP_HEADERS")
    return [
        QueueItem(
            index,
            Group.from_sheet_row([str(value) for value in row[: len(GROUP_HEADERS)]], GROUP_HEADERS),
        )
        for index, row in enumerate(rows[1:], start=2)
        if row
    ]


def _read_pilot_backup_losers(sheets: SheetsClient) -> dict[str, list[str]]:
    losers: dict[str, list[str]] = {}
    for title in sheets.get_sheet_titles():
        if not title.startswith("Backup merge"):
            continue
        if PILOT_BACKUP_MARKERS and not any(marker in title for marker in PILOT_BACKUP_MARKERS):
            continue
        rows = sheets.read(title)
        if not rows:
            continue
        headers = [str(value) for value in rows[0]]
        for row in rows[1:]:
            values = _row_values(headers, row)
            if values.get("entity_type") != "Company":
                continue
            inn = values.get("inn", "")
            entity_id = values.get("entity_id", "")
            if inn in PILOT_INNS and entity_id:
                losers.setdefault(inn, [])
                if entity_id not in losers[inn]:
                    losers[inn].append(entity_id)
    return losers


def _row_values(headers: list[str], row: list[Any]) -> dict[str, str]:
    return {header: str(row[index]) if index < len(row) else "" for index, header in enumerate(headers)}


def _single_company_id(bitrix: BitrixClient, inn: str) -> str | None:
    ids = bitrix.find_companies_by_inn(inn)
    return ids[0] if len(ids) == 1 else None


def _format_mtime(path: Path, timezone: str) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo(timezone)).isoformat(
        timespec="seconds"
    )
