"""Sheets-клиент с upsert по ключу и пересозданием вкладок."""
from __future__ import annotations

import time
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


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
        creds = Credentials.from_service_account_file(
            str(service_account_path), scopes=self.scopes
        )
        self.service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self.drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    # ---------------- low-level ----------------

    def _execute(self, request, max_retries: int = 5):
        for attempt in range(max_retries):
            try:
                return request.execute()
            except HttpError as e:
                status = getattr(e, "status_code", None) or (
                    e.resp.status if hasattr(e, "resp") else None
                )
                if status in (429, 500, 502, 503, 504):
                    time.sleep(min(2 ** attempt, 16))
                    continue
                raise
        raise RuntimeError("Sheets API: retries exhausted")

    # ---------------- meta ----------------

    def get_tabs(self) -> dict[str, int]:
        meta = self._execute(
            self.service.spreadsheets().get(spreadsheetId=self.sheet_id)
        )
        return {
            s["properties"]["title"]: s["properties"]["sheetId"]
            for s in meta.get("sheets", [])
        }

    def ensure_tab(self, tab: str) -> int:
        tabs = self.get_tabs()
        if tab in tabs:
            return tabs[tab]
        body = {"requests": [{"addSheet": {"properties": {"title": tab}}}]}
        resp = self._execute(
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id, body=body
            )
        )
        return resp["replies"][0]["addSheet"]["properties"]["sheetId"]

    # ---------------- write ----------------

    def replace_tab(
        self,
        tab: str,
        header: list[str],
        rows: list[list],
    ) -> None:
        """Полная перезапись вкладки: очистка + header + данные.

        Используем для справочников (users, stages) и для small fact-таблиц
        где проще перезалить целиком, чем делать upsert.
        """
        self.ensure_tab(tab)
        self._execute(
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.sheet_id,
                range=f"'{tab}'",
                body={},
            )
        )
        values = [header] + rows
        self._execute(
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=f"'{tab}'!A1",
                valueInputOption="RAW",
                body={"values": values},
            )
        )

    def upsert_tab(
        self,
        tab: str,
        header: list[str],
        rows: list[list],
        key_column: str,
    ) -> tuple[int, int]:
        """Upsert по ключевой колонке.

        Возвращает (вставлено, обновлено). Используем для deals/calls,
        где каждый запуск приходят и новые, и изменённые записи.
        """
        self.ensure_tab(tab)
        existing = self._execute(
            self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=f"'{tab}'!A1:ZZ",
                valueRenderOption="UNFORMATTED_VALUE",
            )
        ).get("values", [])

        if not existing:
            # пустая вкладка — просто перезаписываем
            self.replace_tab(tab, header, rows)
            return (len(rows), 0)

        cur_header = existing[0]
        if cur_header != header:
            # схема изменилась — безопаснее перезалить целиком
            self.replace_tab(tab, header, rows)
            return (len(rows), 0)

        key_idx = header.index(key_column)
        existing_data = existing[1:]
        index: dict[str, int] = {}
        for i, row in enumerate(existing_data):
            if key_idx < len(row):
                index[str(row[key_idx])] = i

        inserted = 0
        updated = 0
        new_rows: list[list] = list(existing_data)
        for row in rows:
            key = str(row[key_idx]) if key_idx < len(row) else ""
            if key in index:
                new_rows[index[key]] = row
                updated += 1
            else:
                new_rows.append(row)
                index[key] = len(new_rows) - 1
                inserted += 1

        # перезаливаем целиком: при <50K строк это быстрее, чем точечные update
        self.replace_tab(tab, header, new_rows)
        return (inserted, updated)

    def append_log(self, tab: str, header: list[str], rows: list[list]) -> None:
        """Просто дописать строки в конец (для sync_log)."""
        self.ensure_tab(tab)
        # если таб пустой — пишем header
        existing = self._execute(
            self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=f"'{tab}'!A1:A1",
            )
        ).get("values", [])
        if not existing:
            self._execute(
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range=f"'{tab}'!A1",
                    valueInputOption="RAW",
                    body={"values": [header]},
                )
            )
        self._execute(
            self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=f"'{tab}'!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": rows},
            )
        )

    # ---------------- drive permissions (для user-sync) ----------------

    def list_permissions(self, file_id: str) -> list[dict]:
        resp = self._execute(
            self.drive.permissions().list(
                fileId=file_id,
                fields="permissions(id,emailAddress,role,type)",
                supportsAllDrives=True,
            )
        )
        return resp.get("permissions", [])

    def add_permission(
        self,
        file_id: str,
        email: str,
        role: str = "reader",
        send_notification: bool = False,
    ) -> dict:
        return self._execute(
            self.drive.permissions().create(
                fileId=file_id,
                body={"type": "user", "role": role, "emailAddress": email},
                sendNotificationEmail=send_notification,
                supportsAllDrives=True,
            )
        )

    def remove_permission(self, file_id: str, permission_id: str) -> None:
        self._execute(
            self.drive.permissions().delete(
                fileId=file_id,
                permissionId=permission_id,
                supportsAllDrives=True,
            )
        )
