from __future__ import annotations

import os
import subprocess
import sys

import pytest

from crm_company_merge.config import Config, ConfigError


COMMAND = [sys.executable, "-m", "crm_company_merge.cli"]
STAGES = (
    "discover",
    "inventory",
    "classify",
    "transfer",
    "merge",
    "verify",
    "rollback",
    "status",
    "migrate-pilot",
    "pause",
    "resume",
)


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*COMMAND, *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_help_shows_all_stages() -> None:
    result = run_cli("--help")

    assert result.returncode == 0
    output = result.stdout
    for stage in STAGES:
        assert stage in output


def test_unknown_stage_returns_exit_code_3() -> None:
    result = run_cli("unknown-stage")

    assert result.returncode == 3
    assert "invalid choice" in result.stderr
    assert "unknown-stage" in result.stderr


def test_inventory_requires_limit() -> None:
    result = run_cli("inventory")

    assert result.returncode == 3
    assert "для стадии 'inventory' обязателен флаг --limit N" in result.stderr


def test_verify_reaches_stage_stub() -> None:
    result = run_cli("verify")

    assert result.returncode != 0
    assert "NotImplementedError" in result.stderr
    assert "stage 'verify' not implemented yet" in result.stderr


def test_config_from_env_requires_mandatory_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "BITRIX_STATE_PATH",
        "SHEET_ID",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TZ",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigError, match="BITRIX_STATE_PATH, SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON"):
        Config.from_env()
