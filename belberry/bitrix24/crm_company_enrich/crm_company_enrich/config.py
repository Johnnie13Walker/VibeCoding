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

# Телемаркетинг: целевая воронка и ротация ответственных.
TELEMARKETING_CATEGORY_ID = "50"
TELEMARKETING_NEW_STAGE_ID = "C50:NEW"
TELEMARKETING_SOURCE_ID = "12"
TELEMARKETING_REFUSAL_STAGE_IDS = frozenset({"C50:APOLOGY", "C50:LOSE", "C50:UC_1S1KIU"})
TELEMARKETING_AUTO_REJECT_SCAN_STAGES = ("C50:UC_1S1KIU", "C50:NEW")
TELEMARKETING_ASSIGNEES = (
    ("2772", "Дарья Исаева"),
    ("2832", "Аркадий Вострецов"),
)

# ID ХОЛОД-причин отказа (enum UF_CRM_1771324790).
HOLD_REASON_BUSINESS_CLOSED = "8538"   # Бизнес закрылся
HOLD_REASON_LOW_REVENUE = "8542"       # Выручка менее 30 млн/год
HOLD_REASON_FIELD = "UF_CRM_1771324790"
HOLD_REASON_COMMENT_FIELD = "UF_CRM_635011179F7DD"
HOLD_MARKER_FLAG_FIELD = "UF_CRM_1733394127643"
HOLD_MARKER_DESC_FIELD = "UF_CRM_1733394206255"

# Статус «Ликвидирована» в company.UF_CRM_ORG_STATUS.
ORG_STATUS_LIQUIDATED = "8852"

# Порог выручки для auto-reject (рубли в год). Если revenue < threshold
# → reason 8542. Если revenue не определён (None/0/пусто) → не reject.
HOLD_REVENUE_THRESHOLD_RUB = int(
    os.environ.get("CCE_HOLD_REVENUE_THRESHOLD_RUB", "30000000")
)

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

def _env_optional_positive_int(name: str, default: int) -> int | None:
    raw = os.environ.get(name, str(default)).strip()
    if raw.isdigit():
        value = int(raw)
        return value if value > 0 else None
    return None


# История BP-конфига:
#   - BP 8618: создавал placeholder-контакты с LAST_NAME="!"
#     (50 шт удалено вручную 2026-05-16). Отвергнут в коммите a20a753.
#   - BP 5614 «Автозаполнение реквизитов по ИНН»: использовался как
#     единичный BP-обогатитель. Заменён на двухступенчатую схему по
#     требованию менеджера 2026-05-17.
#   - Сейчас: два BP, см. CCE_BIZPROC_FIRST_ENTRY_ID и
#     CCE_BIZPROC_UPDATE_ID ниже.
#
# Первичный BP, запускается только при первом внесении реквизитов.
# «Изменение компании и заполнение данных» — мгновенный.
CCE_BIZPROC_FIRST_ENTRY_ID = _env_optional_positive_int("CCE_BIZPROC_FIRST_ENTRY_ID", 5938)

# Основной BP, запускается всегда после реквизитов.
# «Обновление компании и заполнение данных» — около 4 минут, подтягивает
# ОГРН/КПП/адрес/статус/выручку из ЕГРЮЛ/ДаДата.
CCE_BIZPROC_UPDATE_ID = _env_optional_positive_int("CCE_BIZPROC_UPDATE_ID", 8612)

# Пауза между write-запросами (rate-limit для crm.requisite.add).
CCE_APPLY_SLEEP_S = float(os.environ.get("CCE_APPLY_SLEEP_S", "0.5"))

# Гибридный apply: пауза после bizproc.workflow.start перед verify-чтением
# реквизитов (BP подтягивает данные из ЕГРЮЛ — реалистично 5-20 сек).
CCE_BIZPROC_WAIT_S = int(os.environ.get("CCE_BIZPROC_WAIT_S", "15"))

