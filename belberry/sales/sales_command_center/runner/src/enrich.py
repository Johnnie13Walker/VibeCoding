import re
import time
import urllib.request
from typing import Any

TOKEN_RE = re.compile(r"(auth|token|downloadToken|access_token)=([^&\s]+)", re.IGNORECASE)


def _mask(text: str) -> str:
    return TOKEN_RE.sub(r"\1=***", text)


def _extract_transcript_url(meeting: dict[str, Any]) -> str | None:
    value = meeting.get("ufCrm16Transcript")
    if isinstance(value, dict):
        return value.get("urlMachine") or None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("urlMachine"):
                return item["urlMachine"]
    return None


def _download_transcript(
    url: str,
    *,
    opener=urllib.request.urlopen,
    timeout: int = 120,
    retries: int = 3,
) -> bytes:
    for attempt in range(retries):
        try:
            with opener(url, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            if attempt == retries - 1:
                _mask(str(exc))
                return b""
            time.sleep(1.5 * (attempt + 1))
    return b""


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
) -> dict[int, dict[str, Any]]:
    cache = cache if cache is not None else {}
    for meeting in raw.get("meet_day", []):
        meeting_id = int(meeting["id"])
        if meeting_id in cache:
            continue
        url = _extract_transcript_url(meeting)
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
        text = body.decode("utf-8", errors="replace")
        cache[meeting_id] = {
            "text": text,
            "transcript_status": _validate_match(meeting, text),
            "url": url,
            "meeting_title": meeting.get("title"),
        }
    return cache
