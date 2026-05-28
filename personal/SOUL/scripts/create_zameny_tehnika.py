#!/usr/bin/env python3
"""Создать новую вкладку `Замены_техника` в общей таблице SOUL и залить данные.

Структура аналогична листу `Замены`:
A=Зона | B=Текущий | C=Цена | D=Альт | E=Цена | F=Комментарий | G=Премиум | H=Цена

Из 18 позиций листа `Техника` для 7 предложены альт/премиум, остальные «—».
Цены — рыночные новые в Москве (allowed: avito = новое из параллельного импорта).
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

# 1. Создаём вкладку (если уже есть — скрипт упадёт, защита от дубликата)
meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
existing = [s["properties"]["title"] for s in meta["sheets"]]
if SHEET_NAME in existing:
    print(f"⚠ Лист `{SHEET_NAME}` уже существует — пропускаю создание.")
    sheet_id = next(s["properties"]["sheetId"] for s in meta["sheets"] if s["properties"]["title"] == SHEET_NAME)
else:
    resp = svc.spreadsheets().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"requests": [{"addSheet": {"properties": {
            "title": SHEET_NAME,
            "gridProperties": {"rowCount": 30, "columnCount": 8, "frozenRowCount": 1},
        }}}]}
    ).execute()
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"✓ Создана вкладка `{SHEET_NAME}`, sheetId={sheet_id}")

# 2. Заливаем данные
def hl(url, text):
    return f'=HYPERLINK("{url}";"{text.replace(chr(34), chr(34)*2)}")'

HEADER = ["Зона / позиция", "Текущий вариант", "Цена текущего", "Альтернатива (улучшение качества)", "Цена альт", "Комментарий", "Премиум-аналог", "Премиум-цена"]

# Каждая строка: [A, B, C, D, E, F, G, H]
rows = [HEADER]

# Строка 2: Кухня — Подключение Dreame (без альт/премиум)
rows.append([
    "Кухня / подкл. Dreame",
    hl("https://dreame-store.ru/catalog/roboty-pylesosy/komplekt-dlya-podklyucheniya-k-vodoprovodu-i-kanalizacii-dreame-sewer-connection-kit-raw7-dlya-x50-ultra-x50-ultra-complete?utm_source=chatgpt.com",
       "Dreame Sewer Connection Kit RAW7 для X50 Ultra"),
    12000,
    "—", 0, "Расходник к роботу-пылесосу. Альт не требуется.", "—", 0,
])

# Строка 3: Робот-пылесос Dreame X50 Ultra (флагман — без альт/премиум)
rows.append([
    "Кухня-гостиная / робот-пылесос",
    hl("https://www.avito.ru/moskva/bytovaya_tehnika/dreame_x50_ultra_complete_7389284695",
       "Dreame X50 Ultra Complete (avito, новое)"),
    80000,
    "—", 0, "Флагман Dreame 2025. Уже топ — альт/премиум не предлагается.", "—", 0,
])

# Строка 4: Кофемашина De'Longhi
rows.append([
    "Кухня / кофемашина",
    hl("https://www.avito.ru/moskva/bytovaya_tehnika/novaya_kofemashina_delonghi_eletta_explore_ecam_450.65.g_8053164041",
       "De'Longhi Eletta Explore ECAM450.65.G (avito, новое)"),
    68000,
    hl("https://delonghi.ru/product/de-longhi-kofemashina-ecam610-75-mb/",
       "De'Longhi PrimaDonna Soul ECAM610.75.MB (delonghi.ru, новое)"),
    99990,
    "Eletta Explore — мейнстрим De'Longhi. PrimaDonna Soul (Serie 610) — топ-серия с тачскрином и Latte Crema. Премиум — ECAM610.74.MB с Bean Adapt Technology (auto-настройка под зерно).",
    hl("https://delonghi.ru/product/de-longhi-kofemashina-ecam610-74-mb/",
       "De'Longhi PrimaDonna Soul ECAM610.74.MB Bean Adapt (delonghi.ru, новое)"),
    149990,
])

# Строка 5: Вытяжка AEG (без альт/премиум — норм средний класс)
rows.append([
    "Кухня / вытяжка",
    hl("https://aeg-official.ru/product/vstraivaemaya-vytyazhka-aeg-dge5861hm/",
       "AEG DGE5861HM встраиваемая (aeg-official.ru, новое)"),
    37000,
    "—", 0, "Норм средний класс под кухню 95 м². Альт не требуется (премиум — Falmec/Sirius, но это уже декор).", "—", 0,
])

# Строка 6: Холодильник Haier → Bosch
rows.append([
    "Кухня / холодильник",
    hl("https://www.avito.ru/moskva/bytovaya_tehnika/vstraivaemyy_holodilnik_haier_hbcn_7190u1_7500354130",
       "Haier HBCN7190U1 встраиваемый (avito, новое)"),
    100000,
    hl("https://bosch-centre.ru/bosch/holodilniki/dvuhkamernye-holodilniki/vstraivaemyy-dvukhkamernyy-kholodilnik-bosch-kin86nse0.html",
       "Bosch KIN86NSE0 Serie 4 NoFrost (bosch-centre.ru, новое)"),
    136790,
    "Haier выпадает из общего класса AEG/Bosch. Bosch Serie 4 KIN86NSE0 — единая экосистема с посудомойкой/СВЧ Bosch. Премиум — KIN86VFE0 (Serie 4 расширенная, NoFrost+VitaFresh+стекло-передняя).",
    hl("https://bosch-centre.ru/bosch/holodilniki/dvuhkamernye-holodilniki/vstraivaemyy-dvukhkamernyy-kholodilnik-bosch-kin86vfe0.html",
       "Bosch KIN86VFE0 Serie 4+ NoFrost VitaFresh (bosch-centre.ru, новое)"),
    160100,
])

# Строка 7: Посудомойка Bosch SMV8 (без альт/премиум — топ Bosch)
rows.append([
    "Кухня / посудомойка",
    hl("https://www.avito.ru/moskva/bytovaya_tehnika/posudomoechnaya_mashina_vstraivaemaya_bosch_smv8ycx02e_polnorazmernaya_sushka_s_tseolitom_indikatsiya_vrem_4108683401",
       "Bosch SMV8YCX02E Serie 8 + цеолит (avito, новое)"),
    78000,
    "—", 0, "Топ Bosch — Serie 8 с цеолитной сушкой. Дальше только Miele G7000 за +100K (вне общей экосистемы Bosch/AEG).", "—", 0,
])

# Строка 8: Духовой AEG
rows.append([
    "Кухня / духовой шкаф",
    hl("https://noginsk.technopark.ru/vstraivaemye-duhovye-shkafy-aeg-ta5pb531ab/description/",
       "AEG TA5PB531AB Serie 5 SteamBake пиролиз (technopark, новое)"),
    100000,
    hl("https://aeg-com.ru/catalog/dukhovye-shkafy-aeg/dukhovoy-shkaf-aeg-bse788380m.html",
       "AEG BSE788380M Serie 7 термощуп пар (aeg-com.ru, новое)"),
    141670,
    "Serie 5000 — мейнстрим. Serie 7 (BSE788380M) — термощуп, 23 режима, паровая обработка. Премиум — AEG SteamPro 9000 BSE998330M с WiFi и низкотемп. вакуумом sous vide (тренд 2025).",
    hl("https://www.afonya-spb.ru/Duxovoy-Shkaf-AEG-SteamPro-BSE998330M-594x595x567-Vstraivaemyy-Parovoy-Wi-Fi-Upravlenie/",
       "AEG SteamPro 9000 BSE998330M Steamify Wi-Fi (afonya-spb.ru, новое)"),
    218007,
])

# Строка 9: СВЧ Bosch
rows.append([
    "Кухня / СВЧ",
    hl("https://bosch-centre.ru/bosch/mikrovolnovye-pechi/vstraivaemaya-mikrovolnovaya-pech-bosch-bel554mb0.html",
       "Bosch BEL554MB0 Serie 4 базовая (bosch-centre.ru, новое)"),
    54000,
    hl("https://bosch-centre.ru/bosch/mikrovolnovye-pechi/vstraivaemaya-mikrovolnovaya-pech-bosch-bel7321b1.html",
       "Bosch BEL7321B1 Serie 6 (bosch-centre.ru, новое)"),
    100900,
    "Текущая Serie 4 выпадает на ступень от посудомойки Serie 8. Serie 6 BEL7321B1 — гриль, AutoPilot. Премиум — CFA634GS1 (Serie 8 микроволновка С ПАРОМ — комбо-режим, 36 л).",
    hl("https://bosch-centre.ru/bosch/mikrovolnovye-pechi/mikrovolnovaya-pech-bosch-cfa634gs1.html",
       "Bosch CFA634GS1 Serie 8 СВЧ + пар (bosch-centre.ru, новое)"),
    118680,
])

# Строка 10: Варочная AEG
rows.append([
    "Кухня / варочная",
    hl("https://www.avito.ru/moskva/bytovaya_tehnika/varochnaya_panel_aeg_ike64441fb_7425614179",
       "AEG IKE64441FB Serie 6 индукционная 60см (avito, новое)"),
    43000,
    hl("https://aeg-com.ru/catalog/varochnye-paneli-aeg/induktsionnye/",
       "AEG IKE85651FB Serie 8 80см MaxiSense Bridge + Hob2Hood (aeg-com.ru, новое)"),
    85000,
    "Hob2Hood в Serie 8 синхронизирует мощность вытяжки с конфоркой автоматически. Расширение до 80 см (5 зон). Премиум — IAE84881FB (Serie 8 расширенная функциональность, FlexiBridge).",
    hl("https://aeg-com.ru/catalog/varochnye-paneli-aeg/induktsionnye/aeg-iae84881fb.html",
       "AEG IAE84881FB Serie 8 80см FlexiBridge (aeg-com.ru, новое)"),
    95000,
])

# Строка 11: Измельчитель
rows.append([
    "Кухня / измельчитель отходов",
    hl("https://www.avito.ru/moskva/bytovaya_tehnika/insinkerator_s60_izmelchitel_7364924002",
       "InSinkErator S60 (avito, новое) — БАЗА"),
    40000,
    hl("https://www.insinkerator-rus.ru/byitovyie-izmelchiteli/in-sink-erator-evolution-100",
       "InSinkErator Evolution 100 (1 л.с., MultiGrind, тише на 40%) — insinkerator-rus.ru"),
    23000,
    "S60 — базовая 0.55 л.с. Evolution 100 — 1 л.с. + MultiGrind двухступенчатое + Dura-Drive (тише на 40%). НЕ ДОРОЖЕ! При выборе альт получаем апгрейд И экономию −17K. Премиум Evolution 200 — 1.1 л.с., 3 ступени (best-in-class).",
    hl("https://insinkerator-shop.ru/catalog/bytovye-izmelchiteli-insinkerator/",
       "InSinkErator Evolution 200 (1.1 л.с., 3 ступени, лидер категории) — insinkerator-shop.ru"),
    29000,
])

# Строка 12: Фильтр (без альт/премиум)
rows.append([
    "Кухня / фильтр питьевой воды",
    hl("https://market.yandex.ru/card/baryer-ekspert-zhestkost-kh2-filtr-pod-moyku-dlya-ochistki-vody-dvoynaya-zashchita-ot-nakipi-trekhstupenchatyy-bystrosyemnyy-bez-krana/102216314517",
       "Барьер Эксперт Жёсткость К2 трёхступенчатый (market.yandex)"),
    7000,
    "—", 0, "Базовый фильтр под мойку. Альт — обратный осмос (Аквафор Морион 12-15K), премиум — стационарный осмос с минерализатором (25-40K).", "—", 0,
])

# Строка 13: Вертикальный пылесос Dreame Z30 (флагман)
rows.append([
    "Прихожая / вертикальный пылесос",
    hl("https://market.yandex.ru/card/pylesos-dlya-doma-dreame-z30-vzv17a-besprovodnoy-pylesbornik-obyemom-600-ml-7-nasadok-chernyy/4465556503",
       "Dreame Z30 VZV17A 600 мл, 7 насадок (market.yandex)"),
    45000,
    "—", 0, "Флагман Dreame в категории. Альт не требуется.", "—", 0,
])

# Строка 14: Колонка Яндекс
rows.append([
    "Санузел 5.0 / умная колонка",
    hl("https://market.yandex.ru/card/umnaya-kolonka-yandeks-stantsiya-mini-3-s-chasami--chernaya--black/4789742822",
       "Яндекс Станция Мини 3 с часами, чёрная (market.yandex)"),
    9000,
    "—", 0, "Аксессуар. Альт не требуется.", "—", 0,
])

# Строка 15: Водонагреватель Stiebel Eltron (топ)
rows.append([
    "Санузел 5.0 / водонагреватель",
    hl("https://www.avito.ru/moskva/remont_i_stroitelstvo/stiebel_eltron_dce-x_1012_premium_2288400583",
       "Stiebel Eltron DCE-X 10/12 Premium (avito, новое)"),
    36000,
    "—", 0, "Лучший в категории электр.-проточных (Stiebel Eltron — немецкий лидер). Альт/премиум не требуется.", "—", 0,
])

# Строка 16: Asko Classic 17 (топ)
rows.append([
    "Постирочная / Asko комплект",
    hl("https://asko-russia.ru/catalog/complects-asko/domashnyaya-prachechnaya/komplekt-asko-classic-17-w1094w-t108hw-hi150w.html",
       "Asko Classic 17 (стирка W1094W + сушка T108HW + пьедестал HI150W) — asko-russia.ru"),
    255000,
    "—", 0, "Премиум-класс уже. Альт — Miele WTR860 (~280K, тоже топ). Менять смысла нет.", "—", 0,
])

# Строка 17: Винный шкаф
rows.append([
    "Кабинет / винный шкаф",
    hl("https://www.ozon.ru/product/vinnyy-shkaf-weissgauff-wwc-12-compressor-kompressornyy-holodilnik-dlya-vina-12-butylok-2884781687/",
       "Weissgauff WWC-12 (12 бутылок, базовый) — ozon"),
    20000,
    hl("https://www.winecool.ru/catalog/vinnye-shkafy-vstraivaemye/vinnyy-shkaf-caso-winemaster-touch-38-2d/",
       "Caso WineMaster Touch 38-2D (38 бут., 2 зоны, тач снаружи) — winecool.ru"),
    72400,
    "12 бутылок для премиум-кухни — мало. Caso WineMaster 38-2D: 2 зоны (5-20°C), 38 бут., деревянные полки, UV-фильтр. Премиум — Caso WineComfort 38 Black: тач-управление ВНУТРИ, blue LED, два независимых контура.",
    hl("https://caso-bt.ru/vinnye-shkafy/winecomfort/vinnyy-shkaf-caso-winecomfort-38-black",
       "Caso WineComfort 38 Black (тач внутри, два контура, премиум) — caso-bt.ru"),
    175500,
])

# Строка 18: TV гостиная (флагман дизайн)
rows.append([
    "Гостиная / TV",
    hl("https://www.avito.ru/moskva/audio_i_video/65televizor_samsung_the_frame_qe65ls03fauxru2025_7788366971",
       "Samsung The Frame QE65LS03FAUXRU 2025 (avito, новое)"),
    122000,
    "—", 0, "Дизайнерский TV-картина 2025 (глубина 24.9 мм). Альт = OLED (Sony A95L/Samsung S95D) — другая философия (без рамы-картины). Менять не имеет смысла.", "—", 0,
])

# Строка 19: TV кабинет
rows.append([
    "Кабинет / TV",
    hl("https://www.avito.ru/moskva/audio_i_video/televizor_samsung_qe55ls03fauxru_novinka_2025_rst_7890790000",
       "Samsung The Frame QE55LS03FAUXRU 2025 (avito, новое)"),
    100000,
    "—", 0, "55\" версия того же The Frame для кабинета. Альт не требуется.", "—", 0,
])

# Строка 20: ИТОГО
rows.append([
    "ИТОГО", "",
    "=SUM(C2:C19)", "",
    "=SUMIF(E2:E19;\">0\")", "",
    "",
    "=SUMIF(H2:H19;\">0\")"
])

# Заливаем
data = [{"range": f"{SHEET_NAME}!A1:H{len(rows)}", "values": rows}]
resp = svc.spreadsheets().values().batchUpdate(
    spreadsheetId=SHEET_ID,
    body={"valueInputOption": "USER_ENTERED", "data": data}
).execute()
print(f"✓ Залито ячеек: {resp.get('totalUpdatedCells')}")

# 3. Применяем оформление: цвета фона по секциям
# Секции: B/C — розовый (#FCE4EC), D/E — зелёный (#E8F5E9), G/H — жёлтый (#FFF9C4)
# Шапка — серый #1F2937 текст белый, жирный
def fill(start_col, end_col, color, header_color=None, text_color=None):
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1, "endRowIndex": 19,
                "startColumnIndex": start_col, "endColumnIndex": end_col,
            },
            "cell": {"userEnteredFormat": {"backgroundColor": color}},
            "fields": "userEnteredFormat.backgroundColor",
        }
    }

requests = [
    # Шапка: тёмно-серый, белый текст, жирный
    {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": 8},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.122, "green": 0.161, "blue": 0.216},
                "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }
    },
    # B и C — розовый
    fill(1, 3, {"red": 0.988, "green": 0.894, "blue": 0.925}),
    # D и E — зелёный
    fill(3, 5, {"red": 0.910, "green": 0.961, "blue": 0.914}),
    # G и H — жёлтый
    fill(6, 8, {"red": 1.0, "green": 0.976, "blue": 0.769}),
    # Строка ИТОГО (20-я, индекс 19) — жирная
    {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 19, "endRowIndex": 20,
                      "startColumnIndex": 0, "endColumnIndex": 8},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
            }},
            "fields": "userEnteredFormat(textFormat,backgroundColor)",
        }
    },
    # Числовой формат для C, E, H — рубли
    {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 20,
                      "startColumnIndex": 2, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "# ##0 ₽"}}},
            "fields": "userEnteredFormat.numberFormat",
        }
    },
    {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 20,
                      "startColumnIndex": 4, "endColumnIndex": 5},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "# ##0 ₽"}}},
            "fields": "userEnteredFormat.numberFormat",
        }
    },
    {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 20,
                      "startColumnIndex": 7, "endColumnIndex": 8},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "# ##0 ₽"}}},
            "fields": "userEnteredFormat.numberFormat",
        }
    },
    # Перенос текста для F
    {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 20,
                      "startColumnIndex": 5, "endColumnIndex": 6},
            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
            "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)",
        }
    },
    # Ширина колонок
    {"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 200}, "fields": "pixelSize"
    }},
    {"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
        "properties": {"pixelSize": 320}, "fields": "pixelSize"
    }},
    {"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4},
        "properties": {"pixelSize": 320}, "fields": "pixelSize"
    }},
    {"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 5, "endIndex": 6},
        "properties": {"pixelSize": 400}, "fields": "pixelSize"
    }},
    {"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 6, "endIndex": 7},
        "properties": {"pixelSize": 320}, "fields": "pixelSize"
    }},
]
svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": requests}).execute()
print("✓ Применено оформление")

# Читаем итоги
totals = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range=f"{SHEET_NAME}!A20:H20",
    valueRenderOption="FORMATTED_VALUE"
).execute().get("values", [[]])[0]
print(f"ИТОГО: {totals}")
