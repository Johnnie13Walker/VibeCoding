"""Канонический runtime-пакет Льва Петровича."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "LevPetrovichAgent",
    "LevPetrovichAgentError",
    "SalesAgent",
    "SalesAgentError",
    "build_sales_report_from_env",
    "main",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    module = import_module(".agent", __name__)
    return getattr(module, name)
