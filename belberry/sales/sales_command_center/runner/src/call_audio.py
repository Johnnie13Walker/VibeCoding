"""Расшифровка и подготовка к анализу записей звонков сделки.

Источник аудио — Voximplant/Calltouch: `voximplant.statistic.get` отдаёт
`CALL_RECORD_URL` (прямая ссылка на запись). Записи живут ~1–3 мес, потом
Calltouch отдаёт 404 — для старых сделок аудио недоступно (честно помечаем
status='expired'). Транскрипция — faster-whisper, офлайн, модель из кэша.

Тяжёлая часть (Whisper) ленивая и за флагом SCC_AUDIO — чтобы детерминированный
аудит и cron не зависели от наличия модели/времени на распознавание.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from typing import Any

import requests

from . import bx_client

WHISPER_MODEL = os.environ.get("SCC_WHISPER_MODEL", "small")  # small=быстро, medium=точнее
# Бюджет на распознавание: чтобы интерактивный аудит не висел минутами, берём не
# больше N самых свежих звонков и суммарно не больше ~12 минут аудио.
MAX_CALLS = int(os.environ.get("SCC_AUDIO_MAX_CALLS", "6"))
MAX_TOTAL_SEC = int(os.environ.get("SCC_AUDIO_MAX_TOTAL_SEC", "720"))
MIN_DURATION = int(os.environ.get("SCC_AUDIO_MIN_SEC", "25"))  # < этого — не разговор

# Whisper на CPU идёт примерно в реальном времени, поэтому длинная видеозапись
# встречи (30–45 мин) одна растягивала аудит на полчаса. transcribe() отдаёт сегменты
# ЛЕНИВО (генератор) → рвём цикл по wall-clock дедлайну и по объёму текста, не домалывая
# файл. Это держит интерактивный аудит в разумных минутах независимо от длины записи.
CALLS_WALL_SEC = int(os.environ.get("SCC_AUDIO_CALLS_WALL_SEC", "150"))  # на ВСЕ звонки суммарно
VIDEO_WALL_SEC = int(os.environ.get("SCC_AUDIO_VIDEO_WALL_SEC", "180"))  # на одну видеозапись
CALL_MAX_CHARS = int(os.environ.get("SCC_AUDIO_CALL_MAX_CHARS", "3000"))  # потом обрежется до PER_CALL_CHARS
VIDEO_MAX_CHARS = int(os.environ.get("SCC_AUDIO_VIDEO_MAX_CHARS", "14000"))  # ~суть встречи, потом обрезка
# Видеовстреча бывает 1–2 часа и при прямой подаче в faster-whisper съедает >3 ГБ RAM
# → OOM-kill воркера (сервер 3.7 ГБ). Поэтому сначала ПОТОКОВО извлекаем аудиодорожку
# в маленький wav (16кГц моно), обрезая по времени — память не зависит от размера видео.
VIDEO_MAX_SEC = int(os.environ.get("SCC_AUDIO_VIDEO_MAX_SEC", "1200"))  # первые 20 мин встречи
# Сервис-аккаунт Google для скачивания видеозаписей встреч с Drive. Чтобы он видел
# запись, папку записей нужно расшарить на его email (см. SA .json client_email).
GOOGLE_SA = os.environ.get(
    "GOOGLE_SA_JSON",
    "/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json",
)
_MODEL = None  # ленивый кэш модели на процесс


def audio_enabled() -> bool:
    return os.environ.get("SCC_AUDIO", "0") == "1"


def _digits(phone: Any) -> str:
    return re.sub(r"\D", "", str(phone or ""))[-10:]


def _deal_phones(ctx: dict) -> set[str]:
    phones: set[str] = set()
    for src in (ctx.get("contact") or {}, ctx.get("company") or {}):
        for v in (src.get("PHONE") or []):
            d = _digits(v.get("VALUE") if isinstance(v, dict) else v)
            if len(d) == 10:
                phones.add(d)
    # из активностей-звонков (SUBJECT часто содержит номер)
    for a in ctx.get("activities") or []:
        if str(a.get("TYPE_ID")) == "2":
            for m in re.findall(r"\d[\d\s\-()]{9,}", a.get("SUBJECT", "")):
                d = _digits(m)
                if len(d) == 10:
                    phones.add(d)
    return phones


def _phone_formats(core10: str) -> list[str]:
    # Voximplant матчит по конкретному формату номера: на этом портале записи
    # лежат под «+7XXXXXXXXXX». Пробуем несколько вариантов и дедуплицируем по ID.
    return [f"+7{core10}", f"7{core10}", f"8{core10}", core10]


def list_recordings(ctx: dict) -> list[dict[str, Any]]:
    """Записи звонков по сделке через voximplant, с URL и признаком жив/стёрт.
    Возвращает метаданные (без скачивания) — дёшево, можно показать всегда."""
    phones = _deal_phones(ctx)
    seen: dict[str, dict] = {}
    formats = [fmt for core in phones for fmt in _phone_formats(core)]
    for ph in formats:
        resp = bx_client.call("voximplant.statistic.get", {"FILTER": {"PHONE_NUMBER": ph}})
        for c in resp.get("result") or []:
            cid = str(c.get("ID"))
            if cid in seen:
                continue
            seen[cid] = {
                "id": cid,
                "date": c.get("CALL_START_DATE"),
                "duration": int(c.get("CALL_DURATION") or 0),
                "direction": c.get("CALL_TYPE"),  # 1=исх, 2=вх
                "user_id": c.get("PORTAL_USER_ID"),
                "url": c.get("CALL_RECORD_URL") or "",
            }
    recs = sorted(seen.values(), key=lambda r: r["date"] or "", reverse=True)
    return recs


def _get_model():
    global _MODEL
    if _MODEL is None:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from faster_whisper import WhisperModel  # ленивый тяжёлый импорт

        _MODEL = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _MODEL


def _extract_audio_to_wav(src_path: str, dst_wav: str, max_sec: int) -> bool:
    """Потоково декодирует аудиодорожку media-файла в маленький wav (16кГц моно s16),
    обрезая по времени. Декод по кадру → пиковая память не растёт с длиной/размером видео
    (фикс OOM на часовых видеовстречах). Вернёт True, если что-то записали."""
    import wave

    import av  # бандлится с faster-whisper (PyAV)

    container = av.open(src_path)
    astream = next((s for s in container.streams if s.type == "audio"), None)
    if astream is None:
        container.close()
        return False
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    wrote = False
    wf = wave.open(dst_wav, "wb")
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(16000)
    try:
        for frame in container.decode(astream):
            for rf in resampler.resample(frame):
                wf.writeframes(bytes(rf.planes[0]))
                wrote = True
            if frame.time is not None and frame.time >= max_sec:
                break
    finally:
        wf.close()
        container.close()
    return wrote


def _transcribe_segments(path: str, deadline: float | None, max_chars: int | None) -> str | None:
    """Распознаёт файл, прерываясь по wall-clock дедлайну/объёму. faster-whisper отдаёт
    сегменты лениво — ранний выход реально экономит счёт, а не только обрезает результат.
    beam_size=1 (greedy) — на CPU в 2–4× быстрее дефолтного beam=5 при минимальной потере."""
    segments, _ = _get_model().transcribe(path, language="ru", vad_filter=True, beam_size=1)
    parts, total = [], 0
    for s in segments:
        t = s.text.strip()
        if t:
            parts.append(t)
            total += len(t) + 1
        if max_chars and total >= max_chars:
            break
        if deadline and time.monotonic() >= deadline:
            break
    return " ".join(parts) or None


def _download(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=60)
    except Exception:
        return None
    ct = r.headers.get("Content-Type", "")
    body = r.content
    # Calltouch на стёртой записи отдаёт HTML 404 — отсеиваем не-аудио
    if r.status_code != 200 or "audio" not in ct and not body[:3] == b"ID3" and b"<html" in body[:200].lower():
        return None
    if b"<html" in body[:200].lower():
        return None
    return body


def _transcribe_file(path: str, deadline: float | None = None, max_chars: int | None = None) -> str | None:
    # faster-whisper читает и аудио, и видео-контейнеры (PyAV декодирует дорожку).
    return _transcribe_segments(path, deadline, max_chars)


def transcribe_url(url: str, deadline: float | None = None) -> str | None:
    body = _download(url)
    if not body:
        return None
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as f:
        f.write(body)
        f.flush()
        return _transcribe_file(f.name, deadline=deadline, max_chars=CALL_MAX_CHARS)


# ── Видеозаписи встреч (Google Drive через сервис-аккаунт) ────────────────────
def _drive_file_id(url: str) -> str | None:
    if not url:
        return None
    m = re.search(r"/d/([\w-]{20,})", url) or re.search(r"[?&]id=([\w-]{20,})", url)
    return m.group(1) if m else None


def _drive_download(file_id: str, dest: str) -> tuple[bool, str]:
    """Скачать файл Drive сервис-аккаунтом. Вернёт (ok, reason)."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
    except Exception:
        return False, "google libs not installed"
    if not os.path.exists(GOOGLE_SA):
        return False, "no SA json"
    try:
        cred = service_account.Credentials.from_service_account_file(
            GOOGLE_SA, scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        svc = build("drive", "v3", credentials=cred)
        req = svc.files().get_media(fileId=file_id, supportsAllDrives=True)
        with open(dest, "wb") as fh:
            dl = MediaIoBaseDownload(fh, req)
            done = False
            while not done:
                _, done = dl.next_chunk()
        return True, "ok"
    except Exception as exc:
        msg = str(exc)
        if "404" in msg or "notFound" in msg:
            return False, "нет доступа (расшарить запись на сервис-аккаунт)"
        return False, msg[:120]


def transcribe_meeting_video(url: str) -> tuple[str | None, str]:
    """Видеозапись встречи → текст. Вернёт (text|None, status).
    Поддерживает Google Drive (через сервис-аккаунт) и прямые URL."""
    fid = _drive_file_id(url)
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as f, \
            tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as w:
        if fid:
            ok, reason = _drive_download(fid, f.name)
            if not ok:
                return None, reason
        else:
            body = _download(url)
            if not body:
                return None, "download failed"
            f.write(body)
            f.flush()
        # Сначала ПОТОКОВО вытаскиваем первые VIDEO_MAX_SEC аудио в маленький wav — иначе
        # часовое видео грузится в память целиком и убивает воркер по OOM. Дальше Whisper
        # читает уже крошечный wav. + wall-clock и лимит символов (чтобы не растягивало аудит).
        try:
            if not _extract_audio_to_wav(f.name, w.name, VIDEO_MAX_SEC):
                return None, "no audio track"
        except Exception as exc:  # битый контейнер / нет кодека — не валим аудит
            return None, f"decode error: {type(exc).__name__}"
        text = _transcribe_file(
            w.name, deadline=time.monotonic() + VIDEO_WALL_SEC, max_chars=VIDEO_MAX_CHARS)
    return (text, "ok") if text else (None, "empty transcript")


def transcribe_deal_calls(ctx: dict) -> list[dict[str, Any]]:
    """Расшифровки звонков сделки. Без флага SCC_AUDIO — пустой список.
    Каждый элемент: дата/длительность/направление + transcript|status."""
    if not audio_enabled():
        return []
    recs = [r for r in list_recordings(ctx) if r["duration"] >= MIN_DURATION]
    out: list[dict[str, Any]] = []
    spent = 0  # суммарная длительность уже распознанного аудио, сек
    wall_deadline = time.monotonic() + CALLS_WALL_SEC  # общий потолок реального времени на все звонки
    for r in recs[:MAX_CALLS]:
        item = {k: r[k] for k in ("date", "duration", "direction", "user_id")}
        budget_out = spent >= MAX_TOTAL_SEC or time.monotonic() >= wall_deadline
        if r["url"] and budget_out:
            item["status"] = "skipped_budget"  # бюджет (аудио/время) исчерпан — не висим
            out.append(item)
            continue
        if not r["url"]:
            item["status"] = "no_url"
        else:
            text = None
            try:
                text = transcribe_url(r["url"], deadline=wall_deadline)
            except Exception as exc:  # модель недоступна / битый файл — не валим аудит
                item["status"] = f"error:{type(exc).__name__}"
            if text:
                item["status"] = "ok"
                item["transcript"] = text
                spent += int(r["duration"] or 0)  # учёт бюджета аудио
            elif "status" not in item:
                item["status"] = "expired"  # 404/нет аудио — стёрта по ретенции
        out.append(item)
    return out


# Потолок длины одной расшифровки в промпте: длинные звонки целиком раздувают
# контекст LLM (наблюдалось — модель возвращала пустой разбор). 2500 символов
# (~400 слов) достаточно, чтобы понять суть разговора.
PER_CALL_CHARS = int(os.environ.get("SCC_AUDIO_CALL_CHARS", "2500"))


def format_for_llm(calls: list[dict[str, Any]]) -> str:
    lines = []
    for c in calls:
        head = f"[{(c.get('date') or '')[:16]}] звонок {c.get('duration')}с"
        if c.get("status") == "ok":
            text = (c.get("transcript") or "")[:PER_CALL_CHARS]
            lines.append(f"{head}:\n{text}")
        else:
            lines.append(f"{head}: запись недоступна ({c.get('status')})")
    return "\n\n".join(lines)
