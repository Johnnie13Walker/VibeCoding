"""Workflow веб-поиска Ларисы Ивановны."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Callable
from zoneinfo import ZoneInfo

from cloudbot.orchestrator.search_state import clear_search_state, load_search_state, save_search_state
from cloudbot.skills.web_search import run as web_search_skill_run

MSK_TZ = ZoneInfo("Europe/Moscow")
SPORT_CLARIFICATION_MAP = {
    "футбол": "футбольный",
    "футбольный": "футбольный",
    "хоккей": "хоккейный",
    "хоккейный": "хоккейный",
    "баскетбол": "баскетбольный",
    "баскетбольный": "баскетбольный",
}
SPORT_SIGNAL_TOKENS = ("сыграл", "матч", "счёт", "счет", "результат", "таблица")
SPORT_ENTITY_TOKENS = ("цска",)
SCORE_RE = re.compile(r"\b\d+\s*[:\-]\s*\d+\b")
QUESTION_PREFIX_RE = re.compile(
    r"^(что такое|кто такой|кто такая|кто такие|как|где|когда|почему|зачем|сколько)\s+",
    flags=re.IGNORECASE,
)
TRAILING_PUNCTUATION_RE = re.compile(r"[?!.,:;]+$")


@dataclass(frozen=True)
class SearchWorkflowDeps:
    search_runner: Callable[[dict[str, Any], dict[str, Any] | None], dict[str, Any]] = web_search_skill_run


def run_search_workflow(
    *,
    query: str,
    chat_id: str = "",
    user_id: str = "",
    deps: SearchWorkflowDeps | None = None,
) -> dict[str, object]:
    workflow_deps = deps or SearchWorkflowDeps()
    normalized_query = _normalize_query(query)
    if not normalized_query:
        return {
            "text": "Напиши, что именно найти в интернете.",
            "results": [],
            "provider": "duckduckgo",
            "query": "",
        }

    pending = load_search_state(chat_id, user_id)
    merged_query = _merge_pending_search(normalized_query, pending)
    if merged_query is not None:
        normalized_query = merged_query
        clear_search_state(chat_id, user_id)

    clarification = _build_clarification_prompt(normalized_query)
    if clarification:
        save_search_state(
            chat_id,
            user_id,
            {
                "mode": "sports_disambiguation",
                "query": normalized_query,
            },
        )
        return {
            "text": clarification,
            "results": [],
            "provider": "duckduckgo",
            "query": normalized_query,
            "needs_clarification": True,
        }

    queries = _rewrite_queries(normalized_query)
    results = _run_search_queries(queries, workflow_deps)
    if not results:
        return {
            "text": (
                f"Не смогла надёжно найти результат по запросу «{normalized_query}». "
                "Попробуй уточнить дату, регион или саму сущность запроса."
            ),
            "results": [],
            "provider": "duckduckgo",
            "query": normalized_query,
        }

    clear_search_state(chat_id, user_id)
    text = _format_answer(normalized_query, results)
    return {
        "text": text,
        "results": results,
        "provider": "duckduckgo",
        "query": normalized_query,
        "rewritten_queries": queries,
    }


def _normalize_query(query: str) -> str:
    collapsed = " ".join(str(query or "").strip().split())
    return collapsed.strip()


def _merge_pending_search(query: str, pending: dict[str, Any] | None) -> str | None:
    if not pending or str(pending.get("mode") or "") != "sports_disambiguation":
        return None
    normalized = query.lower().strip()
    sport = SPORT_CLARIFICATION_MAP.get(normalized)
    if not sport:
        return None
    original_query = str(pending.get("query") or "").strip()
    if not original_query:
        return None
    return f"{sport} {original_query}"


def _build_clarification_prompt(query: str) -> str:
    normalized = query.lower()
    if not any(token in normalized for token in SPORT_ENTITY_TOKENS):
        return ""
    if not any(token in normalized for token in SPORT_SIGNAL_TOKENS):
        return ""
    if any(token in normalized for token in SPORT_CLARIFICATION_MAP.values()):
        return ""
    if any(token in normalized for token in SPORT_CLARIFICATION_MAP):
        return ""
    return "Уточни, пожалуйста: футбольный, хоккейный или баскетбольный ЦСКА?"


def _rewrite_queries(query: str) -> list[str]:
    normalized = query.strip()
    current = datetime.now(MSK_TZ)
    queries = [normalized]
    lower = normalized.lower()
    simplified = _simplify_query(normalized)
    if simplified and simplified.lower() != lower:
        queries.append(simplified)
    if "цска" in lower and any(token in lower for token in SPORT_SIGNAL_TOKENS):
        sport = next((token for token in SPORT_CLARIFICATION_MAP.values() if token in lower), "")
        team_label = f"{sport} ЦСКА".strip() if sport else "ЦСКА"
        queries.append(f"{team_label} результат матча")
        queries.append(f"{team_label} счет матча")
        if "сегодня" in lower:
            queries.append(f"{team_label} сегодня результат матча")
            queries.append(f"{team_label} {current.strftime('%d.%m.%Y')} результат матча")
    if "сегодня" in lower:
        queries.append(lower.replace("сегодня", current.strftime("%d.%m.%Y")))
        queries.append(lower.replace("сегодня", current.strftime("%Y-%m-%d")))
    seen: set[str] = set()
    unique: list[str] = []
    for item in queries:
        prepared = " ".join(item.split()).strip()
        if prepared and prepared not in seen:
            seen.add(prepared)
            unique.append(prepared)
    return unique[:5]


def _simplify_query(query: str) -> str:
    normalized = TRAILING_PUNCTUATION_RE.sub("", query.strip())
    normalized = QUESTION_PREFIX_RE.sub("", normalized)
    normalized = " ".join(normalized.split())
    return normalized


def _run_search_queries(queries: list[str], deps: SearchWorkflowDeps) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for query in queries:
        result = deps.search_runner(
            {"query": query, "limit": 5},
            providers={"search": {"provider": "duckduckgo"}},
        )
        if not bool(result.get("ok")):
            continue
        for item in result.get("results") or []:
            url = str(item.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            merged.append(
                {
                    "title": str(item.get("title") or "").strip(),
                    "url": url,
                    "snippet": str(item.get("snippet") or "").strip(),
                }
            )
        if len(merged) >= 5:
            break
    return merged[:5]


def _format_answer(query: str, results: list[dict[str, str]]) -> str:
    score_hint = _extract_score_hint(results)
    query_lower = query.lower()
    if score_hint and any(token in query_lower for token in SPORT_SIGNAL_TOKENS):
        intro = f"По нескольким результатам чаще всего встречается счёт {score_hint}."
    elif any(token in query_lower for token in SPORT_SIGNAL_TOKENS):
        intro = "Нашла материалы по запросу, но не вижу надёжно подтверждённого точного счёта."
    else:
        intro = f"Нашла по запросу «{query}»."

    lines = [intro, "Источники:"]
    for index, item in enumerate(results[:3], start=1):
        title = item["title"] or item["url"]
        lines.append(f"{index}. {title} — {item['url']}")
    return "\n".join(lines)


def _extract_score_hint(results: list[dict[str, str]]) -> str:
    candidates: list[str] = []
    for item in results:
        haystack = " ".join((item.get("title") or "", item.get("snippet") or ""))
        for match in SCORE_RE.findall(haystack):
            prepared = match.replace(" ", "")
            if ":" not in prepared:
                prepared = prepared.replace("-", ":")
            candidates.append(prepared)
    if not candidates:
        return ""
    top_score, top_count = Counter(candidates).most_common(1)[0]
    if top_count < 2:
        return ""
    return top_score
