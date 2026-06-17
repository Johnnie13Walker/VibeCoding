from types import SimpleNamespace

from src import report_author


class _Client:
    def __init__(self, text):
        self._text = text

    class _Messages:
        def __init__(self, text):
            self._text = text

        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(text=self._text)])

    @property
    def messages(self):
        return _Client._Messages(self._text)


def test_daily_kpis_counts_and_excludes_spam():
    rows = {"meetings": [{"meeting_id": 1}, {"meeting_id": 2}]}
    raw = {
        "user_roles": {"10": "Менеджер по продажам", "20": "Телемаркетолог"},
        "deals_created": [
            {"ID": "1", "UF_CRM_1771495464": None},
            {"ID": "2", "UF_CRM_1771495464": "8588"},  # СПАМ
            {"ID": "3", "UF_CRM_1771495464": "8574"},
        ],
        "briefs": [{"id": 1}, {"id": 2}],
        "kp": [{"id": 1}],
        "meet_created_day": [{"createdBy": 20}, {"createdBy": 20}, {"createdBy": 10}],
        "stagehistory": [
            {"OWNER_ID": "100", "STAGE_ID": "C10:LOSE"},
            {"OWNER_ID": "101", "STAGE_ID": "C10:LOSE"},
            {"OWNER_ID": "200", "STAGE_ID": "C50:APOLOGY"},  # ТМ-отвал, не воронка Продажи
        ],
        "rejected_deals": [
            {"ID": "100", "UF_CRM_1771495464": "8588"},  # СПАМ
            {"ID": "101", "UF_CRM_1771495464": "8580"},
        ],
    }
    k = report_author._daily_kpis(rows, raw)
    assert k["meetings_held"] == 2
    assert k["briefs"] == 2 and k["kp"] == 1
    assert k["new_deals"] == 2 and k["new_deals_total"] == 3 and k["new_deals_spam"] == 1
    assert k["meetings_set_tm"] == 2 and k["meetings_set_op"] == 1
    assert k["sales_rejects"] == 1 and k["sales_rejects_total"] == 2 and k["sales_rejects_spam"] == 1


def test_build_kpi_strip_renders():
    k = report_author._daily_kpis({"meetings": [{"x": 1}]}, {})
    out = report_author.build_kpi_strip(k)
    assert 'id="kpi-strip"' in out
    assert "Встречи проведены" in out and "Отказы в воронке Продажи" in out


def test_build_kpi_strip_empty():
    assert report_author.build_kpi_strip(None) == ""


def test_inject_blocks_replaces_both_placeholders():
    body = '<div class="hero"></div>[[KPI_STRIP]]<section id="tiger">T</section>[[OPER_SCORECARD]]'
    payload = {
        "daily_kpis": report_author._daily_kpis({"meetings": []}, {}),
        "telephony": [{"manager": "A", "role": "x", "operational_score": 1.0, "oper_status": "СТОП"}],
    }
    out = report_author._inject_blocks(body, payload)
    assert "[[KPI_STRIP]]" not in out and "[[OPER_SCORECARD]]" not in out
    assert 'id="kpi-strip"' in out and 'id="oper-scorecard"' in out


