from __future__ import annotations

import re
from pathlib import Path
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

OUTPUT_SHEET_ID = "1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE"

WRITEABLE_TABS = {"tm_metrics", "sales_plan", "mop_metrics", "sync_log"}
READ_ONLY_TABS = {"Plan", "Plan_MRR"}

PRODUCTS: dict[str, int] = {
    "SEO": 7658,
    "PPC": 2,
    "ORM": 6,
    "SMM": 4,
    "WD": 8,
    "Program": 12,
    "Deposit": 19150,
    "WDT": 17918,
    "TB": 7752,
    "AEO": 19134,
}
OTHER_PRODUCT = "Прочее"

TM_POSITION_REGEX = re.compile(r"телемарк", re.IGNORECASE)
MOP_POSITION_REGEX = re.compile(r"менеджер по продаж", re.IGNORECASE)

RECENT_WEEKS = 8

SECRETS_DIR = Path("/Users/pro2kuror/.config/vibecoding/assistant/secrets")
GOOGLE_SA_KEY = SECRETS_DIR / "finance-director-sheets-903611b799c3.json"

STATE_DIR = Path(__file__).parent.parent / "state"
ETL_STATE_PATH = STATE_DIR / "kpi_state.json"

PACKAGE_ROOT = Path(__file__).parent.parent
LOGS_DIR = PACKAGE_ROOT / "logs"
