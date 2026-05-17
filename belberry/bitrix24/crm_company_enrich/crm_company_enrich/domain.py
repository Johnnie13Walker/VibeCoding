"""Нормализация домена из TITLE компании или поля WEB.

Скопировано из crm_deal_merge.domain. Используется при попытке вытащить из
TITLE/WEB компании домен сайта-кандидата для enrich_web.
"""
from __future__ import annotations

import re

DOMAIN_RE = re.compile(
    r"([a-zA-Z0-9\-Ѐ-ӿ]+(?:\.[a-zA-Z0-9\-Ѐ-ӿ]+)*\.(?:ru|com|info|net|org|moscow|tech|рф|spb|me|io|ai))",
    re.IGNORECASE,
)

STRIP_PREFIXES = {
    "www",
    "new",
    "shop",
    "spb",
    "msk",
    "moscow",
    "kazan",
    "ekaterinburg",
    "novosibirsk",
    "krasnodar",
    "pushkino",
    "korolev",
    "rostov",
    "perm",
    "tula",
    "ufa",
    "samara",
    "voronezh",
    "kaliningrad",
    "vladivostok",
    "irkutsk",
}


def normalize_domain(title: str | None) -> str | None:
    if not title:
        return None
    m = DOMAIN_RE.search(title.lower().strip())
    if not m:
        return None
    domain = m.group(1).strip(".-")
    parts = domain.split(".")
    while len(parts) > 2 and parts[0] in STRIP_PREFIXES:
        parts = parts[1:]
    if len(parts) < 2:
        return None
    canonical_base = parts[-2].replace("-", "")
    canonical_tld = parts[-1]
    return f"{canonical_base}.{canonical_tld}"
