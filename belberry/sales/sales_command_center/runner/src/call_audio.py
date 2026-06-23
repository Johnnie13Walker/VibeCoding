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
from typing import Any

import requests

from . import bx_client

WHISPER_MODEL = os.environ.get("SCC_WHISPER_MODEL", "small")  # small=быстро, medium=точнее
MAX_CALLS = int(os.environ.get("SCC_AUDIO_MAX_CALLS", "12"))
MIN_DURATION = int(os.environ.get("SCC_AUDIO_MIN_SEC", "25"))  # < этого — не разговор
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


def _transcribe_file(path: str) -> str | None:
    # faster-whisper читает и аудио, и видео-контейнеры (PyAV декодирует дорожку).
    segments, _ = _get_model().transcribe(path, language="ru", vad_filter=True)
    parts = [s.text.strip() for s in segments if s.text.strip()]
    return " ".join(parts) or None


def transcribe_url(url: str) -> str | None:
    body = _download(url)
    if not body:
        return None
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as f:
        f.write(body)
        f.flush()
        return _transcribe_file(f.name)


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
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as f:
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
        text = _transcribe_file(f.name)
    return (text, "ok") if text else (None, "empty transcript")


def transcribe_deal_calls(ctx: dict) -> list[dict[str, Any]]:
    """Расшифровки звонков сделки. Без флага SCC_AUDIO — пустой список.
    Каждый элемент: дата/длительность/направление + transcript|status."""
    if not audio_enabled():
        return []
    recs = [r for r in list_recordings(ctx) if r["duration"] >= MIN_DURATION]
    out: list[dict[str, Any]] = []
    for r in recs[:MAX_CALLS]:
        item = {k: r[k] for k in ("date", "duration", "direction", "user_id")}
        if not r["url"]:
            item["status"] = "no_url"
        else:
            text = None
            try:
                text = transcribe_url(r["url"])
            except Exception as exc:  # модель недоступна / битый файл — не валим аудит
                item["status"] = f"error:{type(exc).__name__}"
            if text:
                item["status"] = "ok"
                item["transcript"] = text
            elif "status" not in item:
                item["status"] = "expired"  # 404/нет аудио — стёрта по ретенции
        out.append(item)
    return out


def format_for_llm(calls: list[dict[str, Any]]) -> str:
    lines = []
    for c in calls:
        head = f"[{(c.get('date') or '')[:16]}] звонок {c.get('duration')}с"
        if c.get("status") == "ok":
            lines.append(f"{head}:\n{c.get('transcript','')}")
        else:
            lines.append(f"{head}: запись недоступна ({c.get('status')})")
    return "\n\n".join(lines)
