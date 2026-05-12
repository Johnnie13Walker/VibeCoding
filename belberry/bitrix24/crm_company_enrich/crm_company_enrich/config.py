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
TAB_BACKUP = "enrich_backup"         # backup snapshot перед write-операциями apply

# Вкладки, которые мы только читаем (deal-merge статус)
TAB_DEAL_MERGE_GROUPS = "merge_groups"

# Statuses, при которых компания «занята» в deal-merge — write-операции пропускаем
DEAL_MERGE_ACTIVE_STATUSES = frozenset({"APPROVED", "TRANSFERRED", "MERGED", "MANUAL"})

# Portal
PORTAL_DOMAIN = "belberrycrm.bitrix24.ru"

# Web fetch behaviour
ENRICH_HTTP_TIMEOUT_S = float(os.environ.get("CCE_ENRICH_HTTP_TIMEOUT_S", "10"))
ENRICH_HTTP_DELAY_S = float(os.environ.get("CCE_ENRICH_HTTP_DELAY_S", "1.0"))
ENRICH_HTTP_RETRIES = int(os.environ.get("CCE_ENRICH_HTTP_RETRIES", "3"))
ENRICH_USER_AGENT = os.environ.get(
    "CCE_ENRICH_USER_AGENT",
    # Полноценный Chrome-like UA: некоторые сайты блокируют явные bot-UA.
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)

# Apply stage tunables
# PRESET_ID реквизита для CREATE_REQ. Стандартный preset «Юридическое лицо» на
# большинстве порталов = 1; меняется через ENV для прогонов на dev-портале.
CCE_PRESET_ID = int(os.environ.get("CCE_PRESET_ID", "1"))

# Bizproc-шаблон, запускаемый после успешного crm.requisite.add. Дефолт 5614
# (belberrycrm portal — «Автозаполнение реквизитов по ИНН, наполнение
# информации лида», doc_type=CCrmDocumentCompany). Переопределяется через
# ENV для других порталов / disable через явное CCE_BIZPROC_TEMPLATE_ID=0
# (или любая не-цифра, например "none").
_bp_raw = os.environ.get("CCE_BIZPROC_TEMPLATE_ID", "").strip()
if _bp_raw.isdigit():
    _bp_val = int(_bp_raw)
    CCE_BIZPROC_TEMPLATE_ID: int | None = _bp_val if _bp_val > 0 else None
elif _bp_raw == "":
    CCE_BIZPROC_TEMPLATE_ID = 5614
else:
    CCE_BIZPROC_TEMPLATE_ID = None

# Пауза между write-запросами (rate-limit для crm.requisite.add).
CCE_APPLY_SLEEP_S = float(os.environ.get("CCE_APPLY_SLEEP_S", "0.5"))

# Гибридный apply: пауза после bizproc.workflow.start перед verify-чтением
# реквизитов (BP подтягивает данные из ЕГРЮЛ — реалистично 5-20 сек).
CCE_BIZPROC_WAIT_S = int(os.environ.get("CCE_BIZPROC_WAIT_S", "15"))

# Гибридный apply: touch компании (crm.company.update COMMENTS+=" ") перед BP
# чтобы триггернуть DATE_MODIFY и AUTO_EXECUTE=2 шаблоны. Можно отключить
# если на портале явный bizproc.workflow.start сам по себе работает.
CCE_COMPANY_TOUCH = os.environ.get("CCE_COMPANY_TOUCH", "true").lower() in {"1", "true", "yes", "on", "y"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "y"}


# Записывать ли RQ_COMPANY_NAME_FULL в payload crm.requisite.add. По умолчанию
# FALSE — после post-mortem с Ecodent (HTML-title бренда вместо юр.названия)
# мы не доверяем enrich-сорсам для юр.названия. Bitrix-bizproc / ручной ввод
# подтянет название из ЕГРЮЛ.
CCE_WRITE_NAME_FULL = _env_bool("CCE_WRITE_NAME_FULL", default=False)

# Hybrid apply: после успешного verify_enriched=True удалить наш technical
# INN-only реквизит (созданный crm.requisite.add перед BP), оставив
# BP-обогащённый дубликат с ОГРН/КПП. По умолчанию TRUE — без cleanup в UI
# компании окажется два реквизита.
CCE_APPLY_CLEANUP_DUPLICATE = _env_bool("CCE_APPLY_CLEANUP_DUPLICATE", default=True)

# Brand auto-set: после успешного crm.requisite.add выставляем UF поле
# «Бренд проекта» (UF_CRM_684FE59BA3C8C) на основе эвристики
# is_medical_company:
#   True  → 2444 (Belberry, медицинский сегмент)
#   False → 2442 (Acoola Team, всё остальное)
# Default TRUE. Disable через CCE_APPLY_SET_BRAND=0/false.
UF_BRAND_FIELD = "UF_CRM_684FE59BA3C8C"
UF_BRAND_BELBERRY_ID = "2444"
UF_BRAND_ACOOLA_ID = "2442"
CCE_APPLY_SET_BRAND = _env_bool("CCE_APPLY_SET_BRAND", default=True)
