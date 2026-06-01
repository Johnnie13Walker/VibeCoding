import os

import pytest

from src.config import ConfigError, load_config
from src.db import build_upsert_sql


def test_load_config_lists_missing_required_env(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ConfigError) as exc_info:
        load_config(required=["DATABASE_URL"])

    message = str(exc_info.value)
    assert "Missing required env vars" in message
    assert "DATABASE_URL" in message


def test_load_config_returns_required_values(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://scc:scc@localhost:5432/scc")

    config = load_config(required=["DATABASE_URL"])

    assert config["DATABASE_URL"] == "postgresql://scc:scc@localhost:5432/scc"


def test_build_upsert_sql_contains_conflict_update_clause():
    sql = build_upsert_sql(
        table="reports",
        columns=["report_date", "status", "html"],
        conflict_cols=["report_date"],
        update_cols=["status", "html"],
    )

    assert "INSERT INTO" in sql
    assert "ON CONFLICT" in sql
    assert "DO UPDATE SET" in sql
    assert '"status" = EXCLUDED."status"' in sql


def test_build_upsert_sql_rejects_unsafe_identifiers():
    with pytest.raises(ValueError):
        build_upsert_sql(
            table="reports; drop table users",
            columns=["report_date"],
            conflict_cols=["report_date"],
            update_cols=["report_date"],
        )
