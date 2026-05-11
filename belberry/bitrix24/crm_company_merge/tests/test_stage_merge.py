from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from crm_company_merge.config import Config
from crm_company_merge.models import CONFLICT_HEADERS, GROUP_HEADERS, Group
from crm_company_merge.stages import merge
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


def make_group(
    inn: str,
    *,
    status: Status = Status.TRANSFERRED,
    winner_id: str = "100",
    loser_ids: list[str] | None = None,
) -> Group:
    return Group(
        inn=inn,
        size=2,
        risk_class="B",
        status=status,
        winner_id=winner_id,
        loser_ids=loser_ids or ["200"],
        approved=True,
        approved_by=None,
        approved_at=None,
        actions_planned=1,
        conflicts_count=0,
        last_action_at=None,
        error_message=None,
        backup_sheet="Backup merge 2026-05-11 15-26",
        ui_link=None,
    )


def queue_rows(*groups: Group) -> list[list[str]]:
    return [GROUP_HEADERS, *[group.to_sheet_row() for group in groups]]


def queue_rows_with_manual_columns(*groups: Group) -> list[list[str]]:
    return [
        [*GROUP_HEADERS, "Что делать", "Главная карточка", "Дубли"],
        *[[*group.to_sheet_row(), "ручная заметка", "winner link", "loser link"] for group in groups],
    ]


def conflict_row(
    inn: str,
    field: str,
    resolution: str,
    *,
    kind: str = "text",
    winner_value: str = "",
    loser_value: str = "",
) -> list[str]:
    return [inn, field, kind, winner_value, loser_value, resolution, "0"]


def conflicts_rows(*rows: list[str]) -> list[list[str]]:
    return [CONFLICT_HEADERS, *rows]


