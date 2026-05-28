#!/usr/bin/env python3
"""Правка Grohe Essence 19408AL1 в строках 3 и 4 листа `Замены`:
- ссылка top-santehnika (OOS) → grohe-russia.shop (PreOrder)
- исправление артикула скрытой части: 35600000 → 23572000
- цена 42 000 ₽ остаётся как ориентир
"""
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

URL = "https://grohe-russia.shop/vannaya/smesiteli-dlja-rakoviny/smesitel-dlya-rakoviny-grohe-essence-temnyy-grafit-matovyy-19408al1.html"
TEXT = "Grohe Essence 19408AL1 встр. графит мат. + скрытая часть 23572000 (grohe-russia.shop, под заказ)"

updates = [
    ("G3", hl(URL, TEXT)),
    ("G4", hl(URL, TEXT)),
    # Комментарии — добавим ремарку об артикуле и доступности
    ("F3", (
        "Скрытая часть в комплекте — артикул Grohe 23572000 (для двухвентильного M-Size, не Rapido SmartBox 35600000 — тот для душа). "
        "Цвет графит — сверить с оружейной сталью. "
        "Премиум-Grohe в наличии прямо сейчас в Москве не нашли — везде «под заказ» из параллельного импорта; цена 42 000 ₽ — ориентир (смеситель ~33-45K + скрытая часть ~12K)."
    )),
    ("F4", (
        "Тот же артикул и скрытая часть 23572000, что в 5.0 — единый тон. "
        "Поставка под заказ через параллельный импорт; уточнить наличие при размещении заказа."
    )),
]

data = [{"range": f"{SHEET_NAME}!{c}", "values": [[v]]} for c,v in updates]
resp = svc.spreadsheets().values().batchUpdate(
    spreadsheetId=SHEET_ID,
    body={"valueInputOption": "USER_ENTERED", "data": data}
).execute()
print(f"Updated cells: {resp.get('totalUpdatedCells')}")

totals = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range=f"{SHEET_NAME}!C14:H14",
    valueRenderOption="FORMATTED_VALUE"
).execute().get("values", [[]])[0]
print(f"ИТОГО после правки (после пересчёта формул): {totals}")
