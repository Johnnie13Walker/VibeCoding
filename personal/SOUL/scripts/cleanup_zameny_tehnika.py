#!/usr/bin/env python3
"""Удалить из листа `Замены_техника` строки, где альт-цена = 0 (т.е. без апгрейда).
Остаются только 7 позиций с альт/премиум + шапка + ИТОГО.
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

# Получаем sheetId
meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
sheet_id = next(s["properties"]["sheetId"] for s in meta["sheets"] if s["properties"]["title"] == SHEET_NAME)

# Читаем строки A2:E19 (без шапки, без ИТОГО) — индекс E = 4
vals = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range=f"{SHEET_NAME}!A2:E19",
    valueRenderOption="UNFORMATTED_VALUE"
).execute().get("values", [])

# Определим строки на удаление: где E (col index 4) == 0 или пусто
# Номера строк (1-indexed) на листе: первая строка данных = 2
to_delete = []  # 0-indexed для API
for i, row in enumerate(vals):
    e_val = row[4] if len(row) > 4 else 0
    if not e_val or (isinstance(e_val, (int, float)) and e_val == 0):
        sheet_row_index = i + 1  # 0-based для API: шапка=0, первая строка данных=1
        to_delete.append(sheet_row_index)
        print(f"  Удаляем строку {i+2}: '{row[0][:60]}'")

print(f"\nВсего на удаление: {len(to_delete)} строк")
print(f"Останется: {len(vals) - len(to_delete)} строк данных + шапка + ИТОГО\n")

# Удаляем снизу вверх, чтобы индексы не сдвигались
requests = []
for row_index in sorted(to_delete, reverse=True):
    requests.append({
        "deleteDimension": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": row_index,
                "endIndex": row_index + 1,
            }
        }
    })

if requests:
    svc.spreadsheets().batchUpdate(
        spreadsheetId=SHEET_ID, body={"requests": requests}
    ).execute()
    print(f"✓ Удалено {len(requests)} строк")

# Пересчитаем формулы ИТОГО — теперь данных меньше
# После удаления: 7 строк данных (2-8), ИТОГО — строка 9
new_totals = [
    ("C9", "=SUM(C2:C8)"),
    ("E9", '=SUMIFS(E2:E8;E2:E8;">0")+SUMIFS(C2:C8;E2:E8;"=0")'),
    ("H9", '=SUMIFS(H2:H8;H2:H8;">0")+SUMIFS(C2:C8;H2:H8;"=0")'),
]
data = [{"range": f"{SHEET_NAME}!{c}", "values": [[v]]} for c,v in new_totals]
svc.spreadsheets().values().batchUpdate(
    spreadsheetId=SHEET_ID,
    body={"valueInputOption": "USER_ENTERED", "data": data}
).execute()

# Прочитать финальное состояние
final = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range=f"{SHEET_NAME}!A1:H10",
    valueRenderOption="FORMATTED_VALUE"
).execute().get("values", [])
print("\n=== ФИНАЛЬНОЕ СОСТОЯНИЕ ===")
for i, row in enumerate(final, 1):
    a = row[0] if len(row) > 0 else ""
    c = row[2] if len(row) > 2 else ""
    e = row[4] if len(row) > 4 else ""
    h = row[7] if len(row) > 7 else ""
    print(f"  Row {i}: {a[:35]:<35} | C={c:>12} | E={e:>12} | H={h:>12}")
