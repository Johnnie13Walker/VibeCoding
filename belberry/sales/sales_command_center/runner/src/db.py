import os
import re
from collections.abc import Sequence
from typing import Any

import psycopg

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def connect(dsn: str | None = None):
    return psycopg.connect(dsn or os.environ["DATABASE_URL"])


def _quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier}")
    return f'"{identifier}"'


def build_upsert_sql(
    table: str,
    columns: Sequence[str],
    conflict_cols: Sequence[str],
    update_cols: Sequence[str],
) -> str:
    if not columns:
        raise ValueError("columns must not be empty")
    if not conflict_cols:
        raise ValueError("conflict_cols must not be empty")
    if not update_cols:
        raise ValueError("update_cols must not be empty")

    quoted_table = _quote_identifier(table)
    quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    quoted_conflict = ", ".join(_quote_identifier(column) for column in conflict_cols)
    assignments = ", ".join(
        f"{_quote_identifier(column)} = EXCLUDED.{_quote_identifier(column)}"
        for column in update_cols
    )

    return (
        f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders}) "
        f"ON CONFLICT ({quoted_conflict}) DO UPDATE SET {assignments}"
    )


def upsert(
    conn,
    table: str,
    rows: list[dict[str, Any]],
    conflict_cols: list[str],
    update_cols: list[str],
) -> int:
    if not rows:
        return 0

    columns = list(rows[0].keys())
    sql_text = build_upsert_sql(table, columns, conflict_cols, update_cols)
    values = [tuple(row[column] for column in columns) for row in rows]

    with conn.cursor() as cursor:
        cursor.executemany(sql_text, values)

    return len(rows)
