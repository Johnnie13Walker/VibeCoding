from __future__ import annotations

import logging
from collections.abc import Sequence

from sales_dashboard.sheets_client import SheetsClient

from .config import GOOGLE_SA_KEY, OUTPUT_SHEET_ID, READ_ONLY_TABS, WRITEABLE_TABS

logger = logging.getLogger(__name__)


class SheetsWriter:
    def __init__(self, client: SheetsClient | None = None):
        self.client = client or SheetsClient(OUTPUT_SHEET_ID, GOOGLE_SA_KEY)

    def write_tab(self, tab_name: str, rows: Sequence[Sequence[object]]) -> None:
        if tab_name in READ_ONLY_TABS:
            raise ValueError(f"tab '{tab_name}' read-only, не трогать руками пользователя")
        if tab_name not in WRITEABLE_TABS:
            logger.warning("tab '%s' не входит в WRITEABLE_TABS, пишем для гибкости", tab_name)

        values = [list(row) for row in rows]
        header = values[0] if values else []
        body = values[1:] if values else []
        self.client.replace_tab(tab_name, header, body)
