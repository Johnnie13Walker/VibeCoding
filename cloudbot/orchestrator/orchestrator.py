"""Центральный orchestrator: принимает message и вызывает workflow."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from cloudbot.orchestrator.context import build_context
from cloudbot.orchestrator.router import select_workflow

WORKFLOW_FILE_MAP = {
    "day_briefing": "day_briefing.py",
    "meetings_summary": "meetings_summary.py",
    "tasks_summary": "tasks_summary.py",
    "larisa_weather": "larisa_weather.py",
    "larisa_search": "larisa_search.py",
    "larisa_plan_day": "larisa_plan_day.py",
    "larisa_content_topics": "larisa_content_topics.py",
    "larisa_content_post": "larisa_content_post.py",
    "whoop_report": "whoop_report.py",
    "system_health": "system_health.py",
    "self_healing": "self_healing.py",
    "sales_brief": "sales_brief.py",
    "finance_summary": "finance_summary.py",
    "pnl_analysis": "pnl_analysis.py",
    "cashflow_analysis": "cashflow_analysis.py",
    "expense_structure_analysis": "expense_structure_analysis.py",
    "client_profitability_analysis": "client_profitability_analysis.py",
    "receivables_analysis": "receivables_analysis.py",
    "payables_analysis": "payables_analysis.py",
    "finance_anomaly_scan": "finance_anomaly_scan.py",
    "bitrix_check": "bitrix_check.py",
}


def _load_module_from_file(module_name: str, file_path: Path) -> ModuleType:
    spec = spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось загрузить модуль: {file_path}")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_workflow_runner(workflow_name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    workflow_file = WORKFLOW_FILE_MAP.get(workflow_name)
    if not workflow_file:
        raise KeyError(f"Неизвестный workflow: {workflow_name}")

    workflows_dir = Path(__file__).resolve().parents[1] / "workflows"
    module_path = workflows_dir / workflow_file
    module = _load_module_from_file(f"cloudbot.workflow.{workflow_name}", module_path)

    run_fn = getattr(module, "run", None)
    if not callable(run_fn):
        raise RuntimeError(f"В workflow {workflow_name} нет функции run")
    return run_fn


def _run_workflow(context: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    workflow_name = select_workflow(message)
    runner = _resolve_workflow_runner(workflow_name)
    result = runner(context)

    if not isinstance(result, dict):
        result = {"ok": True, "data": result}

    result.setdefault("workflow", workflow_name)
    result.setdefault("ok", True)
    return result


def handle_incoming_message(message: dict[str, Any]) -> dict[str, Any]:
    context = build_context(message)
    return _run_workflow(context, message)
