from src import team_health


def test_is_sales_rop_includes_mop_and_rop():
    assert team_health.is_sales_rop("Менеджер по продажам") is True
    assert team_health.is_sales_rop("РОП") is True
    assert team_health.is_sales_rop("Руководитель отдела продаж") is True


def test_is_sales_rop_excludes_telemarketing_and_others():
    assert team_health.is_sales_rop("Телемаркетолог") is False
    assert team_health.is_sales_rop("SEO-специалист") is False
    assert team_health.is_sales_rop("Аккаунт-менеджер") is False
    assert team_health.is_sales_rop(None) is False


def test_in_team_includes_tm_and_sales_rop_excludes_others():
    assert team_health.in_team("Менеджер по продажам") is True
    assert team_health.in_team("РОП") is True
    assert team_health.in_team("Телемаркетолог") is True
    assert team_health.in_team("SEO-специалист") is False
    assert team_health.in_team("Аккаунт-менеджер") is False
    assert team_health.is_telemarketing("Телемаркетолог") is True
    assert team_health.is_telemarketing("Менеджер по продажам") is False


def test_compute_efficiency_basic():
    # 3 задачи с дедлайном: 2 закрыты вовремя, 1 с опозданием → 66.67%
    closed = [
        {"deadline": "2026-06-10T18:00:00+03:00", "closedDate": "2026-06-09T10:00:00+03:00"},  # вовремя
        {"deadline": "2026-06-10T18:00:00+03:00", "closedDate": "2026-06-10T18:00:00+03:00"},  # ровно в срок
        {"deadline": "2026-06-10T18:00:00+03:00", "closedDate": "2026-06-12T09:00:00+03:00"},  # опоздал
    ]
    with_dl, ontime, pct = team_health.compute_efficiency(closed)
    assert (with_dl, ontime) == (3, 2)
    assert pct == 66.67


def test_compute_efficiency_ignores_no_deadline():
    closed = [
        {"deadline": None, "closedDate": "2026-06-09T10:00:00+03:00"},
        {"deadline": "2026-06-10T18:00:00+03:00", "closedDate": "2026-06-09T10:00:00+03:00"},
    ]
    with_dl, ontime, pct = team_health.compute_efficiency(closed)
    assert (with_dl, ontime, pct) == (1, 1, 100.0)


def test_compute_efficiency_none_when_no_deadlined_tasks():
    with_dl, ontime, pct = team_health.compute_efficiency([{"deadline": None, "closedDate": "2026-06-09T10:00:00+03:00"}])
    assert with_dl == 0 and ontime == 0 and pct is None


def test_compute_efficiency_uppercase_keys():
    closed = [{"DEADLINE": "2026-06-10T18:00:00+03:00", "CLOSED_DATE": "2026-06-09T10:00:00+03:00"}]
    assert team_health.compute_efficiency(closed) == (1, 1, 100.0)
