from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS, TAB_INVENTORY
from crm_deal_merge.models import GROUP_HEADERS, INVENTORY_HEADERS, Group
from crm_deal_merge.stages import transfer
from crm_deal_merge.stages.transfer import _is_not_transferable
from crm_deal_merge.state import Status


class FakeBitrix:
    def __init__(self) -> None:
        self.reassign_activity_calls: list[tuple] = []
        self.batch_calls: list[dict] = []

    def get_deal(self, deal_id):
        return {"ID": deal_id, "TITLE": "foo.ru", "STAGE_ID": "C38:NEW", "COMMENTS": ""}

    def list_deal_contacts(self, deal_id):
        return []

    def reassign_activity(self, *args):
        self.reassign_activity_calls.append(args)
        return True

    def reassign_task_activity(self, *args):
        return True

    def batch(self, commands):
        self.batch_calls.append(commands)
        return {key: True for key in commands}


class FakeSheets:
    def __init__(self, details: str) -> None:
        self.group = Group(
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
            TAB_GROUPS: [GROUP_HEADERS, self.group.to_sheet_row()],
            TAB_INVENTORY: [
                INVENTORY_HEADERS,
                ["10", "100", "activity", "501", "sms", details, "0", "", ""],
            ],
        }
        self.inventory_updates: list[list[str]] = []

    def read(self, sheet, *args, **kwargs):
        return self.rows.get(sheet, [])

    def update(self, sheet, range_, rows, **kwargs):
        if sheet == TAB_INVENTORY:
            self.inventory_updates.extend(rows)

    def append(self, *args, **kwargs):
        pass

    def ensure_sheet(self, *args, **kwargs):
        pass

    def batch_update(self, data, **kwargs):
        for item in data:
            if item["range"].startswith(TAB_INVENTORY):
                self.inventory_updates.extend(item["values"])


def test_is_not_transferable_known_providers() -> None:
    assert _is_not_transferable('{"PROVIDER_ID": "CRM_SMS"}')
    assert _is_not_transferable('{"PROVIDER_ID": "IMOPENLINES_SESSION"}')
    assert _is_not_transferable('{"PROVIDER_ID": "VOXIMPLANT_CALL"}')
    assert not _is_not_transferable('{"PROVIDER_ID": "CRM_EMAIL"}')


def test_sequential_crm_sms_marked_not_transferable_without_reassign() -> None:
    bx = FakeBitrix()
    sheets = FakeSheets('{"PROVIDER_ID": "CRM_SMS"}')

    transfer.run(bx, sheets, dry_run=False, limit=1)

    assert bx.reassign_activity_calls == []
    updated = dict(zip(INVENTORY_HEADERS, sheets.inventory_updates[-1]))
    assert updated["transferred"] == "0"
    assert updated["note"] == "not_transferable"


def test_batch_crm_sms_not_in_activity_batch() -> None:
    bx = FakeBitrix()
    sheets = FakeSheets('{"PROVIDER_ID": "CRM_SMS"}')

    transfer.run(bx, sheets, dry_run=False, batch_mode=True, limit=1)

    assert bx.batch_calls == []
    updated = dict(zip(INVENTORY_HEADERS, sheets.inventory_updates[-1]))
    assert updated["note"] == "not_transferable"


def test_dry_run_skips_not_transferable_activity_counter() -> None:
    bx = FakeBitrix()
    sheets = FakeSheets('{"PROVIDER_ID": "CRM_SMS"}')

    result = transfer.run(bx, sheets, dry_run=True, limit=1)

    assert result == {"groups": 1}
