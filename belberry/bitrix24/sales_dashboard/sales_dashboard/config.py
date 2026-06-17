"""Конфигурация sales_dashboard."""
from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

# ---------- Bitrix ----------
PORTAL_DOMAIN = "belberrycrm.bitrix24.ru"
STATE_PATH = Path(
    "/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json"
)
SYNC_SCRIPT = Path(
    "/Users/pro2kuror/Desktop/VibeCoding/shared/scripts/bitrix-sync-state.sh"
)

# Воронки, которые включаем в дашборд.
# Пустой список = все воронки. Числа = CATEGORY_ID из crm.dealcategory.list.
DEAL_CATEGORIES: list[int] = []  # [28, 50, 38] если нужно ограничить

# ---------- Google ----------
SERVICE_ACCOUNT_JSON = Path(
    "/Users/pro2kuror/.config/vibecoding/assistant/secrets/"
    "finance-director-sheets-903611b799c3.json"
)

# Целевой Google Sheet с raw-данными для Looker Studio.
# Чистый dedicated Sheet, расшарен на сервисник как Editor.
SHEET_ID = "1W11eS3q4ft_iCMECqpQZ4x_81GAeoBKE1Fx9EtXf3f8"

# Названия вкладок. Каждая = отдельный data source в Looker Studio.
TAB_DEALS = "deals"
TAB_CALLS = "calls"
TAB_USERS = "users"
TAB_STAGES = "stages"
TAB_CATEGORIES = "categories"
TAB_DAILY = "daily_metrics"
TAB_MANAGER_KPI = "manager_kpi"
TAB_SYNC_LOG = "sync_log"

# ---------- ETL ----------
# Сколько дней истории грузить при первом запуске (full reload).
INITIAL_BACKFILL_DAYS = 30  # деалы — 30 дней для первого smoke. После — поднять до 90.
INITIAL_BACKFILL_CALLS_DAYS = 7  # звонки — 7 дней (их сильно больше)
# При инкрементальном запуске — окно для перепросмотра обновлённых записей.
INCREMENTAL_LOOKBACK_HOURS = 2

# ---------- Paths ----------
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # belberry/bitrix24/sales_dashboard
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "sales_dashboard.csv"
STATE_DIR = PROJECT_ROOT / "state"
STATE_DIR.mkdir(exist_ok=True)
ETL_STATE_PATH = STATE_DIR / "etl_state.json"
USER_SYNC_STATE_PATH = STATE_DIR / "user_sync_state.json"

# ---------- Rate limit ----------
RATE_LIMIT_SLEEP_S = 0.08

# ---------- Timezone ----------
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
