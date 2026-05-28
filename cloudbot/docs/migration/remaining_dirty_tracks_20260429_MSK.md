# Remaining dirty tracks — 2026-04-29 МСК

## Статус

После фиксации safe migration commits в рабочем дереве остаются только два класса изменений:

1. `infra/orchestrator/*` runtime/deploy/server scripts.
2. `scripts/finansist_*.mjs` Google Sheets helper tools.

Эти изменения не входят в текущую safe migration baseline и не должны попадать в общий commit.

## Track 1: infra/orchestrator runtime scripts

### Файлы

- `infra/orchestrator/run_workflow.sh`
- `infra/orchestrator/workflows/cloudbot_github_migrate.sh`
- `infra/orchestrator/workflows/cloudbot_repo_setup.sh`
- `infra/orchestrator/workflows/cloudbot_runtime_verify.sh`
- `infra/orchestrator/workflows/daily_ops.sh`
- `infra/orchestrator/workflows/larisa_agent_deploy.sh`
- `infra/orchestrator/workflows/larisa_evening_review.sh`
- `infra/orchestrator/workflows/larisa_midday_replan.sh`
- `infra/orchestrator/workflows/openclaw_gateway_repair.sh`
- `infra/orchestrator/workflows/openclaw_healthcheck_schedule.sh`
- `infra/orchestrator/workflows/openclaw_update.sh`
- `infra/orchestrator/workflows/sales_agent_deploy.sh`
- `infra/orchestrator/workflows/todo-digest-remediate.apply.remote.sh`
- `infra/orchestrator/workflows/todo-digest-remediate.smoke.remote.sh`
- `infra/orchestrator/workflows/todo-digest-repair.sh`
- `infra/orchestrator/workflows/todo_digest_schedule.sh`

### Решение

Не принимать в safe migration commit.

Причина: изменения затрагивают deploy, cron, Docker, OpenClaw runtime, todo server workspace и remote remediation scripts.

### Минимальная проверка

- `bash -n` по всем 16 shell-файлам должен проходить.

Эта проверка подтверждает только синтаксис. Она не является runtime approval.

### Условие принятия позже

Нужен отдельный owner-approved runtime track с:

- точным scope;
- smoke checklist;
- rollback expectation;
- dry-run или inspect mode, если доступен;
- отдельным commit без смешивания с structural migration.

## Track 2: finance Google helper tools

### Файлы

- `scripts/finansist_build_employee_dictionary.mjs`
- `scripts/finansist_build_fot_analytics.mjs`
- `scripts/finansist_build_fot_demo.mjs`
- `scripts/finansist_build_fot_dynamics.mjs`
- `scripts/finansist_build_fot_salary_articles.mjs`
- `scripts/finansist_build_opiu_from_dds.mjs`
- `scripts/finansist_build_opiu_two_tabs.mjs`
- `scripts/finansist_update_employee_department.mjs`
- `scripts/finansist_update_employee_name.mjs`

Read-only helper scripts already moved to canonical path:

- `apps/finansist/tools/analyze_employee_names.mjs`
- `apps/finansist/tools/google_read_ranges.mjs`
- `apps/finansist/tools/google_sheet_inspect.mjs`

Compatibility wrappers remain in `scripts/finansist_*.mjs`.

### Решение

Не принимать в finance core commit.

Причина: это operational tooling для Google Sheets, часть scripts потенциально пишет во внешние таблицы или требует live credentials.

### Минимальная проверка

- `node --check scripts/finansist_*.mjs`
- secret scan по явным assignment-паттернам.

Эти проверки подтверждают только локальную валидность файлов. Они не подтверждают безопасность live Google operations.

### Условие принятия позже

Нужен отдельный finance tools track с:

- разделением read-only и write scripts;
- dry-run contract;
- Google credentials contract;
- fixture или mock validation;
- запретом live write без owner approval.

## Общий запрет

Не использовать `git add .` до закрытия этих двух tracks.

Любой следующий commit должен явно перечислять staged files и не смешивать:

- structural migration;
- runtime/deploy scripts;
- Google operational tools.