# Гибридный apply: touch компании (crm.company.update COMMENTS+=" ") перед BP.
# По умолчанию выключено: на belberrycrm есть AUTO_EXECUTE=2 шаблон 5938,
# который при любом изменении компании создаёт пустые контакты с LAST_NAME="!".
# Включать только вручную через CCE_COMPANY_TOUCH=1 после исправления BP.
CCE_COMPANY_TOUCH = os.environ.get("CCE_COMPANY_TOUCH", "false").lower() in {"1", "true", "yes", "on", "y"}


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
# «Бренд проекта» (UF_CRM_1737098476975 — строковое, не enum) на основе
# эвристики is_medical_company:
#   True  → "Belberry"     (медорганизация оказывает медуслуги)
#   False → "Acoola Team"  (всё остальное)
# Default TRUE. Disable через CCE_APPLY_SET_BRAND=0/false.
#
# История: ранее использовалось enum-поле UF_CRM_684FE59BA3C8C (2444/2442),
# но UI карточки компании читает именно это строковое поле, которое
# BP 5614 заполняет автоматически из ЕГРЮЛ. Сменили на правильное.
UF_BRAND_FIELD = "UF_CRM_1737098476975"
UF_BRAND_BELBERRY = "Belberry"
UF_BRAND_ACOOLA = "Acoola Team"
CCE_APPLY_SET_BRAND = _env_bool("CCE_APPLY_SET_BRAND", default=True)
COMPANY_UF_RUSPROFILE_CHECKO_URL = "UF_CRM_RUSPROFILE_CHECKO_URL"  # Ссылка на Rusprofile / Checko
COMPANY_UF_ORGANIZATION_STATUS = "UF_CRM_ORG_STATUS"  # Статус организации (enum)
COMPANY_ORGANIZATION_STATUS_ENUM = {
    "Действующая": "8850",
    "Ликвидирована": "8852",
}

# Поля сделки, которые зеркалируются из карточки компании после обогащения.
# Это отдельная стадия, потому что crm.requisite/BP наполняют company-level
# данные, а карточка сделки не всегда подтягивает их сама.
DEAL_UF_SITE_PRIMARY = "UF_CRM_69E8AB2E0715A"      # Сайт клиента 1
DEAL_UF_SITE_MULTI = "UF_CRM_1776434217"           # Сайт клиента
DEAL_UF_BRAND_PROJECT = "UF_CRM_1721661506"        # Бренд проекта (enum)
DEAL_UF_CITY = "UF_CRM_5FB3854A1EDBC"              # Город
DEAL_UF_INN = "UF_CRM_67B35193A09DE"               # ИНН
DEAL_UF_REVENUE_TEXT = "UF_CRM_5E79DD26CB010"      # Оборот компании (строка)
DEAL_UF_REVENUE_MONEY = "UF_CRM_67B35193BAFB4"     # Оборот компании (деньги)
DEAL_UF_REVENUE_NUMBER = "UF_CRM_1774971054"       # Оборот компании (число)
DEAL_UF_INDUSTRY = "UF_CRM_6179712C57A4D"          # Сфера деятельности (enum)
DEAL_UF_RUSPROFILE_URL = "UF_CRM_1772384612740"    # Ссылка на руспрофиль

# Значения enum в сделке.
DEAL_BRAND_ENUM = {
    UF_BRAND_BELBERRY: "1000",
    UF_BRAND_ACOOLA: "1820",
}
DEAL_INDUSTRY_ENUM = {
    "E-commerce": "456",
    "Медицина": "434",
    "Туризм, отдых, путешествия": "460",
    "Услуги для бизнеса": "498",
    "Другое": "2122",
}

# Значения стандартного поля компании INDUSTRY.
COMPANY_INDUSTRY_STATUS = {
    "E-commerce": "UC_QOXULA",
    "Медицина": "UC_0M5893",
    "Туризм, отдых, путешествия": "UC_5ZP2PO",
    "Услуги для бизнеса": "UC_LEDS72",
    "Другое": "OTHER",
}
