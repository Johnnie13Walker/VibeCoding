from __future__ import annotations

import dataclasses
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from crm_company_merge.bitrix_client import BitrixClient
from crm_company_merge.config import Config
from crm_company_merge.models import (
    CONFLICT_HEADERS,
    GROUP_HEADERS,
    INVENTORY_HEADERS,
    Conflict,
    Group,
    InventoryRecord,
)
from crm_company_merge.notifications import send_telegram
from crm_company_merge.sheets_client import SheetsClient
from crm_company_merge.state import Status

QUEUE_SHEET = "Очередь merge"
INVENTORY_SHEET = "Inventory"
CONFLICTS_SHEET = "Конфликты полей"

MULTIFIELD_KEYS = {"PHONE", "EMAIL", "WEB", "IM", "LINK"}
UF_PREFIX = "UF_CRM_"
IGNORE_FIELDS = {
    "ID",
    "DATE_CREATE",
    "DATE_MODIFY",
    "CREATED_BY_ID",
    "MODIFY_BY_ID",
    "LAST_NAME",
    "FIRST_NAME",
}
TEXT_FIELDS = [
    "TITLE",
    "COMMENTS",
    "INDUSTRY",
    "EMPLOYEES",
    "REVENUE",
    "CURRENCY_ID",
    "IS_MY_COMPANY",
    "OPENED",
]


def run(args, config=None) -> None:
    """
    Запускается через CLI: `crm-company-merge classify --limit N [--dry-run]`.
    Обрабатывает группы со статусом INVENTORIED, по args.limit штук.
    """
    config = _resolve_config(args, config)
    pause_flag = Path(config.pause_flag_path)
    if pause_flag.exists():
        print(f"Paused since {_format_mtime(pause_flag, config.timezone)}")
        return

    bitrix = BitrixClient(config.bitrix_state_path)
    sheets = SheetsClient(config.sheet_id, config.google_service_account_json)
    queue_items = _parse_queue_rows(sheets.read(QUEUE_SHEET))
    targets = [item for item in queue_items if item.group.status == Status.INVENTORIED][
        : args.limit
    ]
    if not targets:
        print("Classify: нет групп INVENTORIED для обработки")
        return

    inventory_index = _build_inventory_index(sheets.read(INVENTORY_SHEET))
    now = datetime.now(ZoneInfo(config.timezone))
    company_cache: dict[str, dict | None] = {}
    updated_groups: list[tuple[int, Group]] = []
    all_conflicts: list[Conflict] = []
    class_counts: Counter[str] = Counter()

    for item in targets:
        updated, conflicts = _classify_group(
            bitrix=bitrix,
            group=item.group,
            inventory_index=inventory_index,
            company_cache=company_cache,
            now=now,
        )
        updated_groups.append((item.row_number, updated))
        if updated.risk_class:
            class_counts[updated.risk_class] += 1
        all_conflicts.extend(conflicts)

    if args.dry_run:
        print(
            f"[dry-run] would update {len(updated_groups)} groups: "
            f"{class_counts['A']} class A, {class_counts['B']} class B, "
            f"{class_counts['C']} class C"
        )
        print(f"[dry-run] would append {len(all_conflicts)} conflicts")
        return

    _ensure_sheet_header(sheets, CONFLICTS_SHEET, CONFLICT_HEADERS)
    if all_conflicts:
        sheets.append(CONFLICTS_SHEET, [conflict.to_sheet_row() for conflict in all_conflicts])
    for row_number, group in updated_groups:
        sheets.update(QUEUE_SHEET, f"A{row_number}:O{row_number}", [group.to_sheet_row()])

    print(f"Classify: обработано {len(updated_groups)} групп, конфликтов {len(all_conflicts)}")
    status_counts = _status_counts(_groups_after_updates(queue_items, updated_groups))
    text = (
        f"Classify: обработано {len(updated_groups)} групп. "
        f"Классы: A={class_counts['A']} / B={class_counts['B']} / C={class_counts['C']}. "
        f"Очередь: {status_counts[Status.PLAN_READY]} PLAN_READY / "
        f"{status_counts[Status.MANUAL]} MANUAL / {status_counts[Status.FAILED]} FAILED"
    )
    if config.telegram_bot_token and config.telegram_chat_id is not None:
        send_telegram(config.telegram_bot_token, config.telegram_chat_id, text)