def install_clients(monkeypatch, bitrix: Mock, sheets: Mock) -> None:
    monkeypatch.setattr(merge, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(merge, "SheetsClient", Mock(return_value=sheets))


def sheet_reader(queue: list[list[str]], conflicts: list[list[str]] | None = None):
    conflicts = conflicts or [CONFLICT_HEADERS]

    def _read(sheet: str, *args, **kwargs):
        if sheet == merge.QUEUE_SHEET:
            return queue
        if sheet == merge.CONFLICTS_SHEET:
            return conflicts
        if sheet == merge.MERGE_LOG_SHEET:
            return []
        raise AssertionError(f"unexpected sheet: {sheet}")

    return _read


def setup_bitrix(bitrix: Mock) -> None:
    bitrix.get_company.side_effect = lambda company_id: {
        "ID": company_id,
        "TITLE": f"Company {company_id}",
        "PHONE": [{"VALUE": f"+7{company_id}", "VALUE_TYPE": "WORK"}],
    }
    bitrix.list_deals.return_value = []
    bitrix.list_requisites.return_value = []
    bitrix.list_bank_details.return_value = []
    bitrix.update_company.return_value = True
    bitrix.delete_bank_detail.return_value = True
    bitrix.delete_requisite.return_value = True
    bitrix.delete_company.return_value = True


def updated_group(sheets: Mock, index: int = 1) -> Group:
    queue_updates = [
        call for call in sheets.update.call_args_list if call.args[0] == merge.QUEUE_SHEET
    ]
    row_number = index + 1
    for call in reversed(queue_updates):
        range_ = call.args[1]
        rows = call.args[2]
        if range_.startswith(f"A{row_number}:"):
            return Group.from_sheet_row(rows[0], GROUP_HEADERS)
    raise AssertionError(f"queue row {row_number} was not updated")


def log_rows(sheets: Mock) -> list[list[str]]:
    rows: list[list[str]] = []
    for call in sheets.append.call_args_list:
        if call.args[0] == merge.MERGE_LOG_SHEET:
            rows.extend(call.args[1])
    return rows


def test_merge_processes_only_transferred(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    queue = queue_rows(
        make_group("111", status=Status.NEW),
        make_group("222"),
        make_group("333", status=Status.DONE),
    )
    sheets.read.side_effect = sheet_reader(queue)
    install_clients(monkeypatch, bitrix, sheets)

    merge.run(make_args(limit=5), config=make_config(tmp_path))

    bitrix.delete_company.assert_called_once_with("200")
    assert updated_group(sheets, index=2).status == Status.MERGED


def test_merge_accepts_manual_queue_columns(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows_with_manual_columns(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    merge.run(make_args(limit=1), config=make_config(tmp_path))

    bitrix.delete_company.assert_called_once_with("200")
    sheets.update.assert_any_call(merge.QUEUE_SHEET, "A2:O2", [updated_group(sheets).to_sheet_row()])


def test_merge_applies_winner_wins_no_update(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        conflicts_rows(conflict_row("111", "TITLE", "winner_wins", winner_value="winner", loser_value="loser")),
    )
    install_clients(monkeypatch, bitrix, sheets)

    merge.run(make_args(limit=1), config=make_config(tmp_path))

    bitrix.update_company.assert_not_called()
    bitrix.delete_company.assert_called_once_with("200")


def test_merge_applies_loser_wins_field_set(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        conflicts_rows(conflict_row("111", "TITLE", "loser_wins", winner_value="Short", loser_value="Long Title")),
    )
    install_clients(monkeypatch, bitrix, sheets)

    merge.run(make_args(limit=1), config=make_config(tmp_path))

    bitrix.update_company.assert_called_once_with("100", {"TITLE": "Long Title"})


def test_merge_applies_union_for_multifield(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    bitrix.get_company.side_effect = lambda company_id: {
        "ID": company_id,
        "PHONE": [{"VALUE": "A", "VALUE_TYPE": "WORK"}]
        if company_id == "100"
        else [{"VALUE": "B", "VALUE_TYPE": "WORK"}],
    }
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        conflicts_rows(conflict_row("111", "PHONE", "union", kind="multifield")),
    )
    install_clients(monkeypatch, bitrix, sheets)

    merge.run(make_args(limit=1), config=make_config(tmp_path))

    fields = bitrix.update_company.call_args.args[1]
    assert fields["PHONE"] == [
        {"VALUE": "A", "VALUE_TYPE": "WORK"},
        {"VALUE": "B", "VALUE_TYPE": "WORK"},
    ]


def test_merge_skips_manual_with_log(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        conflicts_rows(conflict_row("111", "TITLE", "manual", winner_value="A", loser_value="B")),
    )
    install_clients(monkeypatch, bitrix, sheets)

    merge.run(make_args(limit=1), config=make_config(tmp_path))

    bitrix.update_company.assert_not_called()
    assert any("manual_conflict_skipped" in row[6] for row in log_rows(sheets))


def test_merge_orphan_deals_blocks_delete(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    bitrix.list_deals.return_value = [{"ID": "d1"}]
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    merge.run(make_args(limit=1), config=make_config(tmp_path))

    bitrix.delete_company.assert_not_called()
    group = updated_group(sheets)
    assert group.status == Status.FAILED
    assert group.error_message == "orphan deals on 200"


def test_merge_deletes_loser_chain(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    bitrix.list_requisites.return_value = [{"ID": "r1"}]
    bitrix.list_bank_details.return_value = [{"ID": "b1"}]
    events: list[str] = []
    bitrix.delete_bank_detail.side_effect = lambda item_id: events.append(f"bank:{item_id}") or True
    bitrix.delete_requisite.side_effect = lambda item_id: events.append(f"req:{item_id}") or True
    bitrix.delete_company.side_effect = lambda item_id: events.append(f"company:{item_id}") or True
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    merge.run(make_args(limit=1), config=make_config(tmp_path))

    assert events == ["bank:b1", "req:r1", "company:200"]
    assert updated_group(sheets).status == Status.MERGED


def test_merge_skips_when_paused(tmp_path: Path, monkeypatch, capsys) -> None:
    config = make_config(tmp_path)
    config.pause_flag_path.write_text("paused", encoding="utf-8")
    bitrix = Mock()
    sheets = Mock()
    install_clients(monkeypatch, bitrix, sheets)

    merge.run(make_args(limit=1), config=config)

    assert "Paused since" in capsys.readouterr().out
    bitrix.get_company.assert_not_called()
    sheets.read.assert_not_called()


def test_merge_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    bitrix.list_requisites.return_value = [{"ID": "r1"}]
    bitrix.list_bank_details.return_value = [{"ID": "b1"}]
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        conflicts_rows(conflict_row("111", "TITLE", "loser_wins", loser_value="Long Title")),
    )
    install_clients(monkeypatch, bitrix, sheets)

    merge.run(make_args(limit=1, dry_run=True), config=make_config(tmp_path))

    assert "[dry-run] would merge 1 groups: 1 field updates, 3 deletes" in capsys.readouterr().out
    bitrix.update_company.assert_not_called()
    bitrix.delete_bank_detail.assert_not_called()
    bitrix.delete_requisite.assert_not_called()
    bitrix.delete_company.assert_not_called()
    sheets.append.assert_not_called()
    sheets.update.assert_not_called()


def test_merge_winner_disappeared(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    bitrix.get_company.side_effect = lambda company_id: None if company_id == "100" else {"ID": company_id}
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    merge.run(make_args(limit=1), config=make_config(tmp_path))

    group = updated_group(sheets)
    assert group.status == Status.FAILED
    assert group.error_message == "winner gone during merge"
    bitrix.delete_company.assert_not_called()
