from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cron_refresh.sh"


def test_cron_refresh_script_has_safe_shell_shape() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "flock -n 9" in text
    assert "bitrix-sync-state.sh" in text
    assert "state synced, retrying refresh" in text
    assert "PYTHONPATH=\"$SALES_DASHBOARD_DIR\"" in text
    assert "sales_kpi_dashboard.cli refresh" in text


def test_cron_refresh_script_is_not_dry_run() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "--dry-run" not in text
