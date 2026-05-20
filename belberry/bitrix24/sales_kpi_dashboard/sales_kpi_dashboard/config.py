from __future__ import annotations

import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

OUTPUT_SHEET_ID = "1LQR4qe3mofrfIS-YY8A8rgtBZdIJ7RpoKg-NytpcBIE"

WRITEABLE_TABS = {"tm_metrics", "sales_plan", "mop_metrics", "sync_log"}
READ_ONLY_TABS = {"Plan", "Plan_MRR"}

# Smart-process «Встречи» (entityTypeId=1048).
SP_MEETING_ENTITY_TYPE_ID = 1048
SP_MEETING_SUCCESS_STAGE_ID = "DT1048_24:SUCCESS"
# UF-поле «Дата встречи» в SP 1048. Имя автогенерировано Bitrix.
SP_MEETING_DATE_FIELD = "ufCrm16_1751009238"

# Smart-process «КП».
SP_KP_ENTITY_TYPE_ID = 1106
SP_KP_SENT_STAGE_ID = "DT1106_54:SUCCESS"

# Smart-process «Договор».
SP_CONTRACT_ENTITY_TYPE_ID = 1110
SP_CONTRACT_SIGNED_STAGE_ID = "DT1110_56:SUCCESS"

SHEET_TAB_TITLES = {
    "Plan": "Plan",
    "tm_metrics": "tm_metrics",
    "sales_plan": "sales_plan",
    "mop_metrics": "mop_metrics",
    "sync_log": "sync_log",
}

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
GOOGLE_SA_KEY = Path(
    os.environ.get(
        "GOOGLE_SA_KEY",
        SECRETS_DIR / "finance-director-sheets-903611b799c3.json",
    )
)

STATE_DIR = Path(__file__).parent.parent / "state"
ETL_STATE_PATH = STATE_DIR / "kpi_state.json"

PACKAGE_ROOT = Path(__file__).parent.parent
LOGS_DIR = PACKAGE_ROOT / "logs"
