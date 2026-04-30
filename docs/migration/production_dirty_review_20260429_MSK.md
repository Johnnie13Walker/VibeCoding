# Production dirty review — 2026-04-29 МСК

## Статус

Этот документ фиксирует разбор оставшегося production dirty-state после безопасных migration/config commits.

Это не approval на deploy и не approval на live runtime changes.

## Общий вывод

Оставшиеся изменения нельзя принимать одним commit.

Они делятся на два больших функциональных блока:

1. Лариса Ивановна: content/search feature и изменения daily/evening/calendar formatting.
2. Лев Петрович / Sales: report contract hardening, follow-up delivery, daily history, product rows, bridge behavior.

Оба блока затрагивают user-facing Telegram output и runtime routing.

## Bucket 1 — Лариса content/search feature

Файлы:

- `agents/larisa_ivanovna/agent.py`
- `agents/larisa_ivanovna/commands/__init__.py`
- `agents/larisa_ivanovna/config.py`
- `agents/larisa_ivanovna/commands/get_content_post.py`
- `agents/larisa_ivanovna/commands/get_content_topics.py`
- `agents/larisa_ivanovna/commands/get_web_search.py`
- `agents/larisa_ivanovna/formatters/telegram_content_post.py`
- `agents/larisa_ivanovna/formatters/telegram_content_topics.py`
- `agents/larisa_ivanovna/schemas/content.py`
- `agents/larisa_ivanovna/workflows/content_topics.py`
- `agents/larisa_ivanovna/workflows/search.py`
- `cloudbot/workflows/larisa_content_post.py`
- `cloudbot/workflows/larisa_content_topics.py`
- `cloudbot/workflows/larisa_search.py`
- `cloudbot/workflows/larisa_runtime.py`
- `cloudbot/orchestrator/router.py`
- `cloudbot/orchestrator/orchestrator.py`
- `cloudbot/providers/search_provider.py`
- `cloudbot/skills/web_search.py`
- `cloudbot/orchestrator/search_state.py`
- `infra/orchestrator/workflows/larisa_content_topics.sh`

Роль:

Новый функциональный контур Ларисы для поиска, тем постов и черновиков постов.

Риск:

- может изменить routing команд `/search`, `/topics`, `/draft`;
- может добавить новые зависимости на web search;
- может повлиять на shared orchestrator;
- не должен включаться в cron без отдельного approval.

Решение:

Принимать только отдельным feature commit после scoped тестов Ларисы.

Не смешивать с Sales/Lev и config/env/cron.

Минимальные тесты перед принятием:

- `python3 -m unittest tests.integration.test_larisa_agent`
- `python3 -m unittest tests.integration.test_larisa_search`
- `python3 -m unittest tests.integration.test_system_health`

## Bucket 2 — Лариса daily/calendar/formatting hardening

Файлы:

- `agents/larisa_ivanovna/formatters/telegram_brief.py`
- `agents/larisa_ivanovna/formatters/telegram_meetings.py`
- `agents/larisa_ivanovna/providers/calendar_provider.py`
- `agents/larisa_ivanovna/providers/telegram_provider.py`
- `agents/larisa_ivanovna/workflows/daily_brief.py`
- `agents/larisa_ivanovna/workflows/evening_review.py`
- `docs/larisa_execution_checklist_MSK.md`
- `docs/message_for_larisa_MSK.md`

Роль:

Изменение качества вывода, нормализации времени, фильтрации календаря и Telegram routing для Ларисы.

Риск:

- может изменить утренний brief;
- может скрыть или иначе отформатировать встречи;
- может повлиять на delivery route;
- требует ручной проверки Telegram preview.

Решение:

Принимать после Bucket 1 или отдельным commit, если diff будет отделён от feature routing.

Минимальные тесты перед принятием:

- `python3 -m unittest tests.integration.test_larisa_agent`
- `python3 -m unittest tests.integration.test_system_health`

## Bucket 3 — Sales/Lev report contract hardening

Файлы:

- `agents/sales_agent/pipeline_analyzer.py`
- `agents/sales_agent/risk_detector.py`
- `agents/sales_agent/sales_agent.py`
- `agents/sales_agent/sales_formatter.py`
- `scripts/run_sales_copilot.py`
- `cloudbot/devops/sales_dispatch_health.py`
- `docs/sales_copilot.md`

Роль:

Усиление ежедневного отчёта продаж: contract markers, follow-up, daily history, product rows, overdue/postponed blocks, bridge behavior.

Риск:

- может изменить формат Telegram отчёта Льва;
- может изменить follow-up dispatch;
- может записывать local history file;
- может затронуть runtime bridge `scripts/run_sales_copilot.py`.

Решение:

Принимать отдельным Sales/Lev commit только после focused тестов.

Минимальные тесты перед принятием:

- `python3 -m unittest tests.integration.test_lev_petrovich_runtime`
- `python3 -m unittest tests.integration.test_sales_dispatch_contract`
- `python3 -m unittest tests.unit.test_bitrix_sales_adapter`

## Bucket 4 — Shared core / orchestration coupling

Файлы:

- `cloudbot/orchestrator/orchestrator.py`
- `cloudbot/orchestrator/router.py`
- `cloudbot/workflows/system_health.py`
- `agents/__init__.py`
- `Makefile`
- `checks/check_access.sh`
- `checks/instruction_conflicts.sh`
- `checks/post_change_verify.sh`
- `checks/smoke_test.py`

Роль:

Связывает новые route/workflow/test проверки с существующим runtime.

Риск:

- shared-core change может одновременно влиять на Ларису и Sales;
- нельзя принимать без понимания, какой feature block его требует.

Решение:

Не принимать как отдельный cleanup.

Принимать только вместе с тем feature block, который доказывает необходимость изменения.

## Bucket 5 — Finance contour

Файлы:

- `apps/finansist/` canonical, `agents/finansist/` compatibility shim
- `cloudbot/workflows/cashflow_analysis.py`
- `cloudbot/workflows/client_profitability_analysis.py`
- `cloudbot/workflows/expense_structure_analysis.py`
- `cloudbot/workflows/finance_anomaly_scan.py`
- `cloudbot/workflows/finance_runtime.py`
- `cloudbot/workflows/finance_summary.py`
- `cloudbot/workflows/payables_analysis.py`
- `cloudbot/workflows/pnl_analysis.py`
- `cloudbot/workflows/receivables_analysis.py`
- `scripts/finansist_*.mjs`
- `tests/unit/test_finansist_agent.py`

Роль:

Отдельный finance contour.

Риск:

Не относится к текущей migration line и может затянуть scope.

Решение:

Не включать в текущий production migration commit.

Вынести отдельным track позже.

## Рекомендуемый порядок следующих commit

1. Лариса content/search feature только после focused Larisa tests.
2. Лариса daily/calendar/formatting hardening только после preview/smoke review.
3. Sales/Lev report contract hardening только после focused Sales tests.
4. Shared core changes только вместе с доказанным feature block.
5. Finance contour отдельно, не в текущей ветке миграции.

## Проверка этого review artifact

Документ не меняет runtime, imports, env, cron, systemd или docker.

Перед commit:

- `git diff --check`
- `python3 -m unittest discover -s tests/unit`
- `python3 -m unittest discover -s tests/integration`
