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


def test_parse_deadline_explicit_dates():
    base = date(2026, 6, 11)  # четверг — день встречи delficlinic/medcel
    # кейс 523340: «созвон 24 июня» дедлайн должен быть 24.06, а не фолбэк 12.06
    assert T.parse_deadline("24.06.2026", base) == (date(2026, 6, 24), True)
    assert T.parse_deadline("24.06", base) == (date(2026, 6, 24), True)
    assert T.parse_deadline("24 июня", base) == (date(2026, 6, 24), True)
    assert T.parse_deadline("к 24 числа", base) == (date(2026, 6, 24), True)
    assert T.parse_deadline("к 24-му", base) == (date(2026, 6, 24), True)
    assert T.parse_deadline("20-го", base) == (date(2026, 6, 20), True)
    assert T.parse_deadline("16-е", base) == (date(2026, 6, 16), True)
    assert T.parse_deadline("18-е", base) == (date(2026, 6, 18), True)
    assert T.parse_deadline("сегодня", base) == (date(2026, 6, 11), True)


def test_parse_deadline_explicit_date_rolls_forward():
    base = date(2026, 6, 11)  # дата уже прошла в этом месяце/году → переносим вперёд
    assert T.parse_deadline("5 июня", base) == (date(2027, 6, 5), True)   # месяц прошёл → +год
    assert T.parse_deadline("01.03", base) == (date(2027, 3, 1), True)    # март прошёл → +год
    assert T.parse_deadline("3 числа", base) == (date(2026, 7, 3), True)  # день прошёл → след. месяц
    # год указан явно — не переносим, даже если в прошлом
    assert T.parse_deadline("01.03.2026", base) == (date(2026, 3, 1), True)


def test_parse_deadline_weekday_next_week():
    base = date(2026, 6, 4)  # четверг
    # «понедельник ... на следующей неделе» → 8 июня (ближайший пн)
    d, ok = T.parse_deadline("понедельник или вторник на следующей неделе", base)
    assert ok and d == date(2026, 6, 8)


def test_parse_deadline_fallback_business_days():
    base = date(2026, 6, 4)  # чт → следующий раб.день = пт 5 июня
    d, ok = T.parse_deadline("как получится", base)
    assert ok is False and d == date(2026, 6, 5)
    # пятница → следующий раб.день = понедельник (пропускаем сб/вс)
    d2, ok2 = T.parse_deadline("", date(2026, 6, 5))
    assert ok2 is False and d2 == date(2026, 6, 8)


def test_is_kp_formation():
    assert T.is_kp_formation("Подготовить КП по SEO") is True
    assert T.is_kp_formation("сформировать коммерческое предложение") is True
    assert T.is_kp_formation("составить КП") is True
    # «отправить/защитить КП» — НЕ формирование
    assert T.is_kp_formation("Отправить КП клиенту") is False
    assert T.is_kp_formation("Защитить КП на встрече") is False
    assert T.is_kp_formation("Запросить доступ к Метрике") is False


def test_actionable_steps_drops_kp_formation():
    steps = [
        {"what": "Отправить доступ к Метрике", "kind": "operational"},
        {"what": "Подготовить КП", "kind": "scheduled"},
        {"what": "Получить ответ клиента", "kind": "scheduled", "deadline": "через неделю"},
    ]
    out = T.actionable_steps(steps)
    whats = [s["what"] for s in out]
    assert "Подготовить КП" not in whats
    assert "Отправить доступ к Метрике" in whats and "Получить ответ клиента" in whats


def test_operational_deadline_is_next_business_day():
    # operational → следующий рабочий день, даже если на словах «через неделю»
    f = T.build_task_fields(
        deal_id=1, deal_title="x.ru", responsible_id=10,
        step={"what": "Отправить кейсы", "kind": "operational", "deadline": "через неделю"},
        analysis={}, base_date=date(2026, 6, 4), creator_id=12,
    )
    assert f["DEADLINE"].startswith("2026-06-05T15:00:00")  # чт → пт


def test_scheduled_deadline_parses_date():
    f = T.build_task_fields(
        deal_id=1, deal_title="x.ru", responsible_id=10,
        step={"what": "Созвон по итогам", "kind": "scheduled", "deadline": "в понедельник"},
        analysis={}, base_date=date(2026, 6, 4), creator_id=12,
    )
    assert f["DEADLINE"].startswith("2026-06-08T15:00:00")  # ближайший пн


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
    assert f["DEADLINE"].startswith("2026-06-11T15:00:00")
    assert "insightai.ru" in f["TITLE"]
    assert "Метрик" in f["DESCRIPTION"] and "Цитата клиента" in f["DESCRIPTION"]


# ── Семантический дедуп (Phase 1 умной постановки) ──

def _steps(*whats):
    return [{"what": w} for w in whats]


def test_canonical_action_categories():
    assert T.canonical_action("Отправить клиенту материалы и КП") == "send"
    assert T.canonical_action("Получить от клиента обратную связь по смете") == "await"
    assert T.canonical_action("Получить гостевой доступ к Яндекс.Метрике") == "await"
    assert T.canonical_action("Оценить рынок и прогнозные значения") == "internal"
    assert T.canonical_action("Проанализировать рекламные кампании и Метрику") == "internal"
    assert T.canonical_action("Обсудить КП с клиентом после оценки") == "discuss"
    # неизвестное — не сливаем (свой ключ)
    assert T.canonical_action("Покрасить забор").startswith("other:")


