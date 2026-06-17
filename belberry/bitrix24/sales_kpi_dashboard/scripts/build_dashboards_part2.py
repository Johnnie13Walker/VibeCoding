"""Дополнить дашборды: Дашборд План + Дашборд МОП."""
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE"

creds = Credentials.from_service_account_file(KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID, fields="sheets.properties").execute()
tabs = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}

TM_ID = tabs["tm_metrics"]
SP_ID = tabs["sales_plan"]
MOP_ID = tabs["mop_metrics"]
PLAN_ID = tabs["Plan"]
DPLAN_ID = tabs["Дашборд План"]
DMOP_ID = tabs["Дашборд МОП"]


def header_title_format(sheet_id, text, cols=8, font_size=16, color=(0.85, 0.93, 0.97)):
    return [
        {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": cols}, "mergeType": "MERGE_ALL"}},
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": cols},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": color[0], "green": color[1], "blue": color[2]},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                "textFormat": {"bold": True, "fontSize": font_size},
            }},
            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 50}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": cols},
            "properties": {"pixelSize": 140}, "fields": "pixelSize",
        }},
    ]


def kpi_format(sheet_id, header_row, value_row, cols):
    return [
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": header_row, "endRowIndex": header_row + 1, "startColumnIndex": 0, "endColumnIndex": cols},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                "textFormat": {"bold": True, "fontSize": 10}, "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": value_row, "endRowIndex": value_row + 1, "startColumnIndex": 0, "endColumnIndex": cols},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "fontSize": 18},
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(textFormat,horizontalAlignment,verticalAlignment)",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": value_row, "endIndex": value_row + 1},
            "properties": {"pixelSize": 50}, "fields": "pixelSize",
        }},
    ]


def chart(sheet_id, anchor_row, title, source_sheet_id, x_col, y_cols, start_row, end_row, ctype="COLUMN", width=700, height=320, anchor_col=0):
    return {"addChart": {"chart": {
        "spec": {
            "title": title,
            "basicChart": {
                "chartType": ctype,
                "legendPosition": "BOTTOM_LEGEND",
                "axis": [{"position": "BOTTOM_AXIS"}, {"position": "LEFT_AXIS"}],
                "domains": [{"domain": {"sourceRange": {"sources": [{
                    "sheetId": source_sheet_id,
                    "startRowIndex": start_row, "endRowIndex": end_row,
                    "startColumnIndex": x_col, "endColumnIndex": x_col + 1,
                }]}}}],
                "series": [{
                    "series": {"sourceRange": {"sources": [{
                        "sheetId": source_sheet_id,
                        "startRowIndex": start_row - 1, "endRowIndex": end_row,
                        "startColumnIndex": col, "endColumnIndex": col + 1,
                    }]}},
                    "targetAxis": "LEFT_AXIS",
                } for col in y_cols],
                "headerCount": 1,
            },
        },
        "position": {"overlayPosition": {
            "anchorCell": {"sheetId": sheet_id, "rowIndex": anchor_row, "columnIndex": anchor_col},
            "widthPixels": width, "heightPixels": height,
        }},
    }}}


# === ДАШБОРД ПЛАН ===
# Layout:
# Row 1: заголовок (merge A1:H1)
# Row 3-4: KPI: Факт оплат, План, % плана, Прогноз
# Row 6+: helper-таблицы (далеко справа в J-P) + чарты слева

# 1. Заголовок + KPI ячейки
plan_values = [
    ["Выполнение плана ОП — май 2026", "", "", "", "", "", "", ""],
    [""],
    ["Факт оплат, ₽", "План оплат, ₽", "% выполнения плана", "Прогноз на конец месяца, ₽", "Доп. ожидаем, ₽"],
    [
        '=SUMIFS(sales_plan!D:D,sales_plan!B:B,"integration_summary")',  # факт (payments_received)
        '=VLOOKUP("План_общий",Plan!B:D,3,FALSE)',  # план из Plan!План_общий
        '=IFERROR(SUMIFS(sales_plan!D:D,sales_plan!B:B,"integration_summary")/VLOOKUP("План_общий",Plan!B:D,3,FALSE),0)',  # % плана
        '=SUMIFS(sales_plan!F:F,sales_plan!B:B,"integration_summary")',  # forecast
        '=SUMIFS(sales_plan!G:G,sales_plan!B:B,"integration_summary")',  # trend = доп.ожидаем
    ],
]
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд План'!A1:H4",
    valueInputOption="USER_ENTERED", body={"values": plan_values},
).execute()

# 2. Helper-данные для чартов — в скрытых колонках J:N
# J:K — продукты (имя + fact)
# M:N — МОП (имя + fact + plan)
# P:Q — meetings_product (имя + count)
helper = [
    ["Продукт", "Выручка ₽", "", "МОП", "Факт ₽", "План ₽", "", "Продукт", "Встреч"],
    [
        '=IFERROR(QUERY(sales_plan!A:H,"SELECT C, D WHERE B = \'product\' ORDER BY D DESC",0),"")',
    ],
]
# Используем формулу QUERY с одним вызовом — она сама заполнит несколько строк
# В Sheets QUERY-result разрастается вниз/вправо автоматически
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд План'!J6:R6",
    valueInputOption="USER_ENTERED",
    body={"values": [["Продукт", "Выручка ₽", "", "МОП", "Факт ₽", "План ₽", "", "Продукт", "Встреч"]]},
).execute()
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд План'!J7",
    valueInputOption="USER_ENTERED",
    body={"values": [['=QUERY(sales_plan!A:H,"SELECT C, D WHERE B = \'product\' ORDER BY D DESC",0)']]},
).execute()
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд План'!M7",
    valueInputOption="USER_ENTERED",
    body={"values": [['=QUERY(sales_plan!A:H,"SELECT C, D, E WHERE B = \'mop\' ORDER BY D DESC",0)']]},
).execute()
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд План'!P7",
    valueInputOption="USER_ENTERED",
    body={"values": [['=QUERY(sales_plan!A:H,"SELECT C, D WHERE B = \'meetings_product\' AND D > 0 ORDER BY D DESC",0)']]},
).execute()

