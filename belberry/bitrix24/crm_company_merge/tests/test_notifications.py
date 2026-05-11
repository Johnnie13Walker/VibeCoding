from __future__ import annotations

from crm_company_merge.notifications import build_progress_message


def test_build_progress_message_basic() -> None:
    text = build_progress_message(
        stage_title="Merge завершён",
        batch_stats=[("Групп обработано", 5), ("Полей обновлено", 16)],
        queue_counts={"MERGED": 16, "PLAN_READY": 147, "FAILED": 1},
    )

    assert text.startswith("✅ Merge завершён")
    assert "Результат пакета:" in text
    assert "  • Групп обработано: 5" in text
    assert "📈 Прогресс дедупа:" in text
    assert "Очередь сейчас:" in text
    assert "✅ MERGED" in text
    assert "🔵 PLAN_READY" in text
    assert "🔴 FAILED" in text


def test_progress_bar_full() -> None:
    text = build_progress_message(
        stage_title="Merge завершён",
        batch_stats=[],
        queue_counts={"MERGED": 10},
    )

    assert "▓▓▓▓▓▓▓▓▓▓ 10 / 10  (100%)" in text


def test_progress_bar_zero() -> None:
    text = build_progress_message(
        stage_title="Discover завершён",
        batch_stats=[],
        queue_counts={"NEW": 10},
    )

    assert "░░░░░░░░░░ 0 / 10  (0%)" in text


def test_zero_total_safe() -> None:
    text = build_progress_message(
        stage_title="Inventory завершён",
        batch_stats=[],
        queue_counts={},
    )

    assert "░░░░░░░░░░ 0 / 1  (0%)" in text
    assert "Очередь сейчас:" in text
