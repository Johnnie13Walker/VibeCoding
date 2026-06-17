"""Конфиг модуля. Пути и идентификаторы — через env, с разумными дефолтами для мака."""

import os
from pathlib import Path

# Bitrix OAuth state — sync-скрипт обновляет access_token раз в 1ч.
BITRIX_STATE = Path(
    os.environ.get(
        "BITRIX_STATE_PATH",
        "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json",
    )
)

# Service-account для Google Sheets (см. reference_finance_director_sheets.md).
SA_KEY = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json",
)

# Telegram-бот «Лариса Ивановна» (см. reference_larisa_ivanovna_bot.md).
# Файл с токеном (не сам токен — секрет читается из файла на VPS/маке).
TG_BOT_TOKEN_FILE = os.environ.get("LARISA_TELEGRAM_BOT_TOKEN_FILE", "")
TG_CHAT_ID = os.environ.get("LARISA_TELEGRAM_CHAT_ID", "81681699")

# Куда складывать JSON-дампы и snapshot для расчёта дельты.
DATA_DIR = Path(os.environ.get("EMPTY_CO_DATA_DIR", "/tmp/empty_co"))

# Целевая таблица Sheets — общая с dup_sheet_sync (gid=235411137 «Дубли компаний»).
# Эта вкладка — `gid=1756722113`, заполняется через title.
SHEET_ID = "13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4"
TARGET_TAB = "Пустые компании (скоринг)"
PORTAL_BASE = "https://belberrycrm.bitrix24.ru/crm/company/details"

# UF-поля компании (Бренд/Город/Сайт/Оборот) — см. project_belberry_company_enrich.
UF_BRAND = "UF_CRM_1737098476975"
UF_CITY = "UF_CRM_1584876724"
UF_SITE = "UF_CRM_5DEF838D882A2"
UF_REVENUE = "UF_CRM_1737098549301"
UF_FIELDS = [UF_BRAND, UF_CITY, UF_SITE, UF_REVENUE]
UF_LABELS = ["Бренд", "Город", "Сайт", "Оборот"]

# Колонки выходной таблицы (18, A..R).
COLUMNS = [
    "Компания (название, гиперссылка в Б24)",  # A
    "Score (0-3)",                              # B
    "Safe-to-delete",                           # C
    "Сделок",                                   # D
    "Контактов",                                # E
    "Лидов",                                    # F
    "ИНН",                                      # G
    "UF заполнено",                             # H
    "UF поля",                                  # I
    "Бренд",                                    # J
    "Город",                                    # K
    "Сайт",                                     # L
    "Оборот",                                   # M
    "Ответственный",                            # N
    "Создал",                                   # O
    "Создана",                                  # P
    "Изменена",                                 # Q
    "company_id",                               # R
]
