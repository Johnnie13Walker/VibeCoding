"""Пакет Архитектора OpenClo."""

from __future__ import annotations

__all__ = [
    "AGENT_DIRECTORY",
    "AGENT_CONFIG_PATH",
    "PROMPT_PATH",
]

from pathlib import Path

AGENT_DIRECTORY = Path(__file__).resolve().parent
AGENT_CONFIG_PATH = AGENT_DIRECTORY / "agent.yaml"
PROMPT_PATH = AGENT_DIRECTORY / "prompt.md"
