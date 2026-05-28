"""Форматирование KPI-ячеек: рубли с разделителем, проценты."""
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE"
creds = Credentials.from_service_account_file(KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID, fields="sheets.properties").execute()
tabs = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
DTM, DPLAN, DMOP = tabs["Дашборд ТМ"], tabs["Дашборд План"], tabs["Дашборд МОП"]

RUB_FMT = '#,##0" ₽"'  # рубли с пробелом-тысячником, без копеек
PCT_FMT = '0%'
NUM_FMT = '#,##0.0'  # обычное число с 1 знаком

def cell_format(sheet_id, row, col_start, col_end, pattern, ftype="NUMBER"):
    return {"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": row, "endRowIndex": row + 1,
                  "startColumnIndex": col_start, "endColumnIndex": col_end},
        "cell": {"userEnteredFormat": {"numberFormat": {"type": ftype, "pattern": pattern}}},
        "fields": "userEnteredFormat.numberFormat",
    }}

# Также расширю колонку D (Прогноз на конец месяца) до 200 px чтобы текст не обрезался
def widen_col(sheet_id, col_idx, px=200):
    return {"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": col_idx, "endIndex": col_idx + 1},
        "properties": {"pixelSize": px}, "fields": "pixelSize",
    }}

requests = []

# Дашборд ТМ — A4 (факт), B4 (план), C4 (% плана), D4 (прогноз), E4 (конверсия)
# A B D — целые числа; C — процент; E — уже строка с %
requests.append(cell_format(DTM, 3, 0, 2, NUM_FMT))
requests.append(cell_format(DTM, 3, 2, 3, PCT_FMT, "PERCENT"))
requests.append(cell_format(DTM, 3, 3, 4, NUM_FMT))

# Дашборд План — A B D E — рубли, C — процент
requests.append(cell_format(DPLAN, 3, 0, 2, RUB_FMT))
requests.append(cell_format(DPLAN, 3, 2, 3, PCT_FMT, "PERCENT"))
requests.append(cell_format(DPLAN, 3, 3, 5, RUB_FMT))
# Расширить колонки A-E на дашборде План до 180 px
for col in range(5):
    requests.append(widen_col(DPLAN, col, 180))
# Расширить колонку D отдельно до 220 (текст "Прогноз на конец месяца" длинный)
requests.append(widen_col(DPLAN, 3, 220))

# Helper-секция J:R на дашборде План — сделать менее визуально заметной (серый текст)
requests.append({"repeatCell": {
    "range": {"sheetId": DPLAN, "startRowIndex": 5, "endRowIndex": 20, "startColumnIndex": 9, "endColumnIndex": 18},
    "cell": {"userEnteredFormat": {
        "textFormat": {"foregroundColor": {"red": 0.6, "green": 0.6, "blue": 0.6}},
    }},
    "fields": "userEnteredFormat.textFormat.foregroundColor",
}})
# Helper-заголовок (row 6) — поменьше шрифт + курсив
requests.append({"repeatCell": {
    "range": {"sheetId": DPLAN, "startRowIndex": 5, "endRowIndex": 6, "startColumnIndex": 9, "endColumnIndex": 18},
    "cell": {"userEnteredFormat": {
        "textFormat": {"italic": True, "fontSize": 9, "foregroundColor": {"red": 0.5, "green": 0.5, "blue": 0.5}},
    }},
    "fields": "userEnteredFormat.textFormat",
}})

# Также: number-format для helper-данных (рубли в J7:K17 и в M:N, простое число в Q)
requests.append(cell_format(DPLAN, 6, 10, 11, RUB_FMT))  # K — выручка
# helper строки могут раздуваться вниз — применю до строки 20
requests.append({"repeatCell": {
    "range": {"sheetId": DPLAN, "startRowIndex": 6, "endRowIndex": 20, "startColumnIndex": 10, "endColumnIndex": 11},
    "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": RUB_FMT}}},
    "fields": "userEnteredFormat.numberFormat",
}})
requests.append({"repeatCell": {
    "range": {"sheetId": DPLAN, "startRowIndex": 6, "endRowIndex": 20, "startColumnIndex": 13, "endColumnIndex": 15},
    "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": RUB_FMT}}},
    "fields": "userEnteredFormat.numberFormat",
}})

svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": requests}).execute()
print(f"Применено {len(requests)} format-requests")

# Финальная проверка
print("\n=== Дашборд План A3:E4 (после форматирования) ===")
for r in svc.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="'Дашборд План'!A3:E4", valueRenderOption="FORMATTED_VALUE").execute().get("values", []):
    print(" ", r)
print("\n=== Дашборд ТМ A3:E4 ===")
for r in svc.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="'Дашборд ТМ'!A3:E4", valueRenderOption="FORMATTED_VALUE").execute().get("values", []):
    print(" ", r)
