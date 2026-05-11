from __future__ import annotations

import dataclasses
from collections import Counter
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from crm_company_merge.bitrix_client import BitrixClient
from crm_company_merge.config import Config
from crm_company_merge.models import GROUP_HEADERS, INVENTORY_HEADERS, Group, InventoryRecord
from crm_company_merge.notifications import build_progress_message, send_telegram
from crm_company_merge.sheets_client import SheetsClient
from crm_company_merge.state import Status

QUEUE_SHEET = "Очередь merge"
INVENTORY_SHEET = "Inventory"
TRANSFERABLE_TYPES = {"Deal", "Contact", "Activity", "Lead"}


def run(args, config=None) -> None:
    """
    Запускается через CLI: `crm-company-merge inventory --limit N [--dry-run]`.
    Обрабатывает группы со статусом NEW, по args.limit штук за прогон.
    """
    config = _resolve_config(args, config)
    pause_flag = Path(config.pause_flag_path)
    if pause_flag.exists():
        print(f"Paused since {_format_mtime(pause_flag, config.timezone)}")
        return

    bitrix = BitrixClient(config.bitrix_state_path)
    sheets = SheetsClient(config.sheet_id, config.google_service_account_json)
    queue_rows = sheets.read(QUEUE_SHEET)
    queue_items = _parse_queue_rows(queue_rows)
    targets = [item for item in queue_items if item.group.status == Status.NEW][: args.limit]

    if not targets:
        print("Inventory: нет групп NEW для обработки")
        return

    now = datetime.now(ZoneInfo(config.timezone))
    processed = 0
    total_records = 0
    type_counts: Counter[str] = Counter()
    updated_groups: list[tuple[int, Group]] = []

    if not args.dry_run:
        _ensure_inventory_header(sheets)

    for item in targets:
        group = item.group
        company_ids = bitrix.find_companies_by_inn(group.inn)
        if len(company_ids) < 2:
            failed = replace(
                group,
                size=len(company_ids),
                status=Status.FAILED,
                error_message=f"Дубль исчез: {len(company_ids)} карточек",
                last_action_at=now,
            )
            updated_groups.append((item.row_number, failed))
            if not args.dry_run:
                sheets.update(QUEUE_SHEET, f"A{item.row_number}:O{item.row_number}", [failed.to_sheet_row()])
            processed += 1
            continue

        records = _collect_group_inventory(bitrix, group.inn, company_ids)
        actions_planned = _count_transferable_actions(records)
        updated = replace(
            group,
            size=len(company_ids),
            status=Status.INVENTORIED,
            actions_planned=actions_planned,
            conflicts_count=0,
            last_action_at=now,
            error_message=None,
        )
        updated_groups.append((item.row_number, updated))
        processed += 1
        total_records += len(records)
        type_counts.update(record.entity_type for record in records)

        if not args.dry_run:
            if records:
                sheets.append(INVENTORY_SHEET, [record.to_sheet_row() for record in records])
            sheets.update(QUEUE_SHEET, f"A{item.row_number}:O{item.row_number}", [updated.to_sheet_row()])

    if args.dry_run:
        print(
            f"[dry-run] would inventory {processed} groups, "
            f"{total_records} relationships, actions_planned={sum(g.actions_planned for _, g in updated_groups)}"
        )
        print(f"[dry-run] relationship_types {_format_type_counts(type_counts)}")
    else:
        print(f"Inventory: обработано {processed} групп, всего связей {total_records}")

        status_counts = _status_counts(_groups_after_updates(queue_items, updated_groups))
        text = build_progress_message(
            stage_title="Inventory завершён",
            batch_stats=[
                ("Групп обработано", processed),
                ("Связей найдено", total_records),
            ],
            queue_counts=_queue_counts_for_message(status_counts),
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


def _parse_queue_rows(rows: list[list]) -> list[QueueItem]:
    if not rows:
        return []
    headers = [str(value) for value in rows[0]]
    if headers[: len(GROUP_HEADERS)] != GROUP_HEADERS:
        raise ValueError("Лист 'Очередь merge' должен начинаться с GROUP_HEADERS")
    items: list[QueueItem] = []
    for index, row in enumerate(rows[1:], start=2):
        if row:
            items.append(
                QueueItem(
                    index,
                    Group.from_sheet_row(
                        [str(value) for value in row[: len(GROUP_HEADERS)]], GROUP_HEADERS
                    ),
                )
            )
    return items


def _collect_group_inventory(
    bitrix: BitrixClient, inn: str, company_ids: list[str]
) -> list[InventoryRecord]:
    records: list[InventoryRecord] = []
    for company_id in company_ids:
        company = bitrix.get_company(company_id)
        if company is None:
            records.append(
                InventoryRecord(
                    inn=inn,
                    loser_id=company_id,
                    entity_type="Company",
                    child_id=company_id,
                    child_name="(удалена)",
                    owner="",
                    details="deleted",
                    transferred=False,
                    transferred_at=None,
                )
            )
            continue

        records.extend(_deal_record(inn, company_id, deal) for deal in bitrix.list_deals(company_id))
        records.extend(
            _contact_record(inn, company_id, contact) for contact in bitrix.list_contacts(company_id)
        )
        records.extend(
            _activity_record(inn, company_id, activity)
            for activity in bitrix.list_activities(company_id)
        )
        records.extend(_lead_record(inn, company_id, lead) for lead in bitrix.list_leads(company_id))
        for entity_type_id, items in bitrix.list_smart_items_for_company(company_id):
            records.extend(
                _smart_item_record(inn, company_id, entity_type_id, item) for item in items
            )
        for requisite in bitrix.list_requisites(company_id):
            records.append(_requisite_record(inn, company_id, requisite))
            requisite_id = _id(requisite)
            if requisite_id:
                records.extend(
                    _bank_detail_record(inn, company_id, bank_detail)
                    for bank_detail in bitrix.list_bank_details(requisite_id)
                )
        records.extend(
            _timeline_comment_record(inn, company_id, comment)
            for comment in bitrix.list_timeline_comments("company", company_id)
        )
    return records


def _deal_record(inn: str, company_id: str, deal: dict) -> InventoryRecord:
    return InventoryRecord(
        inn=inn,
        loser_id=company_id,
        entity_type="Deal",
        child_id=_id(deal),
        child_name=str(deal.get("TITLE") or ""),
        owner=_owner(deal),
        details=f"stage={deal.get('STAGE_ID', '')}, category={deal.get('CATEGORY_ID', '')}",
        transferred=False,
        transferred_at=None,
    )


def _contact_record(inn: str, company_id: str, contact: dict) -> InventoryRecord:
    name = " ".join(
        part
        for part in (str(contact.get("LAST_NAME") or "").strip(), str(contact.get("NAME") or "").strip())
        if part
    )
    return InventoryRecord(
        inn=inn,
        loser_id=company_id,
        entity_type="Contact",
        child_id=_id(contact),
        child_name=name,
        owner=_owner(contact),
        details="",
        transferred=False,
        transferred_at=None,
    )


def _activity_record(inn: str, company_id: str, activity: dict) -> InventoryRecord:
    return InventoryRecord(
        inn=inn,
        loser_id=company_id,
        entity_type="Activity",
        child_id=_id(activity),
        child_name=str(activity.get("SUBJECT") or ""),
        owner=_owner(activity),
        details=f"provider={activity.get('PROVIDER_ID', '')}, type={activity.get('TYPE_ID', '')}",
        transferred=False,
        transferred_at=None,
    )


def _lead_record(inn: str, company_id: str, lead: dict) -> InventoryRecord:
    return InventoryRecord(
        inn=inn,
        loser_id=company_id,
        entity_type="Lead",
        child_id=_id(lead),
        child_name=str(lead.get("TITLE") or ""),
        owner=_owner(lead),
        details=f"status={lead.get('STATUS_ID', '')}",
        transferred=False,
        transferred_at=None,
    )


def _smart_item_record(
    inn: str, company_id: str, entity_type_id: int, item: dict
) -> InventoryRecord:
    return InventoryRecord(
        inn=inn,
        loser_id=company_id,
        entity_type=f"SmartItem:{entity_type_id}",
        child_id=_id(item),
        child_name=str(item.get("title") or item.get("TITLE") or ""),
        owner=_owner(item),
        details=f"entityTypeId={entity_type_id}",
        transferred=False,
        transferred_at=None,
    )


def _requisite_record(inn: str, company_id: str, requisite: dict) -> InventoryRecord:
    child_name = f"{requisite.get('RQ_INN', '')}:{requisite.get('RQ_KPP', '')}"
    return InventoryRecord(
        inn=inn,
        loser_id=company_id,
        entity_type="Requisite",
        child_id=_id(requisite),
        child_name=child_name,
        owner=_owner(requisite),
        details=f"preset={requisite.get('PRESET_ID', '')}",
        transferred=False,
        transferred_at=None,
    )


def _bank_detail_record(inn: str, company_id: str, bank_detail: dict) -> InventoryRecord:
    return InventoryRecord(
        inn=inn,
        loser_id=company_id,
        entity_type="BankDetail",
        child_id=_id(bank_detail),
        child_name=str(bank_detail.get("BANK_DETAIL_NAME") or bank_detail.get("NAME") or ""),
        owner=_owner(bank_detail),
        details=f"rq_acc_num={bank_detail.get('RQ_ACC_NUM', '')}",
        transferred=False,
        transferred_at=None,
    )


def _timeline_comment_record(inn: str, company_id: str, comment: dict) -> InventoryRecord:
    text = str(comment.get("COMMENT") or "")
    return InventoryRecord(
        inn=inn,
        loser_id=company_id,
        entity_type="TimelineComment",
        child_id=_id(comment),
        child_name=text[:60],
        owner=_owner(comment),
        details="",
        transferred=False,
        transferred_at=None,
    )


def _count_transferable_actions(records: list[InventoryRecord]) -> int:
    return sum(
        1
        for record in records
        if record.entity_type in TRANSFERABLE_TYPES or record.entity_type.startswith("SmartItem:")
    )


def _ensure_inventory_header(sheets: SheetsClient) -> None:
    sheets.ensure_sheet(INVENTORY_SHEET)
    rows = sheets.read(INVENTORY_SHEET, "A1:I1")
    if not rows:
        sheets.update(INVENTORY_SHEET, "A1", [INVENTORY_HEADERS])


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


def _queue_counts_for_message(status_counts: dict[Status, int]) -> dict[str, int]:
    return {status.value: count for status, count in status_counts.items()}


def _format_type_counts(type_counts: Counter[str]) -> str:
    if not type_counts:
        return "{}"
    return ", ".join(f"{name}={count}" for name, count in sorted(type_counts.items()))


def _format_mtime(path: Path, timezone: str) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo(timezone)).isoformat(
        timespec="seconds"
    )


def _id(item: dict) -> str:
    return str(item.get("ID") or item.get("id") or "").strip()


def _owner(item: dict) -> str:
    return str(
        item.get("ASSIGNED_BY_ID")
        or item.get("assignedById")
        or item.get("RESPONSIBLE_ID")
        or item.get("responsibleId")
        or ""
    )
