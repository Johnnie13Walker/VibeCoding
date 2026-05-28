#!/usr/bin/env python3
"""Точечные правки в ТЗ Google Sheet (лист `ТЕХНИКА + МЕБЕЛЬ`):
- Баг 1: B-ячейка строки 8 — название Bosch SMV6YCX02E → SMV8YCX02E
- Баг 3: F-ячейка строки 11 — добавить альт-ссылку InSinkErator на офиц.дилера (in-stock, новая)
"""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
TZ_SHEET_ID = "19xa4EdEN6ih9AoHYzMGg9D4ALLgxetOu8qZsfsbu5w8"
SHEET_NAME = "ТЕХНИКА + МЕБЕЛЬ"

creds = Credentials.from_service_account_file(
    KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

# Сначала прочитаем строки 8 и 11 целиком, чтобы убедиться, что мы правим то, что нужно
print("=== ДО правки ===")
vals = svc.spreadsheets().values().get(
    spreadsheetId=TZ_SHEET_ID, range=f"{SHEET_NAME}!A8:F11",
    valueRenderOption="FORMATTED_VALUE"
).execute().get("values", [])
for i, row in enumerate(vals, 8):
    print(f"  Row {i}: {[c[:60] if isinstance(c,str) else c for c in row]}")
print()

# Применяем
def hl(url, text):
    return f'=HYPERLINK("{url}";"{text.replace(chr(34), chr(34)*2)}")'

ALT_URL = "https://insinkerator-shop.ru/catalog/bytovye-izmelchiteli-insinkerator/izmelchitel-pishchevykh-otkhodov-insinkerator-ise-s60.html"
ALT_TEXT = "InSinkErator ISE S60 — официальный дилер, 28 750 ₽, в наличии, новый (insinkerator-shop.ru)"

updates = [
    # Баг 1: переименовать SMV6 → SMV8 (Serie 8 — то, что в ссылках)
    ("B8", "Встраиваемая посудомоечная машина Bosch SMV8YCX02E"),
    # Баг 3: добавить альт-ссылку для InSinkErator (в смете 40K avito, в ТЗ уже 25K market — добавим third option)
    ("F11", hl(ALT_URL, ALT_TEXT)),
]

data = [{"range": f"{SHEET_NAME}!{c}", "values": [[v]]} for c,v in updates]
resp = svc.spreadsheets().values().batchUpdate(
    spreadsheetId=TZ_SHEET_ID,
    body={"valueInputOption": "USER_ENTERED", "data": data}
).execute()
print(f"Updated cells: {resp.get('totalUpdatedCells')}")

# Проверяем после
print("\n=== ПОСЛЕ правки ===")
vals = svc.spreadsheets().values().get(
    spreadsheetId=TZ_SHEET_ID, range=f"{SHEET_NAME}!A8:F11",
    valueRenderOption="FORMATTED_VALUE"
).execute().get("values", [])
for i, row in enumerate(vals, 8):
    print(f"  Row {i}: {[c[:60] if isinstance(c,str) else c for c in row]}")
