from __future__ import annotations

from pathlib import Path

from crm_company_enrich.stages import auto_revive_lose


def test_log_dir_isolated_from_production():
    log_dir_str = str(auto_revive_lose.LOG_DIR)

    assert "Desktop/VibeCoding/belberry/bitrix24/logs" not in log_dir_str


def test_writing_csv_does_not_touch_production():
    prod_path = Path(
        "/Users/pro2kuror/Desktop/VibeCoding/belberry/bitrix24/"
        "logs/auto_revive_lose.csv"
    )
    mtime_before = prod_path.stat().st_mtime if prod_path.exists() else 0
    outcome = auto_revive_lose.ReviveOutcome(
        deal_id="test-deal",
        company_id="test-company",
        old_assignee="2772",
        new_assignee="2832",
        due_date="2026-05-17",
        status="REVIVED",
    )

    auto_revive_lose._append_audit_row(outcome, revive_count=1)

    mtime_after = prod_path.stat().st_mtime if prod_path.exists() else 0
    assert mtime_after == mtime_before
