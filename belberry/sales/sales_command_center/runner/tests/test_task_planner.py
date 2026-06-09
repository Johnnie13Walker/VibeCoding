from src import task_planner as P


def test_normalize_caps_to_two():
    parsed = {"tasks": [
        {"title": "a", "type": "send"},
        {"title": "b", "type": "await"},
        {"title": "c", "type": "internal"},
    ]}
    out = P.normalize_plan(parsed)
    assert len(out) == 2
    assert [t["title"] for t in out] == ["a", "b"]


def test_normalize_drops_empty_title():
    out = P.normalize_plan({"tasks": [{"title": "  ", "type": "send"}, {"title": "ok"}]})
    assert [t["title"] for t in out] == ["ok"]


def test_normalize_bad_type_defaults_internal():
    out = P.normalize_plan({"tasks": [{"title": "x", "type": "weird"}]})
    assert out[0]["type"] == "internal"


def test_normalize_single_control_only():
    out = P.normalize_plan({"tasks": [
        {"title": "a", "control": True},
        {"title": "b", "control": True},
    ]})
    assert [t["control"] for t in out] == [True, False]


def test_normalize_garbage_returns_empty():
    assert P.normalize_plan(None) == []
    assert P.normalize_plan({"tasks": "nope"}) == []
    assert P.normalize_plan({}) == []


def test_build_message_contains_key_fields():
    msg = P.build_planner_message(
        {"meeting_type": "briefing", "verdict": "сильный", "next_steps": [{"what": "отправить КП"}]},
        deal_title="x.ru", stage="C10:PREPAYMENT",
    )
    assert "x.ru" in msg and "C10:PREPAYMENT" in msg and "отправить" in msg