def test_build_telegram_digest():
    payload = {
        "weekday_date_ru": "Среда, 3 июня 2026",
        "daily_kpis": {"meetings_held": 4, "briefs": 6, "kp": 6, "new_deals": 4, "new_deals_total": 12,
                       "new_deals_spam": 8, "meetings_set_tm": 0, "meetings_set_op": 3,
                       "sales_rejects": 0, "sales_rejects_total": 6, "sales_rejects_spam": 6},
        "telephony": [
            {"manager": "Семенихин Егор", "operational_score": 7.0, "oper_status": "НОРМ"},
            {"manager": "Исаева Дарья", "operational_score": 5.7, "oper_status": "РИСК"},
        ],
    }
    payload["health_score"] = {"components": {"meeting_score_percent": 60, "stale_count": 26, "risk_money": 3670000}}
    payload["action_items"] = [{"owner": "Семенихин Егор", "action": "Добить дату решения по phznanie.ru"}]
    payload["telephony"][0].update({"role": "Менеджер по продажам", "meetings_held": 2, "calls_60s_plus": 9})
    payload["telephony"][1]["role"] = "Телемаркетолог"
    html_body = '<div class="hero-subtitle">День спокойный, темп в норме.</div><div class="hero-verdict"><span class="hv-icon">⚠️</span><b>Итог за ночь:</b> фокус на КП.</div>'
    d = report_author.build_telegram_digest(payload, html_body)
    assert "Сводка отдела продаж — Среда, 3 июня 2026" in d
    assert "Тигр дня" in d and "Семенихин Егор" in d
    assert "−8 спам" in d
    assert "День спокойный, темп в норме." in d
    assert "Итог за ночь" in d
    assert "ср. балл 6.0/10" in d
    assert "зависших 26 на 3,7 млн ₽" in d
    assert "(ОП)" in d and "(ТМ)" in d
    assert "На сегодня:" in d and "phznanie.ru" in d
    assert "2 встреч" in d and "9 разговоров 60с+" in d


def test_build_oper_scorecard_renders_rows():
    tel = [
        {"manager": "Семенихин Егор", "role": "Менеджер по продажам", "dials_total": 9,
         "calls_answered": 3, "calls_60s_plus": 3, "messenger_dialogs": 1, "emails_sent": 1,
         "meetings_held": 3, "operational_score": 7.0, "oper_status": "НОРМ"},
        {"manager": "Исаева Дарья", "role": "Телемаркетолог", "dials_total": 84,
         "calls_answered": 22, "calls_60s_plus": 15, "messenger_dialogs": 8, "emails_sent": 7,
         "meetings_held": 0, "operational_score": 5.7, "oper_status": "РИСК"},
    ]
    out = report_author.build_oper_scorecard(tel)
    assert 'id="oper-scorecard"' in out
    assert "Семенихин Егор" in out and ">ОП<" in out
    assert "Исаева Дарья" in out and ">ТМ<" in out
    assert "b-green" in out and "b-amber" in out
    assert "<b>7.0</b>" in out


def test_build_oper_scorecard_empty():
    assert report_author.build_oper_scorecard([]) == ""


def test_inject_scorecard_replaces_placeholder():
    body = '<div class="hero"></div>[[OPER_SCORECARD]]<section>x</section>'
    out = report_author._inject_blocks(
        body, {"telephony": [{"manager": "A", "role": "x", "operational_score": 1.0, "oper_status": "СТОП"}]}
    )
    assert "[[OPER_SCORECARD]]" not in out
    assert 'id="oper-scorecard"' in out


def test_inject_scorecard_fallback_after_tiger():
    body = '<section id="tiger">T</section><section id="x">Y</section>'
    out = report_author._inject_blocks(
        body, {"telephony": [{"manager": "A", "role": "x", "operational_score": 1.0, "oper_status": "СТОП"}]}
    )
    assert out.index("oper-scorecard") > out.index("tiger")
    assert out.index("oper-scorecard") < out.index('id="x"')


def test_substitute_photos_injects_and_clears():
    body = '<img class="tiger-photo" src="photo:2806"><img class="mgr-ava" src="photo:999" alt="Нет фото">'
    out = report_author.substitute_photos(body, {"2806": "data:image/jpeg;base64,AAA"})
    assert 'src="data:image/jpeg;base64,AAA"' in out
    assert '<span class="mgr-ava photo-fallback" data-no-photo="1">Н</span>' in out
    assert 'src=""' not in out


