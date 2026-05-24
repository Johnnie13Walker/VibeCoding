from __future__ import annotations

import json
from pathlib import Path

from crm_deal_merge.config import TAB_BACKUP_PREFIX, TAB_GROUPS
from crm_deal_merge.models import GROUP_HEADERS, Group
from crm_deal_merge.stages import archive_old_backups
from crm_deal_merge.state import Status


class FakeSheets:
    def __init__(self) -> None:
        self.backup_sheet = f"{TAB_BACKUP_PREFIX}10_foo.ru"
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
            status=Status.DONE,
            approved=True,
            backup_sheet=self.backup_sheet,
        )
        self.rows = {
            TAB_GROUPS: [GROUP_HEADERS, group.to_sheet_row()],
            self.backup_sheet: [
                ["ts_msk", "company_id", "domain", "loser_id", "raw_json"],
                ["2026-05-11T10:00:00+03:00", "10", "foo.ru", "100", json.dumps({"ID": "100", "STAGE_ID": "C38:OLD"})],
            ],
        }
        self.deleted: list[str] = []
        self.updated: list[Group] = []

    def read(self, sheet, *args, **kwargs):
        return self.rows.get(sheet, [])

    def update(self, sheet, range_, rows, **kwargs):
        if sheet == TAB_GROUPS:
            self.updated.append(Group.from_sheet_row(rows[0], GROUP_HEADERS))

    def delete_sheet(self, title):
        self.deleted.append(title)
        return True


def test_archive_old_backups_exports_json_and_deletes_sheet(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_old_backups, "BACKUP_DIR", tmp_path)
    sheets = FakeSheets()

    result = archive_old_backups.run(sheets, before="2026-05-12")

    assert result == {"archived": 1, "deleted": 1, "skipped": 0}
    assert sheets.deleted == [sheets.backup_sheet]
    updated = sheets.updated[-1]
    assert updated.backup_sheet
    backup_file = Path(updated.backup_sheet)
    data = json.loads(backup_file.read_text(encoding="utf-8"))
    assert data["losers"][0]["loser_id"] == "100"
    assert data["losers"][0]["raw"]["STAGE_ID"] == "C38:OLD"
