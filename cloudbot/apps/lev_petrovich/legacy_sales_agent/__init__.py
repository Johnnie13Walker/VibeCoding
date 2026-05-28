"""Legacy compatibility package для runtime Льва Петровича."""

from __future__ import annotations

__all__ = [
    "SalesAgent",
    "SalesAgentError",
    "build_sales_report_from_env",
    "main",
]


def __getattr__(name: str):
    if name in {"SalesAgent", "SalesAgentError", "build_sales_report_from_env", "main"}:
        from .sales_agent import SalesAgent, SalesAgentError, build_sales_report_from_env, main

        return {
            "SalesAgent": SalesAgent,
            "SalesAgentError": SalesAgentError,
            "build_sales_report_from_env": build_sales_report_from_env,
            "main": main,
        }[name]
    raise AttributeError(name)
