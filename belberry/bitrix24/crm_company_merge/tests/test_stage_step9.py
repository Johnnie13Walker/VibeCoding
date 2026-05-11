from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from crm_company_merge.config import Config
from crm_company_merge.models import GROUP_HEADERS, Group
from crm_company_merge.stages import export_manual, migrate_pilot, reclassify_failed
from crm_company_merge.state import Status


def make_config(tmp_path: Path) -> Config:
    return Config(
        bitrix_state_path=tmp_path / "install.latest.json",
        sheet_id="sheet123",
        google_service_account_json=tmp_path / "sa.json",
        telegram_bot_token=None,
        telegram_chat_id=None,
        pause_flag_path=tmp_path / "crm_company_merge.paused",
    )


def make_args(dry_run: bool = False) -> SimpleNamespace:
    return SimpleNamespace(dry_run=dry_run, limit=None, sheet=None, verbose=False)


def make_group(
    inn: str,
    *,
    status: Status = Status.FAILED,
    error_message: str | None = "Дубль исчез: 1 карточек",
    winner_id: str | None = None,
    loser_ids: list[str] | None = None,
    risk_class: str | None = "B",
) -> Group:
    return Group(
        inn=inn,
        size=2,
        risk_class=risk_class,
        status=status,
        winner_id=winner_id,
        loser_ids=loser_ids or [],
        approved=False,
        approved_by=None,
        approved_at=None,
        actions_planned=0,
        conflicts_count=0,
        last_action_at=None,
        error_message=error_message,
        backup_sheet=None,
        ui_link=None,
    )


def queue_rows(*groups: Group) -> list[list[str]]:
    return [GROUP_HEADERS, *[group.to_sheet_row() for group in groups]]


def updated_groups(sheets: Mock, sheet_name: str) -> list[Group]:
    groups: list[Group] = []
    for call in sheets.update.call_args_list:
        if call.args[0] == sheet_name and call.args[1].startswith("A"):
            groups.append(Group.from_sheet_row(call.args[2][0], GROUP_HEADERS))
    return groups


def test_migrate_pilot_marks_11_inns_as_done(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    bitrix.find_companies_by_inn.side_effect = lambda inn: [f"winner-{inn}"]
    sheets = Mock()
    groups = [make_group(inn) for inn in sorted(migrate_pilot.PILOT_INNS)]
    sheets.read.side_effect = lambda sheet, *args, **kwargs: (
        queue_rows(*groups)
        if sheet == migrate_pilot.QUEUE_SHEET
        else [["timestamp", "inn", "entity_type", "entity_id", "raw_json"]]
    )
    sheets.get_sheet_titles.return_value = []
    monkeypatch.setattr(migrate_pilot, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(migrate_pilot, "SheetsClient", Mock(return_value=sheets))

    migrate_pilot.run(make_args(), config=make_config(tmp_path))

    updates = updated_groups(sheets, migrate_pilot.QUEUE_SHEET)
    assert len(updates) == 11
    assert {group.status for group in updates} == {Status.DONE}
    assert all(group.approved for group in updates)
    assert all(group.error_message == "migrated from pre-workflow pilot" for group in updates)
    assert any(group.winner_id == "4822" for group in updates if group.inn == "1003001854")
    assert any(group.winner_id == "9040" for group in updates if group.inn == "1215157275")


def test_reclassify_failed_with_one_company(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    bitrix.find_companies_by_inn.return_value = ["100"]
    sheets = Mock()
    sheets.read.return_value = queue_rows(make_group("111"))
    monkeypatch.setattr(reclassify_failed, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(reclassify_failed, "SheetsClient", Mock(return_value=sheets))

    reclassify_failed.run(make_args(), config=make_config(tmp_path))

    group = updated_groups(sheets, reclassify_failed.QUEUE_SHEET)[0]
    assert group.status == Status.DONE
    assert group.winner_id == "100"
    assert group.error_message == "merged_externally_before_workflow"


def test_reclassify_failed_with_zero_companies(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    bitrix.find_companies_by_inn.return_value = []
    sheets = Mock()
    sheets.read.return_value = queue_rows(make_group("111"))
    monkeypatch.setattr(reclassify_failed, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(reclassify_failed, "SheetsClient", Mock(return_value=sheets))

    reclassify_failed.run(make_args(), config=make_config(tmp_path))

    group = updated_groups(sheets, reclassify_failed.QUEUE_SHEET)[0]
    assert group.status == Status.DONE
    assert group.winner_id is None
    assert group.error_message == "no_companies_found"


def test_reclassify_failed_with_two_companies_stays_failed(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    bitrix.find_companies_by_inn.return_value = ["100", "200"]
    sheets = Mock()
    sheets.read.return_value = queue_rows(make_group("111"))
    monkeypatch.setattr(reclassify_failed, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(reclassify_failed, "SheetsClient", Mock(return_value=sheets))

    reclassify_failed.run(make_args(), config=make_config(tmp_path))

    sheets.update.assert_not_called()


def test_export_manual_creates_sheet_with_links(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    bitrix.get_company.side_effect = lambda company_id: {
        "ID": company_id,
        "TITLE": f"Компания {company_id}",
    }
    sheets = Mock()
    group = make_group(
        "111",
        status=Status.MANUAL,
        error_message=None,
        winner_id="100",
        loser_ids=["200"],
        risk_class="C",
    )
    sheets.read.return_value = queue_rows(group)
    monkeypatch.setattr(export_manual, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(export_manual, "SheetsClient", Mock(return_value=sheets))

    export_manual.run(make_args(), config=make_config(tmp_path))

    sheets.ensure_sheet.assert_called_once_with(export_manual.MANUAL_EXPORT_SHEET)
    sheets.clear.assert_called_once_with(export_manual.MANUAL_EXPORT_SHEET)
    rows_call = sheets.update.call_args_list[1]
    assert rows_call.args[0] == export_manual.MANUAL_EXPORT_SHEET
    row = rows_call.args[2][0]
    assert row[0] == "111"
    assert "HYPERLINK" in row[1]
    assert "/crm/company/details/100/" in row[1]
    assert "/crm/company/details/200/" in row[2]
    assert "/crm/deduplicate/" in row[3]
