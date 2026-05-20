"""Belberry Sales KPI Dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["__version__"]

__version__ = "0.1.0"

_SIBLING_SALES_DASHBOARD = Path(__file__).resolve().parents[2] / "sales_dashboard"
if _SIBLING_SALES_DASHBOARD.exists() and str(_SIBLING_SALES_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_SIBLING_SALES_DASHBOARD))
