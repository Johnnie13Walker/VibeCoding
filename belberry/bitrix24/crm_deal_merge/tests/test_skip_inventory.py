from __future__ import annotations

from crm_deal_merge.config import TAB_INVENTORY
from crm_deal_merge.models import INVENTORY_HEADERS
from crm_deal_merge.stages import skip_inventory


class FakeSheets:
    def __init__(self) -> None:
        self.rows = [
            INVENTORY_HEADERS,
            ["36", "366", "sp:1040", "1", "dash", "{}", "0", "", ""],
            ["36", "366", "sp:1044", "2", "dash stage", "{}", "0", "", ""],
            ["36", "366", "activity", "3", "call", "{}", "0", "", ""],
            ["42", "380", "sp:1040", "4", "other", "{}", "0", "", ""],
            ["42", "380", "sp:1048", "5", "meeting", "{}", "0", "", ""],
        ]
        self.updated: list[tuple[str, list[str]]] = []

    def ensure_sheet(self, *args, **kwargs):
        return 1

    def read(self, sheet: str, *args, **kwargs):
        assert sheet == TAB_INVENTORY
        return self.rows

    def update(self, sheet: str, range_: str, rows: list[list[str]], **kwargs) -> None:
        assert sheet == TAB_INVENTORY
        row_number = int("".join(ch for ch in range_.split(":", 1)[0] if ch.isdigit()))
        for offset, row in enumerate(rows):
            self.updated.append((range_, row))
            self.rows[row_number - 1 + offset] = row


def test_skip_inventory_marks_rows_by_prefix() -> None:
    sheets = FakeSheets()

    result = skip_inventory.run(
        sheets,
        entity_type_prefix="sp:1040",
        where={"company_id": "36"},
    )

    assert result["changed"] == 1
    updated = dict(zip(INVENTORY_HEADERS, sheets.updated[0][1]))
    assert updated["company_id"] == "36"
    assert updated["entity_type"] == "sp:1040"
    assert updated["transferred"] == "1"
    assert updated["note"] == "skipped_sp_telemetry"


def test_skip_inventory_filters_company_id() -> None:
    sheets = FakeSheets()

    result = skip_inventory.run(
        sheets,
        entity_type_prefix="sp:1040",
        where={"company_id": "42"},
    )

    assert result["changed"] == 1
    updated = dict(zip(INVENTORY_HEADERS, sheets.updated[0][1]))
    assert updated["company_id"] == "42"


def test_parse_where_normalizes_keys() -> None:
    assert skip_inventory.parse_where(["company-id=36"]) == {"company_id": "36"}


def test_mass_skip_all_companies() -> None:
    sheets = FakeSheets()

    result = skip_inventory.run(
        sheets,
        entity_type_prefix="sp:1040",
        all_companies=True,
    )

    assert result["changed"] == 2
    updated_rows = [
        dict(zip(INVENTORY_HEADERS, row))
        for _, row in sheets.updated
        if dict(zip(INVENTORY_HEADERS, row))["entity_type"] == "sp:1040"
    ]
    assert {row["company_id"] for row in updated_rows} == {"36", "42"}
    assert all(row["transferred"] == "1" for row in updated_rows)
    assert all(row["note"] == "skipped_sp_telemetry" for row in updated_rows)


def test_mass_skip_does_not_touch_other_prefix() -> None:
    sheets = FakeSheets()

    skip_inventory.run(
        sheets,
        entity_type_prefix="sp:1040",
        all_companies=True,
    )

    untouched = dict(zip(INVENTORY_HEADERS, sheets.rows[5]))
    assert untouched["entity_type"] == "sp:1048"
    assert untouched["transferred"] == "0"
