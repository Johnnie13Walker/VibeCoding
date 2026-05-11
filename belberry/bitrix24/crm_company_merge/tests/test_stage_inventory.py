from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from crm_company_merge.config import Config
from crm_company_merge.models import GROUP_HEADERS, Group
from crm_company_merge.stages import inventory
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


def make_args(limit: int = 3, dry_run: bool = False) -> SimpleNamespace:
    return SimpleNamespace(limit=limit, dry_run=dry_run, sheet=None, verbose=False)


def make_group(inn: str, status: Status = Status.NEW) -> Group:
    return Group(
        inn=inn,
        size=2,
        risk_class=None,
        status=status,
        winner_id=None,
        loser_ids=[],
        approved=False,
        approved_by=None,
        approved_at=None,
        actions_planned=0,
        conflicts_count=0,
        last_action_at=None,
        error_message=None,
        backup_sheet=None,
        ui_link=None,
    )


def queue_rows(*groups: Group) -> list[list[str]]:
    return [GROUP_HEADERS, *[group.to_sheet_row() for group in groups]]


def install_clients(monkeypatch, bitrix: Mock, sheets: Mock) -> None:
    monkeypatch.setattr(inventory, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(inventory, "SheetsClient", Mock(return_value=sheets))


def empty_bitrix(bitrix: Mock, company_ids: list[str] | None = None) -> None:
    bitrix.find_companies_by_inn.return_value = company_ids or ["100", "200"]
    bitrix.get_company.return_value = {"ID": "100", "TITLE": "Company"}
    bitrix.list_deals.return_value = []
    bitrix.list_contacts.return_value = []
    bitrix.list_activities.return_value = []
    bitrix.list_leads.return_value = []
    bitrix.list_smart_items_for_company.return_value = []
    bitrix.list_requisites.return_value = []
    bitrix.list_timeline_comments.return_value = []


def test_inventory_processes_only_new(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    empty_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = [queue_rows(make_group("111"), make_group("222", Status.INVENTORIED), make_group("333", Status.DONE)), []]
    install_clients(monkeypatch, bitrix, sheets)

    inventory.run(make_args(limit=5), config=make_config(tmp_path))

    bitrix.find_companies_by_inn.assert_called_once_with("111")
    sheets.update.assert_any_call("Очередь merge", "A2:O2", sheets.update.call_args_list[-1].args[2])


def test_inventory_respects_limit(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    empty_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = [queue_rows(*[make_group(str(i)) for i in range(5)]), []]
    install_clients(monkeypatch, bitrix, sheets)

    inventory.run(make_args(limit=2), config=make_config(tmp_path))

    assert bitrix.find_companies_by_inn.call_count == 2
    assert sheets.update.call_count == 3  # Inventory header + 2 queue rows


def test_inventory_writes_progress_after_each_group(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    empty_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = [queue_rows(make_group("111"), make_group("222")), []]
    events: list[str] = []
    sheets.append.side_effect = lambda *args, **kwargs: events.append(f"append:{args[0]}")
    sheets.update.side_effect = lambda *args, **kwargs: events.append(f"update:{args[0]}:{args[1]}")
    install_clients(monkeypatch, bitrix, sheets)

    inventory.run(make_args(limit=2), config=make_config(tmp_path))

    assert events == [
        "update:Inventory:A1",
        "update:Очередь merge:A2:O2",
        "update:Очередь merge:A3:O3",
    ]


def test_inventory_collects_all_relationships(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    bitrix.find_companies_by_inn.return_value = ["100", "200"]
    bitrix.get_company.return_value = {"ID": "100", "TITLE": "Company"}
    bitrix.list_deals.side_effect = [
        [{"ID": "d1", "TITLE": "Deal 1"}, {"ID": "d2", "TITLE": "Deal 2"}],
        [],
    ]
    bitrix.list_contacts.side_effect = [
        [{"ID": "c1", "LAST_NAME": "Иванов", "NAME": "Иван"}],
        [{"ID": "c2", "LAST_NAME": "Петров", "NAME": "Пётр"}],
    ]
    bitrix.list_activities.side_effect = [[], [{"ID": "a1", "SUBJECT": "Call"}]]
    bitrix.list_leads.side_effect = [[{"ID": "l1", "TITLE": "Lead"}], []]
    bitrix.list_smart_items_for_company.side_effect = [[(177, [{"id": "s1", "title": "Smart"}])], []]
    bitrix.list_requisites.side_effect = [[{"ID": "r1", "RQ_INN": "111", "RQ_KPP": "222"}], []]
    bitrix.list_bank_details.return_value = []
    bitrix.list_timeline_comments.return_value = []
    sheets = Mock()
    sheets.read.side_effect = [queue_rows(make_group("111")), []]
    install_clients(monkeypatch, bitrix, sheets)

    inventory.run(make_args(limit=1), config=make_config(tmp_path))

    inventory_append = [
        call for call in sheets.append.call_args_list if call.args[0] == "Inventory"
    ][0]
    assert len(inventory_append.args[1]) == 8
    queue_update = [
        call for call in sheets.update.call_args_list if call.args[0] == "Очередь merge"
    ][0]
    updated_group = Group.from_sheet_row(queue_update.args[2][0], GROUP_HEADERS)
    assert updated_group.actions_planned == 7
    assert updated_group.status == Status.INVENTORIED


def test_inventory_marks_failed_when_no_duplicates(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    bitrix.find_companies_by_inn.return_value = ["100"]
    sheets = Mock()
    sheets.read.return_value = queue_rows(make_group("111"))
    install_clients(monkeypatch, bitrix, sheets)

    inventory.run(make_args(limit=1), config=make_config(tmp_path))

    bitrix.get_company.assert_not_called()
    queue_update = sheets.update.call_args
    updated_group = Group.from_sheet_row(queue_update.args[2][0], GROUP_HEADERS)
    assert updated_group.status == Status.FAILED
    assert updated_group.error_message == "Дубль исчез: 1 карточек"


def test_inventory_handles_deleted_company(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    empty_bitrix(bitrix)
    bitrix.get_company.side_effect = [{"ID": "100"}, None]
    sheets = Mock()
    sheets.read.side_effect = [queue_rows(make_group("111")), []]
    install_clients(monkeypatch, bitrix, sheets)

    inventory.run(make_args(limit=1), config=make_config(tmp_path))

    inventory_append = [
        call for call in sheets.append.call_args_list if call.args[0] == "Inventory"
    ][0]
    rows = inventory_append.args[1]
    assert any(row[2] == "Company" and row[4] == "(удалена)" for row in rows)


def test_inventory_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    bitrix = Mock()
    empty_bitrix(bitrix)
    sheets = Mock()
    sheets.read.return_value = queue_rows(make_group("111"))
    install_clients(monkeypatch, bitrix, sheets)

    inventory.run(make_args(limit=1, dry_run=True), config=make_config(tmp_path))

    bitrix.list_deals.assert_called()
    sheets.append.assert_not_called()
    sheets.update.assert_not_called()
    assert "[dry-run] would inventory 1 groups" in capsys.readouterr().out


def test_inventory_skips_when_paused(tmp_path: Path, monkeypatch, capsys) -> None:
    config = make_config(tmp_path)
    config.pause_flag_path.write_text("paused", encoding="utf-8")
    bitrix_cls = Mock()
    sheets_cls = Mock()
    monkeypatch.setattr(inventory, "BitrixClient", bitrix_cls)
    monkeypatch.setattr(inventory, "SheetsClient", sheets_cls)

    inventory.run(make_args(), config=config)

    assert "Paused since" in capsys.readouterr().out
    bitrix_cls.assert_not_called()
    sheets_cls.assert_not_called()
