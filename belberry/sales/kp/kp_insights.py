#!/usr/bin/env python3
"""Смысловой слой КП: бриф + транскрипт встречи + сайт клиента → боли и решения.

LLM-проход (Anthropic API, ключ ANTHROPIC_API_KEY из окружения — на проде он в
scc.env) по правилам анти-выдумки: цитаты ТОЛЬКО дословные из материалов, каждая
проблема сайта — с указанием, что именно на сайте увидели/не увидели. Нет
материала — пустые списки, это честный результат.

    python3 kp_insights.py <папка-клиента>   # читает bitrix.json (+audit.json),
                                             # краулит сайт, пишет insights.json
"""

from __future__ import annotations

import html as html_mod
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
API_URL = "https://api.anthropic.com/v1/messages"
OPENAI_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MAX_TRANSCRIPT = 14_000   # символов транскрипта в промт
MAX_PAGE = 4_000          # символов текста одной страницы сайта
MAX_PAGES = 4             # сколько внутренних страниц краулим

SYSTEM = """Ты — коммерческий аналитик digital-агентства. По брифу клиента,
транскрипту встречи и тексту страниц его сайта найди боли клиента и проблемы
сайта, мешающие получать заявки. Правила железные:
1. Цитаты — ТОЛЬКО дословные фрагменты из брифа или транскрипта. Не перефразируй.
2. Проблема сайта существует, только если ты видишь её в переданном тексте страниц
   (чего-то нет, что-то спрятано, тексты слабые) — укажи, что именно увидел.
3. Ничего не выдумывай. Мало материала — верни пустые списки.
Ответ — строго JSON без markdown:
{"pains": [{"pain": "боль одной фразой", "quote": "дословная цитата",
            "source": "бриф|встреча"}],
 "site_issues": [{"issue": "что не так на сайте", "evidence": "что видно в тексте
                  страницы (дословный признак)", "action": "что делаем"}],
 "key_argument": "главный аргумент продажи для этого клиента, 1-2 фразы",
 "next_step": "какой следующий шаг предложить клиенту"}
Боли — максимум 4, проблемы сайта — максимум 4. Пиши по-русски, без англицизмов."""


# ── сбор материала ───────────────────────────────────────────────────────────

def fetch_text(url: str, limit: int = MAX_PAGE) -> str:
    """Текст страницы без разметки (stdlib, как в build_kp)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "ignore")
    raw = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    text = html_mod.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text).strip()[:limit]


INNER_HINTS = ("uslug", "service", "price", "цен", "catalog", "product", "about", "o-kompanii")


def pick_inner_links(home_html: str, base: str, limit: int = MAX_PAGES) -> list[str]:
    """До N внутренних страниц по говорящим ссылкам (услуги/цены/каталог/о компании)."""
    seen, out = set(), []
    for href in re.findall(r'href="([^"#?]+)"', home_html):
        if href.startswith("http") and base not in href:
            continue
        path = href if href.startswith("/") else "/" + href.split(base, 1)[-1].lstrip("/")
        if any(h in path.lower() for h in INNER_HINTS) and path not in seen and len(path) > 2:
            seen.add(path)
            out.append(f"https://{base}{path}")
            if len(out) >= limit:
                break
    return out


def collect_site(domain: str) -> dict[str, str]:
    """Главная + внутренние страницы → {url: текст}. Ошибки страниц не фатальны."""
    pages: dict[str, str] = {}
    try:
        req = urllib.request.Request(f"https://{domain}/", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            home_raw = r.read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        return {f"https://{domain}/": f"(сайт недоступен: {e})"}
    home_text = re.sub(r"<[^>]+>", " ", re.sub(
        r"<(script|style)[^>]*>.*?</\1>", " ", home_raw, flags=re.S | re.I))
    pages[f"https://{domain}/"] = re.sub(r"\s+", " ", html_mod.unescape(home_text)).strip()[:MAX_PAGE]
    for url in pick_inner_links(home_raw, domain):
        try:
            pages[url] = fetch_text(url)
        except Exception:  # noqa: BLE001
            continue
    return pages


def build_prompt(bitrix: dict, pages: dict[str, str]) -> str:
    """Материал для модели: бриф целиком, транскрипт (обрезан), страницы сайта."""
    parts = []
    brief = bitrix.get("brief") or {}
    if brief:
        parts.append("=== БРИФ КЛИЕНТА ===\n" + "\n".join(
            f"{k}: {v}" for k, v in brief.items()))
    tr = bitrix.get("transcript")
    if tr and len(tr.strip()) > 50:
        parts.append("=== ТРАНСКРИПТ ВСТРЕЧИ ===\n" + tr.strip()[:MAX_TRANSCRIPT])
    for url, text in pages.items():
        parts.append(f"=== СТРАНИЦА САЙТА {url} ===\n{text}")
    return "\n\n".join(parts)


# ── LLM ──────────────────────────────────────────────────────────────────────

def pick_provider() -> tuple[str, str] | None:
    """(провайдер, ключ): Anthropic в приоритете, OpenAI как на проде SCC."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", os.environ["ANTHROPIC_API_KEY"]
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", os.environ["OPENAI_API_KEY"]
    return None


