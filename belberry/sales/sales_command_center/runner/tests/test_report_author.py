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
    # «Опер»: short 69×0.25=17.25 + 60с+ 20×5=100 + meet 1×60=60 = 177.25 → 5.9
    assert payload["telephony"][0]["operational_score"] == 5.9
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


def test_build_payload_adds_tm_funnel():
    rows = {
        "meetings": [],
        "kp_briefs": [],
        "manager_activity": [
            {
                "manager_id": 11,
                "dials_total": 100,
                "calls_answered": 25,
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
        "calls_120s_plus": 5,
        "meetings_set": 3,
        "meetings_held": 2,
        "deals_created_count": 1,
        "answered_percent": 25,
        "long_call_percent": 20,
        "meeting_set_percent": 60,
        "deal_create_percent": 50,
    }


def test_fmt_until_formats_dates():
    from src.report_author import _fmt_until
    assert _fmt_until("08.06.2026 18:00:00") == "08.06"
    assert _fmt_until("2026-06-08T18:00:00") == "08.06"
    assert _fmt_until(None) is None
