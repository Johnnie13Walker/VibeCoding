from __future__ import annotations

import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from unittest.mock import Mock

from crm_company_merge.config import Config
from crm_company_merge.models import GROUP_HEADERS, Group
from crm_company_merge.notifications import send_telegram
from crm_company_merge.stages import discover
from crm_company_merge.state import Status


class FakeTelegramResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return b'{"ok": true}'


def make_config(tmp_path: Path) -> Config:
    return Config(
        bitrix_state_path=tmp_path / "install.latest.json",
        sheet_id="sheet123",
        google_service_account_json=tmp_path / "sa.json",
        telegram_bot_token="token",
        telegram_chat_id=81681699,
        pause_flag_path=tmp_path / "crm_company_merge.paused",
    )


def make_args(dry_run: bool = False) -> SimpleNamespace:
    return SimpleNamespace(dry_run=dry_run, sheet=None, verbose=False)


def make_queue_group(inn: str, status: Status = Status.NEW) -> Group:
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


def test_discover_skips_when_paused(tmp_path: Path, monkeypatch, capsys) -> None:
    config = make_config(tmp_path)
    config.pause_flag_path.write_text("paused", encoding="utf-8")
    bitrix_cls = Mock()
    sheets_cls = Mock()
    monkeypatch.setattr(discover, "BitrixClient", bitrix_cls)
    monkeypatch.setattr(discover, "SheetsClient", sheets_cls)

    discover.run(make_args(), config=config)

    assert "Paused since" in capsys.readouterr().out
    bitrix_cls.assert_not_called()
    sheets_cls.assert_not_called()


def test_discover_collects_new_inns(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    bitrix.paginate.return_value = iter(
        [
            {"RQ_INN": "111", "ENTITY_ID": "1"},
            {"RQ_INN": "111", "ENTITY_ID": "2"},
            {"RQ_INN": "222", "ENTITY_ID": "3"},
            {"RQ_INN": "333", "ENTITY_ID": "4"},
            {"RQ_INN": "", "ENTITY_ID": "5"},
        ]
    )
    sheets = Mock()
    sheets.read.side_effect = lambda sheet, *args, **kwargs: {
        discover.HISTORICAL_DUPLICATES_SHEET: [["444"]],
        discover.QUEUE_SHEET: [],
    }[sheet]
    monkeypatch.setattr(discover, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(discover, "SheetsClient", Mock(return_value=sheets))
    monkeypatch.setattr(discover, "send_telegram", Mock(return_value=True))

    discover.run(make_args(), config=make_config(tmp_path))

    sheets.append.assert_called_once()
    appended_rows = sheets.append.call_args.args[1]
    assert len(appended_rows) == 2
    assert {row[0] for row in appended_rows} == {"111", "444"}


def test_discover_idempotent(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    bitrix.paginate.return_value = iter(
        [
            {"RQ_INN": "111", "ENTITY_ID": "1"},
            {"RQ_INN": "111", "ENTITY_ID": "2"},
        ]
    )
    sheets = Mock()
    existing = make_queue_group("111").to_sheet_row()
    sheets.read.side_effect = lambda sheet, *args, **kwargs: {
        discover.HISTORICAL_DUPLICATES_SHEET: [["444"]],
        discover.QUEUE_SHEET: [GROUP_HEADERS, existing],
    }[sheet]
    monkeypatch.setattr(discover, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(discover, "SheetsClient", Mock(return_value=sheets))
    monkeypatch.setattr(discover, "send_telegram", Mock(return_value=True))

    discover.run(make_args(), config=make_config(tmp_path))

    sheets.append.assert_called_once()
    appended_rows = sheets.append.call_args.args[1]
    assert len(appended_rows) == 1
    assert appended_rows[0][0] == "444"


def test_discover_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    bitrix = Mock()
    bitrix.paginate.return_value = iter(
        [
            {"RQ_INN": "111", "ENTITY_ID": "1"},
            {"RQ_INN": "111", "ENTITY_ID": "2"},
        ]
    )
    sheets = Mock()
    sheets.read.side_effect = lambda sheet, *args, **kwargs: {
        discover.HISTORICAL_DUPLICATES_SHEET: [],
        discover.QUEUE_SHEET: [],
    }[sheet]
    monkeypatch.setattr(discover, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(discover, "SheetsClient", Mock(return_value=sheets))
    notify = Mock(return_value=True)
    monkeypatch.setattr(discover, "send_telegram", notify)

    discover.run(make_args(dry_run=True), config=make_config(tmp_path))

    sheets.append.assert_not_called()
    notify.assert_not_called()
    output = capsys.readouterr().out
    assert "[dry-run] would append 1 rows" in output
    assert "[dry-run] would notify" in output


def test_discover_no_new_groups(tmp_path: Path, monkeypatch, capsys) -> None:
    bitrix = Mock()
    bitrix.paginate.return_value = iter(
        [
            {"RQ_INN": "111", "ENTITY_ID": "1"},
            {"RQ_INN": "111", "ENTITY_ID": "2"},
        ]
    )
    sheets = Mock()
    sheets.read.side_effect = lambda sheet, *args, **kwargs: {
        discover.HISTORICAL_DUPLICATES_SHEET: [],
        discover.QUEUE_SHEET: [GROUP_HEADERS, make_queue_group("111").to_sheet_row()],
    }[sheet]
    monkeypatch.setattr(discover, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(discover, "SheetsClient", Mock(return_value=sheets))

    discover.run(make_args(), config=make_config(tmp_path))

    sheets.append.assert_not_called()
    assert "очередь актуальна" in capsys.readouterr().out


def test_send_telegram_success(monkeypatch) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeTelegramResponse()

    monkeypatch.setattr("crm_company_merge.notifications.urllib.request.urlopen", fake_urlopen)

    assert send_telegram("token", 123, "hello") is True

    request, timeout = calls[0]
    assert request.full_url == "https://api.telegram.org/bottoken/sendMessage"
    assert timeout == 20
    payload = urllib.parse.parse_qs(request.data.decode("utf-8"))
    assert payload == {"chat_id": ["123"], "text": ["hello"]}


def test_send_telegram_failure(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 500, "fail", hdrs=None, fp=None)

    monkeypatch.setattr("crm_company_merge.notifications.urllib.request.urlopen", fake_urlopen)

    assert send_telegram("token", 123, "hello") is False
