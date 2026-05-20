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


def test_deploy_cron_uses_utc_schedule() -> None:
    cron = (ROOT / "scripts" / "deploy" / "cloudbot-larisa-sales-kpi.cron").read_text(encoding="utf-8")

    assert "0 3,7,11,15 * * * root" in cron
    assert "UTC" in cron
    assert "06:00 МСК" in cron


def test_deploy_wrapper_exports_secret_paths_without_values() -> None:
    wrapper = (ROOT / "scripts" / "deploy" / "cloudbot-larisa-sales-kpi.sh").read_text(encoding="utf-8")

    assert "source /opt/openclaw/.env" in wrapper
    assert "source /etc/openclaw/larisa.env" in wrapper
    assert "LARISA_TELEGRAM_BOT_TOKEN" in wrapper
    assert "GOOGLE_SA_KEY" in wrapper
    assert "81681699" not in wrapper
