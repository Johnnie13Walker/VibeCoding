from __future__ import annotations

from pathlib import Path


def test_cron_refresh_has_lock_log_rotation_audit_and_notify() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "cron_refresh.sh").read_text(encoding="utf-8")

    assert "flock -n 9" in script
    assert "rotate_log_weekly" in script
    assert "empty-companies-refresh" in script
    assert "audit_empty_company_duplicates.py" in script
    assert "notify_telegram.py" in script
    assert "delete_strict_empty_companies" not in script


def test_weekly_cron_runs_in_low_msk_window() -> None:
    cron = Path(__file__).resolve().parents[4] / "deploy" / "cron" / "empty_companies_weekly.cron"
    text = cron.read_text(encoding="utf-8")

    assert "TZ=Europe/Moscow" in text
    assert "30 3 * * 1" in text
    assert "empty_companies_cron.log" in text
