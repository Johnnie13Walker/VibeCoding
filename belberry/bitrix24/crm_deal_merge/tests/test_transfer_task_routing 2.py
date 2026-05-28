"""Тесты что transfer корректно роутит TASKS и CRM_TASKS_TASK через reassign_task_activity."""
from __future__ import annotations

from crm_deal_merge.config import TAB_GROUPS, TAB_INVENTORY
from crm_deal_merge.models import GROUP_HEADERS, INVENTORY_HEADERS, Group
from crm_deal_merge.stages import transfer
from crm_deal_merge.stages.transfer import _is_not_transferable, _is_task_activity
from crm_deal_merge.state import Status


def test_is_task_activity_classic():
    assert _is_task_activity('{"PROVIDER_ID": "TASKS", "TYPE_ID": "6"}')


def test_is_task_activity_crm_tasks_task():
    assert _is_task_activity('{"PROVIDER_ID": "CRM_TASKS_TASK", "TYPE_ID": "6"}')


def test_is_task_activity_voximplant_negative():
    assert not _is_task_activity('{"PROVIDER_ID": "VOXIMPLANT_CALL", "TYPE_ID": "2"}')


def test_is_task_activity_email_negative():
    assert not _is_task_activity('{"PROVIDER_ID": "CRM_EMAIL", "TYPE_ID": "4"}')


def test_is_task_activity_malformed_json():
    assert not _is_task_activity("not a json")
    assert not _is_task_activity("")
    assert not _is_task_activity("null")


def test_is_not_transferable_known_locked_providers():
    assert _is_not_transferable('{"PROVIDER_ID": "VOXIMPLANT_CALL"}')
    assert _is_not_transferable('{"PROVIDER_ID": "CRM_SMS"}')
    assert _is_not_transferable('{"PROVIDER_ID": "IMOPENLINES_SESSION"}')
    assert _is_not_transferable('{"PROVIDER_ID": "CRM_TODO"}')
    assert not _is_not_transferable('{"PROVIDER_ID": "CRM_EMAIL"}')


class _BitrixRouting:
    def __init__(self):
        self.calls = []

    def list_deal_contacts(self, deal_id):
        return []

    def get_deal(self, deal_id):
        return {"ID": deal_id, "TITLE": "foo.ru", "STAGE_ID": "C50:NEW", "COMMENTS": ""}

    def reassign_activity(self, child_id, new_owner):
        self.calls.append(("reassign_activity", child_id, new_owner))
        return True

    def reassign_task_activity(self, child_id, loser, winner):
        self.calls.append(("reassign_task_activity", child_id, loser, winner))
        return True

    def add_deal_timeline_comment(self, *a, **k):
        return "1"

    def add_deal_contact(self, *a, **k):
        return True

    def relink_smart_item(self, *a, **k):
        return True

    def update_deal(self, *a, **k):
        return True


class _Sheets:
    def __init__(self, rows):
        self.rows = rows

    def read(self, sheet, *args, **kwargs):
        return self.rows.get(sheet, [])

    def update(self, *a, **k):
        if len(a) >= 3:
            sheet, range_, rows = a[:3]
            if sheet in self.rows and rows:
                import re

                match = re.search(r"(\d+)", str(range_))
                if match:
                    index = int(match.group(1)) - 1
                    if 0 <= index < len(self.rows[sheet]):
                        self.rows[sheet][index] = rows[0]

    def append(self, *a, **k):
        pass

    def ensure_sheet(self, *a, **k):
        pass


def _group(status=Status.APPROVED, approved=True):
    return Group(
        company_id="10",
        company_name="C",
        inn="123",
        domain="foo.ru",
        winner_id="200",
        winner_stage="C50:NEW",
        winner_stage_name="N",
        winner_closed=False,
        loser_ids=["100"],
        n_total=2,
        n_winner=1,
        status=status,
        approved=approved,
    )


def test_transfer_routes_crm_tasks_task_through_task_path():
    """CRM_TASKS_TASK должен идти через reassign_task_activity, не reassign_activity."""
    bx = _BitrixRouting()
    sheets = _Sheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: [
            INVENTORY_HEADERS,
            ["10", "100", "activity", "501", "task", '{"COMPLETED": "Y", "PROVIDER_ID": "CRM_TASKS_TASK", "TYPE_ID": "6"}', "0", "", ""],
        ],
    })
    transfer.run(bx, sheets, dry_run=False, limit=1)
    methods = [c[0] for c in bx.calls]
    assert "reassign_task_activity" in methods, f"Expected reassign_task_activity, got {bx.calls}"
    assert "reassign_activity" not in methods, f"Should NOT call reassign_activity for CRM_TASKS_TASK"


def test_transfer_routes_classic_tasks_through_task_path():
    """Старый PROVIDER_ID=TASKS тоже идёт через reassign_task_activity."""
    bx = _BitrixRouting()
    sheets = _Sheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: [
            INVENTORY_HEADERS,
            ["10", "100", "activity", "501", "task", '{"COMPLETED": "Y", "PROVIDER_ID": "TASKS", "TYPE_ID": "6"}', "0", "", ""],
        ],
    })
    transfer.run(bx, sheets, dry_run=False, limit=1)
    methods = [c[0] for c in bx.calls]
    assert "reassign_task_activity" in methods


def test_transfer_routes_non_task_activity_through_generic():
    """Не-task activity идёт через reassign_activity."""
    bx = _BitrixRouting()
    sheets = _Sheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: [
            INVENTORY_HEADERS,
            ["10", "100", "activity", "501", "email", '{"PROVIDER_ID": "CRM_EMAIL", "TYPE_ID": "4"}', "0", "", ""],
        ],
    })
    transfer.run(bx, sheets, dry_run=False, limit=1)
    methods = [c[0] for c in bx.calls]
    assert "reassign_activity" in methods
    assert "reassign_task_activity" not in methods


def test_transfer_skips_crm_sms_without_generic_reassign():
    bx = _BitrixRouting()
    sheets = _Sheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: [
            INVENTORY_HEADERS,
            ["10", "100", "activity", "501", "sms", '{"PROVIDER_ID": "CRM_SMS", "TYPE_ID": "6"}', "0", "", ""],
        ],
    })
    transfer.run(bx, sheets, dry_run=False, limit=1)
    methods = [c[0] for c in bx.calls]
    assert "reassign_activity" not in methods
    assert "reassign_task_activity" not in methods


def test_transfer_gracefully_marks_http_400_activity_dynamic():
    class Bitrix400(_BitrixRouting):
        def reassign_activity(self, child_id, new_owner):
            from crm_deal_merge.bitrix_client import BitrixError

            self.calls.append(("reassign_activity", child_id, new_owner))
            raise BitrixError("HTTP 400 on crm.activity.update")

    row = ["10", "100", "activity", "501", "email", '{"PROVIDER_ID": "CRM_EMAIL", "TYPE_ID": "4"}', "0", "", ""]
    bx = Bitrix400()
    sheets = _Sheets({
        TAB_GROUPS: [GROUP_HEADERS, _group().to_sheet_row()],
        TAB_INVENTORY: [INVENTORY_HEADERS, row],
    })
    result = transfer.run(bx, sheets, dry_run=False, limit=1)
    assert result.get("failed", 0) == 0
    updated = sheets.rows[TAB_INVENTORY][1]
    assert updated[6] == "0"
    assert updated[8] == "not_transferable_dynamic"
