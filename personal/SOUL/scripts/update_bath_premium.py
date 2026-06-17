#!/usr/bin/env python3
"""Замена премиум-ванны 5.0: Bette Classic (сталь) → Delice Diapason 180x70 (литьевой мрамор)."""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1cXhvMVjCTb3JREUeKZhy1cxF544fpegW0s-JINLlQTs"
SHEET_NAME = "Замены"

creds = Credentials.from_service_account_file(
    KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

def hl(url, text):
    return f'=HYPERLINK("{url}";"{text.replace(chr(34), chr(34)*2)}")'

URL = "https://santehnica.ru/product/1796361.html"
TEXT = "Delice Diapason DLR330008-M 180×70 литьевой мрамор матовый, белый (santehnica.ru, в наличии)"

updates = [
    ("G8", hl(URL, TEXT)),
    ("H8", 75000),
    ("F8", (
        "Эстет Дельта 180/70 — точное совпадение размера (литьевой мрамор, blumart 61 250, в наличии). "
        "Премиум — Delice Diapason DLR330008-M (Франция/литьевой мрамор, матовый белый, 180×70, толщина 18 мм, в наличии на santehnica.ru). "
        "Стальные ванны (Bette, Kaldewei) исключены — заказчик хочет только литой материал во всех сегментах. "
        "Astra-Form / Salini Orlanda / Эстет Альфа в стандартном 180×70 не выпускаются."
    )),
]

data = [{"range": f"{SHEET_NAME}!{c}", "values": [[v]]} for c,v in updates]
resp = svc.spreadsheets().values().batchUpdate(
    spreadsheetId=SHEET_ID,
    body={"valueInputOption": "USER_ENTERED", "data": data}
).execute()
print(f"Updated cells: {resp.get('totalUpdatedCells')}")
