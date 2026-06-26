import gzip
import io
import re
import time
import urllib.request
from typing import Any

from . import bx_client

# Смарт-процесс «Встречи» в Bitrix (entityTypeId), откуда берём UF_CRM_16_TRANSCRIPT.
MEETING_ENTITY_TYPE_ID = 1048

TOKEN_RE = re.compile(r"(auth|token|downloadToken|access_token)=([^&\s]+)", re.IGNORECASE)


def _mask(text: str) -> str:
    return TOKEN_RE.sub(r"\1=***", text)


# Поля с файлом транскрипта. Старое ufCrm16Transcript (memoai PDF) на части встреч
# пустое — транскрипт теперь кладут в новое файл-поле «Транскрибация встречи (TXT)».
# Читаем оба, по приоритету; структура у обоих — dict/list с urlMachine.
TRANSCRIPT_FIELDS = ("ufCrm16Transcript", "ufCrm16_1782395353")


def _extract_transcript_url(meeting: dict[str, Any]) -> str | None:
    for field in TRANSCRIPT_FIELDS:
        value = meeting.get(field)
        if isinstance(value, dict) and value.get("urlMachine"):
            return value["urlMachine"]
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("urlMachine"):
                    return item["urlMachine"]
    return None


def _refresh_transcript_url(meeting_id: int, client) -> str | None:
    """Свежий urlMachine транскрипта через crm.item.get.

    Токен во вшитом в сборе urlMachine короткоживущий и протухает за время
    долгого collect (особенно Wazzup ~5 мин) → к моменту скачивания 401.
    Поэтому перед загрузкой берём ссылку заново непосредственно перед download.
    """
    try:
        response = client.call(
            "crm.item.get", {"entityTypeId": MEETING_ENTITY_TYPE_ID, "id": meeting_id}
        )
    except Exception:
        return None
    item = (response.get("result") or {}).get("item") or {}
    return _extract_transcript_url(item)


def _download_transcript(
    url: str,
    *,
    opener=urllib.request.urlopen,
    timeout: int = 120,
    retries: int = 5,
) -> bytes:
    for attempt in range(retries):
        try:
            with opener(url, timeout=timeout) as response:
                body = response.read()
            if body:
                return body
            # Пустое тело при 200 — частый транзиент (короткоживущий токен/гонка
            # генерации файла на стороне Bitrix). Ретраим, как и обычную ошибку.
            if attempt == retries - 1:
                print("[enrich] download empty body after retries", flush=True)
                return b""
        except Exception as exc:
            if attempt == retries - 1:
                print(f"[enrich] download failed: {_mask(str(exc))[:200]}", flush=True)
                return b""
        time.sleep(2.0 * (attempt + 1))
    return b""


def _extract_pdf_text(body: bytes) -> str:
    """Текст из PDF-транскрипта (memoai.tech отдаёт PDF). Пусто при сбое/скан-PDF."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(body))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[enrich] PDF extract failed: {str(exc)[:200]}", flush=True)
        return ""


def _decode_transcript(body: bytes) -> str:
    """Байты транскрипта → текст. Форматы: gzip (txt от сервера часто отдаётся
    `Content-Encoding: gzip`, а urllib его не распаковывает), PDF (`%PDF-`, memoai),
    иначе plain-text UTF-8. Раньше всё декодилось как UTF-8 → мусор → LLM не читал."""
    if body[:2] == b"\x1f\x8b":  # gzip → распаковать, дальше как обычно (внутри txt или PDF)
        try:
            body = gzip.decompress(body)
        except Exception as exc:  # noqa: BLE001
            print(f"[enrich] gzip decompress failed: {str(exc)[:200]}", flush=True)
            return ""
    if body[:5] == b"%PDF-":
        return _extract_pdf_text(body)
    return body.decode("utf-8", errors="replace")


def _duration_seconds_from_text(text: str) -> int | None:
    match = re.search(r"Длительность:\s*(\d{2}):(\d{2}):(\d{2})", text)
    if not match:
        return None
    hours, minutes, seconds = [int(part) for part in match.groups()]
    return hours * 3600 + minutes * 60 + seconds


def _meeting_duration_seconds(meeting: dict[str, Any]) -> int | None:
    for key in ["duration_seconds", "duration", "DURATION"]:
        if meeting.get(key) is not None:
            try:
                return int(meeting[key])
            except (TypeError, ValueError):
                return None
    return None


def _validate_match(meeting: dict[str, Any], text: str) -> str:
    """Return mismatch only when both durations exist and diverge strongly.

    Tolerance: more than 50 percent AND more than 10 minutes absolute difference.
    Missing metadata is treated as ok so a sparse Bitrix item does not block analysis.
    """
    transcript_duration = _duration_seconds_from_text(text)
    meeting_duration = _meeting_duration_seconds(meeting)
    if not transcript_duration or not meeting_duration:
        return "ok"
    diff = abs(transcript_duration - meeting_duration)
    if diff > 600 and diff / max(meeting_duration, transcript_duration) > 0.5:
        return "mismatch"
    return "ok"


def enrich_meetings(
    raw: dict[str, Any],
    *,
    cache: dict[int, dict[str, Any]] | None = None,
    opener=urllib.request.urlopen,
    bx=None,
    refresh: bool = False,
) -> dict[int, dict[str, Any]]:
    cache = cache if cache is not None else {}
    client = bx or bx_client
    for meeting in raw.get("meet_day", []):
        meeting_id = int(meeting["id"])
        if meeting_id in cache:
            continue
        url = _extract_transcript_url(meeting)
        # Полный crm.item.get перед скачиванием: (1) токен из времени сбора мог протухнуть;
        # (2) новые файл-поля транскрипта (ufCrm16_1782395353) могут НЕ входить в select сбора,
        # и тогда в сырой встрече ссылки нет — full get их вернёт. Поэтому refresh всегда, а не
        # только когда url уже найден (иначе встречи с новым полем уходят в missing).
        if refresh:
            fresh = _refresh_transcript_url(meeting_id, client)
            if fresh:
                url = fresh
        if not url:
            cache[meeting_id] = {
                "text": "",
                "transcript_status": "missing",
                "url": None,
                "meeting_title": meeting.get("title"),
            }
            continue
        body = _download_transcript(url, opener=opener)
        if len(body) < 100:
            cache[meeting_id] = {
                "text": "",
                "transcript_status": "missing",
                "url": url,
                "meeting_title": meeting.get("title"),
            }
            continue
        text = _decode_transcript(body)
        # PDF без текстового слоя (скан) или сбой извлечения → нет пригодного транскрипта.
        if not text.strip():
            cache[meeting_id] = {
                "text": "",
                "transcript_status": "missing",
                "url": url,
                "meeting_title": meeting.get("title"),
            }
            continue
        cache[meeting_id] = {
            "text": text,
            "transcript_status": _validate_match(meeting, text),
            "url": url,
            "meeting_title": meeting.get("title"),
        }
    return cache
