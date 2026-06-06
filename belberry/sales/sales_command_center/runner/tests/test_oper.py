from src import oper


def test_operational_score_with_meeting():
    # dials=10, 60с+=8 → short=2×0.25=0.5; call=8×5=40; meet=1×60=60 → 100.5 → 3.35→3.4
    assert oper.operational_score(dials=10, calls_60s=8, meetings_count=1) == 3.4


def test_meetings_count_for_any_role():
    # роль на балл больше не влияет: 2 встречи = 120 мин → 4.0
    assert oper.operational_score(dials=0, calls_60s=0, meetings_count=2) == 4.0


def test_emails_and_chats_count():
    # 6 чатов×10=60 + 4 письма×5=20 = 80 → 2.7
    assert oper.operational_score(dials=0, calls_60s=0, messenger_dialogs=6, emails=4) == 2.7


def test_short_dials_capped_at_90():
    # 1000 коротких наборов → cap 90 мин → 90/300×10 = 3.0
    assert oper.operational_score(dials=1000, calls_60s=0) == 3.0


def test_score_capped_at_10():
    # 8 встреч×60=480 мин → cap 10.0
    assert oper.operational_score(dials=0, calls_60s=0, meetings_count=8) == 10.0


def test_operational_minutes_raw():
    # 84 набора (60 коротких×0.25=15) + 24 звонка60с+×5=120 + 8 чатов×10=80 = 215
    assert oper.operational_minutes(dials=84, calls_60s=24, messenger_dialogs=8) == 215.0


def test_status_thresholds():
    assert oper.oper_status(6.0) == "НОРМ"
    assert oper.oper_status(3.0) == "РИСК"
    assert oper.oper_status(2.9) == "СТОП"


def test_role_detection():
    assert oper.is_telemarketing("Телемаркетолог")
    assert not oper.is_telemarketing("Менеджер по продажам")
