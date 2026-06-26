"""Тесты бюджетирования распознавания: длинная запись не должна растягивать аудит.

Ядро фикса 24.06 (аудит #20584 висел >15 мин на полной видеозаписи встречи):
transcribe() отдаёт сегменты лениво → рвём по объёму символов и по wall-clock дедлайну,
не домалывая файл. Модель Whisper замокана — проверяем именно логику обрезки."""

import time

from src import call_audio as ca


class _Seg:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    """Отдаёт бесконечный поток сегментов; считает, сколько реально запросили
    (ленивость → ранний выход экономит счёт, что и проверяем)."""

    def __init__(self, sink, per_seg_text="абвгде ", sleep=0.0):
        self.sink = sink
        self.per_seg_text = per_seg_text
        self.sleep = sleep

    def transcribe(self, path, **kwargs):
        # beam_size=1 должен прокидываться — это часть ускорения
        assert kwargs.get("beam_size") == 1
        def gen():
            i = 0
            while True:
                i += 1
                self.sink["yielded"] = i
                if self.sleep:
                    time.sleep(self.sleep)
                yield _Seg(self.per_seg_text)
        return gen(), None


def test_max_chars_stops_early(monkeypatch):
    sink = {"yielded": 0}
    monkeypatch.setattr(ca, "_get_model", lambda: _FakeModel(sink))
    text = ca._transcribe_segments("x.mp4", deadline=None, max_chars=100)
    assert text and len(text) >= 100
    # не должен молотить бесконечно — обрезался около лимита, а не на тысячах сегментов
    assert sink["yielded"] < 100


def test_deadline_stops_early(monkeypatch):
    sink = {"yielded": 0}
    # каждый сегмент «думает» 5 мс; дедлайн через 50 мс → ~десяток сегментов и стоп
    monkeypatch.setattr(ca, "_get_model", lambda: _FakeModel(sink, sleep=0.005))
    text = ca._transcribe_segments("x.mp4", deadline=time.monotonic() + 0.05, max_chars=None)
    assert text is not None
    assert sink["yielded"] < 1000  # прервался по времени, не ушёл в бесконечность


def test_empty_segments_return_none(monkeypatch):
    sink = {"yielded": 0}
    monkeypatch.setattr(ca, "_get_model", lambda: _FakeModel(sink, per_seg_text="   "))
    # только пробелы → нет полезного текста; но без лимитов это бы крутилось вечно,
    # поэтому ставим максимум, чтобы тест не завис, и ждём None (нет непустых частей)
    text = ca._transcribe_segments("x.mp4", deadline=time.monotonic() + 0.05, max_chars=None)
    assert text is None


def test_budgets_are_sane():
    # потолки должны быть конечны и в разумных пределах (минуты, не часы)
    assert 30 <= ca.CALLS_WALL_SEC <= 600
    assert 30 <= ca.VIDEO_WALL_SEC <= 600
    assert ca.CALL_MAX_CHARS >= ca.PER_CALL_CHARS  # хватает на последующую обрезку
