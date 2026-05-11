from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from crm_company_merge.config import Config
from crm_company_merge.models import GROUP_HEADERS, INVENTORY_HEADERS, Group, InventoryRecord
from crm_company_merge.stages import transfer
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
    status: Status = Status.PLAN_READY,
    approved: bool = True,
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
        approved=approved,
        approved_by=None,
        approved_at=None,
        actions_planned=1,
        conflicts_count=0,
        last_action_at=None,
        error_message=None,
        backup_sheet=None,
        ui_link=None,
    )


def queue_rows(*groups: Group) -> list[list[str]]:
    return [GROUP_HEADERS, *[group.to_sheet_row() for group in groups]]


def queue_rows_with_manual_columns(*groups: Group) -> list[list[str]]:
    return [
        [*GROUP_HEADERS, "Что делать", "Главная карточка", "Дубли"],
        *[[*group.to_sheet_row(), "ручная заметка", "winner link", "loser link"] for group in groups],
    ]


def inventory_rows(*records: InventoryRecord) -> list[list[str]]:
    return [INVENTORY_HEADERS, *[record.to_sheet_row() for record in records]]


def record(
    inn: str,
    loser_id: str,
    entity_type: str,
    child_id: str = "1",
    *,
    child_name: str = "",
    details: str = "",
) -> InventoryRecord:
    return InventoryRecord(
        inn=inn,
        loser_id=loser_id,
        entity_type=entity_type,
        child_id=child_id,
        child_name=child_name,
        owner="",
        details=details,
        transferred=False,
        transferred_at=None,
    )


def install_clients(monkeypatch, bitrix: Mock, sheets: Mock) -> None:
    monkeypatch.setattr(transfer, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(transfer, "SheetsClient", Mock(return_value=sheets))


def sheet_reader(queue: list[list[str]], inventory: list[list[str]] | None = None):
    inventory = inventory or [INVENTORY_HEADERS]

    def _read(sheet: str, *args, **kwargs):
        if sheet == transfer.QUEUE_SHEET:
            return queue
        if sheet == transfer.INVENTORY_SHEET:
            return inventory
        if sheet == transfer.MERGE_LOG_SHEET:
            return []
        raise AssertionError(f"unexpected sheet: {sheet}")

    return _read


def setup_bitrix(bitrix: Mock) -> None:
    bitrix.get_company.side_effect = lambda company_id: {"ID": company_id, "TITLE": f"Company {company_id}"}
    bitrix.get_deal.return_value = {"ID": "d1", "COMMENTS": "old"}
    bitrix.get_contact.return_value = {"ID": "c1"}
    bitrix.get_lead.return_value = {"ID": "l1"}
    bitrix.get_smart_item.return_value = {"id": "s1"}
    bitrix.update_deal.return_value = True
    bitrix.update_contact.return_value = True
    bitrix.update_activity.return_value = True
    bitrix.update_lead.return_value = True
    bitrix.update_smart_item.return_value = True
    bitrix.add_timeline_comment.return_value = "tc-new"


def updated_group(sheets: Mock, index: int = 1) -> Group:
    queue_updates = [
        call for call in sheets.update.call_args_list if call.args[0] == transfer.QUEUE_SHEET
    ]
    row_number = index + 1
    for call in reversed(queue_updates):
        range_ = call.args[1]
        rows = call.args[2]
        if range_.startswith(f"A{row_number}:"):
            return Group.from_sheet_row(rows[0], GROUP_HEADERS)
        if range_.startswith("A1:") and len(rows) > index:
            return Group.from_sheet_row(rows[index], GROUP_HEADERS)
    raise AssertionError(f"queue row {row_number} was not updated")


def log_rows(sheets: Mock) -> list[list[str]]:
    for call in sheets.append.call_args_list:
        if call.args[0] == transfer.MERGE_LOG_SHEET:
            return call.args[1]
    return []


def test_transfer_skips_unapproved(tmp_path: Path, monkeypatch, capsys) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111", approved=False)))
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=1), config=make_config(tmp_path))

    assert "Skip 111: not approved" in capsys.readouterr().out
    bitrix.get_company.assert_not_called()
    sheets.append.assert_not_called()
    sheets.update.assert_not_called()


