"""Один раз: создать Google Sheet под сервис-аккаунтом и расшарить на админа.

Использование:
    python scripts/bootstrap_sheet.py --admin-email eshchemelev@gmail.com

Если Sheet с таким именем уже существует у сервис-аккаунта — повторно
не создаёт, возвращает существующий ID.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from sales_dashboard.config import SERVICE_ACCOUNT_JSON

SHEET_NAME = "Belberry Sales Dashboard — raw data"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--admin-email", required=True)
    p.add_argument("--name", default=SHEET_NAME)
    args = p.parse_args()

    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_JSON), scopes=SCOPES)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # Поищем существующий Sheet с этим именем
    q = (
        f"name = '{args.name}' "
        f"and mimeType = 'application/vnd.google-apps.spreadsheet' "
        f"and trashed = false"
    )
    existing = drive.files().list(q=q, fields="files(id,name,owners)").execute().get("files", [])

    if existing:
        sheet_id = existing[0]["id"]
        print(f"FOUND existing: {sheet_id}  ({existing[0]['name']})")
    else:
        # Создаём через Drive API (сервисники могут создавать файлы, но
        # не всегда могут через Sheets API). Drive API сразу даст файл
        # с правильным mimeType.
        file = drive.files().create(
            body={
                "name": args.name,
                "mimeType": "application/vnd.google-apps.spreadsheet",
            },
            fields="id",
        ).execute()
        sheet_id = file["id"]
        print(f"CREATED via Drive: {sheet_id}")

    # Шарим на админа как Editor
    perms = drive.permissions().list(fileId=sheet_id, fields="permissions(id,emailAddress,role)").execute()
    has_admin = any(
        (p.get("emailAddress") or "").lower() == args.admin_email.lower()
        for p in perms.get("permissions", [])
    )
    if has_admin:
        print(f"SHARED already: {args.admin_email}")
    else:
        drive.permissions().create(
            fileId=sheet_id,
            body={"type": "user", "role": "writer", "emailAddress": args.admin_email},
            sendNotificationEmail=False,
        ).execute()
        print(f"SHARED with: {args.admin_email}  (role=writer)")

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    print()
    print(f"SHEET_ID = \"{sheet_id}\"")
    print(f"URL: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
