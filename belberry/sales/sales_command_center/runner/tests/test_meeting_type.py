from src.transform import assign_meeting_types


def _m(mid, deal, date, title=""):
    return {"id": mid, "parentId2": deal, "ufCrm16_1751009238": date, "title": title}


def test_name_takes_priority_over_position():
    # Название явно размечено — позиция не важна.
    items = [
        _m(1, 100, "2026-03-02T10:00:00+03:00", "site.ru (Защита)"),
        _m(2, 100, "2026-03-05T10:00:00+03:00", "site.ru (Брифинг)"),
    ]
    assert assign_meeting_types(items) == {1: "defense", 2: "briefing"}


def test_position_fallback_when_title_is_domain():
    # Январские встречи названы доменом → тип по позиции в сделке.
    items = [
        _m(10, 200, "2026-01-20T12:00:00+03:00", "client.ru"),  # вторая по дате → defense
        _m(11, 200, "2026-01-10T12:00:00+03:00", "client.ru"),  # первая → briefing
        _m(12, 300, "2026-01-15T12:00:00+03:00", "other.ru"),  # единственная → briefing
    ]
    assert assign_meeting_types(items) == {11: "briefing", 10: "defense", 12: "briefing"}


def test_meeting_without_deal_keeps_name_type():
    # Без сделки позицию не определить — остаётся «other».
    items = [_m(20, None, "2026-01-10T12:00:00+03:00", "noprm.ru")]
    assert assign_meeting_types(items) == {20: "other"}
