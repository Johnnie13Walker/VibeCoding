#!/usr/bin/env python3
"""Замена ссылки D7 (АЛЬТ Evolution 100) на пользовательскую avito-ссылку.
Цена 23 000 ₽ оставлена как ориентир (avito блокирует автоверификацию)."""
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

def hl(url, text):
    return f'=HYPERLINK("{url}";"{text.replace(chr(34), chr(34)*2)}")'

URL_USER = "https://www.avito.ru/ivanovo/bytovaya_tehnika/izmelchitel_insinkerator_evolution_100_7718435171?slocation=637640"
TEXT = "InSinkErator Evolution 100 (avito Иваново → доставка Москва, новое — ссылка от заказчика)"

# Также фикшу G7 — там была категория. Поставим конкретный товар Evolution Plus 750 EC (in stock 77 400)
URL_PREMIUM = "https://insinkerator-shop.ru/catalog/bytovye-izmelchiteli-insinkerator/izmelchitel-pishchevykh-otkhodov-insinkerator-evolution-plus-750-ec.html"
TEXT_PREMIUM = "InSinkErator Evolution Plus 750 EC (insinkerator-shop.ru, в наличии, новое, гарантия 1 год)"

updates = [
    ("D7", hl(URL_USER, TEXT)),
    # E7 цену не меняем — avito блокирует автопроверку, нужно подтверждение от пользователя
    ("G7", hl(URL_PREMIUM, TEXT_PREMIUM)),
    ("H7", 77400),
    ("F7", (
        "S60 — базовая 0.55 л.с. Evolution 100 — 1 л.с. + MultiGrind двухступенчатое + Dura-Drive (тише на 40%). НЕ ДОРОЖЕ — авито-канал даёт реальную экономию −17K при апгрейде. "
        "Премиум: Evolution Plus 750 EC (0.75 л.с., 60% тише, 6 лет гарантии, in stock на офиц.дилере insinkerator-shop.ru за 77 400 ₽). "
        "Evolution 200 снят с производства — везде Out of Stock, заменён в премиуме на 750 EC. "
        "Для альт: ссылка от заказчика (avito Иваново с доставкой). Цену 23 000 ₽ нужно подтвердить (avito блокирует автоматическую проверку)."
    )),
]
data = [{"range": f"{SHEET_NAME}!{c}", "values": [[v]]} for c,v in updates]
resp = svc.spreadsheets().values().batchUpdate(
    spreadsheetId=SHEET_ID,
    body={"valueInputOption": "USER_ENTERED", "data": data}
).execute()
print(f"Updated cells: {resp.get('totalUpdatedCells')}")

# Итоги
totals = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range=f"{SHEET_NAME}!A9:H9",
    valueRenderOption="FORMATTED_VALUE"
).execute().get("values", [[]])[0]
print(f"ИТОГО: C={totals[2]} | E={totals[4]} | H={totals[7]}")
