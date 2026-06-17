# Finance contour pending review — 2026-04-29 МСК

## Статус

Finance core принят в текущую migration line после отдельной проверки.

Приняты только Python agent/workflows/routing/tests и read-only Google smoke. Google Sheets write/build helper scripts остаются в pending review, потому что они требуют live Google credentials и могут менять внешние таблицы.

## Принято в finance core

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
- `checks/finansist_google_smoke.mjs`
- `tests/unit/test_finansist_agent.py`
- finance aliases inside `cloudbot/bot/telegram/commands.py`
- finance export inside `agents/__init__.py`
- finance smoke additions inside `checks/smoke_test.py`

## Остаётся в pending review

- `scripts/finansist_*.mjs`

## Риск

- может добавить новые Telegram commands до принятия runtime/workflow;
- может требовать Google service account secrets;
- может смешать finance business logic с текущей OpenCloud migration;
- может расширить smoke tests внешними Google Sheets зависимостями.

## Решение

Finance core можно считать принятым. Google Sheets operational scripts не включать в core commit.

Для Google scripts создать отдельный approved track позже:

1. Finance architecture review.
2. Secret handling contract.
3. Google Sheets fixture/dry-run test contract.
4. Telegram routing decision.
5. Focused finance tests.
6. Отдельный commit или отдельная branch/PR.

## Что можно проверять сейчас

- syntax only for local files;
- no secrets scan;
- dependency map.

## Что нельзя делать без owner approval

- принимать Google Sheets write/build scripts без отдельного review;
- требовать live Google secrets для базовой проверки OpenCloud;
- запускать Google write scripts без явного owner approval;
- смешивать finance Google tooling с infra/runtime migration.