def test_transfer_processes_only_approved_plan_ready(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    queue = queue_rows(
        make_group("111", status=Status.NEW),
        make_group("222", approved=False),
        make_group("333"),
    )
    inv = inventory_rows(record("333", "200", "Contact", "c1"))
    sheets.read.side_effect = sheet_reader(queue, inv)
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=5), config=make_config(tmp_path))

    bitrix.update_contact.assert_called_once_with("c1", {"COMPANY_ID": "100"})
    assert updated_group(sheets, index=3).status == Status.TRANSFERRED


def test_transfer_telegram_message_format(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    queue = queue_rows(make_group("111"))
    inv = inventory_rows(record("111", "200", "Contact", "c1"))
    sheets.read.side_effect = sheet_reader(queue, inv)
    notify = Mock(return_value=True)
    monkeypatch.setattr(transfer, "send_telegram", notify)
    install_clients(monkeypatch, bitrix, sheets)
    config = replace(make_config(tmp_path), telegram_bot_token="token", telegram_chat_id=81681699)

    transfer.run(make_args(limit=1), config=config)

    text = notify.call_args.args[2]
    assert "✅ Transfer завершён" in text
    assert "📈 Прогресс" in text
    assert "Очередь сейчас:" in text


def test_transfer_accepts_manual_queue_columns(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    queue = queue_rows_with_manual_columns(make_group("111"))
    inv = inventory_rows(record("111", "200", "Contact", "c1"))
    sheets.read.side_effect = sheet_reader(queue, inv)
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=1), config=make_config(tmp_path))

    bitrix.update_contact.assert_called_once_with("c1", {"COMPANY_ID": "100"})
    assert updated_group(sheets).status == Status.TRANSFERRED


def test_transfer_respects_limit(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    queue = queue_rows(make_group("111"), make_group("222"), make_group("333"))
    inv = inventory_rows(
        record("111", "200", "Contact", "c1"),
        record("222", "200", "Contact", "c2"),
        record("333", "200", "Contact", "c3"),
    )
    sheets.read.side_effect = sheet_reader(queue, inv)
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=2), config=make_config(tmp_path))

    assert bitrix.update_contact.call_count == 2
    assert updated_group(sheets, index=1).status == Status.TRANSFERRED
    assert updated_group(sheets, index=2).status == Status.TRANSFERRED
    queue_updates = [
        call for call in sheets.update.call_args_list if call.args[0] == transfer.QUEUE_SHEET
    ]
    assert not any(call.args[1].startswith("A4:") for call in queue_updates)


def test_transfer_persists_after_each_group(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    queue = queue_rows(make_group("111"), make_group("222"))
    inv = inventory_rows(record("111", "200", "Contact", "c1"), record("222", "200", "Contact", "c2"))
    sheets.read.side_effect = sheet_reader(queue, inv)
    events: list[str] = []
    sheets.append.side_effect = lambda *args, **kwargs: events.append(f"append:{args[0]}")
    sheets.update.side_effect = lambda *args, **kwargs: events.append(f"update:{args[0]}:{args[1]}")
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=2), config=make_config(tmp_path))

    queue_updates = [event for event in events if event.startswith(f"update:{transfer.QUEUE_SHEET}:")]
    assert queue_updates == [
        f"update:{transfer.QUEUE_SHEET}:A2:O2",
        f"update:{transfer.QUEUE_SHEET}:A3:O3",
    ]
    assert events.index(f"update:{transfer.QUEUE_SHEET}:A2:O2") < events.index(f"update:{transfer.QUEUE_SHEET}:A3:O3")


def test_transfer_moves_deal_with_comment(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        inventory_rows(record("111", "200", "Deal", "d1")),
    )
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=1), config=make_config(tmp_path))

    bitrix.update_deal.assert_called_once()
    fields = bitrix.update_deal.call_args.args[1]
    assert fields["COMPANY_ID"] == "100"
    assert "old" in fields["COMMENTS"]
    assert "company_id=200" in fields["COMMENTS"]
    assert updated_group(sheets).status == Status.TRANSFERRED


def test_transfer_moves_contact(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        inventory_rows(record("111", "200", "Contact", "c1")),
    )
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=1), config=make_config(tmp_path))

    bitrix.update_contact.assert_called_once_with("c1", {"COMPANY_ID": "100"})


