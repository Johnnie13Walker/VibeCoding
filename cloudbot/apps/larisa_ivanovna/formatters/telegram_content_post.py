"""Telegram-friendly форматирование черновика поста."""

from __future__ import annotations

from ..schemas.content import ContentPostDraft


def format_telegram_content_post(draft: ContentPostDraft, *, topic_index: int) -> str:
    lines = [
        f"📝 Черновик по теме {topic_index}",
        "",
        f"Тема: {draft.theme.title}",
        f"Угол: {draft.theme.angle}",
        f"Режим: {draft.tone}",
        "",
        f"Хук: {draft.hook}",
        "",
        "План:",
    ]
    lines.extend(f"- {item}" for item in draft.outline)
    lines.extend(["", "Черновик:", draft.post_text])
    return "\n".join(lines)
