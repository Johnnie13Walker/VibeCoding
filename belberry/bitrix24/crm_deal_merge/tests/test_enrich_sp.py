from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS, TAB_INVENTORY
from crm_deal_merge.models import GROUP_HEADERS, INVENTORY_HEADERS, Group
from crm_deal_merge.stages import inventory_sp
from crm_deal_merge.state import Status


class FakeBitrix:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_smart_items_for_deal(self, loser_id: str) -> list[tuple[int, list[dict]]]:
        self.calls.append(loser_id)
        return {
            "100": [(1048, [{"id": "sp1", "title": "Встреча 1"}])],
            "101": [(1056, [{"id": "sp2", "title": "Бриф"}])],
        }.get(loser_id, [])


class FakeSheets:
    def __init__(self) -> None:
        self.group = Group(
            company_id="10",
            company_name="Company",
            inn="123",
            domain="foo.ru",
            winner_id="200",
            winner_stage="C50:NEW",
            winner_stage_name="Новая",
            winner_closed=False,
            loser_ids=["100", "101"],
            status=Status.PLAN_READY,
            n_sp_planned=0,
        )
        self.groups = [GROUP_HEADERS, self.group.to_sheet_row()]
        self.inventory = [
            INVENTORY_HEADERS,
            ["10", "100", "activity", "a1", "call", "{}", "0", "", ""],
        ]

    def ensure_sheet(self, *args, **kwargs):
        return 1

    def read(self, sheet: str, *args, **kwargs):
        if sheet == TAB_GROUPS:
            return self.groups
        if sheet == TAB_INVENTORY:
            return self.inventory
        raise AssertionError(sheet)

    def append(self, sheet: str, rows: list[list[str]], **kwargs) -> None:
        assert sheet == TAB_INVENTORY
        self.inventory.extend(rows)

    def update(self, sheet: str, range_: str, rows: list[list[str]], **kwargs) -> None:
        if sheet == TAB_GROUPS:
            self.groups[1] = rows[0]
        elif sheet == TAB_INVENTORY:
            row_number = int("".join(ch for ch in range_.split(":", 1)[0] if ch.isdigit()))
            self.inventory[row_number - 1] = rows[0]
        else:
            raise AssertionError(sheet)


def test_enrich_sp_adds_only_new_sp_and_updates_group_count() -> None:
    sheets = FakeSheets()
    bx = FakeBitrix()

    result = inventory_sp.run(bx, sheets)

    assert result["processed"] == 1
    assert result["added"] == 2
    assert result["types"] == {"sp:1048": 1, "sp:1056": 1}
    entity_types = [row[2] for row in sheets.inventory[1:]]
    assert entity_types == ["activity", "sp:1048", "sp:1056"]
    updated = Group.from_sheet_row(sheets.groups[1], GROUP_HEADERS)
    assert updated.status == Status.PLAN_READY
    assert updated.n_sp_planned == 2


def test_enrich_sp_is_idempotent() -> None:
    sheets = FakeSheets()
    bx = FakeBitrix()

    first = inventory_sp.run(bx, sheets)
    second = inventory_sp.run(bx, sheets)

    assert first["added"] == 2
    assert second["added"] == 0
    assert len(sheets.inventory) == 4
    updated = Group.from_sheet_row(sheets.groups[1], GROUP_HEADERS)
    assert updated.n_sp_planned == 2
