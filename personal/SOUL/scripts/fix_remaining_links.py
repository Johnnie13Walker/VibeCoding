#!/usr/bin/env python3
"""Дочинить оставшиеся URL в Замены_техника:
- D2: Eletta Cappuccino Evo (404 → NeAmazon, 61 490 ₽ in stock)
- G2: Jura Z10 (market.yandex 403 → mtpark.ru, 364 990 ₽ in stock, чёрный)
- D3: Haier категория → пометка (для РФ конкретной карточки HCR3818ENMM не нашёл)
- G3: Bosch KGP86FWC0N категория → DNS конкретная карточка
- D6: AEG IKE85651FB категория → оставить с пометкой (модель в РФ ограниченно)
"""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1cXhvMVjCTb3JREUeKZhy1cxF544fpegW0s-JINLlQTs"
SHEET_NAME = "Замены_техника"

creds = Credentials.from_service_account_file(KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
svc = build("sheets","v4",credentials=creds,cache_discovery=False)

def hl(url, text): return f'=HYPERLINK("{url}";"{text.replace(chr(34), chr(34)*2)}")'

updates = [
    # D2: NeAmazon Eletta Cappuccino Evo (подтверждено 61 490, in stock, полностью чёрный)
    ("D2", hl(
        "https://neamazon.ru/kofemashina-delonghi-ecam46-860-b-eletta-cappuccino-evo",
        "De'Longhi Eletta Cappuccino Evo ECAM46.860.B (полностью чёрный, neamazon.ru, в наличии)"
    )),
    ("E2", 61490),

    # G2: Jura Z10 → mtpark (подтверждено 364 990, in stock, чёрный)
    ("G2", hl(
        "https://mtpark.ru/product/kofemashina-jura-z10-aluminium-black-15488/",
        "Jura Z10 Aluminium Black 15488 (полностью чёрный, mtpark.ru, в наличии)"
    )),
    ("H2", 364990),
    ("F2", (
        "Заказчик хочет ПОЛНОСТЬЮ чёрную кофемашину. В линейке Eletta Explore (текущая) и PrimaDonna Soul чёрной модели нет. "
        "АЛЬТ: Eletta Cappuccino Evo ECAM46.860.B — старший Eletta, полностью чёрный, LatteCrema, neamazon.ru 61 490 ₽ in stock. Без cold brew vs текущая Eletta Explore (компромисс). "
        "ПРЕМИУМ: Jura Z10 Aluminium Black — швейцарский премиум, 40 программ напитков, 15 бар, in stock на mtpark.ru за 364 990 ₽. "
        "ВАЖНО: текущая модель в смете (ECAM450.65.G Graphite) тоже не чёрная — рекомендуется заменить и её на ECAM46.860.B."
    )),

    # G3: Bosch KGP86FWC0N → DNS конкретная карточка
    ("G3", hl(
        "https://www.dns-shop.ru/product/7f481ebc3e51b1ae/holodilnik-s-morozilnikom---bosch-kgp86fwc0n-belyj/",
        "Bosch KGP86FWC0N French Door 90 см, Serie 6 VitaFresh, 624 л (dns-shop.ru, белый)"
    )),
    # D3: Haier — для РФ карточки HCR3818ENMM не нашёл, оставлю как есть, но с пометкой
    ("F3", (
        "Заказчик хочет ШИРОКИЙ холодильник 80-91 см. Текущий в смете Haier HBCN7190U1 (54 см встр.) — НЕ соответствует требованию.\n\n"
        "ВАЖНОЕ ОГРАНИЧЕНИЕ: встраиваемые широкие 91 см (Liebherr ECBN 6156/6256) — везде «нет в наличии» в Москве (520-1125K, под заказ из параллельного импорта). "
        "По решению заказчика временно ставим ОТДЕЛЬНОСТОЯЩИЕ French Door 90 см (категория ниже по требованию «встраиваемый», но in-stock).\n\n"
        "АЛЬТ: Haier HCR3818ENMM French Door 83.3 см, 467 л — для РФ конкретный артикул нужно уточнить (в каталоге Hausdorf есть аналоги). "
        "ПРЕМИУМ: Bosch KGP86FWC0N French Door 90 см Serie 6 VitaFresh 624 л — конкретная карточка DNS, ~290K.\n\n"
        "ДЛЯ ВСТРАИВАЕМОГО: вернуться к подбору Liebherr ECBN под заказ позже."
    )),

    # D6: AEG IKE85651FB — модель не находится в РФ, оставлю категорию с пометкой
    ("F6", (
        "Hob2Hood в Serie 8 синхронизирует мощность вытяжки с конфоркой автоматически. Расширение до 80 см (5 зон). Премиум — IAE84881FB (Serie 8 расширенная, FlexiBridge).\n\n"
        "ВАЖНО: модель IKE85651FB ограниченно представлена в РФ — конкретная карточка нашлась только у евр. дилеров. URL ведёт на категорию AEG-индукционные на aeg-com.ru (нужно уточнить SKU при заказе у дилера). Цена 85 000 ₽ — ориентир по евр. рынку."
    )),
]

data = [{"range": f"{SHEET_NAME}!{c}", "values": [[v]]} for c,v in updates]
resp = svc.spreadsheets().values().batchUpdate(
    spreadsheetId=SHEET_ID,
    body={"valueInputOption": "USER_ENTERED", "data": data}
).execute()
print(f"Updated cells: {resp.get('totalUpdatedCells')}")

totals = svc.spreadsheets().values().get(spreadsheetId=SHEET_ID,range=f"{SHEET_NAME}!A9:H9",valueRenderOption="FORMATTED_VALUE").execute().get("values",[[]])[0]
print(f"ИТОГО: C={totals[2]} | E={totals[4]} | H={totals[7]}")
