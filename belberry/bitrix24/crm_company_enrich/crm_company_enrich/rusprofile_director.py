"""Парсер блока «Руководитель» на rusprofile."""
from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass


@dataclass
class DirectorInfo:
    inn: str = ""
    full_name: str = ""
    post: str = ""
    person_url: str = ""


PERSON_URL_RE = re.compile(r"/person/[a-z0-9\-]+-(\d{12})(?=[/?#\"']|$)", re.IGNORECASE)
HREF_RE = re.compile(r"<a\b[^>]*href=[\"'](?P<href>/person/[^\"']+)[\"'][^>]*>(?P<text>.*?)</a>", re.IGNORECASE | re.DOTALL)


def parse_director_from_rusprofile_html(html: str) -> DirectorInfo | None:
    """Парсит блок «Руководитель» в HTML карточки rusprofile."""
    if not html:
        return None

    candidates = _director_sections(html)
    for section in candidates:
        info = _parse_director_link(section)
        if info:
            return info
    return _parse_director_link(html)


def _extract_inn_from_person_url(url: str) -> str:
    match = PERSON_URL_RE.search(str(url or ""))
    return match.group(1) if match else ""


def _normalize_full_name(raw: str) -> str:
    value = _strip_tags(raw)
    value = value.replace("-", " ")
    # Убираем placeholder-маркер «!» (BP 8618 создавал контакты с
    # LAST_NAME="! Фамилия" — типичный мусор, который остаётся в Bitrix).
    value = re.sub(r"^\s*!+\s*", "", value)
    value = re.sub(r"\s+!+\s+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _director_sections(html: str) -> list[str]:
    sections: list[str] = []
    for match in re.finditer(r"руководител[ьяи]?", html, flags=re.IGNORECASE):
        start = max(0, match.start() - 600)
        end = min(len(html), match.end() + 3000)
        sections.append(html[start:end])
    return sections


def _parse_director_link(section: str) -> DirectorInfo | None:
    for match in HREF_RE.finditer(section):
        href = html_lib.unescape(match.group("href"))
        inn = _extract_inn_from_person_url(href)
        if not inn:
            continue
        full_name = _normalize_full_name(match.group("text"))
        return DirectorInfo(
            inn=inn,
            full_name=full_name,
            post=_extract_post(section, match.start()),
            person_url=href,
        )
    return None


def _extract_post(section: str, link_start: int) -> str:
    before = _strip_tags(section[max(0, link_start - 500):link_start]).lower()
    if "генеральный директор" in before:
        return "Генеральный директор"
    if "директор" in before:
        return "Директор"
    if "руководитель" in before:
        return "Руководитель"
    return ""


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return html_lib.unescape(re.sub(r"\s+", " ", text)).strip()
