# First Safe Staged File Proposal

## Purpose

This is a proposal only.

No files are staged by this document.
No commit is approved by this document.

## Recommended Commit Shape

One selective commit:

- docs and migration boundaries;
- target skeleton README files;
- test layout migration;
- shared contracts and compatibility shims;
- config example relocation.

Do not use `git add .`.

## Candidate Files And Zones To Stage

Documentation:

- `docs/migration/`

Exclude:

- `docs/migration/.DS_Store`

Target skeleton:

- `apps/`
- `shared/`
- `config/env/examples/`
- `archive/`
- `tests/README.md`
- `tests/smoke/README.md`
- `tests/unit/`
- `tests/integration/`

Compatibility markers:

- `agents/sales_agent/README.md`
- `agents/larisa_ivanovna/README.md`
- `agents/lev_petrovich/README.md`

Shared contracts and helpers:

- `shared/contracts/sales_report_contract.py`
- `shared/contracts/sales_report_format_contract.py`
- `shared/contracts/sales_runtime_contract.py`
- `shared/contracts/telegram_routing_contract.py`
- `shared/time/moscow.py`
- `shared/time/business_day.py`

Compatibility shims:

- `agents/sales_agent/report_contract.py`
- `agents/larisa_ivanovna/timezone.py`
- `cloudbot/business_day.py`

Config examples:

- `config/env/examples/app_config.env.example`
- `config/env/examples/integrations.env.example`

Moved tests:

- `tests/unit/test_bitrix_app_auth.py`
- `tests/unit/test_bitrix_sales_adapter.py`
- `tests/unit/test_search_provider.py`
- `tests/integration/test_larisa_agent.py`
- `tests/integration/test_larisa_search.py`
- `tests/integration/test_lev_petrovich_runtime.py`
- `tests/integration/test_sales_dispatch_contract.py`
- `tests/integration/test_system_health.py`

Deleted old test paths to include only as paired moves:

- `tests/test_bitrix_app_auth.py`
- `tests/test_bitrix_sales_adapter.py`
- `tests/test_larisa_agent.py`
- `tests/test_lev_petrovich_runtime.py`
- `tests/test_system_health.py`

Deleted old config example paths to include only as paired moves:

- `configs/app_config.env.example`
- `configs/integrations.env.example`

## Explicit No-Stage List

Do not stage:

- `.env*`
- `.github/`
- `configs/schedule_contract.env`
- `configs/schedules.cron`
- `checks/`
- `infra/orchestrator/workflows/deploy.sh`
- `infra/orchestrator/workflows/rollback.sh`
- `infra/orchestrator/workflows/verify.sh`
- `infra/orchestrator/workflows/audit.sh`
- `control_plane_snapshots/`
- `apps/finansist/` canonical, `agents/finansist/` compatibility shim
- `tests/unit/test_finansist_agent.py`
- `ios/`
- `services/subscription/`
- `ops/*happ*`
- `infra/*happ*`
- finance scripts;
- server-only integrations;
- unrelated modified production files not listed above.
- `agents/sales_agent/sales_agent.py`
- `agents/sales_agent/sales_formatter.py`
- `scripts/run_sales_copilot.py`

## Required Review Before Staging

Before staging, review diffs for:

- `agents/sales_agent/sales_agent.py`
- `agents/sales_agent/sales_formatter.py`
- `scripts/run_sales_copilot.py`

These three files are intentionally excluded from the first safe commit because they contain mixed dirty-state.

## Required Checks After Staging

After selective staging and before commit:

- `git diff --cached --name-status`
- `git diff --cached`
- `python3 -m py_compile` for touched shared/shim modules;
- `python3 -m unittest discover -s tests/unit`
- `python3 -m unittest discover -s tests/integration`
- direct compatibility checks for old/new import paths.

## Status

Selective staging proposal prepared.

No staging performed.
