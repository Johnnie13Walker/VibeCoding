"""Конфигурация и идентичность агента Финансист."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

MSK_TIMEZONE: Final[str] = "Europe/Moscow"

ALLOWED_SCOPES: Final[tuple[str, ...]] = (
    "finance",
    "management_accounting",
    "cashflow",
    "profitability",
    "google_workspace",
    "bitrix_finance",
    "spreadsheets",
)

BLOCKED_SCOPES: Final[tuple[str, ...]] = (
    "personal_assistant",
    "calendar",
    "weather",
    "news",
    "copywriting",
    "deploy",
    "infra_governance",
)

COMMAND_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "get_finance_summary": ("/finance",),
    "get_pnl_analysis": ("/pnl",),
    "get_cashflow_analysis": ("/cashflow", "/runway"),
    "get_expense_structure_analysis": ("/expenses",),
    "get_client_profitability_analysis": ("/clients-profit",),
    "get_receivables_analysis": ("/ar",),
    "get_payables_analysis": ("/ap",),
    "get_finance_risks": ("/finance-risks",),
}

GOOGLE_CREDENTIAL_ENV_CANDIDATES: Final[tuple[str, ...]] = (
    "GOOGLE_WORKSPACE_CREDENTIALS_JSON",
    "GOOGLE_DRIVE_CREDENTIALS_JSON",
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "GOOGLE_OAUTH_CREDENTIALS_JSON",
)

GOOGLE_SOURCE_CATALOG_ENV_CANDIDATES: Final[tuple[str, ...]] = (
    "FINANSIST_SOURCE_CATALOG_JSON",
    "FINANCE_SOURCE_CATALOG_JSON",
    "GOOGLE_WORKSPACE_SOURCE_CATALOG_JSON",
)


@dataclass(frozen=True)
class FinansistConfig:
    agent_id: str = "finansist"
    display_name: str = "Финансист"
    timezone: str = MSK_TIMEZONE
    allowed_scopes: tuple[str, ...] = ALLOWED_SCOPES
    blocked_scopes: tuple[str, ...] = BLOCKED_SCOPES
    google_credential_env_candidates: tuple[str, ...] = GOOGLE_CREDENTIAL_ENV_CANDIDATES
    source_catalog_env_candidates: tuple[str, ...] = GOOGLE_SOURCE_CATALOG_ENV_CANDIDATES


DEFAULT_CONFIG = FinansistConfig()
