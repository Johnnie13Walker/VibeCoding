"""Юнит-тесты устойчивости воркера аудита к транзиентным сбоям.

Ядро фикса инцидента 24.06 (OpenAI 429 insufficient_quota похоронил авто-аудит #20584
в error): временные ошибки (квота/лимит/сеть/5xx) и смерть воркера mid-run должны
вести к повтору с backoff, а не к окончательному error. Чистые функции/инварианты —
без БД и без сети."""

from src import audit_worker as aw


class _Err(Exception):
    """Исключение с произвольным status_code, как у LLM/HTTP SDK."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


# ── _is_retryable: что повторяем ──────────────────────────────────────────────
def test_retryable_openai_insufficient_quota():
    # ровно тот текст, что прилетел в инцидент 24.06
    exc = _Err(
        "Error code: 429 - {'error': {'message': 'You exceeded your current quota', "
        "'type': 'insufficient_quota', 'code': 'insufficient_quota'}}",
        status_code=429,
    )
    assert aw._is_retryable(exc) is True


def test_retryable_by_status_code_without_markers():
    # код 503 без текстовых маркеров — всё равно повторяем
    assert aw._is_retryable(_Err("service unavailable upstream", status_code=503)) is True


def test_retryable_rate_limit_and_overloaded_and_timeout():
    for msg in ("Rate limit reached", "Overloaded", "Read timed out", "connection reset by peer"):
        assert aw._is_retryable(_Err(msg)) is True, msg


def test_non_retryable_permanent_errors():
    # ошибки логики/данных — повторять бессмысленно, должны идти в error
    for exc in (
        _Err("invalid api key", status_code=401),
        _Err("KeyError: 'TITLE'"),
        ValueError("malformed json from llm"),
    ):
        assert aw._is_retryable(exc) is False, exc


def test_is_retryable_handles_missing_code_gracefully():
    # status_code = None не должен падать
    assert aw._is_retryable(_Err("boom", status_code=None)) is False


# ── Инварианты политики повторов ──────────────────────────────────────────────
def test_max_attempts_sane_bound():
    # повторов конечное число — битый аудит не крутится вечно
    assert 2 <= aw.MAX_ATTEMPTS <= 10


def test_pick_sql_respects_backoff_and_returns_attempts():
    # свежий (attempts=0) берётся сразу; повторный — только по истечении backoff;
    # PICK обязан возвращать attempts, иначе process_one не посчитает попытку
    assert "attempts = 0" in aw.PICK_SQL
    assert "make_interval(mins => attempts * 5)" in aw.PICK_SQL
    assert "RETURNING id, deal_id, attempts" in aw.PICK_SQL


def test_reaper_requeues_then_fails_within_cap():
    # застрявший collecting сначала возвращается в pending (есть попытки), потом error
    assert "status='pending'" in aw.REAP_REQUEUE_SQL
    assert "attempts + 1 < %s" in aw.REAP_REQUEUE_SQL
    assert "status='error'" in aw.REAP_FAIL_SQL
    assert "attempts + 1 >= %s" in aw.REAP_FAIL_SQL


# ── process_one: транзиентный сбой → повтор, постоянный → error ────────────────
class _FakeConn:
    """Отдаёт одну pending-строку из PICK, копит выполненные UPDATE'ы."""

    def __init__(self, picked_row):
        self._picked = picked_row
        self.executed = []

    def cursor(self):
        conn = self

        class C:
            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                return False

            def execute(self_, sql, params=None):
                if sql is aw.PICK_SQL:
                    self_._row = conn._picked
                else:
                    conn.executed.append((sql, params))

            def fetchone(self_):
                return getattr(self_, "_row", None)

        return C()

    def commit(self):
        pass


def test_process_one_retries_on_transient(monkeypatch):
    monkeypatch.setattr(aw.audit_engine, "audit_deal",
                        lambda *a, **k: (_ for _ in ()).throw(_Err("429 insufficient_quota", status_code=429)))
    conn = _FakeConn((10, 20584, 0))  # audit_id, deal_id, attempts=0
    aw.process_one(conn)
    sqls = [s for s, _ in conn.executed]
    assert aw.RETRY_SQL in sqls and aw.ERR_SQL not in sqls
    # attempts инкрементнут до 1 (первый параметр RETRY_SQL)
    retry_params = next(p for s, p in conn.executed if s is aw.RETRY_SQL)
    assert retry_params[0] == 1


def test_process_one_errors_when_attempts_exhausted(monkeypatch):
    monkeypatch.setattr(aw.audit_engine, "audit_deal",
                        lambda *a, **k: (_ for _ in ()).throw(_Err("429 quota", status_code=429)))
    conn = _FakeConn((10, 20584, aw.MAX_ATTEMPTS - 1))  # последняя попытка
    aw.process_one(conn)
    sqls = [s for s, _ in conn.executed]
    assert aw.ERR_SQL in sqls and aw.RETRY_SQL not in sqls


def test_process_one_errors_immediately_on_permanent(monkeypatch):
    monkeypatch.setattr(aw.audit_engine, "audit_deal",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("bad json")))
    conn = _FakeConn((10, 20584, 0))
    aw.process_one(conn)
    sqls = [s for s, _ in conn.executed]
    assert aw.ERR_SQL in sqls and aw.RETRY_SQL not in sqls