def test_substitute_photos_falls_back_to_alt_user_name():
    body = '<img class="tiger-photo" src="photo:999" alt="Вострецов Аркадий">'
    out = report_author.substitute_photos(
        body,
        {"2832": "data:image/jpeg;base64,BBB"},
        {"2832": "Вострецов Аркадий"},
    )

    assert 'src="data:image/jpeg;base64,BBB"' in out
    assert "photo-fallback" not in out


def test_validate_rules():
    assert report_author._validate('<div class="hero">' + "x" * 500 + "</div>")
    assert not report_author._validate('<div class="hero"><script>x</script></div>')
    assert not report_author._validate("слишком коротко")


def test_author_report_strips_fence_and_returns_body():
    text = '```html\n<div class="hero">' + "y" * 500 + "</div>\n```"
    body = report_author.author_report({"report_date": "2026-05-29"}, client=_Client(text))
    assert body.startswith('<div class="hero">')
    assert "```" not in body


def test_author_report_none_on_invalid():
    assert report_author.author_report({}, client=_Client("нет")) is None


def test_system_prompt_requires_reference_meeting_layout():
    prompt = report_author.SYSTEM_PROMPT

    for token in (
        "quote client",
        "quote-author",
        "hilight-grid",
        "analysis.observations",
        "analysis.next_step",
        "Коммитмент",
        "transcript_based=false",
        "разбор по краткому статусу, не по транскрипту",
        "checks",
    ):
        assert token in prompt


def test_build_payload_shapes_day():
    rows = {
        "deals_snapshot": [],
        "meetings": [{"meeting_id": 2180, "deal_id": 24304, "meeting_type": "defense", "manager_id": 10, "status": "success"}],
        "manager_activity": [{"manager_id": 10, "dials_total": 89, "calls_answered": 30, "calls_60s_plus": 20, "calls_120s_plus": 8, "emails_sent": 0}],
        "kp_briefs": [],
    }
    extras = {
        "report_date": "2026-05-29",
        "users": {"10": "Семенихин Егор"},
        "raw": {
            "deals_created": [],
            "deals_open": [{"ID": "24304", "OPPORTUNITY": "150000"}],
            "meet_day": [{"id": 2180, "title": "kandela.ru"}],
            "user_roles": {"10": "Менеджер по продажам"},
        },
        "stale": {},
        "rejections": [{"deal_id": "14652", "title": "aclinic.ru", "stage": "C10:LOSE", "reason": "F"}],
        "analyses": {
            2180: {
                "verdict": "v",
                "client_quote": "Жду прогноз.",
                "next_step": {"what": "Отправить прогноз", "who": "Семенихин Егор", "deadline": "сегодня"},
                "observations": [{"kind": "risk", "text": "Не показан кейс.", "metric": "кейс"}],
            }
        },
        "narrative": {
            "quote_of_day": {"text": "Жду прогноз.", "meta": "kandela.ru"},
            "manager_coaching": [
                {"manager": "Семенихин Егор", "manager_id": 10, "advice": "Показывать кейс до цены.", "basis": "кейс"}
            ],
        },
    }
    payload = report_author.build_payload(rows, extras)
    assert payload["weekday_date_ru"].startswith("Пятница")
    assert payload["meetings"][0]["title"] == "kandela.ru"
    assert payload["meetings"][0]["manager"] == "Семенихин Егор"
    assert payload["meetings"][0]["analysis"]["verdict"] == "v"
    assert payload["meetings"][0]["deal_opportunity"] == 150000.0  # сумма сделки подтянута к встрече
    assert payload["quote_of_day"]["text"] == "Жду прогноз."
    assert payload["manager_coaching"][0]["advice"] == "Показывать кейс до цены."
    assert payload["action_items"][0]["owner"] == "Семенихин Егор"
    assert payload["action_items"][0]["deadline"] == "сегодня"
    assert payload["action_items"][0]["urgency"] == "сегодня"
    assert payload["rejections"][0]["reason_label"] == "Отказ (воронка Продажи)"  # не код F
    assert payload["stats"]["calls_total"] == 89
    # «Опер»: short 69×2=138→cap90 + 60с+ 20×5=100 + meet 1×60=60 = 250 → 8.3
    assert payload["telephony"][0]["operational_score"] == 8.3
    assert payload["telephony"][0]["calls_60s_plus"] == 20
    assert payload["health_score"]["score"] > 0
    assert payload["health_score"]["level"] in {"green", "amber", "red"}
    assert payload["tm_funnel"]["count"] == 0


