from src import oper


def test_operational_score_sm_with_meeting():
    # ОП: dials=10, answered=8 → empty=2×1.5=3; call=8×15=120; meet=1×50=50 → 173 → 5.8
    assert oper.operational_score(dials=10, normal_calls=8, meetings_count=1, is_tm=False) == 5.8


def test_operational_score_tm_no_meetings():
    # ТМ: empty=2×1.5=3; call=8×12=96 → 99 → 3.3; встречи не учитываются
    assert oper.operational_score(dials=10, normal_calls=8, meetings_count=5, is_tm=True) == 3.3


def test_empty_dial_minutes_capped_at_90():
    # 1000 пустых наборов → cap 90 мин → 90/300×10 = 3.0
    assert oper.operational_score(dials=1000, normal_calls=0, is_tm=False) == 3.0


def test_score_capped_at_10():
    assert oper.operational_score(dials=74, normal_calls=40, is_tm=True) == 10.0


def test_status_thresholds():
    assert oper.oper_status(6.0) == "НОРМ"
    assert oper.oper_status(3.0) == "РИСК"
    assert oper.oper_status(2.9) == "СТОП"


def test_role_detection():
    assert oper.is_telemarketing("Телемаркетолог")
    assert not oper.is_telemarketing("Менеджер по продажам")
