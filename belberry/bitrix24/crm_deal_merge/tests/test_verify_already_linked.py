from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS, TAB_INVENTORY, TIMELINE_TRANSFER_MARKER
from crm_deal_merge.models import GROUP_HEADERS, INVENTORY_HEADERS, Group
from crm_deal_merge.stages import verify
from crm_deal_merge.state import Status


class FakeBitrix:
    def list_deal_contacts(self, deal_id):
        return [{"CONTACT_ID": "new"}]

    def list_deal_timeline_comments(self, deal_id):
        return [{"COMMENT": f"{TIMELINE_TRANSFER_MARKER} #100"}]

    def get_deal(self, deal_id):
        return {"ID": deal_id, "STAGE_ID": "C38:3"}

    def list_deal_activities(self, deal_id):
        return []


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
            n_contacts_planned=3,
            status=Status.MERGED,
            approved=True,
        )
        self.rows = {
            TAB_GROUPS: [GROUP_HEADERS, group.to_sheet_row()],
            TAB_INVENTORY: [
                INVENTORY_HEADERS,
                ["10", "100", "contact", "old1", "", "{}", "1", "2026-05-12T10:00:00+03:00", "already_linked"],
                ["10", "100", "contact", "old2", "", "{}", "1", "2026-05-12T10:00:00+03:00", "already_linked"],
                ["10", "100", "contact", "new", "", "{}", "1", "2026-05-12T10:00:00+03:00", ""],
            ],
        }
        self.updated: list[Group] = []

    def read(self, sheet, *args, **kwargs):
        return self.rows.get(sheet, [])

    def update(self, sheet, range_, rows, **kwargs):
        if sheet == TAB_GROUPS:
            self.updated.append(Group.from_sheet_row(rows[0], GROUP_HEADERS))

    def ensure_sheet(self, title):
        pass


def test_verify_already_linked_contacts_not_false_positive():
    sheets = FakeSheets()

    result = verify.run(FakeBitrix(), sheets)

    assert result == {"done": 1, "failed": 0}
    assert sheets.updated[-1].status == Status.DONE
