from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from crm_company_merge.config import Config
from crm_company_merge.models import (
    GROUP_HEADERS,
    INVENTORY_HEADERS,
    Group,
    InventoryRecord,
)
from crm_company_merge.stages import classify
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


def make_group(inn: str, status: Status = Status.INVENTORIED) -> Group:
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


def inventory_rows(*records: InventoryRecord) -> list[list[str]]:
    return [INVENTORY_HEADERS, *[record.to_sheet_row() for record in records]]


def record(inn: str, loser_id: str, entity_type: str, child_id: str = "1") -> InventoryRecord:
    return InventoryRecord(
        inn=inn,
        loser_id=loser_id,
        entity_type=entity_type,
        child_id=child_id,
        child_name="",
        owner="",
        details="",
        transferred=False,
        transferred_at=None,
    )


def install_clients(monkeypatch, bitrix: Mock, sheets: Mock) -> None:
    monkeypatch.setattr(classify, "BitrixClient", Mock(return_value=bitrix))
    monkeypatch.setattr(classify, "SheetsClient", Mock(return_value=sheets))


def sheet_reader(queue: list[list[str]], inventory: list[list[str]] | None = None):
    inventory = inventory or [INVENTORY_HEADERS]

    def _read(sheet: str, *args, **kwargs):
        if sheet == classify.QUEUE_SHEET:
            return queue
        if sheet == classify.INVENTORY_SHEET:
            return inventory
        if sheet == classify.CONFLICTS_SHEET:
            return []
        raise AssertionError(f"unexpected sheet: {sheet}")

    return _read


def base_companies(title_100: str = "Company 100", title_200: str = "Company 200") -> dict[str, dict]:
    return {
        "100": {"ID": "100", "TITLE": title_100, "DATE_MODIFY": "2026-05-01T10:00:00+03:00"},
        "200": {"ID": "200", "TITLE": title_200, "DATE_MODIFY": "2026-05-01T10:00:00+03:00"},
    }


def setup_bitrix(
    bitrix: Mock,
    companies: dict[str, dict] | None = None,
    company_ids: list[str] | None = None,
    deals: dict[str, list[dict]] | None = None,
) -> None:
    companies = companies or base_companies()
    company_ids = company_ids or list(companies)
    deals = deals or {}
    bitrix.find_companies_by_inn.return_value = company_ids
    bitrix.get_company.side_effect = lambda company_id: companies.get(company_id)
    bitrix.list_deals.side_effect = lambda company_id, closed=None: deals.get(company_id, [])


def updated_group(sheets: Mock) -> Group:
    queue_updates = [
        call for call in sheets.update.call_args_list if call.args[0] == classify.QUEUE_SHEET
    ]
    return Group.from_sheet_row(queue_updates[-1].args[2][0], GROUP_HEADERS)


def appended_conflicts(sheets: Mock) -> list[list[str]]:
    for call in sheets.append.call_args_list:
        if call.args[0] == classify.CONFLICTS_SHEET:
            return call.args[1]
    return []


def test_classify_processes_only_inventoried(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(
        queue_rows(make_group("111", Status.NEW), make_group("222"), make_group("333", Status.DONE))
    )
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=5), config=make_config(tmp_path))

    bitrix.find_companies_by_inn.assert_called_once_with("222")


def test_classify_respects_limit(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(*[make_group(str(index)) for index in range(5)]))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=2), config=make_config(tmp_path))

    assert bitrix.find_companies_by_inn.call_count == 2


