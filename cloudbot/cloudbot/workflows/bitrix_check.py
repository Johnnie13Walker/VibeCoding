"""Workflow live-диагностики Bitrix через bridge runtime."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
BRIDGE_SCRIPT = ROOT_DIR / "scripts" / "run_sales_copilot.py"


def _run_bridge() -> str:
    completed = subprocess.run(
        [sys.executable, str(BRIDGE_SCRIPT), "--report", "bitrixcheck"],
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(detail)
    return (completed.stdout or "").strip()


def run(context: dict[str, Any]) -> dict[str, Any]:
    try:
        text = _run_bridge()
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "workflow": "bitrix_check",
            "text": f"Не удалось выполнить Bitrix check: {error}",
            "error": str(error),
        }

    return {
        "ok": True,
        "workflow": "bitrix_check",
        "text": text,
    }
