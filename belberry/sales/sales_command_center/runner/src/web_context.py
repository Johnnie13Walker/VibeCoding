"""Внешний контекст сделки: аудит СМОТРИТ на сайт клиента, а не только в CRM.

Домен берём из карточки/названия сделки (у Belberry TITLE сделки = домен). Фетч строго
fail-safe — любой сбой даёт пусто, аудит идёт дальше. SSL у мелких клиник часто кривой,
поэтому verify=False (читаем публичную маркетинг-страницу, секреты не шлём). Отзывы и
конкуренты потребуют поискового ключа (Exa/2GIS) — это следующий шаг, не здесь.

Включается флагом SCC_WEB_CONTEXT=1 (по умолчанию вкл). Любая ошибка — тихо None.
"""

from __future__ import annotations

import html as _html
import os
import re

import requests

try:  # глушим предупреждения о verify=False
    import urllib3

    urllib3.disable_warnings()
except Exception:  # pragma: no cover
    pass

WEB_CONTEXT_ON = os.environ.get("SCC_WEB_CONTEXT", "1") == "1"
SITE_MAX_CHARS = int(os.environ.get("SCC_SITE_MAX_CHARS", "6000"))
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BelberryAudit/1.0)"}
_TIMEOUT = int(os.environ.get("SCC_SITE_TIMEOUT", "12"))


def _domain_from(*candidates: str | None) -> str | None:
    """Достаёт домен из строк (название сделки/поля). Поддерживает кириллические .рф."""
    for s in candidates:
        if not s:
            continue
        low = str(s).lower().strip()
        low = re.sub(r"^https?://", "", low).split("/")[0]
        m = re.search(r"([a-z0-9а-яё-]+(?:\.[a-z0-9а-яё-]+)*\.(?:[a-z]{2,}|рф|москва))", low)
        if m:
            return m.group(1).strip(".")
    return None


def _idna(domain: str) -> str:
    try:
        return domain.encode("idna").decode()
    except Exception:
        return domain


def _strip_html(t: str) -> str:
    t = re.sub(r"(?is)<(script|style|head|nav|footer|svg)[^>]*>.*?</\1>", " ", t or "")
    t = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr)\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _html.unescape(t).replace("\xa0", " ").replace("\r", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def _fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, verify=False)
    except Exception:
        return None
    if r.status_code == 200 and "html" in r.headers.get("Content-Type", "").lower():
        return r.text
    return None


def site_snapshot(domain: str | None) -> dict | None:
    """Снимок сайта клиента: заголовок + текст главной (без скриптов/навигации), обрезано."""
    if not domain:
        return None
    host = _idna(domain)
    raw = None
    used = None
    for url in (f"https://{host}", f"https://www.{host}", f"http://{host}"):
        raw = _fetch(url)
        if raw:
            used = url
            break
    if not raw:
        return {"domain": domain, "ok": False}
    title = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    if m:
        title = _strip_html(m.group(1))[:160]
    return {"domain": domain, "ok": True, "url": used, "title": title,
            "text": _strip_html(raw)[:SITE_MAX_CHARS]}


def deal_external_context(deal: dict) -> dict | None:
    """Внешний контекст сделки. Сейчас — снимок сайта клиента (домен из TITLE)."""
    if not WEB_CONTEXT_ON:
        return None
    domain = _domain_from(deal.get("TITLE"), deal.get("UF_CRM_1571030060"))
    snap = site_snapshot(domain)
    return {"site": snap} if snap else None
