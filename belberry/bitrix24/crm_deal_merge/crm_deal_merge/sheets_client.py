from __future__ import annotations

import errno
import socket
import sys
import time
from http.client import RemoteDisconnected
from pathlib import Path
from socket import timeout as SocketTimeout
from typing import Any

import httplib2
from google_auth_httplib2 import AuthorizedHttp
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

DEFAULT_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
WRITE_THROTTLE_SECONDS = 1.1


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
        self._last_write_at = 0.0
        credentials = Credentials.from_service_account_file(
            str(service_account_path),
            scopes=self.scopes,
        )
        http = httplib2.Http(timeout=60)
        auth_http = AuthorizedHttp(credentials, http=http)
        self.service = build("sheets", "v4", http=auth_http)

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
        self._throttle_write()
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
        self._throttle_write()
        self._execute_with_retry(request)

    def batch_update(
        self,
        data: list[dict],
        value_input_option: str = "RAW",
    ) -> None:
        """Многоранжевый update одним HTTP-вызовом.

        data: list of {"range": "Sheet!A1:B5", "values": [[...], ...]} объектов.
        """
        if not data:
            return
        request = self.service.spreadsheets().values().batchUpdate(
            spreadsheetId=self.sheet_id,
            body={"valueInputOption": value_input_option, "data": data},
        )
        self._throttle_write()
        self._execute_with_retry(request)

    def clear(self, sheet: str) -> None:
        request = self.service.spreadsheets().values().clear(
            spreadsheetId=self.sheet_id,
            range=_sheet_ref(sheet),
            body={},
        )
        self._throttle_write()
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
        self._throttle_write()
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
        self._throttle_write()
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
        timeout_delays = (5, 15, 45)
        max_attempts = max(len(timeout_delays), len(_retry_delays(429))) + 1
        for attempt in range(max_attempts):
            try:
                result = request.execute()
                return result if isinstance(result, dict) else {}
            except HttpError as exc:
                status = getattr(exc.resp, "status", 0)
                if status not in {429, 500, 502, 503, 504}:
                    raise
                status_delays = _retry_delays(status)
                if attempt >= len(status_delays):
                    raise
                print(f"[sheets retry] HTTP {status}, retry in {status_delays[attempt]}s", file=sys.stderr)
                time.sleep(status_delays[attempt])
            except (SocketTimeout, TimeoutError, RemoteDisconnected, httplib2.HttpLib2Error, OSError) as exc:
                if isinstance(exc, OSError) and not _is_timeout_os_error(exc):
                    raise
                if attempt >= len(timeout_delays):
                    raise
                print(f"[sheets retry] timeout {exc}, retry in {timeout_delays[attempt]}s", file=sys.stderr)
                time.sleep(timeout_delays[attempt])
        return {}

    def _throttle_write(self) -> None:
        now = time.monotonic()
        wait = WRITE_THROTTLE_SECONDS - (now - self._last_write_at)
        if wait > 0:
            time.sleep(wait)
        self._last_write_at = time.monotonic()


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


def _is_timeout_os_error(exc: OSError) -> bool:
    if isinstance(exc, socket.gaierror):
        return True
    text = str(exc).lower()
    return (
        getattr(exc, "errno", None) in {errno.ETIMEDOUT, errno.ECONNRESET, errno.ECONNABORTED, 54, 60}
        or "timed out" in text
        or "remote end closed connection" in text
        or "nodename nor servname" in text
    )


def _retry_delays(status: int) -> tuple[int, ...]:
    if status == 429:
        return (65, 90, 120, 180)
    return (5, 15, 45)
