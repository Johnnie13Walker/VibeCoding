from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from crm_company_merge import sheets_client
from crm_company_merge.sheets_client import SheetsClient


class FakeRequest:
    def __init__(self, response: dict | None = None):
        self.response = response or {}

    def execute(self) -> dict:
        return self.response


class FakeValues:
    def __init__(self, calls: list[tuple[str, dict]], responses: dict[str, dict]):
        self.calls = calls
        self.responses = responses

    def get(self, **kwargs):
        self.calls.append(("values.get", kwargs))
        return FakeRequest(self.responses.get("values.get", {"values": []}))

    def append(self, **kwargs):
        self.calls.append(("values.append", kwargs))
        return FakeRequest(self.responses.get("values.append", {}))

    def update(self, **kwargs):
        self.calls.append(("values.update", kwargs))
        return FakeRequest(self.responses.get("values.update", {}))

    def clear(self, **kwargs):
        self.calls.append(("values.clear", kwargs))
        return FakeRequest(self.responses.get("values.clear", {}))


class FakeSpreadsheets:
    def __init__(self, calls: list[tuple[str, dict]], responses: dict[str, dict]):
        self.calls = calls
        self.responses = responses
        self.values_api = FakeValues(calls, responses)

    def values(self) -> FakeValues:
        return self.values_api

    def get(self, **kwargs):
        self.calls.append(("spreadsheets.get", kwargs))
        return FakeRequest(self.responses.get("spreadsheets.get", {"sheets": []}))

    def batchUpdate(self, **kwargs):
        self.calls.append(("spreadsheets.batchUpdate", kwargs))
        return FakeRequest(self.responses.get("spreadsheets.batchUpdate", {}))


class FakeService:
    def __init__(self, responses: dict[str, dict] | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.responses = responses or {}
        self.spreadsheets_api = FakeSpreadsheets(self.calls, self.responses)

    def spreadsheets(self) -> FakeSpreadsheets:
        return self.spreadsheets_api


@pytest.fixture
def fake_service(monkeypatch: pytest.MonkeyPatch) -> FakeService:
    service = FakeService()
    monkeypatch.setattr(
        sheets_client.Credentials,
        "from_service_account_file",
        Mock(return_value=Mock(name="credentials")),
    )
    monkeypatch.setattr(sheets_client, "build", Mock(return_value=service))
    return service


def make_client(path: Path) -> SheetsClient:
    return SheetsClient("sheet123", path)


def test_read_calls_correct_range(fake_service: FakeService, tmp_path: Path) -> None:
    fake_service.responses["values.get"] = {"values": [["a"]]}

    rows = make_client(tmp_path / "sa.json").read("Очередь merge", "A1:B2", unformatted=True)

    assert rows == [["a"]]
    assert fake_service.calls[0] == (
        "values.get",
        {
            "spreadsheetId": "sheet123",
            "range": "Очередь merge!A1:B2",
            "valueRenderOption": "UNFORMATTED_VALUE",
        },
    )


def test_append_uses_insert_rows(fake_service: FakeService, tmp_path: Path) -> None:
    make_client(tmp_path / "sa.json").append("Inventory", [["1"]], value_input_option="USER_ENTERED")

    assert fake_service.calls[0] == (
        "values.append",
        {
            "spreadsheetId": "sheet123",
            "range": "Inventory",
            "valueInputOption": "USER_ENTERED",
            "insertDataOption": "INSERT_ROWS",
            "body": {"values": [["1"]]},
        },
    )


def test_ensure_sheet_returns_existing_id_if_exists(
    fake_service: FakeService, tmp_path: Path
) -> None:
    fake_service.responses["spreadsheets.get"] = {
        "sheets": [{"properties": {"sheetId": 10, "title": "Inventory"}}]
    }

    sheet_id = make_client(tmp_path / "sa.json").ensure_sheet("Inventory")

    assert sheet_id == 10
    assert [call[0] for call in fake_service.calls] == ["spreadsheets.get"]


def test_ensure_sheet_creates_new_if_missing(fake_service: FakeService, tmp_path: Path) -> None:
    fake_service.responses["spreadsheets.get"] = {
        "sheets": [{"properties": {"sheetId": 10, "title": "Queue"}}]
    }
    fake_service.responses["spreadsheets.batchUpdate"] = {
        "replies": [{"addSheet": {"properties": {"sheetId": 20}}}]
    }

    sheet_id = make_client(tmp_path / "sa.json").ensure_sheet("Inventory")

    assert sheet_id == 20
    assert fake_service.calls[1] == (
        "spreadsheets.batchUpdate",
        {
            "spreadsheetId": "sheet123",
            "body": {"requests": [{"addSheet": {"properties": {"title": "Inventory"}}}]},
        },
    )


def test_clear_calls_values_clear(fake_service: FakeService, tmp_path: Path) -> None:
    make_client(tmp_path / "sa.json").clear("Inventory")

    assert fake_service.calls[0] == (
        "values.clear",
        {"spreadsheetId": "sheet123", "range": "Inventory", "body": {}},
    )


def test_delete_sheet_returns_false_if_missing(fake_service: FakeService, tmp_path: Path) -> None:
    fake_service.responses["spreadsheets.get"] = {
        "sheets": [{"properties": {"sheetId": 10, "title": "Queue"}}]
    }

    deleted = make_client(tmp_path / "sa.json").delete_sheet("Inventory")

    assert deleted is False
    assert [call[0] for call in fake_service.calls] == ["spreadsheets.get"]


def test_get_sheet_titles(fake_service: FakeService, tmp_path: Path) -> None:
    fake_service.responses["spreadsheets.get"] = {
        "sheets": [
            {"properties": {"sheetId": 10, "title": "Queue"}},
            {"properties": {"sheetId": 20, "title": "Inventory"}},
        ]
    }

    assert make_client(tmp_path / "sa.json").get_sheet_titles() == ["Queue", "Inventory"]
