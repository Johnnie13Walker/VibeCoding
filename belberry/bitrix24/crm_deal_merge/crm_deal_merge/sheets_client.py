from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

DEFAULT_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsClient:
    def __init__(
        self,
        sheet_id: str,
        service_account_path: Path,
        scopes: list[str] | None = None,
    ):
        self.sheet_id = sheet_id
        self.service_account_path = service_account_path
        self.scopes = scopes or DEFAULT_SCOPES
        credentials = Credentials.from_service_account_file(
            str(service_account_path),
            scopes=self.scopes,
        )
        self.service = build("sheets", "v4", credentials=credentials)

    def read(
        self,
        sheet: str,
        range_: str = "A1:Z10000",
        unformatted: bool = False,
    ) -> list[list]:
        request = self.service.spreadsheets().values().get(
            spreadsheetId=self.sheet_id,
            range=_range(sheet, range_),
            valueRenderOption="UNFORMATTED_VALUE" if unformatted else "FORMATTED_VALUE",
        )
        body = self._execute_with_retry(request)
        return body.get("values", [])

    def append(
        self,
        sheet: str,
        rows: list[list],
        value_input_option: str = "RAW",
    ) -> None:
        request = self.service.spreadsheets().values().append(
            spreadsheetId=self.sheet_id,
            range=_sheet_ref(sheet),
            valueInputOption=value_input_option,
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        )
        self._execute_with_retry(request)

    def update(
        self,
        sheet: str,
        range_: str,
        rows: list[list],
        value_input_option: str = "RAW",
    ) -> None:
        request = self.service.spreadsheets().values().update(
            spreadsheetId=self.sheet_id,
            range=_range(sheet, range_),
            valueInputOption=value_input_option,
            body={"values": rows},
        )
        self._execute_with_retry(request)

    def clear(self, sheet: str) -> None:
        request = self.service.spreadsheets().values().clear(
            spreadsheetId=self.sheet_id,
            range=_sheet_ref(sheet),
            body={},
        )
        self._execute_with_retry(request)

    def ensure_sheet(self, title: str) -> int:
        sheets = self._get_sheets()
        existing_id = _find_sheet_id(sheets, title)
        if existing_id is not None:
            return existing_id

        request = self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        )
        body = self._execute_with_retry(request)
        return int(body["replies"][0]["addSheet"]["properties"]["sheetId"])

    def delete_sheet(self, title: str) -> bool:
        sheets = self._get_sheets()
        sheet_id = _find_sheet_id(sheets, title)
        if sheet_id is None:
            return False

        request = self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.sheet_id,
            body={"requests": [{"deleteSheet": {"sheetId": sheet_id}}]},
        )
        self._execute_with_retry(request)
        return True

    def get_sheet_titles(self) -> list[str]:
        return [
            sheet["properties"]["title"]
            for sheet in self._get_sheets()
            if "properties" in sheet and "title" in sheet["properties"]
        ]

    def _get_sheets(self) -> list[dict[str, Any]]:
        request = self.service.spreadsheets().get(
            spreadsheetId=self.sheet_id,
            fields="sheets(properties(sheetId,title))",
        )
        body = self._execute_with_retry(request)
        return body.get("sheets", [])

    def _execute_with_retry(self, request) -> dict[str, Any]:
        delays: tuple[int, ...] = ()
        for attempt in range(5):
            try:
                result = request.execute()
                return result if isinstance(result, dict) else {}
            except HttpError as exc:
                status = getattr(exc.resp, "status", 0)
                if status not in {429, 500, 502, 503, 504}:
                    raise
                delays = _retry_delays(status)
                if attempt >= len(delays):
                    raise
                time.sleep(delays[attempt])
        return {}


def _range(sheet: str, range_: str) -> str:
    if "!" in range_:
        return range_
    return f"{_sheet_ref(sheet)}!{range_}"


def _sheet_ref(sheet: str) -> str:
    """Возвращает имя листа в A1-нотации с кавычками, если нужно."""
    needs_quote = any(ch in sheet for ch in " '-/\\!()") or (sheet and not sheet[0].isalpha())
    if needs_quote:
        safe = sheet.replace("'", "''")
        return f"'{safe}'"
    return sheet


def _find_sheet_id(sheets: list[dict[str, Any]], title: str) -> int | None:
    for sheet in sheets:
        properties = sheet.get("properties", {})
        if properties.get("title") == title:
            return int(properties["sheetId"])
    return None


def _retry_delays(status: int) -> tuple[int, ...]:
    if status == 429:
        return (5, 10, 20, 40)
    return (1, 2, 4)
