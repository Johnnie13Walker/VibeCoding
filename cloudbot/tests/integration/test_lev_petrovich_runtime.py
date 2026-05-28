from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from apps.lev_petrovich.agent import LevPetrovichAgent, SalesAgent, build_sales_report_from_env
from apps.lev_petrovich.legacy_sales_agent.communications_metrics import resolve_sales_team_filter
from apps.lev_petrovich.legacy_sales_agent.sales_agent import SalesAgentError, _attach_hot_stage_product_rows, _resolve_sales_chat_id
from apps.lev_petrovich.legacy_sales_agent.sales_agent import _load_previous_business_day_record, _save_sales_daily_history
from apps.lev_petrovich.legacy_sales_agent.pipeline_analyzer import analyze_pipeline
from apps.lev_petrovich.legacy_sales_agent.risk_detector import detect_risks
from apps.lev_petrovich.telegram_route import resolve_lev_petrovich_bot_token
from apps.lev_petrovich.legacy_sales_agent.sales_formatter import (
    SALES_REPORT_FORMAT_VERSION,
    _build_rop_focus_lines,
    _communications_items,
    _communications_scorecard,
    format_risks_report,
    format_sales_brief,
    report_required_markers,
    report_format_metadata,
)
from cloudbot.business_day import MOSCOW_TZ
from cloudbot.devops.sales_dispatch_health import evaluate_morning_dispatch
from cloudbot.providers.bitrix.bitrix_sales_adapter import BitrixSalesAdapter
from datetime import datetime, timedelta
from scripts.run_sales_copilot import _build_followup_messages, _run_sales_agent


