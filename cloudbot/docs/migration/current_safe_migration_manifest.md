# Current Safe Migration Manifest

## Purpose

This manifest separates the current safe structural migration scope from the pre-existing dirty working tree.

It is not a staging list.
It is not a commit approval.
It is not permission to include unrelated dirty changes.

## Safe Migration Scope

The following zones are considered part of the controlled structural migration work:

- `docs/migration/`
- `apps/`
- `shared/`
- `config/env/examples/`
- `tests/unit/`
- `tests/integration/`
- `tests/smoke/`
- `archive/`
- `agents/sales_agent/README.md`
- `agents/sales_agent/report_contract.py`
- `agents/sales_agent/sales_formatter.py`
- `agents/larisa_ivanovna/timezone.py`
- `agents/larisa_ivanovna/README.md`
- `agents/lev_petrovich/README.md`
- `apps/finansist/` canonical, `agents/finansist/` compatibility shim
- `cloudbot/workflows/finance_runtime.py`
- `cloudbot/workflows/finance_summary.py`
- `cloudbot/workflows/cashflow_analysis.py`
- `cloudbot/workflows/client_profitability_analysis.py`
- `cloudbot/workflows/expense_structure_analysis.py`
- `cloudbot/workflows/finance_anomaly_scan.py`
- `cloudbot/workflows/payables_analysis.py`
- `cloudbot/workflows/pnl_analysis.py`
- `cloudbot/workflows/receivables_analysis.py`
- `tests/unit/test_finansist_agent.py`
- `checks/finansist_google_smoke.mjs`

## Production Compatibility Scope

These files are safe only because they preserve old import paths:

- `agents/sales_agent/report_contract.py`
- `agents/sales_agent/sales_formatter.py`
- `agents/larisa_ivanovna/timezone.py`
- finance core accepted in commit `aefcf1a`

Any future change to these files must keep compatibility until an explicit owner-approved import migration exists.

## Explicitly Excluded From Safe Migration Scope

The following zones must not be included in a safe migration commit without separate review:

- `.env*`
- `configs/*.env`
- `configs/*.cron`
- `infra/orchestrator/workflows/deploy.sh`
- `infra/orchestrator/workflows/rollback.sh`
- `infra/orchestrator/workflows/verify.sh`
- `infra/orchestrator/workflows/audit.sh`
- `scripts/run_sales_copilot.py`
- `scripts/deploy.sh`
- `checks/*`
- `cloudbot/orchestrator/*`
- `cloudbot/providers/*`
- `cloudbot/skills/*`
- `agents/larisa_ivanovna/*` except explicit compatibility markers/shims listed above
- `agents/sales_agent/*` except explicit compatibility markers/shims listed above
- `scripts/finansist_*.mjs`
- `ios/`
- `services/subscription/`
- `ops/*happ*`
- `infra/*happ*`
- `control_plane_snapshots/`

## Commit Safety Rule

A future commit may include only files from the safe migration scope after:

- `git diff --cached` is reviewed;
- unit tests pass;
- integration tests pass;
- compatibility import checks pass;
- no env, cron, systemd, docker, deploy, rollback, verify, or server runtime files are staged.

## Status

Safe migration manifest updated after finance core acceptance.
