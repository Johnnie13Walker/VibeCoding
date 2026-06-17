"""Workflow Sales Copilot через bridge к live Bitrix runtime."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
BRIDGE_SCRIPT = ROOT_DIR / "scripts" / "run_sales_copilot.py"


def _detect_report_type(context: dict[str, Any]) -> str:
    message = context.get("message") or {}
    command = str(message.get("command") or "").strip().lower()
    if command == "/pipeline":
        return "pipeline"
    if command == "/risks":
        return "risks"
    if command == "/focus-sales":
        return "focus"
    return str(context.get("report_type") or "sales").strip().lower() or "sales"


def _run_bridge_payload(report_type: str, *, date_from: str = "", date_to: str = "") -> dict[str, Any]:
    command = [sys.executable, str(BRIDGE_SCRIPT), "--report", report_type, "--json"]
    if date_from:
        command.extend(["--date-from", date_from])
    if date_to:
        command.extend(["--date-to", date_to])
    completed = subprocess.run(
        command,
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(detail)
    raw = (completed.stdout or "").strip()
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Bridge вернул невалидный JSON: {error}") from error
    if not isinstance(payload, dict):
        raise RuntimeError("Bridge вернул неожиданный формат ответа")
    return payload


def run(context: dict[str, Any]) -> dict[str, Any]:
    report_type = _detect_report_type(context)
    date_from = str(context.get("date_from") or "").strip()
    date_to = str(context.get("date_to") or "").strip()
    try:
        payload = _run_bridge_payload(report_type, date_from=date_from, date_to=date_to)
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "workflow": "sales_brief",
            "report_type": report_type,
            "text": f"Не удалось сформировать sales-отчет: {error}",
            "error": str(error),
        }

    text = str(payload.get("text") or "").strip()
    followup_messages = list(payload.get("followup_messages") or [])
    message_chunks = [text]
    for item in followup_messages:
        followup_text = str(item.get("text") or "").strip()
        if followup_text:
            message_chunks.append(followup_text)

    result = {
        "ok": True,
        "workflow": "sales_brief",
        "report_type": report_type,
        "text": text,
        "parse_mode": str(payload.get("parse_mode") or "HTML") or "HTML",
    }
    if len(message_chunks) > 1:
        result["message_chunks"] = message_chunks

    return result