def llm_text(prompt: str, system: str, provider: str, api_key: str,
             max_tokens: int = 4000, timeout: int = 240) -> str:
    """Универсальный вызов LLM (OpenAI на проде / Anthropic локально), сырой текст."""
    if provider == "openai":
        body = json.dumps({
            "model": OPENAI_MODEL,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            # новые модели OpenAI (gpt-5.x) не принимают max_tokens
            "max_completion_tokens": max_tokens,
        }).encode()
        req = urllib.request.Request(OPENAI_URL, data=body, headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + api_key})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read())
        return resp["choices"][0]["message"]["content"]
    body = json.dumps({
        "model": MODEL, "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "Content-Type": "application/json", "x-api-key": api_key,
        "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    return "".join(b.get("text", "") for b in resp.get("content", []))


def call_llm(prompt: str, provider: str, api_key: str) -> dict:
    return parse_insights(llm_text(prompt, SYSTEM, provider, api_key))


def parse_insights(text: str) -> dict:
    """Строгий разбор JSON-ответа (модель может обернуть в ```)."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("в ответе модели нет JSON")
    data = json.loads(m.group(0))
    return {"pains": data.get("pains") or [],
            "site_issues": data.get("site_issues") or [],
            "key_argument": data.get("key_argument") or "",
            "next_step": data.get("next_step") or ""}


# ── рендер в деку ────────────────────────────────────────────────────────────

def render_pains_html(insights: dict, contact_name: str | None = None) -> str | None:
    """Слайд «Боли — вашими словами» как чат со встречи (маркер AUTO:PAINS).

    Слева — дословные цитаты пузырями переписки (аватар-инициал клиента),
    справа — нумерованные выводы и главный аргумент бренд-плашкой.
    """
    pains = insights.get("pains") or []
    if not pains:
        return None
    esc = html_mod.escape
    name = (contact_name or "").strip()
    initial = name[:1].upper() if name else "К"
    bubbles, conclusions = [], []
    for i, p in enumerate(pains[:4]):
        src = "встреча" if p.get("source") == "встреча" else "бриф"
        who = f"{esc(name)} · {src}" if name else src
        bubbles.append(
            f'<div style="display:flex;gap:10px;align-items:flex-end;">'
            f'<span style="width:26px;height:26px;border-radius:50%;background:#3086FB;'
            f'color:#fff;display:inline-flex;align-items:center;justify-content:center;'
            f'font-size:12px;font-weight:800;flex:none;">{initial}</span>'
            f'<div style="background:#fff;border:1px solid #EDF1F7;'
            f'border-radius:16px 16px 16px 4px;padding:13px 17px;max-width:440px;'
            f'box-shadow:0 1px 2px rgba(20,40,80,.04);">'
            f'<div style="font-size:14px;line-height:1.45;color:#313131;">'
            f'«{esc(p.get("quote", ""))}»</div>'
            f'<div style="font-size:10px;color:#9aa3b2;font-weight:600;margin-top:6px;'
            f'text-align:right;">{who}</div></div></div>')
        conclusions.append(
            f'<div style="display:flex;gap:12px;align-items:flex-start;padding:12px 0;'
            f'border-bottom:1px solid #EDF1F7;">'
            f'<span style="width:24px;height:24px;border-radius:8px;background:#eaf2fe;'
            f'color:#3086FB;font-size:12px;font-weight:800;display:inline-flex;'
            f'align-items:center;justify-content:center;flex:none;">{i + 1}</span>'
            f'<div style="font-size:13.5px;line-height:1.45;color:#313131;'
            f'font-weight:600;">{esc(p.get("pain", ""))}</div></div>')
    arg = insights.get("key_argument") or ""
    arg_html = ""
    if arg:
        arg_html = (
            f'<div style="margin-top:14px;background:linear-gradient(135deg,#3086FB,#1F6FDE);'
            f'border-radius:14px;padding:17px 24px;color:#fff;">'
            f'<div style="font-size:10.5px;font-weight:800;letter-spacing:.1em;'
            f'opacity:.75;margin-bottom:6px;">ГЛАВНЫЙ АРГУМЕНТ</div>'
            f'<div style="font-size:14.5px;line-height:1.5;font-weight:600;">{esc(arg)}</div></div>')
    return ('<div style="display:grid;grid-template-columns:1.15fr 1fr;gap:26px;height:548px;">'
            '<div style="display:flex;flex-direction:column;gap:13px;justify-content:center;">'
            + "".join(bubbles) + "</div>"
            '<div style="display:flex;flex-direction:column;justify-content:center;">'
            '<div style="background:#fff;border:1px solid #EDF1F7;border-radius:14px;'
            'padding:7px 22px 5px;">' + "".join(conclusions) + "</div>"
            + arg_html + "</div></div>")


def render_site_rows(insights: dict) -> str | None:
    """Проблемы сайта → строки слайда «проблема → решение» (формат problem_solution)."""
    issues = insights.get("site_issues") or []
    if not issues:
        return None
    esc = html_mod.escape
    return "\n".join(
        f'        <tr><td class="metric">{esc(i.get("issue", ""))} — {esc(i.get("evidence", ""))}'
        f'</td><td>{esc(i.get("action", ""))}</td></tr>' for i in issues)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    if len(sys.argv) < 2:
        print("usage: kp_insights.py <папка-клиента>")
        return 1
    prov = pick_provider()
    if not prov:
        print("⚠ нет ANTHROPIC_API_KEY/OPENAI_API_KEY — смысловой слой пропущен")
        return 2
    provider, api_key = prov
    print(f"  модель: {provider} ({MODEL if provider == 'anthropic' else OPENAI_MODEL})")
    client_dir = Path(sys.argv[1])
    bitrix = json.loads((client_dir / "bitrix.json").read_text(encoding="utf-8"))
    domain = (bitrix.get("site") or bitrix.get("title") or "").strip()
    domain = re.sub(r"^https?://", "", domain).replace("www.", "").split("/")[0]
    print(f"  краулю сайт {domain}…")
    pages = collect_site(domain) if domain else {}
    prompt = build_prompt(bitrix, pages)
    print(f"  материал: бриф={len(bitrix.get('brief') or {})} полей, "
          f"транскрипт={'есть' if bitrix.get('transcript') else 'нет'}, "
          f"страниц сайта={len(pages)}")
    insights = call_llm(prompt, provider, api_key)
    (client_dir / "insights.json").write_text(
        json.dumps(insights, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  болей: {len(insights['pains'])}, проблем сайта: {len(insights['site_issues'])}"
          f" → insights.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