class LevPetrovichRuntimeTests(unittest.TestCase):
    def test_lev_petrovich_alias_points_to_sales_runtime(self) -> None:
        self.assertIs(LevPetrovichAgent, SalesAgent)

    def test_build_sales_report_from_fixtures(self) -> None:
        fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "bitrix_crm_fixtures.json"
        result = build_sales_report_from_env(
            {
                "BITRIX_CRM_FIXTURES_FILE": str(fixture_path),
            },
            report_type="sales",
        )

        self.assertTrue(result["ok"])
        self.assertIn("📊 Сводка по продажам", result["text"])
        self.assertIn("Лев Петрович", result["text"])
        self.assertIn("Итоги за прошлый рабочий день", result["text"])
        self.assertIn("Воронка", result["text"])
        self.assertIn("На стадии договора", result["text"])
        self.assertIn("Источники новых сделок", result["text"])
        self.assertIn("📞 Коммуникации за предыдущий рабочий день", result["text"])
        self.assertIn("🆕 Новые сделки за предыдущий рабочий день", result["text"])
        self.assertIn("🤝 Встречи за предыдущий рабочий день", result["text"])
        self.assertIn("📝 Брифы за предыдущий рабочий день", result["text"])
        self.assertIn("📉 Отказы за предыдущий рабочий день", result["text"])
        self.assertNotIn("Краткая сводка", result["text"])
        self.assertNotIn("Фокус РОПа", result["text"])
        self.assertNotIn("📊 Sales Copilot", result["text"])
        self.assertEqual(result["format_version"], SALES_REPORT_FORMAT_VERSION)
        self.assertEqual(result["template_id"], report_format_metadata("sales")["template_id"])

        focus_result = build_sales_report_from_env(
            {
                "BITRIX_CRM_FIXTURES_FILE": str(fixture_path),
            },
            report_type="focus",
        )

        self.assertTrue(focus_result["ok"])
        self.assertIn("Фокус РОПа", focus_result["text"])
        self.assertNotIn("Где потерян контроль:", focus_result["text"])
        self.assertNotIn("💸 Где взять деньги сегодня:", focus_result["text"])
        self.assertIn("☎️ Где РОПу самому связаться с клиентом:", focus_result["text"])
        self.assertIn("🕳 Упущенные возможности:", focus_result["text"])
        self.assertNotIn("Кого дожать сегодня:", focus_result["text"])
        self.assertIn("Что РОП обязан сделать сегодня:", focus_result["text"])
        self.assertNotIn("🧊 Сделки без следующего шага", focus_result["text"])
        self.assertNotIn("📌 Сделки под контролем", focus_result["text"])
        self.assertNotIn("👥 Команда и дисциплина", focus_result["text"])
        self.assertNotIn("📊 Сигналы по отделу", focus_result["text"])
        self.assertNotIn("🪫 Ложный прогресс:", focus_result["text"])
        self.assertNotIn("Какие сделки нельзя упустить:", focus_result["text"])
        self.assertNotIn("☎️ Где нужен личный вход РОПа:", focus_result["text"])
        self.assertNotIn("Лидеров с 10/10 по операционной вовлечённости за вчера нет.", focus_result["text"])
        self.assertIn("Лидеров с 9+/10 по операционной вовлечённости за вчера нет.", focus_result["text"])
        self.assertEqual(focus_result["format_version"], SALES_REPORT_FORMAT_VERSION)
        self.assertEqual(focus_result["template_id"], report_format_metadata("focus")["template_id"])

        risks_result = build_sales_report_from_env(
            {
                "BITRIX_CRM_FIXTURES_FILE": str(fixture_path),
            },
            report_type="risks",
        )

        self.assertTrue(risks_result["ok"])
        self.assertIn("Риски по сделкам", risks_result["text"])
        self.assertIn("Без движения &gt; 14 дн.", risks_result["text"])
        self.assertIn("Без следующего шага", risks_result["text"])
        self.assertIn("Без коммуникации &gt; 14 дн.", risks_result["text"])
        self.assertIn("Сделки с просрочками", risks_result["text"])
        self.assertEqual(risks_result["format_version"], SALES_REPORT_FORMAT_VERSION)
        self.assertEqual(risks_result["template_id"], report_format_metadata("risks")["template_id"])

    def test_sales_brief_shows_deltas_and_contract_products(self) -> None:
        now = datetime(2026, 4, 1, 9, 30, tzinfo=MOSCOW_TZ)
        analysis = {
            "now": now,
            "metrics": {
                "conducted_meetings_yesterday": 3,
                "accepted_briefs_yesterday": 4,
                "deals_in_work": 50,
                "pipeline_amount": 8132161.0,
                "moving_deals_last_week": 24,
                "stagnant_deals_last_week": 26,
                "postponed_deals_now": 2,
                "hot_stage_deals": 2,
                "hot_stage_amount": 495788.0,
                "deals_without_next_step": 5,
                "deals_without_next_step_amount": 229737.0,
                "stale_communication_deals": 5,
                "stale_communication_amount": 730638.0,
                "overdue_deal_task_deals": 0,
                "overdue_deal_task_amount": 0.0,
            },
            "new_deals_yesterday": [{"amount": 0.0}],
            "new_deal_sources_yesterday": [
                {"source_name": "SEO", "count": 1},
                {"source_name": "Холодный звонок", "count": 1},
                {"source_name": "Контекстная реклама", "count": 2},
            ],
            "lost_deals_yesterday": [{"amount": 965350.0}],
            "hot_stage_deals": [
                {
                    "id": "1",
                    "title": "temed.ru",
                    "card_url": "https://example.com/deal/1",
                    "assigned_name": "Гудинова Анна",
                    "amount": 288688.0,
                    "product_rows": [
                        {"PRODUCT_NAME": "SEO", "SUM": "100000"},
                        {"PRODUCT_NAME": "AEO", "SUM": "188688"},
                    ],
                },
                {
                    "id": "2",
                    "title": "nazimova.com",
                    "card_url": "https://example.com/deal/2",
                    "assigned_name": "Гудинова Анна",
                    "amount": 207100.0,
                    "product_rows": [{"PRODUCT_NAME": "SEO", "SUM": "207100"}],
                },
            ],
            "daily_comparison": {
                "report_day": "2026-03-31",
                "previous_run": {
                    "current_metrics": {
                        "deals_in_work": 52,
                        "moving_deals_last_week": 27,
                        "stagnant_deals_last_week": 23,
                        "postponed_deals_now": 1,
                        "hot_stage_deals": 1,
                        "deal_risks": 28,
                        "deals_without_next_step": 4,
                        "stale_communication_deals": 3,
                        "overdue_deal_task_deals": 0,
                    },
                    "report_day_metrics": {
                        "new_deals_yesterday": 5,
                        "conducted_meetings_yesterday": 4,
                        "accepted_briefs_yesterday": 3,
                        "lost_deals_yesterday": 3,
                    },
                },
            },
            "limitations": [],
        }
        risk_report = {
            "deal_risks": [
                {
                    "entity_id": "stg-1",
                    "title": "mpya.ru",
                    "card_url": "https://example.com/deal/stg-1",
                    "assigned_name": "Гудинова Анна",
                    "amount": 210950.0,
                    "stage_name": "Подготовка КП",
                    "inactive_days": 39,
                    "categories": ["stagnant"],
                }
            ],
            "totals": {
                "deal_risks": 32,
                "risk_amount": 6130788.0,
            },
            "summary_totals": {
                "deal_risks": 14,
                "risk_amount": 2110375.0,
            },
            "category_totals": {
                "stagnant_deals": 7,
                "stagnant_amount": 1150000.0,
                "deals_without_next_step": 5,
                "deals_without_next_step_amount": 229737.0,
                "stale_communication_deals": 5,
                "stale_communication_amount": 730638.0,
                "overdue_deal_task_deals": 0,
                "overdue_deal_task_amount": 0.0,
            },
        }

        text = format_sales_brief(analysis, risk_report, communications_summary={})

        self.assertIn("Срез: 01.04 09:30 МСК", text)
        self.assertIn("Итоги за прошлый рабочий день, 31.03", text)
        self.assertIn("• Новые сделки: 1 (-4 к прошлому дню)", text)
        self.assertIn("• Встречи: 3 (-1 к прошлому дню)", text)
        self.assertIn("• Брифы: 4 (+1 к прошлому дню)", text)
        self.assertIn("• Отложенные сделки: 0 / <b>0 ₽</b> (н/д к прошлому дню)", text)
        self.assertIn("• Отказы: 1 / <b>965 350 ₽</b> (-2 к прошлому дню)", text)
        self.assertIn("• Активные сделки: 50 / <b>8 132 161 ₽</b> (-2 к прошлому дню)", text)
        self.assertIn("• В отложке: 2 (+1 к прошлому дню)", text)
        self.assertIn("• <a href=\"https://example.com/deal/1\">temed.ru</a> - <b>Гудинова Анна</b> - <b>288 688 ₽</b>", text)
        self.assertIn("SEO - <b>100 000 ₽</b>, AEO - <b>188 688 ₽</b>", text)
        self.assertIn("• SEO — 1", text)
        self.assertIn("• Контекстная реклама — 2", text)
        self.assertNotIn("<b>Риски</b>", text)

    def test_sales_brief_shows_nd_delta_when_previous_workday_missing(self) -> None:
        now = datetime(2026, 4, 1, 9, 30, tzinfo=MOSCOW_TZ)
        analysis = {
            "now": now,
            "metrics": {
                "conducted_meetings_yesterday": 3,
                "accepted_briefs_yesterday": 4,
                "deals_in_work": 51,
                "pipeline_amount": 8990781.0,
                "moving_deals_last_week": 48,
                "stagnant_deals_last_week": 3,
                "postponed_deals_now": 4,
                "hot_stage_deals": 2,
                "hot_stage_amount": 495788.0,
                "deals_without_next_step": 2,
                "deals_without_next_step_amount": 0.0,
                "stale_communication_deals": 3,
                "stale_communication_amount": 210950.0,
                "overdue_deal_task_deals": 1,
                "overdue_deal_task_amount": 0.0,
            },
            "new_deals_yesterday": [{"amount": 0.0}],
            "new_deal_sources_yesterday": [],
            "lost_deals_yesterday": [{"amount": 965350.0}] * 5,
            "hot_stage_deals": [],
            "daily_comparison": {"report_day": "2026-03-31", "previous_run": {}},
            "limitations": [],
        }
        risk_report = {"totals": {"deal_risks": 10, "risk_amount": 941750.0}}

        text = format_sales_brief(analysis, risk_report, communications_summary={})

        self.assertIn("• Новые сделки: 1 (н/д к прошлому дню)", text)
        self.assertIn("• Встречи: 3 (н/д к прошлому дню)", text)
        self.assertIn("• Брифы: 4 (н/д к прошлому дню)", text)
        self.assertIn("• Отложенные сделки: 0 / <b>0 ₽</b> (н/д к прошлому дню)", text)
        self.assertIn("• Отказы: 5 / <b>4 826 750 ₽</b> (н/д к прошлому дню)", text)
        self.assertIn("• Активные сделки: 51 / <b>8 990 781 ₽</b> (н/д к прошлому дню)", text)
        self.assertIn("• В отложке: 4 (н/д к прошлому дню)", text)

    def test_risks_report_shows_category_links_and_unique_summary(self) -> None:
        now = datetime(2026, 4, 10, 10, 5, tzinfo=MOSCOW_TZ)
        analysis = {
            "now": now,
            "limitations": [],
            "metrics": {
                "deals_without_next_step": 2,
                "deals_without_next_step_amount": 75000.0,
                "stale_communication_deals": 5,
                "stale_communication_amount": 203520.0,
                "overdue_deal_task_deals": 1,
                "overdue_deal_task_amount": 75000.0,
            },
            "active_deals": [
                {
                    "id": "1",
                    "title": "deal-1.ru",
                    "card_url": "https://example.com/deal/1",
                    "assigned_name": "Иванов Иван",
                    "amount": 75000.0,
                    "stage_name": "Подготовка КП",
                },
                {
                    "id": "2",
                    "title": "deal-2.ru",
                    "card_url": "https://example.com/deal/2",
                    "assigned_name": "Петров Петр",
                    "amount": 128520.0,
                    "stage_name": "Квалификация",
                },
            ],
            "deals_without_next_step_items": [
                {
                    "id": "1",
                    "title": "deal-1.ru",
                    "card_url": "https://example.com/deal/1",
                    "assigned_name": "Иванов Иван",
                    "amount": 75000.0,
                    "stage_name": "Подготовка КП",
                }
            ],
            "stale_communication_deals": [
                {
                    "id": "1",
                    "title": "deal-1.ru",
                    "card_url": "https://example.com/deal/1",
                    "assigned_name": "Иванов Иван",
                    "amount": 75000.0,
                    "stage_name": "Подготовка КП",
                    "communication_gap_days": 21,
                },
                {
                    "id": "2",
                    "title": "deal-2.ru",
                    "card_url": "https://example.com/deal/2",
                    "assigned_name": "Петров Петр",
                    "amount": 128520.0,
                    "stage_name": "Квалификация",
                    "communication_gap_days": 17,
                },
            ],
            "overdue_deal_tasks": [
                {
                    "deal_id": "1",
                    "days_overdue": 5,
                    "task_title": "Согласовать КП",
                }
            ],
            "daily_comparison": {
                "previous_run": {
                    "current_metrics": {
                        "deal_risks": 8,
                        "stagnant_risk_deals": 3,
                        "deals_without_next_step": 4,
                        "stale_communication_deals": 5,
                        "overdue_deal_task_deals": 2,
                    }
                }
            },
        }
        risk_report = {
            "deal_risks": [
                {
                    "entity_id": "1",
                    "title": "deal-1.ru",
                    "card_url": "https://example.com/deal/1",
                    "assigned_name": "Иванов Иван",
                    "amount": 75000.0,
                    "stage_name": "Подготовка КП",
                    "inactive_days": 16,
                    "categories": ["stagnant", "next_step", "stale_communication", "overdue_tasks"],
                },
                {
                    "entity_id": "2",
                    "title": "deal-2.ru",
                    "card_url": "https://example.com/deal/2",
                    "assigned_name": "Петров Петр",
                    "amount": 128520.0,
                    "stage_name": "Квалификация",
                    "inactive_days": 0,
                    "categories": ["stale_communication"],
                },
            ],
            "summary_totals": {
                "deal_risks": 2,
                "risk_amount": 203520.0,
            },
            "category_totals": {
                "stagnant_deals": 1,
                "stagnant_amount": 75000.0,
                "deals_without_next_step": 1,
                "deals_without_next_step_amount": 75000.0,
                "stale_communication_deals": 2,
                "stale_communication_amount": 203520.0,
                "overdue_deal_task_deals": 1,
                "overdue_deal_task_amount": 75000.0,
            },
        }

        text = format_risks_report(analysis, risk_report, communications_summary={})

        self.assertIn("⚠️ Риски по сделкам", text)
        self.assertIn("• Уникальные риск-сделки: 2 / <b>203 520 ₽</b> (-6 к прошлому дню)", text)
        self.assertIn("• Без движения &gt; 14 дн.: 1 / <b>75 000 ₽</b> (-2 к прошлому дню)", text)
        self.assertIn("• Без следующего шага: 1 / <b>75 000 ₽</b> (-3 к прошлому дню)", text)
        self.assertIn("• Без коммуникации &gt; 14 дн.: 2 / <b>203 520 ₽</b> (-3 к прошлому дню)", text)
        self.assertIn("• Сделки с просрочками: 1 / <b>75 000 ₽</b> (-1 к прошлому дню)", text)
        self.assertIn("<b>Без движения &gt; 14 дн.</b>", text)
        self.assertIn("<b>Без следующего шага</b>", text)
        self.assertIn("<b>Без коммуникации &gt; 14 дн.</b>", text)
        self.assertIn("<b>Сделки с просрочками</b>", text)
        self.assertIn("• <a href=\"https://example.com/deal/1\">deal-1.ru</a>", text)
        self.assertIn("следующего шага нет", text)
        self.assertIn("без коммуникации: 21 дн.", text)
        self.assertIn("просрочка: 5 дн.; задача: Согласовать КП", text)

    def test_sales_brief_shows_all_meetings_briefs_and_lost_deals(self) -> None:
        now = datetime(2026, 4, 2, 9, 30, tzinfo=MOSCOW_TZ)
        analysis = {
            "now": now,
            "metrics": {
                "conducted_meetings_yesterday": 4,
                "accepted_briefs_yesterday": 4,
                "deals_in_work": 10,
                "pipeline_amount": 100000.0,
                "moving_deals_last_week": 7,
                "stagnant_deals_last_week": 3,
                "hot_stage_deals": 0,
                "hot_stage_amount": 0.0,
                "deals_without_next_step": 0,
                "deals_without_next_step_amount": 0.0,
                "stale_communication_deals": 0,
                "stale_communication_amount": 0.0,
                "overdue_deal_task_deals": 0,
                "overdue_deal_task_amount": 0.0,
            },
            "new_deals_yesterday": [],
            "new_deal_sources_yesterday": [],
            "lost_deals_yesterday": [
                {"title": "lost-1.ru", "card_url": "https://example.com/lost/1", "amount": 1000.0, "lost_reason": "r1"},
                {"title": "lost-2.ru", "card_url": "https://example.com/lost/2", "amount": 2000.0, "lost_reason": "r2"},
                {"title": "lost-3.ru", "card_url": "https://example.com/lost/3", "amount": 3000.0, "lost_reason": "r3"},
                {"title": "lost-4.ru", "card_url": "https://example.com/lost/4", "amount": 4000.0, "lost_reason": "r4"},
            ],
            "conducted_meetings": [
                {"title": "meeting-1", "card_url": "https://example.com/meeting/1", "moved_at": now, "yesterday_moved": True},
                {"title": "meeting-2", "card_url": "https://example.com/meeting/2", "moved_at": now, "yesterday_moved": True},
                {"title": "meeting-3", "card_url": "https://example.com/meeting/3", "moved_at": now, "yesterday_moved": True},
                {"title": "meeting-4", "card_url": "https://example.com/meeting/4", "moved_at": now, "yesterday_moved": True},
            ],
            "accepted_briefs": [
                {"title": "brief-1", "card_url": "https://example.com/brief/1", "moved_at": now, "yesterday_moved": True},
                {"title": "brief-2", "card_url": "https://example.com/brief/2", "moved_at": now, "yesterday_moved": True},
                {"title": "brief-3", "card_url": "https://example.com/brief/3", "moved_at": now, "yesterday_moved": True},
                {"title": "brief-4", "card_url": "https://example.com/brief/4", "moved_at": now, "yesterday_moved": True},
            ],
            "hot_stage_deals": [],
            "daily_comparison": {"report_day": "2026-04-01", "previous_run": {}},
            "limitations": [],
        }

        text = format_sales_brief(analysis, {"totals": {"deal_risks": 0, "risk_amount": 0.0}}, communications_summary={})

        self.assertIn("meeting-4", text)
        self.assertIn("brief-4", text)
        self.assertIn("lost-4.ru", text)

    def test_sales_brief_shows_postponed_deals_before_lost_deals(self) -> None:
        now = datetime(2026, 4, 10, 9, 30, tzinfo=MOSCOW_TZ)
        analysis = {
            "now": now,
            "metrics": {
                "conducted_meetings_yesterday": 0,
                "accepted_briefs_yesterday": 0,
                "postponed_deals_yesterday": 2,
                "postponed_deals_yesterday_amount": 3800000.0,
                "lost_deals_yesterday": 1,
                "lost_deals_yesterday_amount": 120000.0,
                "deals_in_work": 10,
                "pipeline_amount": 100000.0,
                "moving_deals_last_week": 7,
                "stagnant_deals_last_week": 3,
                "hot_stage_deals": 0,
                "hot_stage_amount": 0.0,
                "deals_without_next_step": 0,
                "deals_without_next_step_amount": 0.0,
                "stale_communication_deals": 0,
                "stale_communication_amount": 0.0,
                "overdue_deal_task_deals": 0,
                "overdue_deal_task_amount": 0.0,
            },
            "new_deals_yesterday": [],
            "new_deal_sources_yesterday": [],
            "postponed_deals_yesterday": [
                {
                    "title": "Клиника Альфа",
                    "card_url": "https://example.com/deal/alpha",
                    "amount": 1500000.0,
                    "assigned_name": "Иванов Иван",
                    "next_step_at": datetime(2026, 4, 25, 11, 0, tzinfo=MOSCOW_TZ),
                },
                {
                    "title": "Стоматология Гамма",
                    "card_url": "https://example.com/deal/gamma",
                    "amount": 2300000.0,
                    "assigned_name": "Петров Петр",
                    "next_step_at": None,
                },
            ],
            "lost_deals_yesterday": [
                {"title": "lost-1.ru", "card_url": "https://example.com/lost/1", "amount": 120000.0, "lost_reason": "r1"}
            ],
            "conducted_meetings": [],
            "accepted_briefs": [],
            "hot_stage_deals": [],
            "daily_comparison": {
                "report_day": "2026-04-09",
                "previous_run": {"report_day_metrics": {"postponed_deals_yesterday": 1, "lost_deals_yesterday": 3}},
            },
            "limitations": [],
        }

        text = format_sales_brief(analysis, {"totals": {"deal_risks": 0, "risk_amount": 0.0}}, communications_summary={})

        self.assertIn("• Отложенные сделки: 2 / <b>3 800 000 ₽</b> (+1 к прошлому дню)", text)
        self.assertIn("<b>⏸ Отложенные сделки за предыдущий рабочий день</b>", text)
        self.assertIn('<a href="https://example.com/deal/alpha">Клиника Альфа</a> — <b>1 500 000 ₽</b> — <b>Иванов Иван</b> — след. контакт 25 апреля (через 15 дн.)', text)
        self.assertIn('<a href="https://example.com/deal/gamma">Стоматология Гамма</a> — <b>2 300 000 ₽</b> — <b>Петров Петр</b> — без даты следующего контакта', text)
        self.assertLess(text.index("⏸ Отложенные сделки за предыдущий рабочий день"), text.index("📉 Отказы за предыдущий рабочий день"))

    def test_previous_business_day_record_uses_friday_for_monday_run(self) -> None:
        monday_now = datetime(2026, 4, 6, 9, 30, tzinfo=MOSCOW_TZ)
        with tempfile.TemporaryDirectory() as tmp_dir:
            history_path = Path(tmp_dir) / "sales_daily_history.json"
            _save_sales_daily_history(
                {"SALES_DAILY_HISTORY_FILE": str(history_path)},
                {
                    "records": {
                        "2026-04-03": {
                            "run_day": "2026-04-03",
                            "report_day": "2026-04-02",
                            "current_metrics": {"deals_in_work": 47},
                            "report_day_metrics": {"lost_deals_yesterday": 4},
                        }
                    }
                },
            )

            record = _load_previous_business_day_record(
                {"SALES_DAILY_HISTORY_FILE": str(history_path)},
                now=monday_now,
            )

        self.assertEqual(record.get("run_day"), "2026-04-03")

    def test_sales_daily_history_uses_sales_log_directory_when_explicit_path_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "reports" / "sales_agent.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            history_path = log_path.parent / "sales_daily_history.json"

            _save_sales_daily_history(
                {"SALES_LOG_FILE": str(log_path)},
                {
                    "records": {
                        "2026-04-09": {
                            "run_day": "2026-04-09",
                            "report_day": "2026-04-08",
                            "current_metrics": {"deals_in_work": 42},
                            "report_day_metrics": {"lost_deals_yesterday": 3},
                        }
                    }
                },
            )

            payload = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["records"]["2026-04-09"]["current_metrics"]["deals_in_work"], 42)

    def test_focus_report_shows_missed_sales_steps(self) -> None:
        now = datetime(2026, 3, 22, 12, 0, tzinfo=MOSCOW_TZ)
        analysis = {
            "now": now,
            "active_deals": [
                {
                    "id": "1",
                    "title": "Alpha Clinic",
                    "card_url": "https://example.com/deal/1",
                    "assigned_id": "101",
                    "assigned_name": "Петр Дудин",
                    "stage_name": "Подготовка БРИФа",
                    "amount": 300000.0,
                    "communication_gap_days": 9,
                    "inactive_days": 9,
                    "late_stage": False,
                    "high_probability": False,
                    "missing_next_step": False,
                    "needs_leader": False,
                    "effective_probability": 45.0,
                    "probability": 45.0,
                    "relation_suffix": "Alpha Clinic",
                },
                {
                    "id": "2",
                    "title": "Beta Dental",
                    "card_url": "https://example.com/deal/2",
                    "assigned_id": "102",
                    "assigned_name": "Анна Гудинова",
                    "stage_name": "Подготовка КП",
                    "amount": 220000.0,
                    "communication_gap_days": 10,
                    "inactive_days": 10,
                    "late_stage": True,
                    "high_probability": True,
                    "missing_next_step": True,
                    "needs_leader": True,
                    "effective_probability": 80.0,
                    "probability": 80.0,
                    "relation_suffix": "Beta Dental",
                },
            ],
            "overdue_deal_tasks": [],
            "overdue_deal_tasks_by_manager": [],
            "deadline_reschedule_focus_tasks": [],
            "conducted_meetings": [
                {
                    "id": "m1",
                    "title": "Бриф по Beta Dental",
                    "assigned_id": "102",
                    "assigned_name": "Анна Гудинова",
                    "stage_name": "Встреча проведена",
                    "moved_at": now - timedelta(days=8),
                }
            ],
            "accepted_briefs": [],
        }

        lines = _build_rop_focus_lines(analysis, {"deal_risks": []}, {})
        text = "\n".join(["🎯 Фокус РОПа", *lines])

        self.assertNotIn("Где потерян контроль:", text)
        self.assertNotIn("💸 Где взять деньги сегодня:", text)
        self.assertIn("🕳 Упущенные возможности:", text)
        self.assertNotIn("Кого дожать сегодня:", text)
        self.assertIn("Alpha Clinic", text)
        self.assertIn("этапе «Подготовка БРИФа», но в истории нет ни одной встречи", text)
        self.assertIn("Beta Dental", text)
        self.assertIn("после брифа прошло 8 дн., а встречи по защите КП нет", text)

    def test_focus_report_shows_people_with_operational_score_from_nine(self) -> None:
        analysis = {
            "active_deals": [],
            "overdue_deal_tasks": [],
            "overdue_deal_tasks_by_manager": [],
            "deadline_reschedule_focus_tasks": [],
            "conducted_meetings": [
                {
                    "assigned_id": "sales-1",
                    "assigned_name": "Елизавета Деговцова",
                    "yesterday_moved": True,
                },
                {
                    "assigned_id": "sales-1",
                    "assigned_name": "Елизавета Деговцова",
                    "yesterday_moved": True,
                },
            ],
        }
        communications_summary = {
            "thresholds": {"telemarketing_min_dials": 40},
            "managers": [
                {
                    "manager_id": "sales-1",
                    "manager_name": "Елизавета Деговцова",
                    "employee_role": "sales",
                    "dials": 33,
                    "normal_calls": 4,
                    "messenger_dialogs": 10,
                    "connect_rate": 4 / 33,
                    "total_known": 43,
                }
            ],
        }

        lines = _build_rop_focus_lines(analysis, {"deal_risks": []}, communications_summary)
        text = "\n".join(["🎯 Фокус РОПа", *lines])

        self.assertNotIn("Где потерян контроль:", text)
        self.assertNotIn("💸 Где взять деньги сегодня:", text)
        self.assertIn("🔥 Молодцы за вчера", text)
        self.assertNotIn("Кого дожать сегодня:", text)
        self.assertIn("Деговцова Елизавета", text)
        self.assertIn("10/10", text)
        self.assertNotIn("Лидеров с 9+/10 по операционной вовлечённости за вчера нет.", text)

    def test_deal_with_linked_future_meeting_is_not_marked_without_next_step(self) -> None:
        now = datetime(2026, 3, 23, 11, 30, tzinfo=MOSCOW_TZ)
        analysis = analyze_pipeline(
            {
                "portal_base_url": "https://belberrycrm.bitrix24.ru",
                "active_deals": [
                    {
                        "id": "18472",
                        "title": "ternovs.dental",
                        "assigned_id": "2818",
                        "created_at": "2026-02-18T11:49:42+03:00",
                        "updated_at": "2026-03-20T14:03:51+03:00",
                        "moved_at": "2026-03-05T18:31:44+03:00",
                        "last_activity_at": "2026-03-19T12:00:00+03:00",
                        "last_communication_at": "2026-03-04T09:42:13+03:00",
                        "stage_id": "C10:EXECUTING",
                        "semantic_id": "P",
                        "amount": "222500.00000000",
                        "company_id": "23438",
                        "contact_id": "32190",
                        "category_id": "10",
                    }
                ],
                "closed_deals": [],
                "recent_deals": [],
                "recent_leads": [],
                "active_leads": [],
                "meetings": [
                    {
                        "id": "1732",
                        "title": "ternovs.dental (Защита КП)",
                        "created_at": "2026-03-12T12:54:39+03:00",
                        "updated_at": "2026-03-19T12:00:32+03:00",
                        "moved_at": "2026-03-12T12:54:39+03:00",
                        "category_id": "24",
                        "stage_id": "DT1048_24:NEW",
                        "assigned_id": "2818",
                        "parent_deal_id": "18472",
                        "raw": {
                            "id": 1732,
                            "title": "ternovs.dental (Защита КП)",
                            "parentId2": 18472,
                            "ufCrm16_1751009238": "2026-03-25T11:00:00+03:00",
                            "assignedById": 2818,
                            "stageId": "DT1048_24:NEW",
                            "createdTime": "2026-03-12T12:54:39+03:00",
                            "updatedTime": "2026-03-19T12:00:32+03:00",
                            "movedTime": "2026-03-12T12:54:39+03:00",
                        },
                    }
                ],
                "conducted_meetings": [],
                "briefs": [],
                "accepted_briefs": [],
                "responsibles": {
                    "2818": {
                        "id": "2818",
                        "name": "Иван",
                        "last_name": "Халин",
                        "full_name": "Халин Иван",
                        "active": True,
                    }
                },
                "companies": [{"id": "23438", "title": "ООО Авторская стоматология Терновых"}],
                "contacts": [{"id": "32190", "full_name": "Виктория"}],
                "departments_by_head": {},
                "deal_stage_map": [{"STATUS_ID": "C10:EXECUTING", "NAME": "Подготовка КП"}],
                "meeting_stage_map": [{"STATUS_ID": "DT1048_24:NEW", "NAME": "Запланирована"}],
                "brief_stage_map": [],
                "deal_source_map": [],
                "next_step_source": "crm.activity.list",
            },
            now=now,
        )

        deal = analysis["active_deals"][0]
        self.assertFalse(deal["missing_next_step"])
        self.assertEqual(deal["next_step_source"], "crm.item.list:meeting")
        self.assertEqual(deal["next_step_at"], datetime(2026, 3, 25, 11, 0, tzinfo=MOSCOW_TZ))
        self.assertEqual(deal["meeting_titles"], ["ternovs.dental (Защита КП)"])
        self.assertEqual(deal["communication_gap_days"], 3)
        self.assertEqual(analysis["stale_communication_deals"], [])

    def test_deal_field_meeting_date_is_used_as_next_step(self) -> None:
        now = datetime(2026, 4, 1, 10, 0, tzinfo=MOSCOW_TZ)
        analysis = analyze_pipeline(
            {
                "portal_base_url": "https://belberrycrm.bitrix24.ru",
                "active_deals": [
                    {
                        "id": "18396",
                        "title": "cdz-alter.ru",
                        "assigned_id": "2822",
                        "created_at": "2026-03-05T11:00:00+03:00",
                        "updated_at": "2026-03-31T15:46:19+03:00",
                        "moved_at": "2026-03-12T14:04:30+03:00",
                        "last_activity_at": "2026-03-20T12:40:23+03:00",
                        "last_communication_at": "2026-03-20T12:40:23+03:00",
                        "stage_id": "C10:EXECUTING",
                        "semantic_id": "P",
                        "amount": "229737",
                        "category_id": "10",
                        "raw": {
                            "UF_CRM_MEETING_PROPOSAL_DATE": "2026-04-01T16:00:00+03:00",
                        },
                    }
                ],
                "closed_deals": [],
                "recent_deals": [],
                "recent_leads": [],
                "active_leads": [],
                "meetings": [],
                "conducted_meetings": [],
                "briefs": [],
                "accepted_briefs": [],
                "responsibles": {"2822": {"id": "2822", "full_name": "Деговцова Елизавета", "active": True}},
                "companies": [],
                "contacts": [],
                "departments_by_head": {},
                "deal_stage_map": [{"STATUS_ID": "C10:EXECUTING", "NAME": "Подготовка КП"}],
                "meeting_stage_map": [],
                "brief_stage_map": [],
                "deal_source_map": [],
                "deal_fields_meta": {
                    "UF_CRM_MEETING_PROPOSAL_DATE": {
                        "title": "Защита КП. Дата встречи",
                    }
                },
                "next_step_source": "crm.activity.list",
            },
            now=now,
        )

        deal = analysis["active_deals"][0]
        self.assertFalse(deal["missing_next_step"])
        self.assertEqual(deal["next_step_source"], "deal.field:meeting_date")
        self.assertEqual(deal["next_step_at"], datetime(2026, 4, 1, 16, 0, tzinfo=MOSCOW_TZ))

    def test_open_future_task_is_used_as_next_step_fallback(self) -> None:
        now = datetime(2026, 4, 1, 10, 0, tzinfo=MOSCOW_TZ)
        analysis = analyze_pipeline(
            {
                "portal_base_url": "https://belberrycrm.bitrix24.ru",
                "active_deals": [
                    {
                        "id": "18396",
                        "title": "cdz-alter.ru",
                        "assigned_id": "2822",
                        "created_at": "2026-03-05T11:00:00+03:00",
                        "updated_at": "2026-03-31T15:46:19+03:00",
                        "moved_at": "2026-03-12T14:04:30+03:00",
                        "last_activity_at": "2026-03-20T12:40:23+03:00",
                        "last_communication_at": "2026-03-20T12:40:23+03:00",
                        "stage_id": "C10:EXECUTING",
                        "semantic_id": "P",
                        "amount": "229737",
                        "category_id": "10",
                    }
                ],
                "closed_deals": [],
                "recent_deals": [],
                "recent_leads": [],
                "active_leads": [],
                "meetings": [],
                "conducted_meetings": [],
                "briefs": [],
                "accepted_briefs": [],
                "responsibles": {"2822": {"id": "2822", "full_name": "Деговцова Елизавета", "active": True}},
                "companies": [],
                "contacts": [],
                "departments_by_head": {},
                "deal_stage_map": [{"STATUS_ID": "C10:EXECUTING", "NAME": "Подготовка КП"}],
                "meeting_stage_map": [],
                "brief_stage_map": [],
                "deal_source_map": [],
                "deal_fields_meta": {},
                "tasks": [
                    {
                        "id": "500430",
                        "title": "Подготовить встречу по защите КП",
                        "status": "2",
                        "deadline": "2026-04-01T18:00:00+03:00",
                        "crm_bindings": ["D_18396"],
                    }
                ],
                "task_status_map": {"5": "Завершена"},
                "next_step_source": "crm.activity.list",
            },
            now=now,
        )

        deal = analysis["active_deals"][0]
        self.assertFalse(deal["missing_next_step"])
        self.assertEqual(deal["next_step_source"], "tasks.task.list")
        self.assertEqual(deal["next_step_at"], datetime(2026, 4, 1, 18, 0, tzinfo=MOSCOW_TZ))

    def test_open_linked_task_without_deadline_is_used_as_next_step_fallback(self) -> None:
        now = datetime(2026, 4, 1, 10, 0, tzinfo=MOSCOW_TZ)
        analysis = analyze_pipeline(
            {
                "portal_base_url": "https://belberrycrm.bitrix24.ru",
                "active_deals": [
                    {
                        "id": "16192",
                        "title": "belberrycrm deal",
                        "assigned_id": "2822",
                        "created_at": "2026-03-20T11:00:00+03:00",
                        "updated_at": "2026-03-31T15:46:19+03:00",
                        "moved_at": "2026-03-31T09:30:00+03:00",
                        "last_activity_at": "2026-03-31T15:46:19+03:00",
                        "last_communication_at": "2026-03-28T12:40:23+03:00",
                        "stage_id": "C10:EXECUTING",
                        "semantic_id": "P",
                        "amount": "229737",
                        "category_id": "10",
                    }
                ],
                "closed_deals": [],
                "recent_deals": [],
                "recent_leads": [],
                "active_leads": [],
                "meetings": [],
                "conducted_meetings": [],
                "briefs": [],
                "accepted_briefs": [],
                "responsibles": {
                    "2822": {"id": "2822", "full_name": "Деговцова Елизавета", "active": True},
                    "9001": {"id": "9001", "full_name": "Сотрудник производства", "active": True},
                },
                "companies": [],
                "contacts": [],
                "departments_by_head": {},
                "deal_stage_map": [{"STATUS_ID": "C10:EXECUTING", "NAME": "Подготовка КП"}],
                "meeting_stage_map": [],
                "brief_stage_map": [],
                "deal_source_map": [],
                "deal_fields_meta": {},
                "tasks": [
                    {
                        "id": "500431",
                        "title": "Подготовить КП",
                        "status": "2",
                        "deadline": None,
                        "responsible_id": "9001",
                        "crm_bindings": ["D_16192"],
                        "raw": {
                            "createdDate": "2026-04-01T09:15:00+03:00",
                            "responsibleId": "9001",
                        },
                    }
                ],
                "task_status_map": {"5": "Завершена"},
                "next_step_source": "crm.activity.list",
            },
            now=now,
        )

        deal = analysis["active_deals"][0]
        self.assertFalse(deal["missing_next_step"])
        self.assertEqual(deal["next_step_source"], "tasks.task.list")
        self.assertEqual(deal["next_step_subject"], "Подготовить КП")
        self.assertEqual(deal["next_step_at"], datetime(2026, 4, 1, 9, 15, tzinfo=MOSCOW_TZ))

    def test_recent_timeline_touch_prevents_stagnant_risk(self) -> None:
        now = datetime(2026, 3, 31, 10, 0, tzinfo=MOSCOW_TZ)
        analysis = analyze_pipeline(
            {
                "portal_base_url": "https://belberrycrm.bitrix24.ru",
                "active_deals": [
                    {
                        "id": "18348",
                        "title": "maxxclinic.ru",
                        "assigned_id": "2818",
                        "created_at": "2026-02-17T18:28:33+03:00",
                        "updated_at": "2026-03-30T18:26:27+03:00",
                        "moved_at": "2026-03-20T17:48:19+03:00",
                        "last_activity_at": "2026-03-26T13:13:39+03:00",
                        "last_communication_at": "2026-03-26T13:13:39+03:00",
                        "stage_id": "C10:EXECUTING",
                        "semantic_id": "P",
                        "amount": "220000.00000000",
                        "company_id": "1",
                        "contact_id": "1",
                        "category_id": "10",
                        "next_step_at": "2026-03-31T18:00:00+03:00",
                        "next_step_subject": "Назначить встречу по защите КП (maxxclinic.ru)",
                        "next_step_source": "crm.activity.list",
                    }
                ],
                "closed_deals": [],
                "recent_deals": [],
                "recent_leads": [],
                "active_leads": [],
                "meetings": [],
                "conducted_meetings": [],
                "briefs": [],
                "accepted_briefs": [],
                "tasks": [],
                "task_status_map": {},
                "deal_timeline_comments": {
                    "18348": [
                        {
                            "created_at": "2026-03-30T17:14:03+03:00",
                            "comment": "[img]https://static.wazzup24.com/images/bitrix/telegram.png[/img] Иван Халин: написал клиенту и согласовал следующий шаг",
                        }
                    ]
                },
                "responsibles": {
                    "2818": {
                        "id": "2818",
                        "name": "Иван",
                        "last_name": "Халин",
                        "full_name": "Халин Иван",
                        "active": True,
                    }
                },
                "companies": [{"id": "1", "title": "Maxx"}],
                "contacts": [{"id": "1", "full_name": "Виктория"}],
                "departments_by_head": {},
                "deal_stage_map": [{"STATUS_ID": "C10:EXECUTING", "NAME": "Подготовка КП"}],
                "meeting_stage_map": [],
                "brief_stage_map": [],
                "deal_source_map": [],
                "next_step_source": "crm.activity.list",
            },
            now=now,
        )
        deal = analysis["active_deals"][0]
        self.assertEqual(deal["communication_gap_days"], 0)
        self.assertTrue(deal["engaged_in_last_week"])

        risks = detect_risks(analysis)
        self.assertFalse(any("stagnant" in item.get("categories", []) for item in risks["deal_risks"]))

    def test_future_meeting_prevents_stale_communication_risk(self) -> None:
        now = datetime(2026, 3, 31, 10, 0, tzinfo=MOSCOW_TZ)
        analysis = analyze_pipeline(
            {
                "portal_base_url": "https://belberrycrm.bitrix24.ru",
                "active_deals": [
                    {
                        "id": "18396",
                        "title": "cdz-alter.ru",
                        "assigned_id": "2358",
                        "created_at": "2026-02-17T18:40:43+03:00",
                        "updated_at": "2026-03-20T12:45:08+03:00",
                        "moved_at": "2026-03-12T14:04:30+03:00",
                        "last_activity_at": "2026-03-20T12:45:08+03:00",
                        "last_communication_at": "2026-03-20T12:40:23+03:00",
                        "stage_id": "C10:EXECUTING",
                        "semantic_id": "P",
                        "amount": "252000.00000000",
                        "company_id": "1",
                        "contact_id": "1",
                        "category_id": "10",
                    }
                ],
                "closed_deals": [],
                "recent_deals": [],
                "recent_leads": [],
                "active_leads": [],
                "meetings": [
                    {
                        "id": "1792",
                        "title": "cdz-alter.ru (Защита КП)",
                        "created_at": "2026-03-20T12:45:02+03:00",
                        "updated_at": "2026-03-20T12:45:08+03:00",
                        "moved_at": "2026-03-20T12:45:02+03:00",
                        "category_id": "24",
                        "stage_id": "DT1048_24:NEW",
                        "assigned_id": "2358",
                        "parent_deal_id": "18396",
                        "raw": {
                            "id": 1792,
                            "title": "cdz-alter.ru (Защита КП)",
                            "parentId2": 18396,
                            "begindate": "2026-04-01T14:00:00+03:00",
                            "assignedById": 2358,
                            "stageId": "DT1048_24:NEW",
                            "createdTime": "2026-03-20T12:45:02+03:00",
                            "updatedTime": "2026-03-20T12:45:08+03:00",
                            "movedTime": "2026-03-20T12:45:02+03:00",
                        },
                    }
                ],
                "conducted_meetings": [],
                "briefs": [],
                "accepted_briefs": [],
                "tasks": [],
                "task_status_map": {},
                "deal_timeline_comments": {},
                "responsibles": {
                    "2358": {
                        "id": "2358",
                        "name": "Елизавета",
                        "last_name": "Деговцова",
                        "full_name": "Деговцова Елизавета",
                        "active": True,
                    }
                },
                "companies": [{"id": "1", "title": "cdz-alter"}],
                "contacts": [{"id": "1", "full_name": "Елена"}],
                "departments_by_head": {},
                "deal_stage_map": [{"STATUS_ID": "C10:EXECUTING", "NAME": "Подготовка КП"}],
                "meeting_stage_map": [{"STATUS_ID": "DT1048_24:NEW", "NAME": "Запланирована"}],
                "brief_stage_map": [],
                "deal_source_map": [],
                "next_step_source": "crm.activity.list",
            },
            now=now,
        )
        deal = analysis["active_deals"][0]
        self.assertEqual(deal["next_step_source"], "crm.item.list:meeting")
        self.assertIsNotNone(deal["upcoming_meeting_at"])
        self.assertTrue(deal["engaged_in_last_week"])

        risks = detect_risks(analysis, stale_communication_days=7)
        self.assertFalse(any("stale_communication" in item.get("categories", []) for item in risks["deal_risks"]))

    def test_stagnant_risk_uses_14_day_threshold(self) -> None:
        now = datetime(2026, 4, 2, 9, 0, tzinfo=MOSCOW_TZ)
        analysis = {
            "now": now,
            "active_deals": [
                {
                    "id": "1",
                    "title": "stuck.ru",
                    "assigned_id": "2818",
                    "assigned_name": "Халин Иван",
                    "amount": 150000.0,
                    "stage_name": "Подготовка КП",
                    "inactive_days": 15,
                    "moved_in_last_week": False,
                    "engaged_in_last_week": False,
                    "late_stage": False,
                    "large_deal": True,
                    "meeting_today": False,
                    "needs_leader": False,
                    "missing_next_step": False,
                    "communication_gap_days": 5,
                    "created_at": now - timedelta(days=30),
                    "card_url": "https://example.com/deal/1",
                }
            ],
            "active_leads": [],
            "overdue_deal_tasks": [],
        }

        risks = detect_risks(analysis)

        self.assertEqual(risks["category_totals"]["stagnant_deals"], 1)
        self.assertEqual(risks["category_totals"]["stagnant_amount"], 150000.0)
        self.assertEqual(risks["summary_totals"]["deal_risks"], 1)
        self.assertEqual(risks["summary_totals"]["risk_amount"], 150000.0)
        self.assertTrue(any("stagnant" in item.get("categories", []) for item in risks["deal_risks"]))

    def test_operational_score_ignores_meetings_for_tm_and_counts_them_for_sm(self) -> None:
        telemarketing_without_meetings = _communications_scorecard(
            {
                "employee_role": "telemarketing",
                "dials": 20,
                "normal_calls": 3,
                "messenger_dialogs": 3,
                "connect_rate": 3 / 20,
            },
            meetings_count=0,
        )
        telemarketing_with_fake_meetings = _communications_scorecard(
            {
                "employee_role": "telemarketing",
                "dials": 20,
                "normal_calls": 3,
                "messenger_dialogs": 3,
                "connect_rate": 3 / 20,
            },
            meetings_count=2,
        )
        sales_with_meeting = _communications_scorecard(
            {
                "employee_role": "sales",
                "dials": 0,
                "normal_calls": 0,
                "messenger_dialogs": 0,
                "connect_rate": 0.0,
            },
            meetings_count=2,
        )

        self.assertEqual(telemarketing_without_meetings["meetings_count"], 0)
        self.assertEqual(telemarketing_without_meetings["meetings_label"], "-")
        self.assertEqual(
            telemarketing_without_meetings["operational_score_label"],
            telemarketing_with_fake_meetings["operational_score_label"],
        )
        self.assertEqual(sales_with_meeting["meeting_minutes"], 100)
        self.assertEqual(sales_with_meeting["operational_minutes"], 100)
        self.assertEqual(sales_with_meeting["meetings_label"], "2")
        self.assertEqual(sales_with_meeting["status_code"], "РИСК")

    def test_operational_score_uses_tm_active_minutes_formula(self) -> None:
        scorecard = _communications_scorecard(
            {
                "employee_role": "telemarketing",
                "dials": 105,
                "normal_calls": 15,
                "messenger_dialogs": 4,
                "connect_rate": 0.14,
            },
            meetings_count=0,
        )

        self.assertEqual(scorecard["empty_dial_minutes"], 90)
        self.assertEqual(scorecard["call_minutes"], 180)
        self.assertEqual(scorecard["chat_minutes"], 40)
        self.assertEqual(scorecard["operational_minutes"], 310)
        self.assertEqual(scorecard["operational_score_label"], "10.0")
        self.assertEqual(scorecard["status_code"], "НОРМ")

    def test_operational_score_uses_sm_active_minutes_formula(self) -> None:
        scorecard = _communications_scorecard(
            {
                "employee_role": "sales",
                "dials": 33,
                "normal_calls": 4,
                "messenger_dialogs": 10,
                "connect_rate": 4 / 33,
            },
            meetings_count=2,
        )

        self.assertEqual(scorecard["empty_dial_minutes"], 43.5)
        self.assertEqual(scorecard["call_minutes"], 60)
        self.assertEqual(scorecard["chat_minutes"], 100)
        self.assertEqual(scorecard["meeting_minutes"], 100)
        self.assertEqual(scorecard["operational_minutes"], 303.5)
        self.assertEqual(scorecard["operational_score_label"], "10.0")
        self.assertEqual(scorecard["status_code"], "НОРМ")

    def test_operational_score_does_not_depend_on_conversion(self) -> None:
        low_conversion = _communications_scorecard(
            {
                "employee_role": "sales",
                "dials": 20,
                "normal_calls": 4,
                "messenger_dialogs": 3,
                "connect_rate": 0.05,
            },
            meetings_count=1,
        )
        high_conversion = _communications_scorecard(
            {
                "employee_role": "sales",
                "dials": 20,
                "normal_calls": 4,
                "messenger_dialogs": 3,
                "connect_rate": 0.35,
            },
            meetings_count=1,
        )

        self.assertEqual(low_conversion["operational_minutes"], high_conversion["operational_minutes"])
        self.assertEqual(low_conversion["operational_score_label"], high_conversion["operational_score_label"])

    def test_communications_block_uses_problem_order_and_monospace_layout(self) -> None:
        summary = {
            "thresholds": {"telemarketing_min_dials": 40},
            "managers": [
                {
                    "manager_id": "tm-1",
                    "manager_name": "Иван Телемаркетолог Очень Длинная Фамилия",
                    "employee_role": "telemarketing",
                    "dials": 41,
                    "normal_calls": 0,
                    "messenger_dialogs": 1,
                    "connect_rate": 0.0,
                    "total_known": 41,
                },
                {
                    "manager_id": "sales-1",
                    "manager_name": "Елизавета Деговцова",
                    "employee_role": "sales",
                    "dials": 18,
                    "normal_calls": 2,
                    "messenger_dialogs": 3,
                    "connect_rate": 2 / 18,
                    "total_known": 21,
                },
                {
                    "manager_id": "sales-2",
                    "manager_name": "Анна Гудинова Сергеевна",
                    "employee_role": "sales",
                    "dials": 12,
                    "normal_calls": 4,
                    "messenger_dialogs": 4,
                    "connect_rate": 4 / 12,
                    "total_known": 16,
                },
            ],
        }
        analysis = {
            "conducted_meetings": [
                {
                    "assigned_id": "sales-2",
                    "assigned_name": "Анна Гудинова",
                    "yesterday_moved": True,
                }
            ]
        }

        lines = _communications_items(summary, analysis)
        self.assertEqual(lines[0], "Статус: 🔥 НОРМ | ⚠️ РИСК | ❌ СТОП")
        self.assertTrue(lines[1].startswith("<pre>"))
        self.assertIn("Статус Менеджер", lines[1])
        self.assertIn("Иван Телемаркетолог", lines[1])
        block_rows = lines[1].removeprefix("<pre>").removesuffix("</pre>").splitlines()
        self.assertTrue(all(len(row) == len(block_rows[0]) for row in block_rows))
        self.assertIn("Роль", lines[1])
        self.assertRegex(lines[1], r"СТОП\s+Иван Телемаркетолог\s+TM.+\s-\s+2\.4")
        self.assertLess(lines[1].find("РИСК"), lines[1].find("СТОП"))
        self.assertRegex(lines[1], r"РИСК\s+Гудинова Анна\s+SM.+\s1\s+5\.4")
        self.assertIn("Итого по отделу:", lines[3])
        self.assertIn("Наб   71 | Дзв    6 | Конв  8.5% | Чаты    8 | Встр    1", lines[4])
        self.assertIn("Опер  3.5", lines[4])
        self.assertEqual(lines[6], "Чистой клиентской активности по команде ниже целевого уровня")
        self.assertNotIn("Расшифровка расчета активности:", lines)
        self.assertNotIn("пустой набор = 1.5 мин", lines)
        self.assertNotIn("дозвон = 15 мин для SM, 12 мин для TM", lines)
        self.assertNotIn("Опер = min(10; активные минуты / 300 × 10)", lines)

    def test_sales_team_filter_keeps_only_active_users_from_target_departments(self) -> None:
        department_filter = resolve_sales_team_filter(
            {"SALES_DEPARTMENT_IDS": "5"},
            snapshot={
                "departments": [
                    {"id": "5", "name": "Отдел продаж", "head_user_id": "900"},
                    {"id": "11", "name": "Группа продаж Belberry", "parent_id": "5"},
                    {"id": "12", "name": "Группа продаж Acoola Team", "parent_id": "5"},
                    {"id": "13", "name": "Телемаркетинг", "parent_id": "5"},
                    {"id": "99", "name": "Финансы"},
                ],
                "responsibles": {
                    "101": {
                        "id": "101",
                        "full_name": "Анна Белберри",
                        "active": True,
                        "department_ids": ["11"],
                    },
                    "102": {
                        "id": "102",
                        "full_name": "Тимур Телемаркетинг",
                        "active": True,
                        "department_ids": ["13"],
                    },
                    "900": {
                        "id": "900",
                        "full_name": "Евгения Романовна",
                        "active": True,
                        "position": "РОП",
                        "department_ids": ["5"],
                    },
                    "901": {
                        "id": "901",
                        "full_name": "Отдел продаж",
                        "active": True,
                        "department_ids": ["5"],
                    },
                    "103": {
                        "id": "103",
                        "full_name": "Фёдор Финансы",
                        "active": True,
                        "department_ids": ["99"],
                    },
                    "104": {
                        "id": "104",
                        "full_name": "Уволенный Менеджер",
                        "active": False,
                        "department_ids": ["11"],
                    },
                },
            },
        )

        self.assertEqual(department_filter["found_departments"], ["Отдел продаж"])
        self.assertEqual(department_filter["allowlist_department_ids"], ["5", "11", "12", "13"])
        self.assertEqual(department_filter["allowlist_users"], ["101", "102"])
        self.assertEqual(department_filter["allowlist_count"], 2)
        self.assertEqual(department_filter["scoped_active_users_count"], 4)
        self.assertNotIn("103", department_filter["allowlist_users"])
        self.assertNotIn("104", department_filter["allowlist_users"])
        self.assertNotIn("900", department_filter["allowlist_users"])
        self.assertNotIn("901", department_filter["allowlist_users"])
        self.assertEqual(
            department_filter["excluded_users"],
            [
                {
                    "id": "900",
                    "name": "Евгения Романовна",
                    "reason": "department_head_or_service_entity",
                    "role": "SM",
                },
                {
                    "id": "901",
                    "name": "Отдел продаж",
                    "reason": "department_head_or_service_entity",
                    "role": "SM",
                },
            ],
        )

    def test_sales_team_filter_promotes_common_sales_parent_for_names_mode(self) -> None:
        department_filter = resolve_sales_team_filter(
            {},
            snapshot={
                "departments": [
                    {"id": "5", "name": "Отдел продаж", "head_user_id": "900", "parent_id": "1"},
                    {"id": "11", "name": "Группа продаж Belberry", "parent_id": "5"},
                    {"id": "12", "name": "Группа продаж Acoola Team", "parent_id": "5"},
                    {"id": "13", "name": "Телемаркетинг", "parent_id": "5"},
                    {"id": "14", "name": "Новая группа продаж", "parent_id": "5"},
                ],
                "responsibles": {
                    "101": {
                        "id": "101",
                        "full_name": "Анна Белберри",
                        "active": True,
                        "department_ids": ["11"],
                    },
                    "102": {
                        "id": "102",
                        "full_name": "Тимур Телемаркетинг",
                        "active": True,
                        "department_ids": ["13"],
                    },
                    "103": {
                        "id": "103",
                        "full_name": "Новый Менеджер",
                        "active": True,
                        "department_ids": ["14"],
                    },
                    "900": {
                        "id": "900",
                        "full_name": "Руководитель Продаж",
                        "active": True,
                        "position": "РОП",
                        "department_ids": ["5"],
                    },
                },
            },
        )

        self.assertEqual(department_filter["allowlist_department_ids"], ["5", "11", "12", "13", "14"])
        self.assertEqual(department_filter["allowlist_users"], ["101", "102", "103"])

    def test_sales_team_filter_excludes_integration_accounts_inside_sales_scope(self) -> None:
        department_filter = resolve_sales_team_filter(
            {"SALES_DEPARTMENT_IDS": "5"},
            snapshot={
                "departments": [
                    {"id": "5", "name": "Отдел продаж", "head_user_id": "900"},
                    {"id": "11", "name": "Группа продаж Belberry", "parent_id": "5"},
                ],
                "responsibles": {
                    "101": {
                        "id": "101",
                        "full_name": "Анна Белберри",
                        "active": True,
                        "department_ids": ["11"],
                    },
                    "777": {
                        "id": "777",
                        "full_name": "Колтач Интегратор",
                        "position": "CRM Integrator",
                        "active": True,
                        "department_ids": ["11"],
                    },
                },
            },
        )

        self.assertEqual(department_filter["allowlist_users"], ["101"])
        self.assertEqual(
            department_filter["excluded_users"],
            [
                {
                    "id": "777",
                    "name": "Колтач Интегратор",
                    "reason": "service_or_integration_account",
                    "role": "SM",
                },
            ],
        )

    def test_pipeline_analysis_excludes_non_sales_managers_from_overdues(self) -> None:
        department_filter = resolve_sales_team_filter(
            {"SALES_DEPARTMENT_IDS": "5"},
            snapshot={
                "departments": [
                    {"id": "5", "name": "Отдел продаж", "head_user_id": "900"},
                    {"id": "11", "name": "Группа продаж Belberry", "parent_id": "5"},
                    {"id": "99", "name": "Финансовый отдел", "parent_id": "1"},
                ],
                "responsibles": {
                    "101": {
                        "id": "101",
                        "name": "Анна",
                        "last_name": "Белберри",
                        "full_name": "Белберри Анна",
                        "active": True,
                        "department_ids": ["11"],
                    },
                    "501": {
                        "id": "501",
                        "name": "Колтач",
                        "last_name": "Интегратор",
                        "full_name": "Интегратор Колтач",
                        "position": "Finance Integrator",
                        "active": True,
                        "department_ids": ["99"],
                    },
                },
                "portal_base_url": "https://belberrycrm.bitrix24.ru",
                "deal_stage_map": [{"STATUS_ID": "C10:EXECUTING", "NAME": "В работе"}],
                "meeting_stage_map": [],
                "brief_stage_map": [],
                "deal_fields_meta": {},
                "deal_source_map": [],
                "recent_deals": [],
                "closed_deals": [],
                "meetings": [],
                "conducted_meetings": [],
                "accepted_briefs": [],
                "companies": [],
                "contacts": [],
                "task_status_map": {"2": "Новая"},
                "tasks": [
                    {
                        "id": "t-1",
                        "title": "Просрочка sales",
                        "status": "2",
                        "deadline": "2026-03-20T12:00:00+03:00",
                        "crm_bindings": ["D_1"],
                    },
                    {
                        "id": "t-2",
                        "title": "Просрочка finance",
                        "status": "2",
                        "deadline": "2026-03-20T12:00:00+03:00",
                        "crm_bindings": ["D_2"],
                    },
                ],
                "active_deals": [
                    {
                        "id": "1",
                        "title": "Sales deal",
                        "assigned_id": "101",
                        "created_at": "2026-03-10T10:00:00+03:00",
                        "updated_at": "2026-03-24T10:00:00+03:00",
                        "moved_at": "2026-03-24T10:00:00+03:00",
                        "last_activity_at": "2026-03-24T10:00:00+03:00",
                        "last_communication_at": "2026-03-24T10:00:00+03:00",
                        "stage_id": "C10:EXECUTING",
                        "semantic_id": "P",
                        "amount": "100000",
                        "category_id": "10",
                    },
                    {
                        "id": "2",
                        "title": "Finance deal",
                        "assigned_id": "501",
                        "created_at": "2026-03-10T10:00:00+03:00",
                        "updated_at": "2026-03-24T10:00:00+03:00",
                        "moved_at": "2026-03-24T10:00:00+03:00",
                        "last_activity_at": "2026-03-24T10:00:00+03:00",
                        "last_communication_at": "2026-03-24T10:00:00+03:00",
                        "stage_id": "C10:EXECUTING",
                        "semantic_id": "P",
                        "amount": "100000",
                        "category_id": "10",
                    },
                ],
            },
        )

        analysis = analyze_pipeline(
            {
                "portal_base_url": "https://belberrycrm.bitrix24.ru",
                "deal_stage_map": [{"STATUS_ID": "C10:EXECUTING", "NAME": "В работе"}],
                "meeting_stage_map": [],
                "brief_stage_map": [],
                "deal_fields_meta": {},
                "deal_source_map": [],
                "recent_deals": [],
                "active_deals": [
                    {
                        "id": "1",
                        "title": "Sales deal",
                        "assigned_id": "101",
                        "created_at": "2026-03-10T10:00:00+03:00",
                        "updated_at": "2026-03-24T10:00:00+03:00",
                        "moved_at": "2026-03-24T10:00:00+03:00",
                        "last_activity_at": "2026-03-24T10:00:00+03:00",
                        "last_communication_at": "2026-03-24T10:00:00+03:00",
                        "stage_id": "C10:EXECUTING",
                        "semantic_id": "P",
                        "amount": "100000",
                        "category_id": "10",
                    },
                    {
                        "id": "2",
                        "title": "Finance deal",
                        "assigned_id": "501",
                        "created_at": "2026-03-10T10:00:00+03:00",
                        "updated_at": "2026-03-24T10:00:00+03:00",
                        "moved_at": "2026-03-24T10:00:00+03:00",
                        "last_activity_at": "2026-03-24T10:00:00+03:00",
                        "last_communication_at": "2026-03-24T10:00:00+03:00",
                        "stage_id": "C10:EXECUTING",
                        "semantic_id": "P",
                        "amount": "100000",
                        "category_id": "10",
                    },
                ],
                "closed_deals": [],
                "meetings": [],
                "conducted_meetings": [],
                "accepted_briefs": [],
                "responsibles": {
                    "101": {
                        "id": "101",
                        "name": "Анна",
                        "last_name": "Белберри",
                        "full_name": "Белберри Анна",
                        "active": True,
                        "department_ids": ["11"],
                    },
                    "501": {
                        "id": "501",
                        "name": "Колтач",
                        "last_name": "Интегратор",
                        "full_name": "Интегратор Колтач",
                        "position": "Finance Integrator",
                        "active": True,
                        "department_ids": ["99"],
                    },
                },
                "departments": [
                    {"id": "5", "name": "Отдел продаж", "head_user_id": "900"},
                    {"id": "11", "name": "Группа продаж Belberry", "parent_id": "5"},
                    {"id": "99", "name": "Финансовый отдел", "parent_id": "1"},
                ],
                "companies": [],
                "contacts": [],
                "tasks": [
                    {
                        "id": "t-1",
                        "title": "Просрочка sales",
                        "status": "2",
                        "deadline": "2026-03-20T12:00:00+03:00",
                        "crm_bindings": ["D_1"],
                    },
                    {
                        "id": "t-2",
                        "title": "Просрочка finance",
                        "status": "2",
                        "deadline": "2026-03-20T12:00:00+03:00",
                        "crm_bindings": ["D_2"],
                    },
                ],
                "task_status_map": {"2": "Новая"},
                "next_step_source": "crm.activity.list",
            },
            now=datetime(2026, 3, 24, 12, 0, tzinfo=MOSCOW_TZ),
            department_filter=department_filter,
        )

        self.assertEqual([item["assigned_id"] for item in analysis["active_deals"]], ["101"])
        self.assertEqual([item["manager_id"] for item in analysis["overdue_deal_tasks_by_manager"]], ["101"])
        self.assertEqual(analysis["metrics"]["overdue_deal_tasks"], 1)
        self.assertEqual(
            analysis["sales_scope"]["excluded_users"],
            [
                {
                    "assigned_id": "501",
                    "assigned_name": "Интегратор Колтач",
                    "reason": "outside_sales_scope",
                }
            ],
        )

    def test_lost_reason_uses_enum_refusal_field_from_bitrix_metadata(self) -> None:
        now = datetime(2026, 3, 23, 12, 0, tzinfo=MOSCOW_TZ)
        analysis = analyze_pipeline(
            {
                "portal_base_url": "https://belberrycrm.bitrix24.ru",
                "recent_deals": [],
                "active_deals": [],
                "closed_deals": [
                    {
                        "id": "23378",
                        "title": "starline.ru",
                        "assigned_id": "2818",
                        "moved_at": "2026-03-20T11:00:00+03:00",
                        "stage_id": "C4:LOSE",
                        "semantic_id": "F",
                        "amount": "0",
                        "raw": {
                            "ID": 23378,
                            "TITLE": "starline.ru",
                            "STAGE_ID": "C4:LOSE",
                            "STAGE_SEMANTIC_ID": "F",
                            "UF_CRM_1771495464": "8574",
                        },
                    }
                ],
                "recent_leads": [],
                "active_leads": [],
                "meetings": [],
                "conducted_meetings": [],
                "briefs": [],
                "accepted_briefs": [],
                "responsibles": {
                    "2818": {
                        "id": "2818",
                        "name": "Иван",
                        "last_name": "Халин",
                        "full_name": "Халин Иван",
                        "active": True,
                    }
                },
                "companies": [],
                "contacts": [],
                "departments": [],
                "deal_stage_map": [{"STATUS_ID": "C4:LOSE", "NAME": "Отказ"}],
                "deal_source_map": [],
                "deal_fields_meta": {
                    "UF_CRM_1771495464": {
                        "type": "enumeration",
                        "formLabel": "ВХОД: Причины отказа",
                        "items": [{"ID": "8574", "VALUE": "Нет связи"}],
                    }
                },
                "meeting_stage_map": [],
                "brief_stage_map": [],
                "next_step_source": "crm.activity.list",
            },
            now=now,
        )

        self.assertEqual(len(analysis["lost_deals_yesterday"]), 1)
        self.assertEqual(analysis["lost_deals_yesterday"][0]["lost_reason"], "Нет связи")

    def test_lost_reason_uses_text_refusal_field_from_bitrix_metadata(self) -> None:
        now = datetime(2026, 3, 23, 12, 0, tzinfo=MOSCOW_TZ)
        analysis = analyze_pipeline(
            {
                "portal_base_url": "https://belberrycrm.bitrix24.ru",
                "recent_deals": [],
                "active_deals": [],
                "closed_deals": [
                    {
                        "id": "16128",
                        "title": "kryomed.ru",
                        "assigned_id": "2822",
                        "moved_at": "2026-03-20T11:00:00+03:00",
                        "stage_id": "C10:LOSE",
                        "semantic_id": "F",
                        "amount": "357795",
                        "raw": {
                            "ID": 16128,
                            "TITLE": "kryomed.ru",
                            "STAGE_ID": "C10:LOSE",
                            "STAGE_SEMANTIC_ID": "F",
                            "UF_CRM_635011179F7DD": "будет актуально в марте",
                        },
                    }
                ],
                "recent_leads": [],
                "active_leads": [],
                "meetings": [],
                "conducted_meetings": [],
                "briefs": [],
                "accepted_briefs": [],
                "responsibles": {
                    "2822": {
                        "id": "2822",
                        "name": "Анна",
                        "last_name": "Гудинова",
                        "full_name": "Гудинова Анна",
                        "active": True,
                    }
                },
                "companies": [],
                "contacts": [],
                "departments": [],
                "deal_stage_map": [{"STATUS_ID": "C10:LOSE", "NAME": "Отказ"}],
                "deal_source_map": [],
                "deal_fields_meta": {
                    "UF_CRM_635011179F7DD": {
                        "type": "string",
                        "formLabel": "Причины отказа (развернутый комментарий)",
                    }
                },
                "meeting_stage_map": [],
                "brief_stage_map": [],
                "next_step_source": "crm.activity.list",
            },
            now=now,
        )

        self.assertEqual(len(analysis["lost_deals_yesterday"]), 0)
        self.assertEqual(len(analysis["postponed_deals_yesterday"]), 1)
        self.assertTrue(analysis["postponed_deals_yesterday"][0]["deferred"])

    def test_sales_delivery_reports_main_failure_and_attempts_risks_and_focus_followups(self) -> None:
        agent = SalesAgent(provider=object(), now=datetime(2026, 3, 24, 9, 30, tzinfo=MOSCOW_TZ))
        fake_payload = {
            "analysis": {},
            "risk_report": {},
            "communications_summary": {},
        }

        with (
            patch.object(SalesAgent, "build_report_payload", return_value=fake_payload),
            patch.object(SalesAgent, "render", side_effect=["main sales", "risks sales", "focus sales"]),
            patch.object(
                SalesAgent,
                "send_to_telegram",
                side_effect=[
                    SalesAgentError("main failed"),
                    {"status": "sent", "chat_id_masked": "12***34", "message_ids": ["79"], "chunks": 1},
                    {"status": "sent", "chat_id_masked": "12***34", "message_ids": ["80"], "chunks": 1},
                ],
            ) as send_mock,
        ):
            with self.assertRaises(SalesAgentError) as error:
                agent.run(report_type="sales", send=True)

        self.assertEqual(send_mock.call_count, 3)
        self.assertIn("main failed", str(error.exception))

    def test_sales_run_builds_focus_followup(self) -> None:
        agent = SalesAgent(provider=object(), now=datetime(2026, 3, 24, 9, 30, tzinfo=MOSCOW_TZ))
        fake_payload = {
            "analysis": {},
            "risk_report": {},
            "communications_summary": {},
        }

        with (
            patch.object(SalesAgent, "build_report_payload", return_value=fake_payload),
            patch.object(
                SalesAgent,
                "render",
                side_effect=[
                    (
                        "<b>📊 Сводка по продажам</b>\n"
                        "<b>Итоги за прошлый рабочий день</b>\n"
                        "<b>Воронка</b>\n"
                        "<b>На стадии договора</b>\n"
                        "<b>Источники новых сделок</b>"
                    ),
                    (
                        "<b>⚠️ Риски по сделкам</b>\n"
                        "Без движения &gt; 14 дн.\n"
                        "Без следующего шага\n"
                        "Без коммуникации &gt; 14 дн.\n"
                        "Сделки с просрочками"
                    ),
                    (
                        "<b>🎯 Фокус РОПа</b>\n"
                        "Что РОП обязан сделать сегодня:\n"
                        "🔥 Молодцы за вчера"
                    ),
                ],
            ),
            patch.object(
                SalesAgent,
                "send_to_telegram",
                side_effect=[
                    {"status": "sent", "chat_id_masked": "12***34", "message_ids": ["78"], "chunks": 1},
                    {"status": "sent", "chat_id_masked": "12***34", "message_ids": ["79"], "chunks": 1},
                    {"status": "sent", "chat_id_masked": "12***34", "message_ids": ["80"], "chunks": 1},
                ],
            ) as send_mock,
        ):
            result = agent.run(report_type="sales", send=True)

        self.assertEqual(send_mock.call_count, 3)
        self.assertEqual(result["followup_build_errors"], [])
        self.assertEqual(len(result["followup_messages"]), 2)
        self.assertEqual([item["report_type"] for item in result["followup_messages"]], ["risks", "focus"])
        self.assertIn("⚠️ Риски по сделкам", result["followup_messages"][0]["text"])
        self.assertIn("🎯 Фокус РОПа", result["followup_messages"][1]["text"])
        self.assertEqual(result["telegram"]["followups"][0]["message_ids"], ["79"])
        self.assertEqual(result["telegram"]["followups"][1]["message_ids"], ["80"])

    def test_sales_run_records_followup_render_error(self) -> None:
        agent = SalesAgent(provider=object(), now=datetime(2026, 3, 24, 9, 30, tzinfo=MOSCOW_TZ))
        fake_payload = {
            "analysis": {},
            "risk_report": {},
            "communications_summary": {},
        }

        with (
            patch.object(SalesAgent, "build_report_payload", return_value=fake_payload),
            patch.object(
                SalesAgent,
                "render",
                side_effect=[
                    (
                        "<b>📊 Сводка по продажам</b>\n"
                        "<b>Итоги за прошлый рабочий день</b>\n"
                        "<b>Воронка</b>\n"
                        "<b>На стадии договора</b>\n"
                        "<b>Источники новых сделок</b>"
                    ),
                    SalesAgentError("risks render failed"),
                    SalesAgentError("focus render failed"),
                ],
            ),
            patch.object(
                SalesAgent,
                "send_to_telegram",
                return_value={"status": "sent", "chat_id_masked": "12***34", "message_ids": ["78"], "chunks": 1},
            ) as send_mock,
        ):
            with self.assertRaises(SalesAgentError) as error:
                agent.run(report_type="sales", send=True)

        self.assertEqual(send_mock.call_count, 1)
        self.assertIn("risks (render): risks render failed", str(error.exception))
        self.assertIn("focus (render): focus render failed", str(error.exception))


