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
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchall(self):
        return self._rows


class _Conn:
    def cursor(self):
        return _Cursor([])


def test_compute_promises_loop_gracefully_handles_no_previous_steps():
    result = compute_promises_loop(_Conn(), date(2026, 6, 3), {"deals_snapshot": [], "kp_briefs": []})

    assert result["items"] == []
    assert result["message"] == "нет структурных обещаний за предыдущий день"
