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


def test_build_payload_shapes_day():
    rows = {
        "deals_snapshot": [],
        "meetings": [{"meeting_id": 2180, "deal_id": 24304, "meeting_type": "defense", "manager_id": 10, "status": "success"}],
        "manager_activity": [{"manager_id": 10, "dials_total": 89, "calls_answered": 30, "calls_120s_plus": 8}],
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
        "analyses": {2180: {"verdict": "v"}},
    }
    payload = report_author.build_payload(rows, extras)
    assert payload["weekday_date_ru"].startswith("Пятница")
    assert payload["meetings"][0]["title"] == "kandela.ru"
    assert payload["meetings"][0]["manager"] == "Семенихин Егор"
    assert payload["meetings"][0]["analysis"] == {"verdict": "v"}
    assert payload["meetings"][0]["deal_opportunity"] == 150000.0  # сумма сделки подтянута к встрече
    assert payload["rejections"][0]["reason_label"] == "Отказ (воронка Продажи)"  # не код F
    assert payload["stats"]["calls_total"] == 89


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
