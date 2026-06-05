from datetime import date

from src import tasks as T


def test_parse_deadline_relative_days():
    base = date(2026, 6, 4)  # четверг
    assert T.parse_deadline("через 2 дня", base) == (date(2026, 6, 6), True)
    assert T.parse_deadline("через 2-3 дня", base) == (date(2026, 6, 7), True)  # верхняя граница
    assert T.parse_deadline("завтра", base) == (date(2026, 6, 5), True)
    assert T.parse_deadline("послезавтра", base) == (date(2026, 6, 6), True)


def test_parse_deadline_weeks():
    base = date(2026, 6, 4)
    assert T.parse_deadline("примерно через неделю", base) == (date(2026, 6, 11), True)
    assert T.parse_deadline("через недельку", base) == (date(2026, 6, 11), True)
    assert T.parse_deadline("через две недели", base) == (date(2026, 6, 18), True)


def test_parse_deadline_weekday_next_week():
    base = date(2026, 6, 4)  # четверг
    # «понедельник ... на следующей неделе» → 8 июня (ближайший пн)
    d, ok = T.parse_deadline("понедельник или вторник на следующей неделе", base)
    assert ok and d == date(2026, 6, 8)


def test_parse_deadline_fallback_business_days():
    base = date(2026, 6, 4)  # чт → +2 раб.дня = пн 8 июня (пропускаем сб/вс)
    d, ok = T.parse_deadline("как получится", base)
    assert ok is False and d == date(2026, 6, 8)


def test_build_task_fields_full():
    analysis = {
        "meeting_type": "briefing", "score": 7, "verdict": "Сильный брифинг",
        "client_quote": "Нормально, не шокирующе", "systemic_conclusion": "Нужны кейсы",
    }
    step = {"who": "Иван", "what": "Отправить доступ к Метрике и подготовить КП", "deadline": "через неделю"}
    f = T.build_task_fields(
        deal_id=15982, deal_title="insightai.ru", responsible_id=2846,
        step=step, analysis=analysis, base_date=date(2026, 6, 4), creator_id=12,
    )
    assert f["RESPONSIBLE_ID"] == 2846 and f["CREATED_BY"] == 12
    assert f["TASK_CONTROL"] == "Y"
    assert f["UF_CRM_TASK"] == ["D_15982"]
    assert f["DEADLINE"].startswith("2026-06-11T18:00:00")
    assert "insightai.ru" in f["TITLE"]
    assert "Метрик" in f["DESCRIPTION"] and "Цитата клиента" in f["DESCRIPTION"]
