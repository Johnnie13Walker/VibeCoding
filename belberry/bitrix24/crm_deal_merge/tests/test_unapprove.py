from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS
from crm_deal_merge.models import GROUP_HEADERS, Group
from crm_deal_merge.stages import unapprove
from crm_deal_merge.state import Status


class FakeSheets:
    def __init__(self, groups: list[Group]) -> None:
        self.rows = [GROUP_HEADERS, *[group.to_sheet_row() for group in groups]]
        self.updated: list[list[str]] = []

    def read(self, sheet: str, *args, **kwargs):
        assert sheet == TAB_GROUPS
        return self.rows

    def update(self, sheet: str, range_: str, rows: list[list[str]], **kwargs) -> None:
        assert sheet == TAB_GROUPS
        self.updated.extend(rows)


def _group(status: Status = Status.APPROVED) -> Group:
    return Group(
        company_id="44",
        company_name="АВТОДИСКЦЕНТР",
        inn="123",
        domain="wheelsboutique.moscow",
        winner_id="11032",
        winner_stage="C50:NEW",
        winner_stage_name="Новая",
        winner_closed=False,
        loser_ids=["382"],
        status=status,
        approved=status == Status.APPROVED,
        approved_by="deal-merge CLI" if status == Status.APPROVED else None,
    )


def test_unapprove_moves_approved_to_plan_ready() -> None:
    sheets = FakeSheets([_group()])

    result = unapprove.run(sheets, company_id="44", domain="wheelsboutique.moscow")

    assert result["changed"] == 1
    updated = Group.from_sheet_row(sheets.updated[0], GROUP_HEADERS)
    assert updated.status == Status.PLAN_READY
    assert updated.approved is False
    assert updated.approved_by is None
    assert updated.approved_at is None


def test_unapprove_does_not_touch_other_statuses() -> None:
    sheets = FakeSheets([_group(Status.PLAN_READY)])

    result = unapprove.run(sheets, company_id="44", domain="wheelsboutique.moscow")

    assert result["changed"] == 0
    assert sheets.updated == []