def test_build_payload_falls_back_to_meeting_quote_and_observation_coaching():
    rows = {
        "deals_snapshot": [],
        "meetings": [{"meeting_id": 2180, "deal_id": 24304, "meeting_type": "defense", "manager_id": 10, "status": "success"}],
        "manager_activity": [{"manager_id": 10, "dials_total": 10, "calls_answered": 4}],
        "kp_briefs": [],
    }
    extras = {
        "report_date": "2026-05-29",
        "users": {"10": "Семенихин Егор"},
        "raw": {"user_roles": {"10": "Менеджер по продажам"}},
        "analyses": {
            2180: {
                "client_quote": "Без кейса не понимаю результат.",
                "observations": [{"kind": "risk", "text": "Клиент просит кейс.", "metric": "кейс"}],
            }
        },
    }

    payload = report_author.build_payload(rows, extras)

    assert payload["quote_of_day"]["text"] == "Без кейса не понимаю результат."
    assert payload["manager_coaching"][0]["manager_id"] == 10
    assert "Клиент просит кейс" in payload["manager_coaching"][0]["advice"]


def test_build_payload_adds_stale_action_items_and_data_quality():
    rows = {
        "deals_snapshot": [],
        "meetings": [
            {
                "meeting_id": 2180,
                "deal_id": 24304,
                "meeting_type": "defense",
                "manager_id": 10,
                "status": "success",
                "transcript_ok": False,
            }
        ],
        "manager_activity": [{"manager_id": 10, "dials_total": 10, "calls_answered": 4}],
        "kp_briefs": [],
    }
    extras = {
        "report_date": "2026-05-29",
        "users": {"10": "Семенихин Егор"},
        "raw": {
            "user_roles": {"10": "Менеджер по продажам"},
            "deals_open": [
                # выше Квалификации с пустой суммой → реальный пробел данных
                {"ID": "24304", "TITLE": "kandela.ru", "OPPORTUNITY": "0", "STAGE_ID": "C10:EXECUTING"},
                # на Квалификации нулевой бюджет нормален → НЕ должно попасть в пробелы
                {"ID": "24999", "TITLE": "lead.ru", "OPPORTUNITY": "0", "STAGE_ID": "C10:NEW"},
            ],
        },
        "stale": {
            "Подготовка КП": [
                {
                    "deal_id": 24304,
                    "title": "kandela.ru",
                    "manager_id": 10,
                    "risk_reason": "молчит 10 дн",
                    "age_level": "critical",
                }
            ]
        },
        "analyses": {2180: {"transcript_based": False}},
    }

    payload = report_author.build_payload(rows, extras)

    assert payload["action_items"][0]["source"] == "stale"
    assert payload["action_items"][0]["urgency"] == "сейчас"
    assert {issue["kind"] for issue in payload["data_quality"]} == {"zero_amount", "missing_transcript"}
    assert payload["data_quality"][0]["count"] == 1


def test_system_prompt_mentions_quote_day_and_no_achievements():
    assert "quote-day" in report_author.SYSTEM_PROMPT
    assert "manager_coaching" in report_author.SYSTEM_PROMPT
    assert "payload.action_items" in report_author.SYSTEM_PROMPT
    assert "payload.data_quality" in report_author.SYSTEM_PROMPT
    assert "payload.promises_loop" in report_author.SYSTEM_PROMPT
    assert ".ach-*" in report_author.SYSTEM_PROMPT