# 3. Формат + чарты
# Чарты ссылаются на helper-диапазоны (на самом дашборде, не на sales_plan).
# Это сделано чтобы фильтр work-around.

plan_format = header_title_format(DPLAN_ID, "Выполнение плана", cols=8) + kpi_format(DPLAN_ID, header_row=2, value_row=3, cols=5)
# Скрыть helper-колонки J-R (после построения чартов)
# Но скрывать после addChart — иначе чарт-references могут сломаться. Не скрываем сейчас.

plan_charts = [
    # Чарт «Выручка по продуктам» — bar на helper J7:K17 (10 продуктов + Прочее)
    chart(DPLAN_ID, anchor_row=5, title="Выручка по продуктам, ₽",
          source_sheet_id=DPLAN_ID, x_col=9,  # колонка J
          y_cols=[10],  # колонка K
          start_row=7, end_row=18, ctype="BAR", width=700, height=350, anchor_col=0),
    # Чарт «План vs Факт по МОПам» — на helper M7:O9
    chart(DPLAN_ID, anchor_row=24, title="Выручка по МОПам: Факт vs План, ₽",
          source_sheet_id=DPLAN_ID, x_col=12,  # M
          y_cols=[13, 14],  # N, O
          start_row=7, end_row=10, ctype="COLUMN", width=700, height=320, anchor_col=0),
    # Чарт «Встречи по продуктам»
    chart(DPLAN_ID, anchor_row=41, title="Встреч по продуктам",
          source_sheet_id=DPLAN_ID, x_col=15,  # P
          y_cols=[16],  # Q
          start_row=7, end_row=17, ctype="COLUMN", width=700, height=320, anchor_col=0),
]
svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": plan_format + plan_charts}).execute()
print("Дашборд План: KPI + 3 чарта построены")

# === ДАШБОРД МОП ===
# Layout: заголовок + 6 чартов (3×2 сетка), по одной метрике на чарт

mop_header = [
    ["Эффективность по МОПам — май 2026", "", "", "", "", "", "", ""],
    [""],
    ["Менеджер", "Звонки 60с+", "Задач закрыто", "КП выслано", "Первых встреч", "Повторных встреч", "Договоров"],
]
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд МОП'!A1:H3",
    valueInputOption="USER_ENTERED", body={"values": mop_header},
).execute()
# Под header вставим прямые ссылки на mop_metrics (динамически, через QUERY)
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд МОП'!A4",
    valueInputOption="USER_ENTERED",
    body={"values": [['=QUERY(mop_metrics!A:I,"SELECT C, D, E, F, G, H, I WHERE C IS NOT NULL AND C <> \'employee_name\'",0)']]},
).execute()

mop_format = (
    header_title_format(DMOP_ID, "Эффективность", cols=8)
    + [
        # Header сводной таблицы (row 3)
        {"repeatCell": {
            "range": {"sheetId": DMOP_ID, "startRowIndex": 2, "endRowIndex": 3, "startColumnIndex": 0, "endColumnIndex": 7},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                "textFormat": {"bold": True, "fontSize": 10}, "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }},
    ]
)

# 6 чартов на основе mop_metrics. Используем сам mop_metrics (не дашборд-таб), потому что
# фильтра не надо.
# Колонки mop_metrics: 0 date, 1 id, 2 name, 3 calls_60s, 4 tasks, 5 kp, 6 m_first, 7 m_repeat, 8 deals
# Строки: 0=header, 1-3 = МОПы (3 строки после merge PR#33 → Гордиенко+Деговцова+Семенихин)

CHART_W = 480
CHART_H = 280

mop_charts = []
# 2x3 сетка чартов в строках 8+, колонки 0-3 и 4-7
metrics_for_chart = [
    (3, "Звонки 60с+", 8, 0),
    (4, "Задач закрыто", 8, 4),
    (5, "КП выслано", 23, 0),
    (6, "Первых встреч", 23, 4),
    (7, "Повторных встреч", 38, 0),
    (8, "Договоров заключено", 38, 4),
]
for y_col, title, anchor_row, anchor_col in metrics_for_chart:
    mop_charts.append(chart(
        DMOP_ID, anchor_row=anchor_row, title=title,
        source_sheet_id=MOP_ID, x_col=2,  # employee_name
        y_cols=[y_col],
        start_row=2, end_row=5,  # строки 1=Деговцова, 2=Семенихин, 3=Гордиенко (после merge)
        ctype="COLUMN", width=CHART_W, height=CHART_H, anchor_col=anchor_col,
    ))

svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": mop_format + mop_charts}).execute()
print("Дашборд МОП: KPI + 6 чартов построены")

print("\n=== ВСЕ 3 ДАШБОРД-ТАБА ГОТОВЫ ===")
print(f"Открой Output Sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")
print(f"  Дашборд ТМ:    gid={tabs.get('Дашборд ТМ', 'NEW')}")
print(f"  Дашборд План:  gid={DPLAN_ID}")
print(f"  Дашборд МОП:   gid={DMOP_ID}")
