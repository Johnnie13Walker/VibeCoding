from datetime import date

from src.promises import compute_promises_loop, evaluate_promises


def test_evaluate_promises_marks_done_by_kp_signal():
    result = evaluate_promises(
        [{"deal_id": 10, "promise": "Отправить КП", "owner": "Семенихин Егор", "deadline": "2026-06-02"}],
        {
            "deals_snapshot": [{"deal_id": 10, "stage": "C10:EXECUTING"}],
            "kp_briefs": [{"deal_id": 10, "item_type": "kp"}],
        },
        {10: "C10:NEW"},
        date(2026, 6, 3),
    )

    assert result["items"][0]["status_key"] == "done"
    assert result["items"][0]["status"] == "✅ выполнено"
    assert set(result["items"][0]["signals"]) == {"стадия изменилась", "КП отправлено"}


def test_evaluate_promises_marks_overdue_without_signals():
    result = evaluate_promises(
        [{"deal_id": 10, "promise": "Созвониться", "owner": "Семенихин Егор", "deadline": "2026-06-02"}],
        {"deals_snapshot": [{"deal_id": 10, "stage": "C10:NEW"}], "kp_briefs": []},
        {10: "C10:NEW"},
        date(2026, 6, 3),
    )

    assert result["items"][0]["status_key"] == "overdue"
    assert result["items"][0]["status"] == "❌ просрочено"


class _Cursor:
    """Фейк-курсор: маршрутизирует по тексту SQL (max(report_date)/meetings/snapshot)."""

    def __init__(self, prev_date=None, meetings=None, stages=None):
        self._prev_date = prev_date
        self._meetings = meetings or []
        self._stages = stages or []
        self._mode = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        if "max(report_date)" in sql:
            self._mode = "prev_date"
        elif "FROM meetings" in sql:
            self._mode = "meetings"
        else:
            self._mode = "stages"

    def fetchone(self):
        return (self._prev_date,)

    def fetchall(self):
        return self._meetings if self._mode == "meetings" else self._stages


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def test_compute_promises_loop_gracefully_handles_no_previous_steps():
    # В БД нет прошлого отчёта → фолбэк на рабочий день, встреч нет → мягкая заглушка.
    result = compute_promises_loop(_Conn(_Cursor()), date(2026, 6, 3), {"deals_snapshot": [], "kp_briefs": []})

    assert result["items"] == []
    assert result["message"] == "нет структурных обещаний за предыдущий день"


def test_compute_promises_loop_anchors_to_last_report_date():
    # Якорь «вчера» = реальная дата последнего отчёта из reports (как у дельт),
    # а не вычисленный prev_working_day. 30 мая — пятница перед 2 июня (вт).
    cursor = _Cursor(
        prev_date=date(2026, 5, 30),
        meetings=[(2180, 10, 7, {"next_step": {"what": "Отправить КП", "who": "Семенихин Егор", "deadline": "2026-06-01"}})],
        stages=[(10, "C10:NEW")],
    )
    result = compute_promises_loop(
        _Conn(cursor),
        date(2026, 6, 2),
        {"deals_snapshot": [{"deal_id": 10, "stage": "C10:EXECUTING"}], "kp_briefs": [{"deal_id": 10, "item_type": "kp"}]},
    )

    assert result["previous_date"] == "2026-05-30"
    assert result["items"][0]["promise"] == "Отправить КП"
    assert result["items"][0]["status_key"] == "done"
