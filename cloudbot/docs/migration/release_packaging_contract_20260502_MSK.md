# Release packaging contract — 2026-05-02 МСК

## Purpose

Prevent runtime releases from missing canonical app or shared modules.

This contract exists because the first Larisa cutover staging attempt failed when `shared/` was not included in the release archive.

## Required release contents

Every Cloudbot runtime release archive must include:

- `apps/larisa_ivanovna`
- `apps/lev_petrovich`
- `apps/lev_petrovich/legacy_sales_agent`
- `apps/finansist`
- `agents/larisa_ivanovna`
- `agents/lev_petrovich`
- `agents/sales_agent`
- `cloudbot/`
- `shared/contracts`
- `shared/time`
- `infra/orchestrator/`
- `scripts/run_sales_copilot.py`

## Source of truth

Release file list is produced by:

`infra/orchestrator/lib.sh::cloudbot_runtime_files`

Deploy scripts that consume this manifest:

- `infra/orchestrator/workflows/larisa_agent_deploy.sh`
- `infra/orchestrator/workflows/sales_agent_deploy.sh`

## Compile check

Remote staging compile checks must include:

- `agents`
- `apps`
- `cloudbot`
- `shared`

## Test

Packaging contract is covered by:

`python3 -m unittest tests.integration.test_release_packaging_contract`

## No-touch

This change does not change runtime pointers, env, cron, systemd, Docker, Telegram routing or `/opt/openclaw`.
