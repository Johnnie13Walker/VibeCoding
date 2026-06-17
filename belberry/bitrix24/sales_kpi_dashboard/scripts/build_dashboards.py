"""Создание 3 дашборд-табов в Output Sheet через Sheets API.
Идемпотентно: если таб существует — пересоздаёт (удаляет + добавляет заново).
"""
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE"

creds = Credentials.from_service_account_file(KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

# Получим текущие табы и их sheetId
meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID, fields="sheets.properties").execute()
tabs = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
print("Existing tabs:", list(tabs.keys()))

# IDs source-табов (нужны для chart-references)
TM_ID = tabs["tm_metrics"]
SP_ID = tabs["sales_plan"]
MOP_ID = tabs["mop_metrics"]
PLAN_ID = tabs["Plan"]

# Удалить старые дашборд-табы если есть (идемпотентность)
DASHBOARDS = ["Дашборд ТМ", "Дашборд План", "Дашборд МОП"]
delete_requests = [{"deleteSheet": {"sheetId": tabs[name]}} for name in DASHBOARDS if name in tabs]
if delete_requests:
    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": delete_requests}).execute()
    print(f"Deleted {len(delete_requests)} old dashboard tabs")

# Создадим 3 свежих таба
add_requests = [{"addSheet": {"properties": {"title": name, "gridProperties": {"rowCount": 100, "columnCount": 20}}}} for name in DASHBOARDS]
resp = svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": add_requests}).execute()
new_ids = {r["addSheet"]["properties"]["title"]: r["addSheet"]["properties"]["sheetId"] for r in resp["replies"]}
print("New tab IDs:", new_ids)

DTM_ID = new_ids["Дашборд ТМ"]
DPLAN_ID = new_ids["Дашборд План"]
DMOP_ID = new_ids["Дашборд МОП"]

# === Контент таба "Дашборд ТМ" ===
# Layout (rows = 0-indexed):
# Row 0: Заголовок (мерж A1:H1) "Телемаркетинг — план/факт по сотрудникам"
# Row 2: KPI карточки A3:E5 — Встречи факт, Встречи план, % плана, Прогноз, Конверсия
# Row 7-22: чарт «Встречи план vs факт vs прогноз»
# Row 23-38: чарт «Наборы в день»
# Row 39-54: чарт «Звонков 120с+ в день»
# Row 55-70: чарт «Конверсии»

# Заголовки и формулы
tm_values = [
    ["Телемаркетинг — план/факт май 2026", "", "", "", "", "", "", ""],  # row 1
    [""],
    ["Встречи факт", "Встречи план", "% плана", "Прогноз", "Конверсия 120с→встреча"],  # row 3
    [
        "=tm_metrics!G2",  # meetings_fact ALL
        "=tm_metrics!H2",  # meetings_plan
        '=IFERROR(tm_metrics!G2/tm_metrics!H2,0)',  # % plan
        "=tm_metrics!J2",  # meetings_forecast
        '=tm_metrics!L2&"%"',  # conv_call_to_meeting
    ],
    [""],
]
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID,
    range=f"'Дашборд ТМ'!A1:H5",
    valueInputOption="USER_ENTERED",
    body={"values": tm_values},
).execute()
print("Дашборд ТМ: header + KPI вставлены")

# Форматирование + добавление чартов
def chart_request(sheet_id, anchor_row, title, source_sheet_id, x_col, y_cols, start_row=1, end_row=4):
    """y_cols: list of (col_index, label) для нескольких серий."""
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "basicChart": {
                        "chartType": "COLUMN",
                        "legendPosition": "BOTTOM_LEGEND",
                        "axis": [
                            {"position": "BOTTOM_AXIS"},
                            {"position": "LEFT_AXIS"},
                        ],
                        "domains": [{
                            "domain": {"sourceRange": {"sources": [{
                                "sheetId": source_sheet_id,
                                "startRowIndex": start_row,
                                "endRowIndex": end_row,
                                "startColumnIndex": x_col,
                                "endColumnIndex": x_col + 1,
                            }]}}
                        }],
                        "series": [
                            {
                                "series": {"sourceRange": {"sources": [{
                                    "sheetId": source_sheet_id,
                                    "startRowIndex": start_row - 1,  # включаем header для имени серии
                                    "endRowIndex": end_row,
                                    "startColumnIndex": col,
                                    "endColumnIndex": col + 1,
                                }]}},
                                "targetAxis": "LEFT_AXIS",
                            }
                            for col, _ in y_cols
                        ],
                        "headerCount": 1,
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {
                            "sheetId": sheet_id,
                            "rowIndex": anchor_row,
                            "columnIndex": 0,
                        },
                        "widthPixels": 700,
                        "heightPixels": 320,
                    }
                },
            }
        }
    }

