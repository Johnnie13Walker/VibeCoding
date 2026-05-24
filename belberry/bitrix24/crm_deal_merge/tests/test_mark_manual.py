from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS
from crm_deal_merge.models import GROUP_HEADERS, Group
from crm_deal_merge.stages import mark_manual
from crm_deal_merge.state import Status


class FakeSheets:
    def __init__(self, group: Group) -> None:
        self.rows = [GROUP_HEADERS, group.to_sheet_row()]
        self.updated: list[Group] = []

    def read(self, sheet, *args, **kwargs):
        assert sheet == TAB_GROUPS
        return self.rows

    def update(self, sheet, range_, rows, **kwargs):
        assert sheet == TAB_GROUPS
        self.updated.append(Group.from_sheet_row(rows[0], GROUP_HEADERS))


def _group(status=Status.FAILED) -> Group:
    return Group(
        company_id="13392",
        company_name="MGKL",
        inn="123",
        domain="mgkl.ru",
        winner_id="14716",
        winner_stage="C50:NEW",
        winner_stage_name="Новая",
        winner_closed=False,
        loser_ids=["5292", "1762"],
        status=status,
        approved=True,
        error_message="old error",
    )


def test_mark_manual_sets_manual_and_clears_approval():
    sheets = FakeSheets(_group())

    result = mark_manual.run(sheets, company_id="13392", domain="mgkl.ru", reason="TITLE=None")

    assert result["changed"] == 1
    updated = sheets.updated[-1]
    assert updated.status == Status.MANUAL
    assert updated.approved is False
    assert updated.error_message == "TITLE=None"


def test_mark_manual_not_found():
    sheets = FakeSheets(_group())

    result = mark_manual.run(sheets, company_id="1", domain="missing.ru", reason="x")

    assert result == {"changed": 0, "status": "NOT_FOUND"}
    assert sheets.updated == []
