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
    body = '<img class="tiger-photo" src="photo:2806"><img class="mgr-ava" src="photo:999">'
    out = report_author.substitute_photos(body, {"2806": "data:image/jpeg;base64,AAA"})
    assert 'src="data:image/jpeg;base64,AAA"' in out
    assert 'data-no-photo="1"' in out  # для 999 фото нет — src очищен


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
        "meetings": [{"meeting_id": 2180, "meeting_type": "defense", "manager_id": 10, "status": "success"}],
        "manager_activity": [{"manager_id": 10, "dials_total": 89, "calls_answered": 30, "calls_120s_plus": 8}],
        "kp_briefs": [],
    }
    extras = {
        "report_date": "2026-05-29",
        "users": {"10": "Семенихин Егор"},
        "raw": {"deals_created": [], "meet_day": [{"id": 2180, "title": "kandela.ru"}]},
        "stale": {},
        "rejections": [],
        "analyses": {2180: {"verdict": "v"}},
    }
    payload = report_author.build_payload(rows, extras)
    assert payload["weekday_date_ru"].startswith("Пятница")
    assert payload["meetings"][0]["title"] == "kandela.ru"
    assert payload["meetings"][0]["manager"] == "Семенихин Егор"
    assert payload["meetings"][0]["analysis"] == {"verdict": "v"}
    assert payload["stats"]["calls_total"] == 89
