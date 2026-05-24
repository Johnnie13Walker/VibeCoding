from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS
from crm_deal_merge.models import GROUP_HEADERS, Group
from crm_deal_merge.stages import inventory_spotcheck
from crm_deal_merge.state import Status


class FakeSheets:
    def __init__(self, groups: list[Group]) -> None:
        self.rows = [GROUP_HEADERS, *[group.to_sheet_row() for group in groups]]

    def read(self, sheet: str, *args, **kwargs):
        assert sheet == TAB_GROUPS
        return self.rows


class FakeBitrix:
    def __init__(self, items_by_loser: dict[str, list[tuple[int, list[dict]]]]) -> None:
        self.items_by_loser = items_by_loser
        self.requested_losers: list[str] = []

    def smart_process_types(self) -> list[dict]:
        return [
            {"entityTypeId": 1040, "title": "Данные для дашборда"},
            {"entityTypeId": 1044, "title": "Данные для дашборда (стадии сделки)"},
            {"entityTypeId": 1052, "title": "Импорт баз"},
            {"entityTypeId": 1056, "title": "Бриф"},
        ]

    def list_smart_items_for_deal(self, loser_id: str) -> list[tuple[int, list[dict]]]:
        self.requested_losers.append(loser_id)
        return self.items_by_loser.get(loser_id, [])


def _group(company_id: str, domain: str | None, loser_ids: list[str], status: Status = Status.PLAN_READY) -> Group:
    return Group(
        company_id=company_id,
        company_name=f"Company {company_id}",
        inn="123",
        domain=domain,
        winner_id=f"2{company_id}",
        winner_stage="C50:NEW",
        winner_stage_name="Новая",
        winner_closed=False,
        loser_ids=loser_ids,
        status=status,
    )


def test_inventory_spotcheck_reports_business_sp_risk(capsys) -> None:
    bx = FakeBitrix(
        {
            "100": [(1040, [{"id": 1}]), (1056, [{"id": 2}, {"id": 3}])],
            "101": [],
        }
    )
    sheets = FakeSheets([
        _group("10", "foo.ru", ["100", "101"]),
        _group("11", None, ["102"]),
        _group("12", "bar.ru", ["103"], Status.DONE),
    ])

    result = inventory_spotcheck.run(bx, sheets, sample=30, seed=42)

    assert bx.requested_losers == ["100", "101"]
    assert result["sampled_groups"] == 1
    assert result["sampled_losers"] == 2
    assert result["losers_with_sp"] == 1
    assert result["entity_counts"] == {"1040": 1, "1056": 2}
    assert result["entity_names"]["1056"] == "Бриф"
    assert result["business_sp_found"] is True
    assert result["business_entity_type_ids"] == ["1056"]
    assert result["top_heavy_losers"][0]["loser_id"] == "100"
    assert "ВНИМАНИЕ: возможна потеря бизнес-связей" in capsys.readouterr().out


def test_inventory_spotcheck_allows_only_telemetry_sp(capsys) -> None:
    bx = FakeBitrix({"100": [(1040, [{"id": 1}]), (1044, [{"id": 2}]), (1052, [{"id": 3}])]})
    sheets = FakeSheets([_group("10", "foo.ru", ["100"])])

    result = inventory_spotcheck.run(bx, sheets, sample=30, seed=42)

    assert result["entity_counts"] == {"1040": 1, "1044": 1, "1052": 1}
    assert result["business_sp_found"] is False
    assert "ВНИМАНИЕ" not in capsys.readouterr().out
