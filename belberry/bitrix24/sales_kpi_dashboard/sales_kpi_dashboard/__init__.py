"""Belberry Sales KPI Dashboard."""

from __future__ import annotations

import sys
import os
from pathlib import Path

__all__ = ["__version__"]

__version__ = "0.1.0"

_SIBLING_SALES_DASHBOARD = Path(__file__).resolve().parents[2] / "sales_dashboard"
if _SIBLING_SALES_DASHBOARD.exists() and str(_SIBLING_SALES_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_SIBLING_SALES_DASHBOARD))

try:
    from sales_dashboard import config as _sales_dashboard_config

    if state_path := os.environ.get("BITRIX_STATE_PATH"):
        _sales_dashboard_config.STATE_PATH = Path(state_path)
    if sync_script := os.environ.get("BITRIX_SYNC_SCRIPT"):
        _sales_dashboard_config.SYNC_SCRIPT = Path(sync_script)
except Exception:
    pass
