"""Конфигурация crm_company_enrich.

ВАЖНО: SHEET_ID — тот же, что и у crm_deal_merge: модули обращаются к разным
вкладкам одной таблицы, чтобы deal-merge мог читать `merge_groups` и говорить
с нами через статусы (см. CROSS_MODULE_TABS).
"""
from __future__ import annotations

import os
from pathlib import Path

# Bitrix entity type для company-реквизитов (4 = COMPANY)
ENTITY_TYPE_COMPANY = 4
OWNER_TYPE_COMPANY = "3"  # для timeline / activity если когда-нибудь понадобится

# State и пути (используем те же файлы, что и crm_deal_merge — общая Bitrix-OAuth сессия)
STATE_PATH = Path(
    os.environ.get(
        "CCE_STATE_PATH",
        "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json",
    )
)
SYNC_SCRIPT = Path(
    os.environ.get(
        "CCE_SYNC_SCRIPT",
        "/Users/pro2kuror/Desktop/VibeCoding/shared/scripts/bitrix-sync-state.sh",
    )
)
SERVICE_ACCOUNT_JSON = Path(
    os.environ.get(
        "CCE_SERVICE_ACCOUNT_JSON",
        "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json",
    )
)
LOG_DIR = Path(
    os.environ.get(
        "CCE_LOG_DIR",
        "/Users/pro2kuror/Desktop/VibeCoding/belberry/bitrix24/logs",
    )
)
LOG_PATH = LOG_DIR / "crm_company_enrich.csv"

# Google Sheet — общий с crm_deal_merge
SHEET_ID = os.environ.get(
    "CCE_SHEET_ID",
    "1WaCtF2BeBorGXkZa0a53Bi6T_lKHeZZwQPEO8qIzmFU",
)

# Вкладки этого модуля
TAB_QUEUE = "company_enrich_queue"   # очередь компаний к обогащению
TAB_LOG = "company_enrich_log"       # лог write-операций (для будущих apply/merge)

# Вкладки, которые мы только читаем (deal-merge статус)
TAB_DEAL_MERGE_GROUPS = "merge_groups"

# Statuses, при которых компания «занята» в deal-merge — write-операции пропускаем
DEAL_MERGE_ACTIVE_STATUSES = frozenset({"APPROVED", "TRANSFERRED", "MERGED", "MANUAL"})

# Portal
PORTAL_DOMAIN = "belberrycrm.bitrix24.ru"

# Web fetch behaviour
ENRICH_HTTP_TIMEOUT_S = 10
ENRICH_HTTP_DELAY_S = 1.0
ENRICH_HTTP_RETRIES = 3
ENRICH_USER_AGENT = (
    "Mozilla/5.0 (compatible; belberry-crm-enrich/0.1; "
    "+https://belberrycrm.bitrix24.ru)"
)