def test_classify_class_A_empty_losers(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    companies = base_companies(title_100="Winner title with more data", title_200="")
    setup_bitrix(bitrix, companies=companies)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    group = updated_group(sheets)
    assert group.status == Status.PLAN_READY
    assert group.risk_class == "A"
    assert group.winner_id == "100"


def test_classify_class_B_small_activity(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    companies = base_companies(title_100="Winner title with more data", title_200="")
    setup_bitrix(bitrix, companies=companies)
    sheets = Mock()
    inv = inventory_rows(
        record("111", "200", "Deal", "d1"),
        record("111", "200", "Deal", "d2"),
        record("111", "200", "Contact", "c1"),
    )
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")), inv)
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    group = updated_group(sheets)
    assert group.status == Status.PLAN_READY
    assert group.risk_class == "B"


def test_classify_class_C_active(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    companies = base_companies(title_100="Winner title with more data", title_200="")
    setup_bitrix(bitrix, companies=companies)
    sheets = Mock()
    inv = inventory_rows(
        *[record("111", "200", "Deal", f"d{index}") for index in range(5)],
        record("111", "200", "SmartItem:177", "s1"),
    )
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")), inv)
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    group = updated_group(sheets)
    assert group.status == Status.MANUAL
    assert group.risk_class == "C"
    assert group.ui_link == "https://belberrycrm.bitrix24.ru/crm/company/details/100/"
    assert appended_conflicts(sheets) == []


def test_classify_winner_heuristic_max_filled(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    companies = {
        "100": {"ID": "100", "TITLE": "A", "DATE_MODIFY": "2026-05-01T10:00:00+03:00"},
        "200": {
            "ID": "200",
            "TITLE": "B",
            "COMMENTS": "filled",
            "INDUSTRY": "food",
            "EMPLOYEES": "10",
            "REVENUE": "100",
            "CURRENCY_ID": "RUB",
            "OPENED": "Y",
            "UF_CRM_1": "x",
            "UF_CRM_2": "y",
            "DATE_MODIFY": "2026-05-01T10:00:00+03:00",
        },
    }
    setup_bitrix(bitrix, companies=companies)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    assert updated_group(sheets).winner_id == "200"


def test_classify_winner_tiebreak_by_modify_date(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    companies = {
        "100": {"ID": "100", "TITLE": "A", "DATE_MODIFY": "2026-05-01T10:00:00+03:00"},
        "200": {"ID": "200", "TITLE": "B", "DATE_MODIFY": "2026-05-02T10:00:00+03:00"},
    }
    setup_bitrix(bitrix, companies=companies)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    assert updated_group(sheets).winner_id == "200"


def test_classify_conflict_text_length_winner_wins(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    companies = base_companies(title_100="Long Title", title_200="Short")
    companies["100"]["UF_CRM_TEST_WINNER_MARKER"] = "filled"
    setup_bitrix(bitrix, companies=companies)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    assert appended_conflicts(sheets)[0] == [
        "111",
        "TITLE",
        "text",
        "Long Title",
        "Short",
        "winner_wins",
        "0",
    ]


def test_classify_conflict_text_loser_wins(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    companies = base_companies(title_100="Short", title_200="Long Title")
    companies["100"]["UF_CRM_TEST_WINNER_MARKER"] = "filled"
    setup_bitrix(bitrix, companies=companies)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    assert appended_conflicts(sheets)[0][5] == "loser_wins"


def test_conflict_empty_loser_value_written_as_empty_string(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    companies = {
        "100": {"ID": "100", "TITLE": "X", "UF_CRM_TEST_WINNER_MARKER": "filled"},
        "200": {"ID": "200", "TITLE": None},
    }
    setup_bitrix(bitrix, companies=companies)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    conflict = appended_conflicts(sheets)[0]
    assert conflict[1] == "TITLE"
    assert conflict[3] == "X"
    assert conflict[4] == ""


def test_classify_conflict_text_equal_manual(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix, companies=base_companies(title_100="Alpha", title_200="Bravo"))
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    assert appended_conflicts(sheets)[0][5] == "manual"


def test_classify_multifield_union(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    companies = {
        "100": {
            "ID": "100",
            "TITLE": "Same",
            "PHONE": [{"ID": "1", "VALUE": "+70000000001", "VALUE_TYPE": "WORK"}],
        },
        "200": {
            "ID": "200",
            "TITLE": "Same",
            "PHONE": [{"ID": "2", "VALUE": "+70000000002", "VALUE_TYPE": "WORK"}],
        },
    }
    setup_bitrix(bitrix, companies=companies)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    conflict = appended_conflicts(sheets)[0]
    assert conflict[1] == "PHONE"
    assert conflict[2] == "multifield"
    assert conflict[5] == "union"


def test_classify_skip_equal_fields(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix, companies=base_companies(title_100="Same", title_200="Same"))
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    assert appended_conflicts(sheets) == []
    assert updated_group(sheets).conflicts_count == 0


def test_classify_skip_both_empty(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    companies = {
        "100": {"ID": "100", "TITLE": "Same", "INDUSTRY": ""},
        "200": {"ID": "200", "TITLE": "Same", "INDUSTRY": ""},
    }
    setup_bitrix(bitrix, companies=companies)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    assert appended_conflicts(sheets) == []


def test_classify_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1, dry_run=True), config=make_config(tmp_path))

    sheets.update.assert_not_called()
    sheets.append.assert_not_called()
    output = capsys.readouterr().out
    assert "[dry-run] would update 1 groups:" in output
    assert "[dry-run] would append" in output


def test_classify_company_disappeared_mid(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(
        bitrix,
        companies={"100": {"ID": "100", "TITLE": "Only live"}, "200": None},
        company_ids=["100", "200"],
    )
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111")))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    group = updated_group(sheets)
    assert group.status == Status.FAILED
    assert group.error_message == "Дубль исчез: 1 карточек"


def test_classify_handles_failed_inventory(tmp_path: Path, monkeypatch) -> None:
    bitrix = Mock()
    setup_bitrix(bitrix)
    sheets = Mock()
    sheets.read.side_effect = sheet_reader(queue_rows(make_group("111", Status.FAILED)))
    install_clients(monkeypatch, bitrix, sheets)

    classify.run(make_args(limit=1), config=make_config(tmp_path))

    bitrix.find_companies_by_inn.assert_not_called()
    sheets.update.assert_not_called()
