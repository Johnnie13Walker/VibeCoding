from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS
from crm_deal_merge.models import GROUP_HEADERS, Group
from crm_deal_merge.stages import unfail
from crm_deal_merge.state import Status


class FakeSheets:
    def __init__(self, group: Group) -> None:
        self.rows = [GROUP_HEADERS, group.to_sheet_row()]
        self.updated: list[Group] = []

    def read(self, sheet: str, *args, **kwargs):
        assert sheet == TAB_GROUPS
        return self.rows

    def update(self, sheet: str, range_: str, rows: list[list[str]], **kwargs) -> None:
        assert sheet == TAB_GROUPS
        self.updated.append(Group.from_sheet_row(rows[0], GROUP_HEADERS))


def _group(status: Status = Status.FAILED) -> Group:
    return Group(
        company_id="23234",
        company_name="Aldita",
        inn="123",
        domain="aldita.ru",
        winner_id="11404",
        winner_stage="C50:NEW",
        winner_stage_name="Новая",
        winner_closed=False,
        loser_ids=["9818"],
        status=status,
        approved=True,
        error_message="HTTP 400 on crm.activity.update" if status == Status.FAILED else None,
    )


def test_unfail_moves_failed_to_approved() -> None:
    sheets = FakeSheets(_group())

    result = unfail.run(sheets, company_id="23234", domain="aldita.ru")

    assert result["changed"] == 1
    updated = sheets.updated[-1]
    assert updated.status == Status.APPROVED
    assert updated.approved is True
    assert updated.error_message is None


def test_unfail_does_not_touch_other_status() -> None:
    sheets = FakeSheets(_group(Status.PLAN_READY))

    result = unfail.run(sheets, company_id="23234", domain="aldita.ru")

    assert result["changed"] == 0
    assert result["status"] == Status.PLAN_READY.value
    assert sheets.updated == []
