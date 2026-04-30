"""Compatibility shim for the Sales report contract.

The canonical contract lives in `shared.contracts.sales_report_contract`.
Keep this module import-compatible during migration.
"""

from __future__ import annotations

from shared.contracts.sales_report_contract import (
    SALES_DISPATCH_SEQUENCE,
    SALES_FOLLOWUP_REPORTS,
    SALES_PRIMARY_REPORT,
    SALES_RUNTIME_REPORT_TYPES,
    sales_dispatch_sequence,
    sales_followup_report_types,
)

__all__ = [
    "SALES_DISPATCH_SEQUENCE",
    "SALES_FOLLOWUP_REPORTS",
    "SALES_PRIMARY_REPORT",
    "SALES_RUNTIME_REPORT_TYPES",
    "sales_dispatch_sequence",
    "sales_followup_report_types",
]
