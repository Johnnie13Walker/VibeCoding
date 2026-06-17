"""Telegram-friendly форматирование тем для постов."""

from __future__ import annotations

from ..schemas.content import ContentTheme, ContentTopicsDigest


def _render_theme(index: int, theme: ContentTheme) -> list[str]:
    lines = [
        f"{index}. {theme.title}",
        f"Почему стоит писать: {theme.angle}",
        f"Аудитория: {theme.audience}",
        f"Формат: {theme.format}",
        f"ID темы: {theme.id}",
    ]
    if theme.evidence:
        lines.append("Фактура:")
        lines.extend(f"- {item}" for item in theme.evidence)
    return lines


def format_telegram_content_topics(digest: ContentTopicsDigest) -> str:
    lines = [
        "✍️ Темы для постов",
        "",
        f"Период: {digest.period_label}",
        digest.summary,
        "",
        f"Фактов в анализе: commits {digest.commit_count}, записи STATUS {digest.status_entry_count}",
    ]

    if digest.themes:
        lines.extend(["", "Что можно публиковать:"])
        for index, theme in enumerate(digest.themes, start=1):
            lines.extend(_render_theme(index, theme))
            if index != len(digest.themes):
                lines.append("")
    else:
        lines.extend(
            [
                "",
                "Сильных тем за период не найдено.",
                "Лучше дождаться более заметного изменения или собрать неделю целиком.",
            ]
        )

    if digest.limitations:
        lines.extend(["", "Ограничения:"])
        lines.extend(f"- {item}" for item in digest.limitations)

    return "\n".join(lines)
