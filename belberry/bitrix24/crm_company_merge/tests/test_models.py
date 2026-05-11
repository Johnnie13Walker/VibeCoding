from __future__ import annotations

from datetime import datetime, timezone

import pytest

from crm_company_merge.models import (
    CONFLICT_HEADERS,
    GROUP_HEADERS,
    INVENTORY_HEADERS,
    LOG_ENTRY_HEADERS,
    Conflict,
    Group,
    InventoryRecord,
    LogEntry,
)
from crm_company_merge.state import Status


def test_group_round_trip() -> None:
    group = Group(
        inn="7701234567",
        size=3,
        risk_class="B",
        status=Status.PLAN_READY,
        winner_id=None,
        loser_ids=["101", "102"],
        approved=True,
        approved_by="Лариса",
        approved_at=None,
        actions_planned=7,
        conflicts_count=2,
        last_action_at=datetime(2026, 5, 11, 10, 30, tzinfo=timezone.utc),
        error_message=None,
        backup_sheet="Backup 2026-05-11 13-30",
        ui_link="https://belberrycrm.bitrix24.ru/crm/company/details/101/",
    )

    restored = Group.from_sheet_row(group.to_sheet_row(), GROUP_HEADERS)

    assert restored == group


def test_group_round_trip_empty_loser_ids() -> None:
    group = Group(
        inn="5001044465",
        size=1,
        risk_class=None,
        status=Status.DONE,
        winner_id="4822",
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

    restored = Group.from_sheet_row(group.to_sheet_row(), GROUP_HEADERS)

    assert restored == group


def test_inventory_record_to_sheet_row() -> None:
    transferred_at = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
    record = InventoryRecord(
        inn="7701234567",
        loser_id="102",
        entity_type="Deal",
        child_id="500",
        child_name="Сделка",
        owner="2812",
        details="pipeline=10",
        transferred=True,
        transferred_at=transferred_at,
    )

    row = record.to_sheet_row()

    assert len(row) == len(INVENTORY_HEADERS)
    assert row == [
        "7701234567",
        "102",
        "Deal",
        "500",
        "Сделка",
        "2812",
        "pipeline=10",
        "1",
        "2026-05-11T15:00:00+03:00",
    ]


def test_conflict_to_sheet_row() -> None:
    conflict = Conflict(
        inn="7701234567",
        field="TITLE",
        kind="text",
        winner_value="Short",
        loser_value="Long company title",
        resolution="loser_wins",
        applied=False,
    )

    assert conflict.to_sheet_row() == [
        "7701234567",
        "TITLE",
        "text",
        "Short",
        "Long company title",
        "loser_wins",
        "0",
    ]
    assert len(conflict.to_sheet_row()) == len(CONFLICT_HEADERS)


def test_log_entry_to_sheet_row() -> None:
    entry = LogEntry(
        ts=datetime(2026, 5, 11, 9, 0, tzinfo=timezone.utc),
        inn="7701234567",
        stage="inventory",
        action="list_deals",
        api_method="crm.deal.list",
        request_hash="abc123",
        response_summary="result:list:2",
        ok=True,
        duration_ms=42,
    )

    row = entry.to_sheet_row()

    assert row == [
        "2026-05-11T12:00:00+03:00",
        "7701234567",
        "inventory",
        "list_deals",
        "crm.deal.list",
        "abc123",
        "result:list:2",
        "1",
        "42",
    ]
    assert len(row) == len(LOG_ENTRY_HEADERS)


def test_group_from_sheet_row_rejects_unknown_status() -> None:
    row = ["7701234567", "2", "", "UNKNOWN"]

    with pytest.raises(ValueError):
        Group.from_sheet_row(row, GROUP_HEADERS)