@dataclasses.dataclass(frozen=True)
class QueueItem:
    row_number: int
    group: Group


def _resolve_config(args, config: Config | None) -> Config:
    resolved = config or Config.from_env()
    if getattr(args, "sheet", None):
        resolved = dataclasses.replace(resolved, sheet_id=args.sheet)
    return resolved


def _classify_group(
    *,
    bitrix: BitrixClient,
    group: Group,
    inventory_index: dict[str, dict[str, list[InventoryRecord]]],
    company_cache: dict[str, dict | None],
    now: datetime,
) -> tuple[Group, list[Conflict]]:
    company_ids = bitrix.find_companies_by_inn(group.inn)
    if len(company_ids) < 2:
        return (
            replace(
                group,
                size=len(company_ids),
                status=Status.FAILED,
                error_message=f"Дубль исчез: {len(company_ids)} карточек",
                last_action_at=now,
            ),
            [],
        )

    companies: dict[str, dict] = {}
    for company_id in company_ids:
        company = _get_company_cached(bitrix, company_cache, company_id)
        if company is not None:
            companies[company_id] = company

    if len(companies) < 2:
        return (
            replace(
                group,
                size=len(companies),
                status=Status.FAILED,
                error_message=f"Дубль исчез: {len(companies)} карточек",
                last_action_at=now,
            ),
            [],
        )

    live_company_ids = sorted(companies, key=_sort_id)
    counts = {
        company_id: _relationship_counts(inventory_index.get(group.inn, {}).get(company_id, []))
        for company_id in live_company_ids
    }
    winner_id = _choose_winner(bitrix, live_company_ids, companies, counts)
    loser_ids = [company_id for company_id in live_company_ids if company_id != winner_id]
    risk_class = _risk_class(loser_ids, counts)

    if risk_class == "C":
        return (
            replace(
                group,
                size=len(live_company_ids),
                risk_class=risk_class,
                status=Status.MANUAL,
                winner_id=winner_id,
                loser_ids=loser_ids,
                conflicts_count=0,
                last_action_at=now,
                error_message=None,
                ui_link=f"https://belberrycrm.bitrix24.ru/crm/company/details/{winner_id}/",
            ),
            [],
        )

    conflicts = _build_conflicts(group.inn, winner_id, loser_ids, companies)
    return (
        replace(
            group,
            size=len(live_company_ids),
            risk_class=risk_class,
            status=Status.PLAN_READY,
            winner_id=winner_id,
            loser_ids=loser_ids,
            conflicts_count=len(conflicts),
            last_action_at=now,
            error_message=None,
            ui_link=None,
        ),
        conflicts,
    )


def _get_company_cached(
    bitrix: BitrixClient, company_cache: dict[str, dict | None], company_id: str
) -> dict | None:
    if company_id not in company_cache:
        company_cache[company_id] = bitrix.get_company(company_id)
    return company_cache[company_id]


def _choose_winner(
    bitrix: BitrixClient,
    company_ids: list[str],
    companies: dict[str, dict],
    counts: dict[str, dict[str, int]],
) -> str:
    active_deals_cache: dict[str, int] = {}

    def active_deals(company_id: str) -> int:
        if company_id not in active_deals_cache:
            active_deals_cache[company_id] = sum(
                1 for deal in bitrix.list_deals(company_id, closed=False) if _is_active_deal(deal)
            )
        return active_deals_cache[company_id]

    # Порядок эвристики winner строго соответствует контракту:
    # filled fields -> active deals -> DATE_MODIFY -> total relationships -> company_id.
    return max(
        company_ids,
        key=lambda company_id: (
            _count_filled_fields(companies[company_id]),
            active_deals(company_id),
            _parse_datetime_sort(companies[company_id].get("DATE_MODIFY")),
            sum(counts[company_id].values()),
            _int_id(company_id),
        ),
    )


def _risk_class(loser_ids: list[str], counts: dict[str, dict[str, int]]) -> str:
    if all(all(counts[loser][key] == 0 for key in counts[loser]) for loser in loser_ids):
        return "A"
    if all(
        counts[loser]["deals"] <= 3
        and counts[loser]["contacts"] <= 2
        and counts[loser]["activities"] <= 5
        and counts[loser]["smart_items"] == 0
        for loser in loser_ids
    ):
        return "B"
    return "C"


