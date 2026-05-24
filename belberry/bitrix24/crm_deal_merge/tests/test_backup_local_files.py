from __future__ import annotations

import json
from pathlib import Path

from crm_deal_merge.config import TAB_GROUPS, TAB_INVENTORY
from crm_deal_merge.models import GROUP_HEADERS, INVENTORY_HEADERS, Group
from crm_deal_merge.stages import rollback, transfer
from crm_deal_merge.state import Status


class FakeBitrix:
    def __init__(self) -> None:
        self.updated: list[tuple[str, dict]] = []

    def get_deal(self, deal_id):
        return {"ID": deal_id, "TITLE": "foo.ru", "STAGE_ID": "C38:NEW", "COMMENTS": "old"}

    def list_deal_contacts(self, deal_id):
        return []

    def update_deal(self, deal_id, fields):
        self.updated.append((deal_id, fields))
        return True

    def list_deal_timeline_comments(self, deal_id):
        return []


class FakeSheets:
    def __init__(self, group: Group) -> None:
        self.rows = {
            TAB_GROUPS: [GROUP_HEADERS, group.to_sheet_row()],
            TAB_INVENTORY: [INVENTORY_HEADERS],
        }
        self.updated_groups: list[Group] = []
        self.ensure_calls: list[str] = []
        self.append_calls: list[tuple] = []

    def read(self, sheet, *args, **kwargs):
        return self.rows.get(sheet, [])

    def update(self, sheet, range_, rows, **kwargs):
        if sheet == TAB_GROUPS:
            self.updated_groups.append(Group.from_sheet_row(rows[0], GROUP_HEADERS))

    def ensure_sheet(self, title):
        self.ensure_calls.append(title)

    def append(self, *args, **kwargs):
        self.append_calls.append(args)


def _group(**kwargs) -> Group:
    data = dict(
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
    data.update(kwargs)
    return Group(**data)


def test_transfer_writes_local_json_backup_not_sheet(tmp_path, monkeypatch):
    monkeypatch.setattr(transfer, "BACKUP_DIR", tmp_path)
    bx = FakeBitrix()
    sheets = FakeSheets(_group())

    result = transfer.run(bx, sheets, dry_run=False, limit=1)

    assert result["groups"] == 1
    assert all(not title.startswith("merge_backup_") for title in sheets.ensure_calls)
    assert sheets.append_calls == []
    updated = sheets.updated_groups[-1]
    assert updated.backup_sheet
    backup_file = Path(updated.backup_sheet)
    data = json.loads(backup_file.read_text(encoding="utf-8"))
    assert data["company_id"] == "10"
    assert data["domain"] == "foo.ru"
    assert data["losers"][0]["loser_id"] == "100"
    assert data["losers"][0]["raw"]["STAGE_ID"] == "C38:NEW"


def test_rollback_reads_local_json_backup(tmp_path):
    backup_file = tmp_path / "10_foo.ru.json"
    backup_file.write_text(
        json.dumps(
            {
                "ts_msk": "2026-05-12T10:00:00+03:00",
                "company_id": "10",
                "domain": "foo.ru",
                "losers": [{"loser_id": "100", "raw": {"ID": "100", "STAGE_ID": "C38:OLD", "COMMENTS": "before"}}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    group = _group(status=Status.DONE, backup_sheet=str(backup_file))
    sheets = FakeSheets(group)
    bx = FakeBitrix()

    result = rollback.run(bx, sheets, company_id="10", domain="foo.ru", confirm_rollback=True)

    assert result["restored_losers"] == 1
    assert bx.updated == [("100", {"STAGE_ID": "C38:OLD", "COMMENTS": "before"})]
