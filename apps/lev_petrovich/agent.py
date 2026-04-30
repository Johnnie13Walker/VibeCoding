"""Канонический entrypoint runtime Льва Петровича."""

from __future__ import annotations

from agents.sales_agent.sales_agent import (
    SalesAgent,
    SalesAgentError,
    build_sales_report_from_env,
    main as sales_main,
)

LevPetrovichAgent = SalesAgent
LevPetrovichAgentError = SalesAgentError


def main(argv: list[str] | None = None) -> int:
    return sales_main(argv)
