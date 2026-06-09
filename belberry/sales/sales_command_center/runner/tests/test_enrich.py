from pathlib import Path

from src.enrich import enrich_meetings

FIXTURE = Path(__file__).parent / "fixtures" / "2026-05-29" / "transcripts" / "2180.txt"


class Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


def opener_for(body: bytes, calls: list[str] | None = None):
    def opener(url, timeout=120):
        if calls is not None:
            calls.append(url)
        return Response(body)

    return opener


def test_fixture_format_valid():
    text = FIXTURE.read_text()

    assert "memoai.tech" in text
    assert "Длительность: 00:18:13" in text
    assert "Краткое содержание" in text
    assert "Расшифровка" in text
    assert "[00:00] Спикер 1:" in text
    assert len(text.splitlines()) >= 30


def test_transcript_downloaded_for_valid_meeting():
    body = FIXTURE.read_bytes()
    raw = {"meet_day": [{"id": 2180, "title": "example", "ufCrm16Transcript": {"urlMachine": "http://x"}}]}

    result = enrich_meetings(raw, opener=opener_for(body))

    assert result[2180]["text"] == body.decode()
    assert result[2180]["transcript_status"] == "ok"
    assert result[2180]["url"] == "http://x"


def test_transcript_url_refreshed_before_download():
    # Токен во вшитом urlMachine протухает за время долгого сбора → перед скачиванием
    # берём свежую ссылку через crm.item.get и качаем именно по ней.
    body = FIXTURE.read_bytes()
    calls: list[str] = []

    class FakeBx:
        def call(self, method, params):
            assert method == "crm.item.get"
            assert params == {"entityTypeId": 1048, "id": 2180}
            return {"result": {"item": {"ufCrm16Transcript": {"urlMachine": "http://fresh"}}}}

    raw = {"meet_day": [{"id": 2180, "ufCrm16Transcript": {"urlMachine": "http://stale"}}]}

    result = enrich_meetings(raw, opener=opener_for(body, calls), bx=FakeBx(), refresh=True)

    assert result[2180]["transcript_status"] == "ok"
    assert result[2180]["url"] == "http://fresh"
    assert calls == ["http://fresh"]


def test_transcript_missing_when_field_empty():
    result = enrich_meetings({"meet_day": [{"id": 1, "ufCrm16Transcript": None}]})

    assert result[1]["transcript_status"] == "missing"
    assert result[1]["text"] == ""


def test_transcript_missing_when_download_too_small():
    raw = {"meet_day": [{"id": 1, "ufCrm16Transcript": {"urlMachine": "http://x"}}]}

    result = enrich_meetings(raw, opener=opener_for(b"x"))

    assert result[1]["transcript_status"] == "missing"


def test_transcript_mismatch_flagged():
    raw = {
        "meet_day": [
            {
                "id": 2180,
                "duration_seconds": 30,
                "ufCrm16Transcript": {"urlMachine": "http://x"},
            }
        ]
    }

    result = enrich_meetings(raw, opener=opener_for(FIXTURE.read_bytes()))

    assert result[2180]["transcript_status"] == "mismatch"
    assert result[2180]["text"]


def test_transcript_cached_idempotent():
    calls = []
    raw = {"meet_day": [{"id": 2180, "ufCrm16Transcript": {"urlMachine": "http://x"}}]}
    cache = {}

    enrich_meetings(raw, cache=cache, opener=opener_for(FIXTURE.read_bytes(), calls))
    enrich_meetings(raw, cache=cache, opener=opener_for(FIXTURE.read_bytes(), calls))

    assert len(calls) == 1


# ── PDF-транскрипты (memoai.tech) — извлечение текста ──
from src import enrich as E  # noqa: E402


def test_decode_plain_text_utf8():
    assert E._decode_transcript("Привет, встреча".encode("utf-8")) == "Привет, встреча"


def test_decode_pdf_routes_to_extractor(monkeypatch):
    monkeypatch.setattr(E, "_extract_pdf_text", lambda body: "ИЗВЛЕЧЁННЫЙ ТЕКСТ")
    assert E._decode_transcript(b"%PDF-1.4\nrubbish") == "ИЗВЛЕЧЁННЫЙ ТЕКСТ"


def test_extract_pdf_text_garbage_returns_empty():
    # битый PDF → не падаем, отдаём пусто (встреча станет missing, а не «мусорный разбор»)
    assert E._extract_pdf_text(b"%PDF-1.4 not a real pdf") == ""


def test_decode_non_pdf_not_routed(monkeypatch):
    monkeypatch.setattr(E, "_extract_pdf_text", lambda body: (_ for _ in ()).throw(AssertionError("не должно вызываться")))
    # обычный текст — извлекатель PDF не трогаем
    assert E._decode_transcript(b"plain transcript text") == "plain transcript text"


import gzip as _gz  # noqa: E402


def test_decode_gzip_text():
    raw = "09.06 брифинг nmlikino.ru".encode("utf-8")
    assert E._decode_transcript(_gz.compress(raw)) == "09.06 брифинг nmlikino.ru"


def test_decode_gzip_of_pdf_routes_to_extractor(monkeypatch):
    monkeypatch.setattr(E, "_extract_pdf_text", lambda body: "PDF_TEXT")
    assert E._decode_transcript(_gz.compress(b"%PDF-1.4 rubbish")) == "PDF_TEXT"


def test_decode_gzip_garbage_returns_empty():
    # битый gzip-поток → не падаем, отдаём пусто
    assert E._decode_transcript(b"\x1f\x8b\x08 broken stream") == ""
