# First Safe Commit Readiness

## Recommendation

The repo is not ready for `git add .`.

It is conditionally ready for a selective migration-only commit if the staged file list is reviewed manually before commit.

## Why Selective Only

The working tree still contains unrelated dirty changes in production, infra, finance, iOS, HAPP/VPN, subscription, deleted deploy scripts, and control-plane snapshots.

A full commit would mix approved structural migration with unrelated or unreviewed changes.

## Migration-Only Candidate Zones

Candidate zones for a first safe structural commit:

- `docs/migration/`
- `apps/`
- `shared/`
- `config/env/examples/`
- `tests/unit/`
- `tests/integration/`
- `tests/smoke/`
- `archive/`
- `cloudbot/business_day.py`
- `agents/sales_agent/README.md`
- `agents/sales_agent/report_contract.py`
- `agents/larisa_ivanovna/timezone.py`
- `agents/larisa_ivanovna/README.md`
- `agents/lev_petrovich/README.md`

## Files That Need Extra Human Attention Before Staging

These touched files are production-adjacent and must be reviewed in `git diff` before staging:

- `agents/sales_agent/sales_agent.py`
- `agents/sales_agent/sales_formatter.py`
- `scripts/run_sales_copilot.py`

Reason:

- their current diffs contain old feature/runtime changes mixed with migration hunks;
- they must not be staged as whole files in the first safe migration commit.

Safe production-adjacent files for the first commit:

- `cloudbot/business_day.py`
- `agents/larisa_ivanovna/timezone.py`
- `agents/sales_agent/report_contract.py`

## Explicitly Excluded From First Safe Commit

Do not stage:

- `.env*`
- `configs/*.env`
- `configs/*.cron`
- `infra/orchestrator/workflows/deploy.sh`
- `infra/orchestrator/workflows/rollback.sh`
- `infra/orchestrator/workflows/verify.sh`
- `infra/orchestrator/workflows/audit.sh`
- `checks/*`
- `control_plane_snapshots/`
- `apps/finansist/` canonical, `agents/finansist/` compatibility shim
- `ios/`
- `services/subscription/`
- `ops/*happ*`
- `infra/*happ*`
- finance scripts;
- server-only integrations.

## Required Checks Before Commit

Before any commit:

- review `git diff --cached`;
- run `python3 -m py_compile` for touched shared/shim modules;
- run `python3 -m unittest discover -s tests/unit`;
- run `python3 -m unittest discover -s tests/integration`;
- run direct compatibility checks for old/new import paths;
- confirm no env, cron, systemd, docker, deploy, rollback, verify, or server runtime files are staged.

## Status

First safe commit is not approved yet.

Selective staging proposal is required first.
