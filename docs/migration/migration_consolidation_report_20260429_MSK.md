# Migration consolidation report — 2026-04-29 МСК

## Статус

Безопасный проход по dirty-state выполнен до границы runtime/finance tracks.

Production blocks Ларисы и Sales/Lev приняты отдельными commits с тестами.

Оставшиеся изменения не являются безопасной structural migration без отдельного approval.

## Принято в текущей линии

1. Config/env/cron examples and contracts.
2. Production dirty-state review.
3. Larisa content/search contour.
4. Larisa daily/calendar/formatting hardening.
5. Sales/Lev report contract hardening.
6. Architecture docs updates.
7. Remote ops SSH helper/env cleanup.
8. Local checks for remote ops.
9. Shared-core marker and root hygiene cleanup.
10. Infra pending review decision.
11. Finance pending review decision.
12. GitHub Actions sales contract checks.
13. Post-change verify sales smoke addition.

## Проверки

В ходе прохода использовались:

- `git diff --check`
- `bash -n` для shell scripts
- `python3 -m py_compile` для изменённых Python files
- `python3 -m unittest tests.integration.test_larisa_agent`
- `python3 -m unittest tests.integration.test_larisa_search`
- `python3 -m unittest tests.integration.test_system_health`
- `python3 -m unittest tests.integration.test_lev_petrovich_runtime tests.integration.test_sales_dispatch_contract -q`
- `python3 checks/sales_morning_dispatch_smoke.py`
- `python3 -m unittest discover -s tests/unit`
- `python3 -m unittest discover -s tests/integration`

Последний полный прогон:

- unit: 12 tests OK
- integration: 99 tests OK

## Оставшийся dirty-state

### Finance contour — deferred

Не принят в текущую migration line.

См. `docs/migration/finance_contour_pending_review_20260429_MSK.md`.

Связанные файлы:

- `apps/finansist/` canonical, `agents/finansist/` compatibility shim
- `cloudbot/workflows/finance_*`
- `cloudbot/workflows/cashflow_analysis.py`
- `cloudbot/workflows/pnl_analysis.py`
- `cloudbot/workflows/payables_analysis.py`
- `cloudbot/workflows/receivables_analysis.py`
- `scripts/finansist_*.mjs`
- `checks/finansist_google_smoke.mjs`
- `tests/unit/test_finansist_agent.py`
- finance additions in `agents/__init__.py`
- finance aliases in `cloudbot/bot/telegram/commands.py`
- finance smoke additions in `checks/smoke_test.py`

### Infra/runtime — deferred

Не принят в текущую migration line.

См. `docs/migration/infra_pending_review_20260429_MSK.md`.

Связанные зоны:

- `infra/orchestrator/run_workflow.sh`
- `infra/orchestrator/workflows/*deploy*`
- `infra/orchestrator/workflows/openclaw_*`
- `infra/orchestrator/workflows/todo-digest-*`
- `infra/orchestrator/workflows/larisa_*`
- `infra/orchestrator/workflows/sales_agent_deploy.sh`

## Почему это граница

Дальше начинаются изменения, которые могут:

- менять production cron;
- менять deploy/runtime release logic;
- менять docker/container behavior;
- требовать server-only dependency map;
- включать новый finance product contour;
- менять Telegram command surface для ещё не принятого finance runtime.

Эти изменения нельзя принимать как продолжение безопасной структурной миграции без отдельного owner approval.

## Следующий рекомендуемый шаг

Выбрать один из двух tracks:

1. Finance contour review and acceptance.
2. Infra/runtime review with separate approval.

Рекомендуемый порядок:

1. Сначала закрыть finance как отдельный feature branch/track или явно отложить.
2. Потом отдельно пройти infra/runtime, начиная с local-only wrappers.
3. Только после этого возвращаться к structural migration apps/shared.
