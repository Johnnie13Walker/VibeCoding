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
    targets = [
        item
        for item in _parse_queue_rows(sheets.read(QUEUE_SHEET))
        if item.group.status == Status.FAILED
        and "Дубль исчез" in (item.group.error_message or "")
    ]
    now = datetime.now(ZoneInfo(config.timezone))
    updated: list[QueueItem] = []
    still_failed: list[str] = []
    one_company = 0
    zero_companies = 0

    for item in targets:
        company_ids = bitrix.find_companies_by_inn(item.group.inn)
        if len(company_ids) == 1:
            one_company += 1
            updated.append(
                QueueItem(
                    item.row_number,
                    replace(
                        item.group,
                        status=Status.DONE,
                        winner_id=company_ids[0],
                        loser_ids=[],
                        last_action_at=now,
                        error_message="merged_externally_before_workflow",
                    ),
                )
            )
        elif len(company_ids) == 0:
            zero_companies += 1
            updated.append(
                QueueItem(
                    item.row_number,
                    replace(
                        item.group,
                        status=Status.DONE,
                        winner_id=None,
                        loser_ids=[],
                        last_action_at=now,
                        error_message="no_companies_found",
                    ),
                )
            )
        else:
            still_failed.append(item.group.inn)

    if args.dry_run:
        print(
            "[dry-run] reclassify-failed: "
            f"targets={len(targets)}, one_company={one_company}, "
            f"zero_companies={zero_companies}, still_failed={len(still_failed)}"
        )
        if still_failed:
            print(f"[dry-run] still failed inns: {', '.join(still_failed)}")
        return

    for item in updated:
        sheets.update(QUEUE_SHEET, f"A{item.row_number}:O{item.row_number}", [item.group.to_sheet_row()])
    print(
        "Reclassify failed: "
        f"DONE={len(updated)}, still_failed={len(still_failed)}"
    )


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


def _format_mtime(path: Path, timezone: str) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo(timezone)).isoformat(
        timespec="seconds"
    )
