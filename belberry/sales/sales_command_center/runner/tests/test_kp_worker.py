"""Тесты чистых частей воркера КП (без БД и подпроцессов)."""

from src.kp_worker import PICK_SQL, finish_sql


def test_pick_sql_uses_skip_locked():
    """Конкурентная выборка: два воркера не возьмут одно задание."""
    assert "FOR UPDATE SKIP LOCKED" in PICK_SQL
    assert "status = 'pending'" in PICK_SQL


def test_finish_sql_ready_clears_error():
    sql = finish_sql(True)
    assert "status = 'ready'" in sql and "error = NULL" in sql and "kp_data" in sql


def test_finish_sql_error_keeps_data_untouched():
    sql = finish_sql(False)
    assert "status = 'error'" in sql and "kp_data" not in sql
