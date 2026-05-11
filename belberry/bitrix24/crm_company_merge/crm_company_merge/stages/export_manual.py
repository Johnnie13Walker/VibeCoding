from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from crm_company_merge.bitrix_client import BitrixClient
from crm_company_merge.config import Config
from crm_company_merge.models import GROUP_HEADERS, Group
from crm_company_merge.sheets_client import SheetsClient
from crm_company_merge.state import Status

QUEUE_SHEET = "Очередь merge"
MANUAL_EXPORT_SHEET = "🔧 Для UI Битрикса"
MANUAL_EXPORT_HEADERS = [
    "ИНН",
    "Название компании (winner)",
    "Дубль (loser)",
    "Открыть в UI дубликатов",
    "Статус ручной обработки",
]
PORTAL_BASE_URL = "https://belberrycrm.bitrix24.ru"


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
    manual_groups = [
        item.group
        for item in _parse_queue_rows(sheets.read(QUEUE_SHEET))
        if item.group.status == Status.MANUAL
    ]
    rows = [_manual_row(bitrix, group) for group in manual_groups]

    if args.dry_run:
        print(f"[dry-run] export-manual: would build {len(rows)} rows with links")
        return

    sheets.ensure_sheet(MANUAL_EXPORT_SHEET)
    sheets.clear(MANUAL_EXPORT_SHEET)
    sheets.update(
        MANUAL_EXPORT_SHEET,
        "A1:E1",
        [MANUAL_EXPORT_HEADERS],
        value_input_option="USER_ENTERED",
    )
    if rows:
        sheets.update(
            MANUAL_EXPORT_SHEET,
            f"A2:E{len(rows) + 1}",
            rows,
            value_input_option="USER_ENTERED",
        )
    print(f"Export manual: создан лист '{MANUAL_EXPORT_SHEET}', строк {len(rows)}")


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


def _manual_row(bitrix: BitrixClient, group: Group) -> list[str]:
    winner_id = group.winner_id or ""
    winner = bitrix.get_company(winner_id) if winner_id else None
    winner_title = _company_title(winner, winner_id)
    loser_cell = _loser_cell(bitrix, group.loser_ids)
    return [
        group.inn,
        _company_link(winner_id, winner_title) if winner_id else "",
        loser_cell,
        _dedupe_link(group.inn),
        "",
    ]


def _loser_cell(bitrix: BitrixClient, loser_ids: list[str]) -> str:
    if not loser_ids:
        return ""
    first_id = loser_ids[0]
    company = bitrix.get_company(first_id)
    title = _company_title(company, first_id)
    if len(loser_ids) == 1:
        return _company_link(first_id, title)
    return f'{_company_link(first_id, title)} & " +{len(loser_ids) - 1}"'


def _company_title(company: dict | None, fallback_id: str) -> str:
    if not company:
        return f"company_id={fallback_id}"
    return str(company.get("TITLE") or f"company_id={fallback_id}")


def _company_link(company_id: str, title: str) -> str:
    url = f"{PORTAL_BASE_URL}/crm/company/details/{company_id}/"
    return _hyperlink(url, title)


def _dedupe_link(inn: str) -> str:
    url = f"{PORTAL_BASE_URL}/crm/deduplicate/?ENTITY_TYPE_ID=COMPANY&filter[inn]={inn}"
    return _hyperlink(url, "Открыть")


def _hyperlink(url: str, label: str) -> str:
    return f'=HYPERLINK("{_escape_formula(url)}"; "{_escape_formula(label)}")'


def _escape_formula(value: str) -> str:
    return value.replace('"', '""')


def _format_mtime(path: Path, timezone: str) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo(timezone)).isoformat(
        timespec="seconds"
    )
