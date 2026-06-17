"""Workflow общей финансовой сводки."""

from __future__ import annotations

from typing import Any

from apps.finansist.workflows.runtime import run_finansist_command


def run(context: dict[str, Any]) -> dict[str, Any]:
    return run_finansist_command("get_finance_summary", context=context)
