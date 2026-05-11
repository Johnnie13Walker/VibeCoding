from __future__ import annotations

import dataclasses
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError

from crm_company_merge.bitrix_client import BitrixClient
from crm_company_merge.config import Config
from crm_company_merge.models import GROUP_HEADERS, Group
from crm_company_merge.notifications import send_telegram
from crm_company_merge.sheets_client import SheetsClient
from crm_company_merge.state import Status

QUEUE_SHEET = "Очередь merge"
HISTORICAL_DUPLICATES_SHEET = "Дубли компаний ИНН"


def run(args, config=None) -> None:
    """
    Запускается через CLI: `crm-company-merge discover [--dry-run]`.
    Если config=None — читает Config.from_env().
    """
    config = _resolve_config(args, config)
    pause_flag = Path(config.pause_flag_path)
    if pause_flag.exists():
        print(f"Paused since {_format_mtime(pause_flag, config.timezone)}")
        return

    bitrix = BitrixClient(config.bitrix_state_path)
    sheets = SheetsClient(config.sheet_id, config.google_service_account_json)

    bitrix_groups = _collect_bitrix_duplicate_groups(bitrix)
    historical_inns = _collect_historical_inns(sheets)
    all_dup_inns = set(bitrix_groups) | historical_inns

    queue_rows, queue_created = _read_or_create_queue(sheets, dry_run=bool(args.dry_run))
    existing_groups = _parse_queue_groups(queue_rows)
    existing_inns = {group.inn for group in existing_groups}
    new_inns = sorted(all_dup_inns - existing_inns)

    if not new_inns:
        print("Дублей не найдено, очередь актуальна")
        return

    now = datetime.now(ZoneInfo(config.timezone))
    new_rows = [
        _new_group_for_inn(inn, bitrix_groups.get(inn, []), now).to_sheet_row()
        for inn in new_inns
    ]

    if queue_created and not args.dry_run:
        sheets.update(QUEUE_SHEET, "A1", [GROUP_HEADERS])

    if args.dry_run:
        print(f"[dry-run] would append {len(new_rows)} rows")
    else:
        sheets.append(QUEUE_SHEET, new_rows)
        print(f"Добавлено {len(new_rows)} новых групп в очередь merge")

    status_counts = _status_counts(existing_groups, len(new_rows))
    text = (
        f"Discover: найдено {len(new_rows)} новых групп дублей. "
        f"Очередь: {status_counts[Status.NEW]} NEW / "
        f"{status_counts[Status.INVENTORIED]} INVENTORIED / "
        f"{status_counts[Status.APPROVED]} APPROVED"
    )
    if args.dry_run:
        print(f"[dry-run] would notify {text}")
    elif config.telegram_bot_token and config.telegram_chat_id is not None:
        send_telegram(config.telegram_bot_token, config.telegram_chat_id, text)


def _resolve_config(args, config: Config | None) -> Config:
    resolved = config or Config.from_env()
    if getattr(args, "sheet", None):
        resolved = dataclasses.replace(resolved, sheet_id=args.sheet)
    return resolved


def _collect_bitrix_duplicate_groups(bitrix: BitrixClient) -> dict[str, list[str]]:
    groups: dict[str, set[str]] = defaultdict(set)
    for row in bitrix.paginate("crm.requisite.list", {"filter": {"ENTITY_TYPE_ID": 4}}):
        inn = str(row.get("RQ_INN") or "").strip()
        company_id = str(row.get("ENTITY_ID") or "").strip()
        if inn and company_id:
            groups[inn].add(company_id)
    return {
        inn: sorted(company_ids, key=_sort_id)
        for inn, company_ids in groups.items()
        if len(company_ids) > 1
    }


def _collect_historical_inns(sheets: SheetsClient) -> set[str]:
    rows = sheets.read(HISTORICAL_DUPLICATES_SHEET)
    inns: set[str] = set()
    for row in rows:
        if not row:
            continue
        inn = str(row[0]).strip()
        if inn and inn.upper() != "ИНН":
            inns.add(inn)
    return inns


def _read_or_create_queue(sheets: SheetsClient, dry_run: bool) -> tuple[list[list], bool]:
    try:
        rows = sheets.read(QUEUE_SHEET)
        return rows, False
    except HttpError:
        if dry_run:
            return [], False
        sheets.ensure_sheet(QUEUE_SHEET)
        return [], True


def _parse_queue_groups(rows: list[list]) -> list[Group]:
    if not rows:
        return []
    headers = [str(value) for value in rows[0]]
    if headers == GROUP_HEADERS:
        return [Group.from_sheet_row([str(value) for value in row], headers) for row in rows[1:] if row]

    groups: list[Group] = []
    for row in rows:
        if not row:
            continue
        inn = str(row[0]).strip()
        if not inn or inn.lower() == "inn" or inn.upper() == "ИНН":
            continue
        status = Status.NEW
        if len(row) > 3:
            try:
                status = Status(str(row[3]).strip())
            except ValueError:
                status = Status.NEW
        groups.append(
            Group(
                inn=inn,
                size=0,
                risk_class=None,
                status=status,
                winner_id=None,
                loser_ids=[],
                approved=False,
                approved_by=None,
                approved_at=None,
                actions_planned=0,
                conflicts_count=0,
                last_action_at=None,
                error_message=None,
                backup_sheet=None,
                ui_link=None,
            )
        )
    return groups


def _new_group_for_inn(inn: str, company_ids: list[str], now: datetime) -> Group:
    return Group(
        inn=inn,
        size=len(company_ids),
        risk_class=None,
        status=Status.NEW,
        winner_id=None,
        loser_ids=[],
        approved=False,
        approved_by=None,
        approved_at=None,
        actions_planned=0,
        conflicts_count=0,
        last_action_at=now,
        error_message=None,
        backup_sheet=None,
        ui_link=None,
    )


def _status_counts(existing_groups: list[Group], new_count: int) -> dict[Status, int]:
    counts = {status: 0 for status in Status}
    for group in existing_groups:
        counts[group.status] += 1
    counts[Status.NEW] += new_count
    return counts


def _format_mtime(path: Path, timezone: str) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo(timezone)).isoformat(
        timespec="seconds"
    )


def _sort_id(value: str) -> tuple[int, str]:
    return (int(value), value) if value.isdigit() else (10**18, value)
