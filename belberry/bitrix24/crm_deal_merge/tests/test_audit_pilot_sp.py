from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS
from crm_deal_merge.models import GROUP_HEADERS, Group
from crm_deal_merge.stages import audit_pilot_sp
from crm_deal_merge.state import Status


class FakeSheets:
    def __init__(self, groups: list[Group]) -> None:
        self.rows = [GROUP_HEADERS, *[group.to_sheet_row() for group in groups]]

    def read(self, sheet: str, *args, **kwargs):
        assert sheet == TAB_GROUPS
        return self.rows


class FakeBitrix:
    def smart_process_types(self) -> list[dict]:
        return [
            {"entityTypeId": 1040, "title": "Данные для дашборда"},
            {"entityTypeId": 1048, "title": "Встречи"},
        ]

    def list_smart_items_for_deal(self, loser_id: str) -> list[tuple[int, list[dict]]]:
        return {
            "100": [(1040, [{"id": "dash"}]), (1048, [{"id": "m1", "title": "Встреча"}])],
            "101": [(1040, [{"id": "dash2"}])],
        }.get(loser_id, [])


def _group(company_id: str, domain: str, loser_id: str) -> Group:
    return Group(
        company_id=company_id,
        company_name=f"Company {company_id}",
        inn="123",
        domain=domain,
        winner_id=f"2{company_id}",
        winner_stage="C50:NEW",
        winner_stage_name="Новая",
        winner_closed=False,
        loser_ids=[loser_id],
        status=Status.DONE,
    )


def test_audit_pilot_sp_reports_manual_business_sp(capsys) -> None:
    sheets = FakeSheets([_group("10", "foo.ru", "100")])

    result = audit_pilot_sp.run(FakeBitrix(), sheets, groups_arg="10:foo.ru")

    assert result["groups_checked"] == 1
    assert result["business_sp_counts"] == {"1048": 1}
    assert result["manual_actions"][0]["entity_type_id"] == "1048"
    out = capsys.readouterr().out
    assert "[РУЧНОЙ ПЕРЕНОС НУЖЕН]" in out
    assert "перепривязать SP:1048 #m1" in out


def test_audit_pilot_sp_reports_ok_when_only_telemetry(capsys) -> None:
    sheets = FakeSheets([_group("11", "bar.ru", "101")])

    result = audit_pilot_sp.run(FakeBitrix(), sheets, groups_arg="11:bar.ru")

    assert result["manual_actions"] == []
    assert result["business_sp_counts"] == {}
    assert "OK, пилот 11:bar.ru без бизнес-SP" in capsys.readouterr().out
