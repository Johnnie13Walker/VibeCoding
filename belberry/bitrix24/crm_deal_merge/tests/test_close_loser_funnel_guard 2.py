from __future__ import annotations

from crm_deal_merge.config import LOSE_STAGE_38, LOSE_STAGE_50, TAB_GROUPS
from crm_deal_merge.models import GROUP_HEADERS, Group
from crm_deal_merge.stages import close_loser
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
        updated = Group.from_sheet_row(rows[0], GROUP_HEADERS)
        self.updated.append(updated)
        self.rows[1] = rows[0]


class FakeBitrix:
    def __init__(self, stage_id: str) -> None:
        self.stage_id = stage_id
        self.updated_deals: list[tuple[str, dict]] = []
        self.timeline_comments: list[tuple[str, str]] = []

    def get_deal(self, deal_id: str) -> dict:
        return {
            "ID": deal_id,
            "TITLE": "foo.ru — дубль",
            "STAGE_ID": self.stage_id,
            "COMMENTS": "old",
        }

    def update_deal(self, deal_id: str, fields: dict) -> bool:
        self.updated_deals.append((deal_id, fields))
        return True

    def add_deal_timeline_comment(self, deal_id: str, text: str) -> str:
        self.timeline_comments.append((deal_id, text))
        return "1"


def _group() -> Group:
    return Group(
        company_id="10",
        company_name="Foo",
        inn="123",
        domain="foo.ru",
        winner_id="200",
        winner_stage="C50:NEW",
        winner_stage_name="Новая",
        winner_closed=False,
        loser_ids=["100"],
        status=Status.TRANSFERRED,
    )


def test_close_loser_fails_when_loser_moved_to_other_funnel() -> None:
    bx = FakeBitrix("C10:NEW")
    sheets = FakeSheets(_group())

    result = close_loser.run(bx, sheets)

    assert result["failed"] == 1
    assert bx.updated_deals == []
    assert sheets.updated[-1].status == Status.FAILED
    assert "close-loser работает только с [38]/[50]" in (sheets.updated[-1].error_message or "")


def test_close_loser_uses_stage_38_for_reanimation_loser() -> None:
    bx = FakeBitrix("C38:UC_B4XV5E")
    sheets = FakeSheets(_group())

    result = close_loser.run(bx, sheets)

    assert result["groups"] == 1
    assert bx.updated_deals[0][1]["STAGE_ID"] == LOSE_STAGE_38
    assert sheets.updated[-1].status == Status.MERGED


def test_close_loser_uses_stage_50_for_telemarketing_loser() -> None:
    bx = FakeBitrix("C50:NEW")
    sheets = FakeSheets(_group())

    result = close_loser.run(bx, sheets)

    assert result["groups"] == 1
    assert bx.updated_deals[0][1]["STAGE_ID"] == LOSE_STAGE_50
    assert sheets.updated[-1].status == Status.MERGED
