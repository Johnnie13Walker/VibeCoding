#!/usr/bin/env python3
"""Фикс итоговых формул в `Замены_техника`:
- E20 (альт-сценарий) = сумма всех позиций: где есть альт-цена > 0 — берём её, иначе — текущую цену
- H20 (премиум-сценарий) = аналогично
- C20 (текущий) — без изменений
"""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1cXhvMVjCTb3JREUeKZhy1cxF544fpegW0s-JINLlQTs"
SHEET_NAME = "Замены_техника"

creds = Credentials.from_service_account_file(
    KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

updates = [
    # E20: сумма по альт-сценарию (если альт>0 — альт, иначе — текущее)
    ("E20", '=SUMIFS(E2:E19;E2:E19;">0")+SUMIFS(C2:C19;E2:E19;"=0")'),
    # H20: сумма по премиум-сценарию
    ("H20", '=SUMIFS(H2:H19;H2:H19;">0")+SUMIFS(C2:C19;H2:H19;"=0")'),
]

data = [{"range": f"{SHEET_NAME}!{c}", "values": [[v]]} for c,v in updates]
svc.spreadsheets().values().batchUpdate(
    spreadsheetId=SHEET_ID,
    body={"valueInputOption": "USER_ENTERED", "data": data}
).execute()

# Читаем результат
totals = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range=f"{SHEET_NAME}!A20:H20",
    valueRenderOption="FORMATTED_VALUE"
).execute().get("values", [[]])[0]
print(f"ИТОГО: A20={totals[0]} | C20={totals[2]} | E20={totals[4]} | H20={totals[7]}")
