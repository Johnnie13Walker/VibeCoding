from datetime import date

from crm_company_enrich.stages import telemarketing_stuck_alerts as stage


class FakeBitrix:
    def __init__(self, deals):
        self.deals = deals

    def list_deals_by_stages(self, *, category_id, stage_ids, closed, select):
        return [
            deal
            for deal in self.deals
            if deal.get("STAGE_ID") in stage_ids and str(deal.get("CLOSED")) == closed
        ]


def test_find_stuck_preparation_returns_old_deals():
    bx = FakeBitrix([
        {"ID": "1", "TITLE": "old", "STAGE_ID": "C50:PREPARATION", "CLOSED": "N", "DATE_MODIFY": "2026-04-01", "ASSIGNED_BY_ID": "2772"}
    ])

    result = stage.find_stuck_preparation(bx, today=date(2026, 5, 17))

    assert len(result) == 1
    assert result[0].reason == "no_communication_21d"


def test_find_stuck_preparation_ignores_recent():
    bx = FakeBitrix([
        {"ID": "1", "STAGE_ID": "C50:PREPARATION", "CLOSED": "N", "DATE_MODIFY": "2026-05-10"}
    ])

    assert stage.find_stuck_preparation(bx, today=date(2026, 5, 17)) == []


def test_find_stuck_wz4kqe_returns_overdue_meetings():
    bx = FakeBitrix([
        {
            "ID": "2",
            "TITLE": "meet",
            "STAGE_ID": "C50:UC_WZ4KQE",
            "CLOSED": "N",
            "UF_CRM_63282B49DC758": "2026-04-20T12:00:00+03:00",
            "ASSIGNED_BY_ID": "2832",
        }
    ])

    result = stage.find_stuck_wz4kqe(bx, today=date(2026, 5, 17))

    assert len(result) == 1
    assert result[0].reason == "meeting_overdue_14d"


def test_find_stuck_wz4kqe_falls_back_to_closedate():
    bx = FakeBitrix([
        {"ID": "2", "TITLE": "meet", "STAGE_ID": "C50:UC_WZ4KQE", "CLOSED": "N", "CLOSEDATE": "2026-04-20", "ASSIGNED_BY_ID": "2832"}
    ])

    result = stage.find_stuck_wz4kqe(bx, today=date(2026, 5, 17))

    assert len(result) == 1


def test_future_closedate_not_stuck():
    bx = FakeBitrix([
        {"ID": "2", "STAGE_ID": "C50:UC_WZ4KQE", "CLOSED": "N", "CLOSEDATE": "2026-05-30"}
    ])

    assert stage.find_stuck_wz4kqe(bx, today=date(2026, 5, 17)) == []


def test_threshold_days_configurable():
    bx = FakeBitrix([
        {"ID": "1", "STAGE_ID": "C50:PREPARATION", "CLOSED": "N", "DATE_MODIFY": "2026-05-01"}
    ])

    assert stage.find_stuck_preparation(bx, threshold_days=10, today=date(2026, 5, 17))
    assert stage.find_stuck_preparation(bx, threshold_days=30, today=date(2026, 5, 17)) == []