def test_dedupe_merges_homogeneous_keeps_first():
    # 25118: 6 шагов → 3 канона (await/internal/discuss)
    steps = _steps(
        "Получить от клиента перечень уникальных операций",
        "Получить обратную связь после разговора с администрацией",
        "Оценить рынок и прогнозные значения по направлениям",
        "Получить решение администрации и уточнённый список операций",
        "Внутренне оценить рынок по нейрохирургии",
        "Обсудить с клиентом КП после внутренней оценки",
    )
    out = T.dedupe_steps(steps, cap=10)
    cats = [T.canonical_action(s["what"]) for s in out]
    assert cats == ["await", "internal", "discuss"]
    # оставлено ПЕРВОЕ вхождение каждого канона
    assert out[0]["what"].startswith("Получить от клиента перечень")


def test_dedupe_send_pair_to_one():
    # 24696: send/await/send/await → send+await
    steps = _steps(
        "Отправить клиенту бриф/вопросы",
        "Получить письменные ответы клиента",
        "Отправить клиенту материалы: бриф/вопросы",
        "Получить ответы клиента на бриф",
    )
    out = T.dedupe_steps(steps, cap=10)
    assert [T.canonical_action(s["what"]) for s in out] == ["send", "await"]


def test_dedupe_cap():
    steps = _steps(
        "Отправить материалы",          # send
        "Получить ответ клиента",        # await
        "Оценить рынок",                 # internal
        "Обсудить КП с клиентом",        # discuss
    )
    assert len(T.dedupe_steps(steps, cap=2)) == 2


def test_dedupe_cross_run_skips_existing():
    # межпрогонная идемпотентность: канон уже стоит по встрече → не дублируем
    steps = _steps("Отправить клиенту обновлённые материалы")
    out = T.dedupe_steps(steps, existing_actions={"send"}, cap=10)
    assert out == []


# ── Интеграция планировщика в create_tasks_for_day (dry-run, без LLM/Bitrix) ──

class _FakeCur:
    def __init__(self, rows): self._rows = rows
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, *a, **k): pass
    def fetchall(self): return self._rows

class _FakeConn:
    def __init__(self, rows): self._rows = rows
    def cursor(self): return _FakeCur(self._rows)


def test_create_tasks_planner_path(monkeypatch):
    from src import task_planner
    rows = [(2228, 25118, 2188, {"meeting_type": "defense", "verdict": "v"}, "pedklin.ru", "C10:PREPAYMENT")]
    monkeypatch.setattr(task_planner, "plan_tasks", lambda *a, **k: [
        {"title": "Оценить рынок по нейрохирургии для Директа", "type": "internal", "owner": "manager", "deadline": "через неделю", "significance": "high", "rationale": "усилить аргументацию", "control": True},
        {"title": "Дожать решение администрации", "type": "await", "owner": "manager", "deadline": None, "significance": "high", "rationale": "без решения не двинется", "control": False},
    ])
    res = T.create_tasks_for_day(_FakeConn(rows), None, date(2026, 6, 8), dry_run=True, client=object())
    planned = [r for r in res if r["status"] == "planned"]
    assert len(planned) == 2
    assert all(r["source"] == "planner" for r in planned)
    titles = [r["fields"]["TITLE"] for r in planned]
    assert titles[0].startswith("pedklin.ru: Оценить рынок")
    # контроль только на первой; срок «через неделю» от 08.06 → 15.06
    assert [r["fields"]["TASK_CONTROL"] for r in planned] == ["Y", "N"]
    assert planned[0]["fields"]["DEADLINE"].startswith("2026-06-15")
    assert "Зачем: усилить аргументацию" in planned[0]["fields"]["DESCRIPTION"]


def test_create_tasks_legacy_fallback_without_client():
    rows = [(2228, 25118, 2188, {"next_steps": [{"what": "Отправить клиенту КП и кейсы"}]}, "pedklin.ru", "C10:PREPAYMENT")]
    res = T.create_tasks_for_day(_FakeConn(rows), None, date(2026, 6, 8), dry_run=True)  # client=None
    planned = [r for r in res if r["status"] == "planned"]
    assert len(planned) == 1 and planned[0]["source"] == "legacy"


def test_create_tasks_skips_already_tasked_meeting(monkeypatch):
    from src import task_planner
    rows = [(2228, 25118, 2188, {"next_steps": [{"what": "Отправить КП"}]}, "x.ru", "C10")]
    monkeypatch.setattr(T, "existing_step_keys", lambda conn, mid: {"abc"})  # по встрече уже есть задачи
    called = []
    monkeypatch.setattr(task_planner, "plan_tasks", lambda *a, **k: called.append(1) or [])
    res = T.create_tasks_for_day(_FakeConn(rows), None, date(2026, 6, 8), dry_run=False, client=object())
    assert any(r["status"] == "skip_meeting_done" for r in res)
    assert called == []  # планировщик НЕ вызывался для обработанной встречи
