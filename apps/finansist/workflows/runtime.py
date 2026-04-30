"""Общие adapter-функции для workflow Финансиста."""

from __future__ import annotations

from typing import Any

from apps.finansist import DEFAULT_CONFIG, FinansistAgentError, build_finansist_agent_from_env

WORKFLOW_BY_COMMAND = {
    "get_finance_summary": "finance_summary",
    "get_pnl_analysis": "pnl_analysis",
    "get_cashflow_analysis": "cashflow_analysis",
    "get_expense_structure_analysis": "expense_structure_analysis",
    "get_client_profitability_analysis": "client_profitability_analysis",
    "get_receivables_analysis": "receivables_analysis",
    "get_payables_analysis": "payables_analysis",
    "get_finance_risks": "finance_anomaly_scan",
}


def build_finance_payload(context: dict[str, Any], *, command_name: str) -> dict[str, Any]:
    message = context.get("message") if isinstance(context, dict) else {}
    message_text = str(message.get("text") or "").strip() if isinstance(message, dict) else ""
    message_metrics = dict(message.get("metrics") or {}) if isinstance(message, dict) else {}
    message_sources = list(message.get("sources") or []) if isinstance(message, dict) else []
    message_facts = tuple(message.get("facts") or ()) if isinstance(message, dict) else ()
    message_period_label = str(message.get("period_label") or "").strip() if isinstance(message, dict) else ""
    return {
        "question": message_text,
        "period_label": str(context.get("period_label") or message_period_label or "текущий период"),
        "metrics": dict(context.get("metrics") or message_metrics),
        "sources": list(context.get("sources") or message_sources),
        "facts": tuple(context.get("facts") or message_facts),
        "command_name": command_name,
    }


def run_finansist_command(
    command_name: str,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    workflow_name = WORKFLOW_BY_COMMAND[command_name]
    try:
        agent = build_finansist_agent_from_env()
        result = agent.execute(command_name, build_finance_payload(context, command_name=command_name), context=context)
    except FinansistAgentError as error:
        return {
            "ok": False,
            "workflow": workflow_name,
            "agent_id": DEFAULT_CONFIG.agent_id,
            "text": f"Не удалось выполнить команду Финансиста: {error}",
            "error": str(error),
        }
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "workflow": workflow_name,
            "agent_id": DEFAULT_CONFIG.agent_id,
            "text": f"Критическая ошибка контура Финансист: {error}",
            "error": str(error),
        }

    return {
        "ok": True,
        "workflow": workflow_name,
        "agent_id": DEFAULT_CONFIG.agent_id,
        "text": str(result.get("text") or ""),
        "payload": result.get("payload"),
    }
