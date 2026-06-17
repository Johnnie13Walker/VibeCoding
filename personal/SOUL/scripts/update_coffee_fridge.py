#!/usr/bin/env python3
"""Правки кофемашины (строка 2) и холодильника (строка 3) в `Замены_техника`:
- Кофемашина: чёрные модели вместо PrimaDonna Soul .MB (металлик с серым)
- Холодильник: широкий French Door 80-91 см вместо узкого встраиваемого

После предыдущей очистки строк актуальная нумерация:
- Row 2: Кухня / кофемашина
- Row 3: Кухня / холодильник
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

def hl(url, text):
    return f'=HYPERLINK("{url}";"{text.replace(chr(34), chr(34)*2)}")'

updates = [
    # === Кофемашина (Row 2) ===
    # АЛЬТ: Eletta Cappuccino Evo ECAM46.860.B (полностью чёрный)
    ("D2", hl(
        "https://delonghi.ru/product/de-longhi-kofemashina-ecam46-860-b/",
        "De'Longhi Eletta Cappuccino Evo ECAM46.860.B (полностью чёрный, delonghi.ru)"
    )),
    ("E2", 75000),
    # ПРЕМИУМ: Jura Z10 Aluminium Black (полностью чёрный)
    ("G2", hl(
        "https://market.yandex.ru/card/kofemashina-jura-z10-aluminium-black-15488/4302449088",
        "Jura Z10 Aluminium Black (полностью чёрный, market.yandex)"
    )),
    ("H2", 350000),
    ("F2", (
        "Заказчик хочет ПОЛНОСТЬЮ чёрную кофемашину. В линейке Eletta Explore (текущая) и PrimaDonna Soul чёрной модели нет — только Graphite/Matte Black с серыми вставками. "
        "АЛЬТ: Eletta Cappuccino Evo ECAM46.860.B — старший Eletta класс, полностью чёрный, LatteCrema, 13 степеней помола. Без cold brew (vs текущая Eletta Explore — это компромисс). "
        "ПРЕМИУМ: Jura Z10 Aluminium Black — швейцарский премиум, 40 программ напитков, 15 бар, полностью чёрный корпус. Параллельный импорт. "
        "ВАЖНО: текущая модель в смете (ECAM450.65.G Graphite) тоже не чёрная — рекомендуется заменить и её."
    )),

    # === Холодильник (Row 3) ===
    # АЛЬТ: Haier HCR3818ENMM French Door 91 см (преемственность бренда)
    ("D3", hl(
        "https://www.hausdorf.ru/catalog/kholodilniki/haier/ext/mnogodvernye-kholodilniki-haier/",
        "Haier HCR3818ENMM French Door 91 см, 467 л, NoFrost (hausdorf.ru)"
    )),
    ("E3", 140000),
    # ПРЕМИУМ: Bosch KGP86FWC0N French Door 90 см
    ("G3", hl(
        "https://bosch-centre.ru/bosch/holodilniki/recommend/shirinoy-90-sm-bs/",
        "Bosch KGP86FWC0N French Door 90 см Serie 6 VitaFresh, 624 л (bosch-centre.ru)"
    )),
    ("H3", 290000),
    ("F3", (
        "Заказчик хочет ШИРОКИЙ холодильник French Door 80-91 см. Текущий Haier HBCN7190U1 в смете — встраиваемый узкий 54 см — НЕ соответствует требованию (другая категория). "
        "АЛЬТ: Haier HCR3818ENMM — French Door 83.3 см, 467 л, тач, NoFrost (преемственность бренда из сметы). "
        "ПРЕМИУМ: Bosch KGP86FWC0N — French Door 90 см, Serie 6 VitaFresh+, инвертор, 624 л, премиум-класс. "
        "ВАЖНО: текущая позиция в смете требует пересогласования с Дарьей — нужно поменять и саму смету (это другая категория техники, не просто другая модель)."
    )),
]

data = [{"range": f"{SHEET_NAME}!{c}", "values": [[v]]} for c,v in updates]
resp = svc.spreadsheets().values().batchUpdate(
    spreadsheetId=SHEET_ID,
    body={"valueInputOption": "USER_ENTERED", "data": data}
).execute()
print(f"Updated cells: {resp.get('totalUpdatedCells')}")

# Читаем итоги
totals = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range=f"{SHEET_NAME}!A9:H9",
    valueRenderOption="FORMATTED_VALUE"
).execute().get("values", [[]])[0]
print(f"ИТОГО: A9={totals[0]} | C9={totals[2]} | E9={totals[4]} | H9={totals[7]}")
