from __future__ import annotations

from crm_deal_merge.bitrix_client import BitrixError
from crm_deal_merge.config import TAB_GROUPS, TAB_INVENTORY
from crm_deal_merge.models import GROUP_HEADERS, INVENTORY_HEADERS, Group
from crm_deal_merge.stages import transfer
from crm_deal_merge.state import Status


class FakeBitrix:
    def get_deal(self, deal_id):
        return {"ID": deal_id, "TITLE": "foo.ru", "STAGE_ID": "C38:NEW", "COMMENTS": ""}

    def list_deal_contacts(self, deal_id):
        return []

    def reassign_activity(self, *args):
        raise BitrixError("HTTP 400 on crm.activity.update")


class FakeSheets:
    def __init__(self) -> None:
        group = Group(
            company_id="10",
            company_name="C",
            inn="123",
            domain="foo.ru",
            winner_id="200",
            winner_stage="C50:NEW",
            winner_stage_name="N",
            winner_closed=False,
            loser_ids=["100"],
            status=Status.APPROVED,
            approved=True,
        )
        self.rows = {
            TAB_GROUPS: [GROUP_HEADERS, group.to_sheet_row()],
            TAB_INVENTORY: [
                INVENTORY_HEADERS,
                ["10", "100", "activity", "501", "email", '{"PROVIDER_ID": "CRM_EMAIL"}', "0", "", ""],
            ],
        }
        self.group_updates: list[Group] = []
        self.inventory_updates: list[list[str]] = []

    def read(self, sheet, *args, **kwargs):
        return self.rows.get(sheet, [])

    def update(self, sheet, range_, rows, **kwargs):
        if sheet == TAB_GROUPS:
            self.group_updates.append(Group.from_sheet_row(rows[0], GROUP_HEADERS))
        if sheet == TAB_INVENTORY:
            self.inventory_updates.extend(rows)

    def append(self, *args, **kwargs):
        pass

    def ensure_sheet(self, *args, **kwargs):
        pass


def test_http_400_activity_update_becomes_dynamic_not_transferable() -> None:
    sheets = FakeSheets()

    result = transfer.run(FakeBitrix(), sheets, dry_run=False, limit=1)

    assert result["groups"] == 1
    assert "failed" not in result
    updated_row = dict(zip(INVENTORY_HEADERS, sheets.inventory_updates[-1]))
    assert updated_row["transferred"] == "0"
    assert updated_row["note"] == "not_transferable_dynamic"
    assert sheets.group_updates[-1].status == Status.TRANSFERRED
