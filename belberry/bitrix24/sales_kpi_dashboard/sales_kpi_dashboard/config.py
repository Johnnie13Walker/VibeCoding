from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

OUTPUT_SHEET_ID = "1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE"

WRITEABLE_TABS = {"tm_metrics", "sales_plan", "mop_metrics", "mrr", "sync_log"}
READ_ONLY_TABS = {"Plan", "Plan_MRR"}

DIRECTIONS = ["СППВР", "ИИ", "Аналитика", "Справочник"]

# TODO: заполнить подтверждённым списком из DISCOVERY.md перед Phase 2.
TM_USERS: dict[int, str] = {}
MOP_USERS: dict[int, str] = {}

RECENT_WEEKS = 8

SECRETS_DIR = Path("/Users/pro2kuror/.config/vibecoding/assistant/secrets")
GOOGLE_SA_KEY = SECRETS_DIR / "finance-director-sheets-903611b799c3.json"

STATE_DIR = Path(__file__).parent.parent / "state"
ETL_STATE_PATH = STATE_DIR / "kpi_state.json"

PACKAGE_ROOT = Path(__file__).parent.parent
LOGS_DIR = PACKAGE_ROOT / "logs"
