"""Фикс формул под локаль ru_RU (разделитель `;` вместо `,`)."""
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE"
creds = Credentials.from_service_account_file(KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

# === Дашборд ТМ — KPI с ; ===
tm_values = [
    [
        "=tm_metrics!G2",
        "=tm_metrics!H2",
        '=IFERROR(tm_metrics!G2/tm_metrics!H2; 0)',
        "=tm_metrics!J2",
        '=tm_metrics!L2&"%"',
    ],
]
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд ТМ'!A4:E4",
    valueInputOption="USER_ENTERED", body={"values": tm_values},
).execute()
print("Дашборд ТМ — KPI формулы фиксированы")

# === Дашборд План — KPI с ; ===
plan_values = [
    [
        '=SUMIFS(sales_plan!D:D; sales_plan!B:B; "integration_summary")',
        '=VLOOKUP("План_общий"; Plan!B:D; 3; FALSE)',
        '=IFERROR(SUMIFS(sales_plan!D:D; sales_plan!B:B; "integration_summary") / VLOOKUP("План_общий"; Plan!B:D; 3; FALSE); 0)',
        '=SUMIFS(sales_plan!F:F; sales_plan!B:B; "integration_summary")',
        '=SUMIFS(sales_plan!G:G; sales_plan!B:B; "integration_summary")',
    ],
]
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд План'!A4:E4",
    valueInputOption="USER_ENTERED", body={"values": plan_values},
).execute()
print("Дашборд План — KPI формулы фиксированы")

# QUERY-helpers (используют ; и кавычки внутри)
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд План'!J7",
    valueInputOption="USER_ENTERED",
    body={"values": [['=QUERY(sales_plan!A:H; "SELECT C, D WHERE B = \'product\' ORDER BY D DESC"; 0)']]},
).execute()
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд План'!M7",
    valueInputOption="USER_ENTERED",
    body={"values": [['=QUERY(sales_plan!A:H; "SELECT C, D, E WHERE B = \'mop\' ORDER BY D DESC"; 0)']]},
).execute()
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд План'!P7",
    valueInputOption="USER_ENTERED",
    body={"values": [['=QUERY(sales_plan!A:H; "SELECT C, D WHERE B = \'meetings_product\' AND D > 0 ORDER BY D DESC"; 0)']]},
).execute()
print("Дашборд План — QUERY-helpers фиксированы")

# === Дашборд МОП — QUERY с ; ===
svc.spreadsheets().values().update(
    spreadsheetId=SHEET_ID, range="'Дашборд МОП'!A4",
    valueInputOption="USER_ENTERED",
    body={"values": [['=QUERY(mop_metrics!A:I; "SELECT C, D, E, F, G, H, I WHERE C IS NOT NULL AND C <> \'employee_name\'"; 0)']]},
).execute()
print("Дашборд МОП — QUERY фиксирован")

# Проверяем результаты
print("\n=== Проверка значений в Дашборд План A4:E4 ===")
vals = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range="'Дашборд План'!A3:E4",
    valueRenderOption="FORMATTED_VALUE",
).execute().get("values", [])
for r in vals: print(" ", r)

print("\n=== Дашборд ТМ A3:E4 ===")
vals = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range="'Дашборд ТМ'!A3:E4",
    valueRenderOption="FORMATTED_VALUE",
).execute().get("values", [])
for r in vals: print(" ", r)

print("\n=== Дашборд План J6:R12 (QUERY-helpers) ===")
vals = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range="'Дашборд План'!J6:R12",
    valueRenderOption="FORMATTED_VALUE",
).execute().get("values", [])
for r in vals: print(" ", r)