def test_transfer_activity_failure_logged_not_blocking(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    bitrix.update_activity.return_value = False
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        inventory_rows(
            record("111", "200", "Activity", "a1", details="provider=VOXIMPLANT_CALL, type=2"),
            record("111", "200", "Contact", "c1"),
        ),
    )
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=1), config=make_config(tmp_path))

    assert updated_group(sheets).status == Status.TRANSFERRED
    assert any("activity_not_transferable" in row[6] for row in log_rows(sheets))


def test_transfer_handles_smart_item(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        inventory_rows(record("111", "200", "SmartItem:177", "s1")),
    )
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=1), config=make_config(tmp_path))

    bitrix.update_smart_item.assert_called_once_with(177, "s1", {"companyId": "100"})


def test_transfer_adds_timeline_comment_to_winner(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        inventory_rows(record("111", "200", "TimelineComment", "t1", child_name="comment text")),
    )
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=1), config=make_config(tmp_path))

    bitrix.add_timeline_comment.assert_called_once()
    assert bitrix.add_timeline_comment.call_args.args[0:2] == ("company", "100")
    assert "company_id=200" in bitrix.add_timeline_comment.call_args.args[2]
    assert "comment text" in bitrix.add_timeline_comment.call_args.args[2]


def test_transfer_creates_backup_sheet(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        inventory_rows(record("111", "200", "Contact", "c1")),
    )
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=1), config=make_config(tmp_path))

    backup_sheet = [
        call.args[0] for call in sheets.ensure_sheet.call_args_list if call.args[0].startswith("Backup merge ")
    ][0]
    assert backup_sheet.startswith("Backup merge ")
    backup_appends = [call for call in sheets.append.call_args_list if call.args[0] == backup_sheet]
    assert backup_appends
    assert backup_appends[0].args[1][0][2] == "Company"
    assert backup_appends[0].args[1][0][3] == "200"


def test_transfer_does_not_create_empty_backup_sheet(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    bitrix.get_company.side_effect = lambda company_id: {"ID": company_id} if company_id == "100" else None
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        inventory_rows(record("111", "200", "Contact", "c1")),
    )
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=1), config=make_config(tmp_path))

    assert not any(
        call.args[0].startswith("Backup merge ") for call in sheets.ensure_sheet.call_args_list
    )
    assert updated_group(sheets).status == Status.DONE


def test_transfer_skips_when_winner_disappeared(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    bitrix.get_company.side_effect = lambda company_id: None if company_id == "100" else {"ID": company_id}
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        inventory_rows(record("111", "200", "Contact", "c1")),
    )
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=1), config=make_config(tmp_path))

    group = updated_group(sheets)
    assert group.status == Status.FAILED
    assert group.error_message == "winner disappeared"
    bitrix.update_contact.assert_not_called()


def test_transfer_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111")),
        inventory_rows(
            record("111", "200", "Deal", "d1"),
            record("111", "200", "Contact", "c1"),
            record("111", "200", "Activity", "a1"),
            record("111", "200", "Lead", "l1"),
            record("111", "200", "SmartItem:177", "s1"),
            record("111", "200", "TimelineComment", "t1"),
        ),
    )
    install_clients(monkeypatch, bitrix, sheets)

    transfer.run(make_args(limit=1, dry_run=True), config=make_config(tmp_path))

    bitrix.update_deal.assert_not_called()
    bitrix.update_contact.assert_not_called()
    bitrix.update_activity.assert_not_called()
    bitrix.update_lead.assert_not_called()
    bitrix.update_smart_item.assert_not_called()
    bitrix.add_timeline_comment.assert_not_called()
    sheets.ensure_sheet.assert_not_called()
    sheets.update.assert_not_called()
    sheets.append.assert_not_called()
    output = capsys.readouterr().out
    assert "[dry-run] would transfer 6 actions across 1 groups" in output
    assert "deals=1" in output
    assert "smart_items=1" in output


def test_transfer_skips_when_paused(tmp_path: Path, monkeypatch, capsys) -> None:
    config = make_config(tmp_path)
    config.pause_flag_path.write_text("paused", encoding="utf-8")
    bitrix_cls = Mock()
    sheets_cls = Mock()
    monkeypatch.setattr(transfer, "BitrixClient", bitrix_cls)
    monkeypatch.setattr(transfer, "SheetsClient", sheets_cls)

    transfer.run(make_args(), config=config)

    assert "Paused since" in capsys.readouterr().out
    bitrix_cls.assert_not_called()
    sheets_cls.assert_not_called()
