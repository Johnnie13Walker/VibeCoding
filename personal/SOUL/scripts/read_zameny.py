#!/usr/bin/env python3
"""Read current state of Замены sheet."""
import json
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1cXhvMVjCTb3JREUeKZhy1cxF544fpegW0s-JINLlQTs"
RANGE = "Замены!A1:H30"

creds = Credentials.from_service_account_file(
    KEY, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
)
svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

# Values (formatted) для отображения
vals = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range=RANGE,
    valueRenderOption="FORMATTED_VALUE"
).execute().get("values", [])

# Formulas — чтобы достать URL из =HYPERLINK
forms = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range=RANGE,
    valueRenderOption="FORMULA"
).execute().get("values", [])

print(json.dumps({"values": vals, "formulas": forms}, ensure_ascii=False, indent=2))