def test_build_payload_excludes_non_sales_roles():
    rows = {
        "meetings": [], "kp_briefs": [],
        "manager_activity": [
            {"manager_id": 10, "dials_total": 50},   # продажи
            {"manager_id": 99, "dials_total": 5},     # рекрутёр — исключить
            {"manager_id": 7, "dials_total": 0},      # роль не указана — исключить
        ],
    }
    extras = {
        "report_date": "2026-05-29",
        "users": {"10": "Семенихин Егор", "99": "Николаева Ирина", "7": "Админ"},
        "raw": {"user_roles": {"10": "Менеджер по продажам", "99": "Рекрутер"}},
    }
    payload = report_author.build_payload(rows, extras)
    ids = [m["manager_id"] for m in payload["manager_activity"]]
    assert ids == [10]  # только ОП/ТМ
    assert payload["stats"]["calls_total"] == 50


def test_build_day_feed_scopes_and_excludes_spam():
    raw = {
        "user_roles": {"10": "Менеджер по продажам", "20": "Телемаркетолог", "99": "Рекрутер"},
        "meet_day": [{"assignedById": 10, "title": "kandela.ru", "ufCrm16_1751009238": "2026-06-04T10:00:00"}],
        "briefs": [{"assignedById": 20, "title": "rant.ru", "createdTime": "2026-06-04T11:00:00"}],
        "kp": [{"assignedById": 99, "title": "hr.ru", "updatedTime": "2026-06-04T12:00:00"}],  # HR — вне скоупа
        "deals_created": [
            {"ASSIGNED_BY_ID": 10, "TITLE": "real.ru", "DATE_CREATE": "2026-06-04T13:00:00"},
            {"ASSIGNED_BY_ID": 10, "TITLE": "spam.ru", "DATE_CREATE": "2026-06-04T14:00:00", "UF_CRM_1771495464": "8588"},
        ],
    }
    feed = report_author.build_day_feed(raw)
    titles = [e["title"] for e in feed]
    assert "kandela.ru" in titles and "rant.ru" in titles and "real.ru" in titles
    assert "hr.ru" not in titles  # рекрутёр вне ОП+ТМ
    assert "spam.ru" not in titles  # спам-сделка исключена
    # сортировка по времени убыв.
    assert feed[0]["at"] >= feed[-1]["at"]


def test_build_payload_adds_tm_funnel():
    rows = {
        "meetings": [],
        "kp_briefs": [],
        "manager_activity": [
            {
                "manager_id": 11,
                "dials_total": 100,
                "calls_answered": 25,
                "calls_60s_plus": 10,
                "calls_120s_plus": 5,
                "meetings_set": 3,
                "meetings_held": 2,
                "deals_created_count": 1,
            },
            {"manager_id": 10, "dials_total": 50, "calls_answered": 20},
        ],
    }
    extras = {
        "report_date": "2026-05-29",
        "users": {"11": "Исаева Дарья", "10": "Семенихин Егор"},
        "raw": {
            "user_roles": {
                "11": "Телемаркетолог",
                "10": "Менеджер по продажам",
            }
        },
    }

    payload = report_author.build_payload(rows, extras)

    assert payload["tm_funnel"] == {
        "count": 1,
        "dials_total": 100,
        "calls_answered": 25,
        "dozvon": 10,
        "calls_60s_plus": 10,
        "meetings_set": 3,
        "meetings_held": 2,
        "deals_created_count": 1,
        "answered_percent": 25,
        "dozvon_percent": 10,
        "meeting_set_percent": 30,
        "deal_create_percent": 50,
    }


def test_fmt_until_formats_dates():
    from src.report_author import _fmt_until
    assert _fmt_until("08.06.2026 18:00:00") == "08.06"
    assert _fmt_until("2026-06-08T18:00:00") == "08.06"
    assert _fmt_until(None) is None
