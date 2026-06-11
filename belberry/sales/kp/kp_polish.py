#!/usr/bin/env python3
"""Стадия polish: LLM-редактор дотягивает тексты авто-деки до клиентских.

Правка по слайдам с двумя МЕХАНИЧЕСКИМИ гардами (LLM не может ни сломать
вёрстку, ни выдумать цифру):
1. Состав HTML-тегов слайда до/после обязан совпадать (мультимножество) —
   структура неприкосновенна.
2. Числа в новом тексте — только из данных клиента или из исходного слайда;
   появилось новое число → слайд отклоняется, остаётся оригинал.

    python3 kp_polish.py <папка-клиента>   # правит kp.html на месте,
                                           # отчёт: сколько слайдов принято
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kp_insights import llm_text, pick_provider

SLIDE_RE = re.compile(r"<section class=\"slide[^\"]*\"[^>]*>.*?</section>", re.S)
TAG_RE = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)")
NUM_RE = re.compile(r"\d+(?:[   ]\d{3})+|\d+[.,]\d+|\d+")
SMALL_INT_OK = 31  # нумерация слайдов, дни, мелкие счётчики — не считаем выдумкой

SYSTEM = """Ты — редактор коммерческих предложений digital-агентства. Тебе дают
JSON с данными клиента и HTML ОДНОГО слайда деки. Перепиши русские тексты слайда
так, чтобы он говорил про ЭТОГО клиента: его ниша, его формулировки, его цифры.
Железные правила:
1. НЕ менять HTML-структуру: ни одного тега не добавить/убрать/переименовать,
   атрибуты и классы не трогать. Меняется только текст между тегами.
2. Числа использовать ТОЛЬКО из данных или уже стоящие в слайде. Новые числа
   придумывать ЗАПРЕЩЕНО.
3. Цитаты клиента — только дословные из данных.
4. Никаких «гарантируем», обещаний результата и англицизмов.
5. Если слайд уже хорош или менять нечего — верни его без изменений.
6. Объём текстов сохраняй примерно прежним: слайд 1280×800, переполнение ломает вёрстку.
7. Узлы с атрибутом data-lock НЕ редактировать — их текст обязан остаться дословно.
Ответ — ТОЛЬКО HTML секции от <section до </section>, без markdown и пояснений."""


# ── гарды (pure, под тестами) ────────────────────────────────────────────────

def tag_multiset(html: str) -> dict[str, int]:
    """Состав тегов слайда: {имя_тега: число вхождений (откр.+закр.)}."""
    counts: dict[str, int] = {}
    for t in TAG_RE.findall(html):
        counts[t.lower()] = counts.get(t.lower(), 0) + 1
    return counts


def extract_numbers(text: str) -> set[str]:
    """Нормализованные числа текста: «21 200»→21200, «1,41»→1.41."""
    out = set()
    for m in NUM_RE.findall(text):
        n = m.replace(" ", "").replace(" ", "").replace(" ", "").replace(",", ".")
        out.add(n)
    return out


def allowed_numbers(slide_html: str, data_json: str) -> set[str]:
    """Разрешённые числа: из данных клиента + из исходного слайда + мелкие."""
    return extract_numbers(slide_html) | extract_numbers(data_json) | {
        str(i) for i in range(SMALL_INT_OK + 1)}


LOCKED_RE = re.compile(r'<([a-z]+)[^>]*\bdata-lock\b[^>]*>(.*?)</\1>', re.S)


def locked_texts(html: str) -> list[str]:
    """Содержимое узлов с data-lock — редактору запрещено их менять."""
    return [m.group(2).strip() for m in LOCKED_RE.finditer(html)]


def validate_slide(original: str, polished: str, data_json: str) -> str | None:
    """None — слайд принят; иначе причина отказа."""
    polished = polished.strip()
    if not polished.startswith("<section") or not polished.endswith("</section>"):
        return "не секция"
    if tag_multiset(original) != tag_multiset(polished):
        return "изменена структура тегов"
    if locked_texts(original) != locked_texts(polished):
        return "изменён запертый текст (data-lock)"
    foreign = extract_numbers(polished) - allowed_numbers(original, data_json)
    if foreign:
        return f"выдуманные числа: {sorted(foreign)[:5]}"
    if "{{" in polished:
        return "плейсхолдеры"
    if "гарантируем" in polished.lower():
        return "обещание результата"
    return None


def split_slides(html: str) -> list[str]:
    return SLIDE_RE.findall(html)


# ── полировка ────────────────────────────────────────────────────────────────

def collect_data_json(client_dir: Path) -> str:
    """Компактный JSON всех данных клиента для промта (и для числового гарда)."""
    blob: dict = {}
    for name in ("kp_data", "insights", "metrika", "smeta"):
        p = client_dir / f"{name}.json"
        if p.exists():
            blob[name] = json.loads(p.read_text(encoding="utf-8"))
    # транскрипт и wazzup в полировку не тащим (объём); цитаты уже в insights
    if "metrika" in blob:
        blob["metrika"].pop("entry_pages", None)
    return json.dumps(blob, ensure_ascii=False)


def polish_slide(slide: str, data_json: str, provider: str, key: str) -> tuple[str, str | None]:
    """(итоговый слайд, причина отказа|None). Ошибка вызова → оригинал."""
    prompt = f"ДАННЫЕ КЛИЕНТА (JSON):\n{data_json[:24000]}\n\nСЛАЙД:\n{slide}"
    try:
        out = llm_text(prompt, SYSTEM, provider, key, max_tokens=6000)
    except Exception as e:  # noqa: BLE001
        return slide, f"вызов не удался: {e}"
    out = re.sub(r"^```(?:html)?\s*|\s*```$", "", out.strip())
    reason = validate_slide(slide, out, data_json)
    return (slide, reason) if reason else (out, None)


def polish_deck(client_dir: Path) -> int:
    prov = pick_provider()
    if not prov:
        print("⚠ нет LLM-ключа — полировка пропущена")
        return 2
    provider, key = prov
    kp_path = client_dir / "kp.html"
    html = kp_path.read_text(encoding="utf-8")
    slides = split_slides(html)
    if not slides:
        print("⚠ слайды не найдены")
        return 1
    data_json = collect_data_json(client_dir)
    print(f"  полировка: {len(slides)} слайдов, модель {provider}")

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(lambda s: polish_slide(s, data_json, provider, key), slides))

    accepted = 0
    for i, (slide, (new, reason)) in enumerate(zip(slides, results), 1):
        if reason is None and new != slide:
            html = html.replace(slide, new, 1)
            accepted += 1
        elif reason:
            print(f"  слайд {i:02d}: оставлен оригинал ({reason})")
    kp_path.write_text(html, encoding="utf-8")
    print(f"  принято правок: {accepted} из {len(slides)}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: kp_polish.py <папка-клиента>")
        return 1
    return polish_deck(Path(sys.argv[1]))


if __name__ == "__main__":
    sys.exit(main())
