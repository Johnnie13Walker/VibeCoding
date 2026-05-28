"""Команда списка задач."""

from __future__ import annotations

from ..config import COMMAND_ALIASES
from ..formatters.telegram_tasks import format_telegram_tasks
from ..workflows.tasks import TasksWorkflowDeps, run_tasks_workflow


def build_command(deps: TasksWorkflowDeps) -> dict[str, object]:
    def handler(payload: dict[str, str], context: dict[str, object] | None = None) -> dict[str, object]:
        result = run_tasks_workflow(date_msk=str(payload.get("date_msk") or ""), deps=deps)
        snapshot = result["snapshot"]
        return {
            "text": format_telegram_tasks(snapshot),
            "payload": result,
        }

    return {
        "name": "get_tasks",
        "aliases": COMMAND_ALIASES["get_tasks"],
        "handler": handler,
    }