class SalesBridgeRuntimeTests(unittest.TestCase):
    def test_build_followup_messages_returns_risks_then_focus_in_mock_mode(self) -> None:
        followups = _build_followup_messages(
            Path("/tmp/fake-root"),
            report_type="sales",
            env={"EXTRA_FLAG": "1"},
            use_mock=True,
        )

        self.assertEqual([item["report_type"] for item in followups], ["risks", "focus"])
        self.assertIn("Риски", followups[0]["text"])
        self.assertIn("Фокус РОПа", followups[1]["text"])

    def test_run_sales_agent_skips_followups_for_sales_preview(self) -> None:
        with patch("scripts.run_sales_copilot.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            run_mock.return_value.stdout = "ok"
            run_mock.return_value.stderr = ""

            result = _run_sales_agent(
                Path("/tmp/fake-root"),
                "sales",
                send=False,
                env={"EXTRA_FLAG": "1"},
            )

        self.assertEqual(result, "ok")
        _, kwargs = run_mock.call_args
        self.assertEqual(kwargs["env"]["SALES_SKIP_ACCESS_REPORT"], "1")
        self.assertNotIn("SALES_SKIP_FOLLOWUPS", kwargs["env"])

    def test_run_sales_agent_send_does_not_set_followup_flag(self) -> None:
        with patch("scripts.run_sales_copilot.subprocess.run") as run_mock:
            run_mock.return_value.returncode = 0
            run_mock.return_value.stdout = "ok"
            run_mock.return_value.stderr = ""

            _run_sales_agent(
                Path("/tmp/fake-root"),
                "sales",
                send=True,
                env={"EXTRA_FLAG": "1"},
            )

        _, kwargs = run_mock.call_args
        self.assertNotIn("SALES_SKIP_ACCESS_REPORT", kwargs["env"])
        self.assertNotIn("SALES_SKIP_FOLLOWUPS", kwargs["env"])


class BitrixSalesAdapterProductRowsTests(unittest.TestCase):
    def test_attach_hot_stage_product_rows_uses_shorter_timeout(self) -> None:
        analysis = {"hot_stage_deals": [{"id": "16266"}]}
        captured_env: dict[str, str] = {}

        class FakeAdapter:
            def get_deal_product_rows(self, deal_ids):  # noqa: ANN001
                self.deal_ids = list(deal_ids)
                return {"16266": [{"PRODUCT_NAME": "SEO"}]}

        fake_adapter = FakeAdapter()

        with patch(
            "apps.lev_petrovich.legacy_sales_agent.sales_agent.BitrixSalesAdapter.from_env",
            side_effect=lambda env: captured_env.update(dict(env)) or fake_adapter,
        ):
            _attach_hot_stage_product_rows(
                {
                    "BITRIX_TIMEOUT_SEC": "20",
                    "SALES_PRODUCT_ROWS_TIMEOUT_SEC": "2",
                },
                analysis,
            )

        self.assertEqual(captured_env["BITRIX_TIMEOUT_SEC"], "2")
        self.assertEqual(analysis["hot_stage_deals"][0]["product_rows"], [{"PRODUCT_NAME": "SEO"}])

    def test_attach_hot_stage_product_rows_retries_with_full_timeout_when_short_pass_returns_empty(self) -> None:
        analysis = {"hot_stage_deals": [{"id": "16266"}]}
        requested_timeouts: list[str] = []

        class FakeAdapter:
            def __init__(self, timeout_value: str) -> None:
                self.timeout_value = timeout_value

            def get_deal_product_rows(self, deal_ids):  # noqa: ANN001
                requested_timeouts.append(self.timeout_value)
                if self.timeout_value == "2":
                    return {}
                return {"16266": [{"PRODUCT_NAME": "SEO", "SUM": "164500"}]}

        with patch(
            "apps.lev_petrovich.legacy_sales_agent.sales_agent.BitrixSalesAdapter.from_env",
            side_effect=lambda env: FakeAdapter(str(env.get("BITRIX_TIMEOUT_SEC") or "")),
        ):
            _attach_hot_stage_product_rows(
                {
                    "BITRIX_TIMEOUT_SEC": "20",
                    "SALES_PRODUCT_ROWS_TIMEOUT_SEC": "2",
                },
                analysis,
            )

        self.assertEqual(requested_timeouts, ["2", "20"])
        self.assertEqual(analysis["hot_stage_deals"][0]["product_rows"], [{"PRODUCT_NAME": "SEO", "SUM": "164500"}])

    def test_get_deal_product_rows_uses_batch_for_app_oauth(self) -> None:
        class FakeProvider:
            def mode(self) -> str:
                return "webhook"

            def call_method(self, *args, **kwargs):  # noqa: ANN002, ANN003
                raise AssertionError("sequential provider fallback should not be used")

        class FakeAppAuth:
            def __init__(self) -> None:
                self.batch_calls: list[tuple[str, dict[str, object], object]] = []

            def is_configured(self) -> bool:
                return True

            def call_payload(self, method: str, params=None, default=None):  # noqa: ANN001
                self.batch_calls.append((method, dict(params or {}), default))
                return {
                    "result": {
                        "result": {
                            "deal_16266": [
                                {"PRODUCT_NAME": "SEO", "PRICE": "164500"},
                                {"PRODUCT_NAME": "AEO", "PRICE": "124188"},
                            ],
                            "deal_16270": [
                                {"PRODUCT_NAME": "Program", "PRICE": "56000"},
                            ],
                        },
                        "result_error": {},
                    }
                }

            def call_method(self, *args, **kwargs):  # noqa: ANN002, ANN003
                raise AssertionError("sequential app fallback should not be used")

        app_auth = FakeAppAuth()
        adapter = BitrixSalesAdapter(provider=FakeProvider(), app_auth=app_auth)

        result = adapter.get_deal_product_rows(["16266", "16270"])

        self.assertEqual(len(app_auth.batch_calls), 1)
        self.assertEqual(app_auth.batch_calls[0][0], "batch")
        self.assertEqual(
            result,
            {
                "16266": [
                    {"PRODUCT_NAME": "SEO", "PRICE": "164500"},
                    {"PRODUCT_NAME": "AEO", "PRICE": "124188"},
                ],
                "16270": [
                    {"PRODUCT_NAME": "Program", "PRICE": "56000"},
                ],
            },
        )


class SalesMorningDispatchHealthTests(unittest.TestCase):
    def test_morning_dispatch_health_reports_success_only_for_scheduled_job(self) -> None:
        now = datetime(2026, 3, 24, 9, 40, tzinfo=MOSCOW_TZ)
        sales_meta = report_format_metadata("sales")
        risks_meta = report_format_metadata("risks")
        focus_meta = report_format_metadata("focus")
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "sales_agent.log"
            events = [
                {
                    "ts_msk": "2026-03-24T09:30:00+03:00",
                    "event": "sales_dispatch_start",
                    "report_type": "sales",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                },
                {
                    "ts_msk": "2026-03-24T09:31:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "sales",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": sales_meta["format_version"],
                    "template_id": sales_meta["template_id"],
                    "format_markers": report_required_markers("sales"),
                },
                {
                    "ts_msk": "2026-03-24T09:32:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "risks",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": risks_meta["format_version"],
                    "template_id": risks_meta["template_id"],
                    "format_markers": report_required_markers("risks"),
                },
                {
                    "ts_msk": "2026-03-24T09:33:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "focus",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": focus_meta["format_version"],
                    "template_id": focus_meta["template_id"],
                    "format_markers": report_required_markers("focus"),
                },
                {
                    "ts_msk": "2026-03-24T09:35:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "focus",
                    "trigger": "manual",
                    "job_name": "manual_focus_dispatch",
                    "format_version": focus_meta["format_version"],
                    "template_id": focus_meta["template_id"],
                    "format_markers": report_required_markers("focus"),
                },
            ]
            log_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in events) + "\n",
                encoding="utf-8",
            )

            result = evaluate_morning_dispatch(now=now, log_path=log_path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_reports"], [])
        self.assertEqual(sorted(result["sent_reports"]), ["focus", "risks", "sales"])

    def test_morning_dispatch_health_detects_missing_risks_and_focus(self) -> None:
        now = datetime(2026, 3, 24, 9, 40, tzinfo=MOSCOW_TZ)
        sales_meta = report_format_metadata("sales")
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "sales_agent.log"
            events = [
                {
                    "ts_msk": "2026-03-24T09:30:00+03:00",
                    "event": "sales_dispatch_start",
                    "report_type": "sales",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                },
                {
                    "ts_msk": "2026-03-24T09:31:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "sales",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": sales_meta["format_version"],
                    "template_id": sales_meta["template_id"],
                    "format_markers": report_required_markers("sales"),
                },
            ]
            log_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in events) + "\n",
                encoding="utf-8",
            )

            result = evaluate_morning_dispatch(now=now, log_path=log_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["missing_reports"], ["risks", "focus"])

    def test_morning_dispatch_health_detects_wrong_followup_order(self) -> None:
        now = datetime(2026, 3, 24, 9, 40, tzinfo=MOSCOW_TZ)
        sales_meta = report_format_metadata("sales")
        risks_meta = report_format_metadata("risks")
        focus_meta = report_format_metadata("focus")
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "sales_agent.log"
            events = [
                {
                    "ts_msk": "2026-03-24T09:30:00+03:00",
                    "event": "sales_dispatch_start",
                    "report_type": "sales",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": sales_meta["format_version"],
                    "template_id": sales_meta["template_id"],
                    "format_markers": report_required_markers("sales"),
                },
                {
                    "ts_msk": "2026-03-24T09:31:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "sales",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": sales_meta["format_version"],
                    "template_id": sales_meta["template_id"],
                    "format_markers": report_required_markers("sales"),
                },
                {
                    "ts_msk": "2026-03-24T09:32:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "focus",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": focus_meta["format_version"],
                    "template_id": focus_meta["template_id"],
                    "format_markers": report_required_markers("focus"),
                },
                {
                    "ts_msk": "2026-03-24T09:33:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "risks",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": risks_meta["format_version"],
                    "template_id": risks_meta["template_id"],
                    "format_markers": report_required_markers("risks"),
                },
            ]
            log_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in events), encoding="utf-8")

            result = evaluate_morning_dispatch(now=now, log_path=log_path)

        self.assertFalse(result["ok"])
        self.assertFalse(result["sequence_ok"])
        self.assertEqual(result["sent_sequence"], ["sales", "focus", "risks"])

    def test_morning_dispatch_health_detects_legacy_format(self) -> None:
        now = datetime(2026, 3, 24, 9, 40, tzinfo=MOSCOW_TZ)
        focus_meta = report_format_metadata("focus")
        risks_meta = report_format_metadata("risks")
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "sales_agent.log"
            events = [
                {
                    "ts_msk": "2026-03-24T09:30:00+03:00",
                    "event": "sales_dispatch_start",
                    "report_type": "sales",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                },
                {
                    "ts_msk": "2026-03-24T09:31:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "sales",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": "legacy-v1",
                    "template_id": "legacy.sales.format",
                    "format_markers": ["📊 Sales Copilot"],
                },
                {
                    "ts_msk": "2026-03-24T09:32:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "risks",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": risks_meta["format_version"],
                    "template_id": risks_meta["template_id"],
                    "format_markers": report_required_markers("risks"),
                },
                {
                    "ts_msk": "2026-03-24T09:33:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "focus",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": focus_meta["format_version"],
                    "template_id": focus_meta["template_id"],
                    "format_markers": report_required_markers("focus"),
                },
            ]
            log_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in events) + "\n",
                encoding="utf-8",
            )

            result = evaluate_morning_dispatch(now=now, log_path=log_path)

        self.assertFalse(result["ok"])
        self.assertIn("sales", result["format_issues_by_report"])

    def test_morning_dispatch_health_detects_missing_required_sections(self) -> None:
        now = datetime(2026, 3, 24, 9, 40, tzinfo=MOSCOW_TZ)
        sales_meta = report_format_metadata("sales")
        risks_meta = report_format_metadata("risks")
        focus_meta = report_format_metadata("focus")
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "sales_agent.log"
            events = [
                {
                    "ts_msk": "2026-03-24T09:30:00+03:00",
                    "event": "sales_dispatch_start",
                    "report_type": "sales",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                },
                {
                    "ts_msk": "2026-03-24T09:31:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "sales",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": sales_meta["format_version"],
                    "template_id": sales_meta["template_id"],
                    "format_markers": [
                        "📊 Сводка по продажам",
                        "Итоги за прошлый рабочий день",
                        "Воронка",
                        "Риски",
                    ],
                },
                {
                    "ts_msk": "2026-03-24T09:32:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "risks",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": risks_meta["format_version"],
                    "template_id": risks_meta["template_id"],
                    "format_markers": report_required_markers("risks"),
                },
                {
                    "ts_msk": "2026-03-24T09:33:00+03:00",
                    "event": "sales_report_sent",
                    "report_type": "focus",
                    "trigger": "scheduled",
                    "job_name": "morning_sales_dispatch",
                    "format_version": focus_meta["format_version"],
                    "template_id": focus_meta["template_id"],
                    "format_markers": report_required_markers("focus"),
                },
            ]
            log_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in events) + "\n",
                encoding="utf-8",
            )

            result = evaluate_morning_dispatch(now=now, log_path=log_path)

        self.assertFalse(result["ok"])
        self.assertIn("sales", result["format_issues_by_report"])
        self.assertTrue(
            any("missing_markers=" in issue for issue in result["format_issues_by_report"]["sales"])
        )


