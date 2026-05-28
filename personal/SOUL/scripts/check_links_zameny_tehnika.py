#!/usr/bin/env python3
"""Систематическая проверка всех URL в листе `Замены_техника`:
- HTTP статус
- Признаки in-stock (наличие фразы 'В наличии' / 'Купить' / availability=InStock)
- Признаки бага (категория/коллекция/главная вместо товара)
"""
import warnings, re, subprocess, json
warnings.filterwarnings("ignore", category=FutureWarning)

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

KEY = "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json"
SHEET_ID = "1cXhvMVjCTb3JREUeKZhy1cxF544fpegW0s-JINLlQTs"
SHEET_NAME = "Замены_техника"

creds = Credentials.from_service_account_file(
    KEY, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
)
svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

# Читаем формулы
forms = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID, range=f"{SHEET_NAME}!A1:H10",
    valueRenderOption="FORMULA"
).execute().get("values", [])

# Извлекаем URL из =HYPERLINK
def extract_url(cell):
    if not isinstance(cell, str): return None
    m = re.search(r'=HYPERLINK\("([^"]+)"', cell)
    return m.group(1) if m else None

# Собираем все URL с координатами
links = []
for r_idx, row in enumerate(forms):
    for c_idx, cell in enumerate(row):
        url = extract_url(cell)
        if url:
            col_letter = chr(ord('A') + c_idx)
            links.append((f"{col_letter}{r_idx+1}", url))

print(f"Всего ссылок: {len(links)}\n")

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

results = []
for cell, url in links:
    try:
        r = subprocess.run(
            ["curl", "-sL", "-A", UA, "--max-time", "20", "-o", "-",
             "-w", "\n===HTTP=%{http_code}==="],
            capture_output=True, text=True, timeout=25,
        )
    except subprocess.TimeoutExpired:
        results.append((cell, url, "TIMEOUT", []))
        continue
    # Простой fallback на curl без stdout — читаем только код
    r = subprocess.run(
        ["curl", "-sIL", "-A", UA, "--max-time", "15", "-o", "/dev/null",
         "-w", "%{http_code}|%{url_effective}", url],
        capture_output=True, text=True, timeout=20,
    )
    code, eff_url = (r.stdout.split("|", 1) + [""])[:2]

    # Простая категория-эвристика
    flags = []
    is_category = False
    path = url.lower()
    if any(k in path for k in ["/catalog/", "/category/", "/collections/", "/recommend/"]) and "/product" not in path and "/p/" not in path:
        is_category = True
        flags.append("URL=категория/коллекция (не товар)")
    if path.rstrip('/').endswith(('.ru', '.com', '.shop')) or path.count('/') < 3:
        flags.append("URL=главная или короткий")

    results.append((cell, url, code, flags))

# Выводим
for cell, url, code, flags in results:
    flag_str = " | " + ", ".join(flags) if flags else ""
    short = url[:80] + "..." if len(url) > 80 else url
    print(f"  {cell}: HTTP={code:>4}{flag_str}\n     {short}\n")
