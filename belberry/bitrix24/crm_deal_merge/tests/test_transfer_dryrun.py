from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS, TAB_INVENTORY
from crm_deal_merge.models import GROUP_HEADERS, INVENTORY_HEADERS, Group
from crm_deal_merge.stages import transfer
from crm_deal_merge.state import Status


class FakeBitrix:
    def __init__(self) -> None:
        self.write_calls: list[str] = []

    def update_deal(self, *args, **kwargs):
        self.write_calls.append("update_deal")

    def reassign_activity(self, *args, **kwargs):
        self.write_calls.append("reassign_activity")

    def add_deal_timeline_comment(self, *args, **kwargs):
        self.write_calls.append("add_deal_timeline_comment")

    def add_deal_contact(self, *args, **kwargs):
        self.write_calls.append("add_deal_contact")

    def relink_smart_item(self, *args, **kwargs):
        self.write_calls.append("relink_smart_item")


class FakeSheets:
    def __init__(self) -> None:
        group = Group(
            company_id="10",
            company_name="Company",
            inn="123",
            domain="foo.ru",
            winner_id="200",
            winner_stage="C50:NEW",
            winner_stage_name="Новая",
            winner_closed=False,
            loser_ids=["100"],
            n_total=2,
            n_winner=1,
            status=Status.APPROVED,
            approved=True,
        )
        self.rows = {
            TAB_GROUPS: [GROUP_HEADERS, group.to_sheet_row()],
            TAB_INVENTORY: [
                INVENTORY_HEADERS,
                ["10", "100", "activity", "501", "call", '{"PROVIDER_ID":"CRM_ACTIVITY_PROVIDER_TASKS_TASK"}', "0", "", ""],
                ["10", "100", "timeline", "601", "comment", '{"COMMENT":"hello"}', "0", "", ""],
                ["10", "100", "contact", "701", "", "{}", "0", "", ""],
            ],
        }
        self.write_calls: list[str] = []

    def read(self, sheet: str, *args, **kwargs):
        return self.rows.get(sheet, [])

    def update(self, *args, **kwargs):
        self.write_calls.append("update")

    def append(self, *args, **kwargs):
        self.write_calls.append("append")

    def ensure_sheet(self, *args, **kwargs):
        self.write_calls.append("ensure_sheet")


def test_transfer_dryrun_does_not_call_write_methods(capsys) -> None:
    bx = FakeBitrix()
    sheets = FakeSheets()

    result = transfer.run(bx, sheets, dry_run=True, limit=1)

    captured = capsys.readouterr()
    assert "dry-run" in captured.out
    assert result["activity"] == 1
    assert result["timeline"] == 1
    assert result["contact"] == 1
    assert bx.write_calls == []
    assert sheets.write_calls == []
