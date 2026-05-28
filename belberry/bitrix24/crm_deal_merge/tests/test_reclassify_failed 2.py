from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS
from crm_deal_merge.models import GROUP_HEADERS, Group
from crm_deal_merge.stages import reclassify_failed
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


def _failed(message: str) -> Group:
    return Group(
        company_id="10",
        company_name="Company",
        inn="123",
        domain="foo.ru",
        winner_id="200",
        winner_stage="C50:NEW",
        winner_stage_name="Новая",
        winner_closed=False,
        loser_ids=["100"],
        status=Status.FAILED,
        error_message=message,
    )


def test_reclassify_failed_groups_error_messages() -> None:
    sheets = FakeSheets([_failed("TITLE safety check failed"), _failed("Bitrix HTTP 429")])

    result = reclassify_failed.run(sheets)

    assert result["failed"] == 2
    assert result["buckets"]["TITLE safety"] == 1
    assert result["buckets"]["Rate limit"] == 1


def test_reclassify_failed_reset_by_pattern() -> None:
    sheets = FakeSheets([_failed("Bitrix HTTP 429")])

    result = reclassify_failed.run(sheets, reset=True, pattern="rate limit")

    assert result["reset"] == 1
    updated = Group.from_sheet_row(sheets.updated[0], GROUP_HEADERS)
    assert updated.status == Status.INVENTORIED
    assert updated.error_message is None