def _build_conflicts(
    inn: str, winner_id: str, loser_ids: list[str], companies: dict[str, dict]
) -> list[Conflict]:
    conflicts: list[Conflict] = []
    winner = companies[winner_id]
    fields = _conflict_fields(winner, [companies[loser_id] for loser_id in loser_ids])
    for loser_id in loser_ids:
        loser = companies[loser_id]
        for field in fields:
            conflict = _field_conflict(inn, field, winner.get(field), loser.get(field))
            if conflict:
                conflicts.append(conflict)
    return conflicts


def _field_conflict(inn: str, field: str, winner_value: Any, loser_value: Any) -> Conflict | None:
    kind = _field_kind(field)
    winner_norm = _normalize_for_compare(winner_value, kind)
    loser_norm = _normalize_for_compare(loser_value, kind)
    if _is_empty_value(winner_norm) and _is_empty_value(loser_norm):
        return None
    if winner_norm == loser_norm:
        return None
    if _is_empty_value(winner_norm):
        resolution = "loser_wins"
    elif _is_empty_value(loser_norm):
        resolution = "winner_wins"
    elif kind == "multifield":
        resolution = "union"
    else:
        winner_len = len(str(winner_norm))
        loser_len = len(str(loser_norm))
        if winner_len > loser_len:
            resolution = "winner_wins"
        elif loser_len > winner_len:
            resolution = "loser_wins"
        else:
            resolution = "manual"
    return Conflict(
        inn=inn,
        field=field,
        kind=kind,
        winner_value=str(winner_norm),
        loser_value=str(loser_norm),
        resolution=resolution,
        applied=False,
    )


def _conflict_fields(winner: dict, losers: list[dict]) -> list[str]:
    fields = list(TEXT_FIELDS) + sorted(MULTIFIELD_KEYS)
    all_companies = [winner, *losers]
    uf_fields = sorted(
        key
        for company in all_companies
        for key, value in company.items()
        if key.startswith(UF_PREFIX) and not _is_empty_value(value)
    )
    for field in uf_fields:
        if field not in fields:
            fields.append(field)
    return fields


def _field_kind(field: str) -> str:
    if field in MULTIFIELD_KEYS:
        return "multifield"
    if field.startswith(UF_PREFIX):
        return "uf"
    return "text"


def _relationship_counts(records: list[InventoryRecord]) -> dict[str, int]:
    return {
        "deals": sum(1 for record in records if record.entity_type == "Deal"),
        "contacts": sum(1 for record in records if record.entity_type == "Contact"),
        "activities": sum(1 for record in records if record.entity_type == "Activity"),
        "leads": sum(1 for record in records if record.entity_type == "Lead"),
        "smart_items": sum(1 for record in records if record.entity_type.startswith("SmartItem:")),
    }


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


def _count_filled_fields(company: dict) -> int:
    return sum(
        1
        for key, value in company.items()
        if key not in IGNORE_FIELDS and not _is_empty_value(value)
    )


def _is_active_deal(deal: dict) -> bool:
    stage = str(deal.get("STAGE_ID") or "")
    closed_suffixes = (":WON", ":LOSE", ":APOLOGY")
    return not any(stage.endswith(suffix) for suffix in closed_suffixes)


def _multifield_to_set(value) -> frozenset[tuple[str, str]]:
    if not value:
        return frozenset()
    return frozenset(
        (str(item.get("VALUE_TYPE", "")), str(item.get("VALUE", "")))
        for item in value
        if isinstance(item, dict)
    )


def _normalize_for_compare(value: Any, kind: str) -> Any:
    if kind == "multifield":
        return _multifield_to_set(value)
    return value


def _is_empty_value(value: Any) -> bool:
    return value in (None, "", 0, "0", [], {}) or value == frozenset()


def _parse_datetime_sort(value: Any) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _format_mtime(path: Path, timezone: str) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo(timezone)).isoformat(
        timespec="seconds"
    )


def _sort_id(value: str) -> tuple[int, str]:
    return (_int_id(value), value) if value.isdigit() else (10**18, value)


def _int_id(value: str) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0
