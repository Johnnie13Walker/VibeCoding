"""Атрибуция Wazzup-диалогов конкретному менеджеру по тексту сообщения.

Все Wazzup-сообщения приходят в timeline от технического пользователя интеграции
(AUTHOR_ID=2358), реальный отправитель закодирован в теле комментария:

    [img]...png[/img]&nbsp; Егор Семенихин: текст сообщения

Исходящие сообщения подписаны именем нашего сотрудника, входящие — именем клиента
(или служебной подписью «Телефон»/«WAZZUP»). Чтобы чаты попадали в «Опер» тому,
кто реально вёл переписку (включая ТМ, которые часто не ответственные за сделку),
парсим отправителя и сопоставляем с полным справочником сотрудников Bitrix.

Диалог = сделка, в переписке которой менеджер написал хотя бы одно сообщение за
целевой день; засчитывается этому менеджеру (одна сделка — один диалог в день).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

_IMG_RE = re.compile(r"\[img\][^\[]*\[/img\]", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_EMOJI_RE = re.compile(r":[0-9a-f]{6,}:")  # вырезаем эмодзи-коды вида :f09f918b:
_TOKEN_RE = re.compile(r"[^а-яёa-z]+")


def _tokens(text: str) -> set[str]:
    """Значимые токены имени (≥2 буквы), регистр/латиница/кириллица нормализованы."""
    return {t for t in _TOKEN_RE.split((text or "").lower()) if len(t) >= 2}


def parse_sender(comment: str | None) -> str | None:
    """Имя отправителя — текст до первого двоеточия (служебная разметка убрана)."""
    if not comment:
        return None
    body = _IMG_RE.sub(" ", str(comment))
    body = _TAG_RE.sub(" ", body)
    body = body.replace("&nbsp;", " ").replace("\xa0", " ")
    body = _EMOJI_RE.sub(" ", body).strip()
    m = re.match(r"\s*([^:]{1,40}?):", body)
    if not m:
        return None
    sender = m.group(1).strip()
    return sender or None


def build_employee_index(employees: Mapping[Any, str]) -> list[tuple[str, frozenset[str]]]:
    """[(employee_id, {токены ФИО})] для сотрудников с ≥2 токенами имени.

    Имена с одним токеном (только «Анна») отбрасываем — слишком неоднозначны,
    дали бы ложные совпадения с клиентами.
    """
    index: list[tuple[str, frozenset[str]]] = []
    for emp_id, name in (employees or {}).items():
        toks = _tokens(name)
        if len(toks) >= 2:
            index.append((str(emp_id), frozenset(toks)))
    return index


def match_sender(sender: str | None, index: list[tuple[str, frozenset[str]]]) -> str | None:
    """ID сотрудника, если отправитель ОДНОЗНАЧНО совпал по всем токенам ФИО.

    Совпадение = все токены имени сотрудника содержатся в имени отправителя
    («Дудин Петр» ⊆ «Петр Дудин»). Неоднозначные (>1 сотрудник) и ненайденные
    (клиенты, «Телефон»/«WAZZUP») → None, чтобы не приписать чужой диалог.
    """
    if not sender:
        return None
    stoks = _tokens(sender)
    if not stoks:
        return None
    hits = [emp_id for emp_id, toks in index if toks <= stoks]
    return hits[0] if len(hits) == 1 else None


def attribute_dialogs(
    wazzup: Mapping[Any, Iterable[Mapping[str, Any]]] | None,
    employees: Mapping[Any, str],
    d0: str,
    d1: str,
) -> dict[str, int]:
    """Число Wazzup-диалогов на менеджера за день — по фактическому отправителю.

    Для каждой сделки: если менеджер (распознанный по подписи) написал хотя бы одно
    сообщение в окне [d0, d1], сделка засчитывается ему как один диалог.
    """
    index = build_employee_index(employees)
    counts: dict[str, int] = {}
    for _deal_id, comments in (wazzup or {}).items():
        managers_today: set[str] = set()
        for c in comments or []:
            created = str(c.get("CREATED") or "")
            if not (d0 <= created <= d1):
                continue
            emp_id = match_sender(parse_sender(c.get("COMMENT")), index)
            if emp_id is not None:
                managers_today.add(emp_id)
        for emp_id in managers_today:
            counts[emp_id] = counts.get(emp_id, 0) + 1
    return counts
