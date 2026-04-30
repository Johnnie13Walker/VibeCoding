"""Точка входа агента Финансист."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any, Callable

from .config import COMMAND_ALIASES, DEFAULT_CONFIG, FinansistConfig
from .providers import FinanceSourceProvider
from .schemas.finance import FinanceRequest
from .workflows.analysis import analyze_finance_request


class FinansistAgentError(RuntimeError):
    """Ошибка финансового контура."""


@dataclass(frozen=True)
class FinansistDependencies:
    source_provider: FinanceSourceProvider


class FinansistAgent:
    def __init__(
        self,
        *,
        config: FinansistConfig = DEFAULT_CONFIG,
        dependencies: FinansistDependencies,
    ) -> None:
        self.config = config
        self.dependencies = dependencies
        self.registry = self._build_registry()

    def _build_registry(self) -> dict[str, dict[str, object]]:
        commands = [
            self._make_command("get_finance_summary", "finance_summary"),
            self._make_command("get_pnl_analysis", "pnl_analysis"),
            self._make_command("get_cashflow_analysis", "cashflow_analysis"),
            self._make_command("get_expense_structure_analysis", "expense_structure_analysis"),
            self._make_command("get_client_profitability_analysis", "client_profitability_analysis"),
            self._make_command("get_receivables_analysis", "receivables_analysis"),
            self._make_command("get_payables_analysis", "payables_analysis"),
            self._make_command("get_finance_risks", "finance_anomaly_scan"),
        ]
        registry: dict[str, dict[str, object]] = {}
        for command in commands:
            registry[str(command["name"])] = command
            for alias in command["aliases"]:
                registry[str(alias)] = command
        return registry

    def _make_command(self, name: str, focus: str) -> dict[str, object]:
        return {
            "name": name,
            "aliases": COMMAND_ALIASES.get(name, ()),
            "focus": focus,
            "handler": self._build_handler(focus),
        }

    def _build_handler(self, focus: str) -> Callable[[Any, dict[str, Any] | None], dict[str, Any]]:
        def _handler(payload: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
            prepared = self._normalize_payload(payload, focus=focus, context=context)
            snapshot = self.dependencies.source_provider.build_snapshot(prepared.sources)
            result = analyze_finance_request(prepared, snapshot)
            return {
                "text": result["text"],
                "payload": {
                    **result,
                    "focus": focus,
                    "agent_id": self.config.agent_id,
                },
            }

        return _handler

    def _normalize_payload(
        self,
        payload: Any,
        *,
        focus: str,
        context: dict[str, Any] | None,
    ) -> FinanceRequest:
        if isinstance(payload, FinanceRequest):
            return payload

        raw = dict(payload or {}) if isinstance(payload, dict) else {}
        question = str(raw.get("question") or raw.get("text") or "").strip()
        period_label = str(raw.get("period_label") or "текущий период").strip()
        metrics = dict(raw.get("metrics") or {})
        facts = tuple(str(item).strip() for item in (raw.get("facts") or ()) if str(item).strip())
        sources_from_payload = list(raw.get("sources") or ())
        text_from_context = ""
        if isinstance(context, dict):
            message = context.get("message") or {}
            if isinstance(message, dict):
                text_from_context = str(message.get("text") or "").strip()
            extra_sources = context.get("sources")
            if isinstance(extra_sources, list):
                sources_from_payload.extend(extra_sources)
        sources_from_payload.extend(self.dependencies.source_provider.extract_urls(question or text_from_context))
        return FinanceRequest(
            question=question or text_from_context or "Финансовый запрос без уточненного текста.",
            focus=focus,
            period_label=period_label,
            metrics=metrics,
            sources=tuple(sources_from_payload),
            facts=facts,
        )

    def execute(
        self,
        command_name: str,
        payload: Any,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        command = self.registry.get(str(command_name))
        if command is None:
            raise FinansistAgentError(f"Команда {command_name} не зарегистрирована.")
        handler = command["handler"]
        return handler(payload, context)


def build_finansist_agent_from_env(env_data: dict[str, str] | None = None) -> FinansistAgent:
    env_payload = dict(env_data or os.environ)
    dependencies = FinansistDependencies(
        source_provider=FinanceSourceProvider(env_data=env_payload),
    )
    return FinansistAgent(
        config=DEFAULT_CONFIG,
        dependencies=dependencies,
    )


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finansist Agent")
    parser.add_argument(
        "--command",
        default="get_finance_summary",
        choices=tuple(COMMAND_ALIASES.keys()),
        help="Команда контура Финансист",
    )
    parser.add_argument(
        "--payload-json",
        default="{}",
        help="JSON payload для финансового запроса",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    payload = json.loads(args.payload_json or "{}")
    agent = build_finansist_agent_from_env()
    result = agent.execute(args.command, payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
