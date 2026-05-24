from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS, TAB_INVENTORY
from crm_deal_merge.models import GROUP_HEADERS, INVENTORY_HEADERS, Group
from crm_deal_merge.stages import transfer
from crm_deal_merge.state import Status


class FakeBitrix:
    def get_deal(self, deal_id):
        return {"ID": deal_id, "TITLE": None, "STAGE_ID": "C38:NEW"}


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
            status=Status.APPROVED,
            approved=True,
        )
        self.rows = {
            TAB_GROUPS: [GROUP_HEADERS, group.to_sheet_row()],
            TAB_INVENTORY: [INVENTORY_HEADERS],
        }
        self.updated: list[Group] = []

    def read(self, sheet, *args, **kwargs):
        return self.rows.get(sheet, [])

    def update(self, sheet, range_, rows, **kwargs):
        if sheet == TAB_GROUPS:
            self.updated.append(Group.from_sheet_row(rows[0], GROUP_HEADERS))

    def ensure_sheet(self, title):
        pass


def test_empty_title_moves_group_to_manual_not_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(transfer, "BACKUP_DIR", tmp_path)
    sheets = FakeSheets()

    result = transfer.run(FakeBitrix(), sheets, dry_run=False, limit=1)

    assert result["failed"] == 1
    updated = sheets.updated[-1]
    assert updated.status == Status.MANUAL
    assert "MANUAL review" in (updated.error_message or "")
