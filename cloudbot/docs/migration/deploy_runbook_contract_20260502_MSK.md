# Deploy runbook contract — 2026-05-02 МСК

## Current canonical deploy entrypoint

For Cloudbot agent runtime, the canonical local deploy entrypoint is:

`infra/orchestrator/run_workflow.sh`

Current deploy workflows:

- `larisa_agent_deploy`
- `sales_agent_deploy`

Direct `scripts/deploy.sh` must not be treated as the active production deploy path for this migration.

## Runtime targets

| Contour | Runtime target | Deploy workflow |
| --- | --- | --- |
| Larisa | `/opt/cloudbot-runtime/larisa/current` | `larisa_agent_deploy` |
| Lev/Sales generic runtime | `/opt/cloudbot-runtime/current` | `sales_agent_deploy` |

`/opt/openclaw` remains a separate server-only contour and is not deployed by these workflows.

## Release manifest

Deploy workflows must use:

`infra/orchestrator/lib.sh::cloudbot_runtime_files`

The manifest is validated by:

`python3 -m unittest tests.integration.test_release_packaging_contract`

## Required preconditions

Before any live deploy:

1. Clean git worktree unless an explicit dirty deploy override is approved.
2. Release commit must exist on `origin/<branch>` unless an explicit unpushed release override is approved.
3. Runtime scope must be explicit: Larisa scoped runtime or generic Sales runtime.
4. Rollback target must be known before switching a runtime pointer.
5. Smoke checklist must be defined for the contour being changed.

## No-touch boundaries

Deploy runbook updates do not permit changing:

- env files
- cron
- systemd
- Docker
- Telegram routing
- `/opt/openclaw`
- runtime pointers outside the explicitly approved contour

## Post-change checks

After deploy-related code changes, run:

- `bash -n infra/orchestrator/lib.sh infra/orchestrator/workflows/larisa_agent_deploy.sh infra/orchestrator/workflows/sales_agent_deploy.sh`
- `python3 -m unittest tests.integration.test_release_packaging_contract`
- `python3 -m unittest tests.integration.test_app_compatibility_contract`
- `python3 checks/smoke_test.py`