class SalesTelegramRoutingTests(unittest.TestCase):
    def test_sales_chat_resolution_normalizes_telegram_prefix_and_keeps_report_chat(self) -> None:
        chat_id = _resolve_sales_chat_id(
            {
                "SALES_TELEGRAM_CHAT_ID": "telegram:-5144911139",
                "SALES_TELEGRAM_OWNER_ID": "telegram:81681699",
            },
            report_type="sales",
        )

        self.assertEqual(chat_id, "-5144911139")

    def test_sales_chat_resolution_falls_back_to_personal_chat(self) -> None:
        chat_id = _resolve_sales_chat_id(
            {
                "SALES_TELEGRAM_OWNER_ID": "telegram:81681699",
            },
            report_type="sales",
        )

        self.assertEqual(chat_id, "81681699")

    def test_lev_petrovich_token_resolution_reads_dedicated_token_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            token_file = Path(tmp_dir) / "lev-petrovich.bot_token"
            token_file.write_text("dedicated-sales-token\n", encoding="utf-8")

            token = resolve_lev_petrovich_bot_token(
                {
                    "SALES_TELEGRAM_BOT_TOKEN_FILE": str(token_file),
                    "TELEGRAM_BOT_TOKEN": "shared-token",
                }
            )

        self.assertEqual(token, "dedicated-sales-token")

    def test_lev_petrovich_token_resolution_does_not_fallback_to_shared_token_by_default(self) -> None:
        token = resolve_lev_petrovich_bot_token(
            {
                "TELEGRAM_BOT_TOKEN": "shared-token",
            }
        )

        self.assertEqual(token, "")


if __name__ == "__main__":
    unittest.main()
