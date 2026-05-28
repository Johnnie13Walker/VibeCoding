#!/usr/bin/env python3
"""Обновление листа `Замены` по согласованному плану."""
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
    text_safe = text.replace('"', '""')
    return f'=HYPERLINK("{url}";"{text_safe}")'

updates = [
    ("G2", hl(
        "https://hans-rus.ru/katalog/talis-m54-kuhonnyy-smesitel-odnorychazhnyy-270-1jet-72840000-72840670.html",
        "Hansgrohe Talis M54 72840670, кухонный 270 1jet, матовый чёрный (hans-rus.ru, в наличии)"
    )),
    ("H2", 34253),

    ("G8", hl(
        "https://mosplitka.ru/product/stalnaya-vanna-bette-classic-180x70sm-1271-000/",
        "Bette Classic 1271-000 180×70 сталь+эмаль BetteGlasur, белая (mosplitka.ru — проверить in-stock перед заказом)"
    )),
    ("H8", 72163),

    ("D9", hl(
        "https://www.iddis.ru/catalog/bathroom/wc_frames/PRO0000i32/",
        "IDDIS Profix PRO0000i32 (инсталляция) + IDDIS Unifix UNI06MBi77 кнопка чёрный матовый"
    )),
    ("E9", 24580),
    ("D10", hl(
        "https://www.iddis.ru/catalog/bathroom/wc_frames/PRO0000i32/",
        "IDDIS Profix PRO0000i32 (инсталляция) + IDDIS Unifix UNI06MBi77 кнопка чёрный матовый"
    )),
    ("E10", 24580),

    ("D11", hl(
        "https://teploluxe.ru/catalog/zashchita-ot-protechek-vody/sistemy-zashchity-ot-protechek/product/sistema-zashchity-ot-protechek-aquacontrol/",
        "Neptun Aquacontrol 1/2 (база, 2 датчика SW007) + 2 доп. датчика для 4 точек (teploluxe.ru, в наличии)"
    )),
    ("E11", 18000),
    ("G11", hl(
        "https://gidrolock-shop.ru/index.php?route=product/product&product_id=373",
        "Gidrolock Premium PLUS BUGATTI 1/2: 2 крана + блок + 3 датчика WSP (gidrolock-shop.ru, в наличии)"
    )),
    ("H11", 32330),

    ("F8", (
        "Эстет Дельта 180/70 — точное совпадение размера (литьевой мрамор, blumart 61 250, в наличии). "
        "Премиум — Bette Classic (Германия), стальная эмалированная 180×70, гарантия 30 лет на эмаль. "
        "Цена премиум обновлена: mosplitka 72 163 ₽ — проверить наличие лично перед заказом (анти-бот блокирует автопроверку). "
        "Astra-Form в 180×70 не выпускается стандартно."
    )),
    ("F9", (
        "Geberit Duofix UP320 — универсальное крепление 18/23 см, EN 33:2011: подходит под Ravak и Roca. "
        "Кнопка Sigma 70 — в палитру оружейной стали. Альт-комплект IDDIS: рама PRO0000i32 (19 990) + кнопка UNI06MBi77 чёрный мат (4 590)."
    )),
    ("F10", (
        "Тот же Geberit Duofix UP320, что в 5.0 — единый стиль кнопок. "
        "Альт-комплект IDDIS: PRO0000i32 + UNI06MBi77 (тот же, что в 5.0)."
    )),
    ("F11", (
        "Требуется по ТЗ: 5.0, 3.4, кухня, постирочная (4 точки). Установка — отдельная строка работ. "
        "Альт Neptun Aquacontrol: база 16 500 + 2 доп. датчика SW007 ~1 500 ₽ для покрытия 4 точек. "
        "Премиум Gidrolock Premium PLUS BUGATTI 1/2 — конкретный комплект на 2 крана + 3 датч (можно расширить до 4)."
    )),
]

data = []
for cell, val in updates:
    rng = f"{SHEET_NAME}!{cell}"
    data.append({"range": rng, "values": [[val]]})

resp = svc.spreadsheets().values().batchUpdate(
    spreadsheetId=SHEET_ID,
    body={"valueInputOption": "USER_ENTERED", "data": data}
).execute()
print(f"Updated cells: {resp.get('totalUpdatedCells')}")

totals = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range=f"{SHEET_NAME}!C14:H14",
    valueRenderOption="FORMATTED_VALUE"
).execute().get("values", [[]])[0]
print(f"ИТОГО: C14={totals[0]} | E14={totals[2]} | H14={totals[5]}")