# tm_metrics колонки (0-indexed):
# 0 date_calc, 1 period, 2 employee_id, 3 employee_name, 4 naborov_per_day, 5 calls_120s, 
# 6 meetings_fact, 7 meetings_plan, 8 meetings_trend, 9 meetings_forecast, 
# 10 conv_nabor_to_call, 11 conv_call_to_meeting, 12 meetings_per_week_avg

# Строки tm_metrics (0-indexed): 0=header, 1=ALL, 2=Вострецов, 3=Исаева
# Для чартов берём строки 2-3 (без ALL), 1=Вострецов, 2=Исаева → start=2, end=4 (exclusive)

chart_requests = [
    chart_request(DTM_ID, 6, "Встречи: план / факт / прогноз (по сотрудникам)", TM_ID, x_col=3,
                  y_cols=[(7, "план"), (6, "факт"), (9, "прогноз")], start_row=2, end_row=4),
    chart_request(DTM_ID, 23, "Наборов в день (по сотрудникам)", TM_ID, x_col=3,
                  y_cols=[(4, "наборы")], start_row=2, end_row=4),
    chart_request(DTM_ID, 40, "Звонков 120с+ в день (по сотрудникам)", TM_ID, x_col=3,
                  y_cols=[(5, "120с+")], start_row=2, end_row=4),
    chart_request(DTM_ID, 57, "Конверсии (%) (по сотрудникам)", TM_ID, x_col=3,
                  y_cols=[(10, "набор→120с+"), (11, "120с+→встреча")], start_row=2, end_row=4),
]

# Форматирование: жирный заголовок A1, мерж, KPI крупным шрифтом
format_requests = [
    # Merge A1:H1
    {"mergeCells": {"range": {"sheetId": DTM_ID, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 8}, "mergeType": "MERGE_ALL"}},
    # Заголовок: bold, 16, центр, фон голубой
    {"repeatCell": {
        "range": {"sheetId": DTM_ID, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 8},
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.85, "green": 0.93, "blue": 0.97},
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "textFormat": {"bold": True, "fontSize": 16},
        }},
        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)",
    }},
    # KPI заголовки (row 3): bold, размер 10, серый фон
    {"repeatCell": {
        "range": {"sheetId": DTM_ID, "startRowIndex": 2, "endRowIndex": 3, "startColumnIndex": 0, "endColumnIndex": 5},
        "cell": {"userEnteredFormat": {
            "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
            "textFormat": {"bold": True, "fontSize": 10},
            "horizontalAlignment": "CENTER",
        }},
        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
    }},
    # KPI значения (row 4): bold, размер 18, центр
    {"repeatCell": {
        "range": {"sheetId": DTM_ID, "startRowIndex": 3, "endRowIndex": 4, "startColumnIndex": 0, "endColumnIndex": 5},
        "cell": {"userEnteredFormat": {
            "textFormat": {"bold": True, "fontSize": 18},
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
        }},
        "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment)",
    }},
    # Высота row 1 (заголовок) — 40 px
    {"updateDimensionProperties": {
        "range": {"sheetId": DTM_ID, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 50}, "fields": "pixelSize",
    }},
    # Высота row 4 (KPI значения) — 50 px
    {"updateDimensionProperties": {
        "range": {"sheetId": DTM_ID, "dimension": "ROWS", "startIndex": 3, "endIndex": 4},
        "properties": {"pixelSize": 50}, "fields": "pixelSize",
    }},
    # Ширина колонок A:H — 140 px
    {"updateDimensionProperties": {
        "range": {"sheetId": DTM_ID, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 8},
        "properties": {"pixelSize": 140}, "fields": "pixelSize",
    }},
]

svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": format_requests + chart_requests}).execute()
print("Дашборд ТМ: формат + 4 чарта применены")

print("\n=== PILOT GOT: only Дашборд ТМ built. Verify in browser then run again for План + МОП ===")
