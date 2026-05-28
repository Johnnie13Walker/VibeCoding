# Phase 3 Larisa cutover report — 2026-04-30 МСК

## Status

Controlled Larisa cutover completed.

Rollback was not needed.

## Scope

Changed:

- created new Larisa runtime release:
  `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635`;
- switched only Larisa current pointer:
  `/opt/cloudbot-runtime/larisa/current`.

Not changed:

- Lev/Sales runtime;
- `/opt/cloudbot-runtime/current`;
- `/opt/openclaw`;
- env files;
- cron files;
- systemd units;
- Docker runtime;
- `/usr/local/bin/cloudbot-larisa-daily-brief.sh`;
- `/etc/cron.d/cloudbot-larisa-daily-brief`.

## Release

- Source repo: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- Branch: `dev`
- Commit used for release: `2bb6635`
- Release id: `dev_2bb6635`
- Old Larisa release: `codex_feature_self-healing_067d326`
- Old target: `/opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326`
- New target: `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635`

## Pre-cutover validation

Local checks before server mutation:

- `python3 -m unittest tests.integration.test_larisa_agent` — OK, 27 tests
- `python3 checks/sales_morning_dispatch_smoke.py` — OK

Server staging checks before switching symlink:

- `bash -n run_larisa_daily_brief_from_runtime_env.sh` — OK
- `bash -n infra/orchestrator/workflows/larisa_daily_brief.sh` — OK
- `python3 -m compileall` for `apps`, `agents`, `shared`, `cloudbot` — OK
- import `apps.larisa_ivanovna` — OK
- import `agents.larisa_ivanovna` — OK
- import `apps.larisa_ivanovna.agent` — OK
- staging dry-run daily brief — OK

## Staging issue found and fixed before cutover

First staging attempt failed before symlink switch:

- failure: `ModuleNotFoundError: No module named 'shared'`;
- cause: initial release archive did not include `shared/`;
- action: rebuilt release archive including `shared/`;
- impact: no runtime switch had happened yet;
- current pointer remained on `/opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326`.

## Cutover result

Cutover applied at approximately:

- `2026-04-30 11:41:43 МСК`

Result:

- `/opt/cloudbot-runtime/larisa/current`
  now resolves to
  `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635`;
- `RELEASE_COMMIT=2bb6635`;
- `RELEASE_BRANCH=dev`;
- `RELEASE_ID=dev_2bb6635`.

## Post-cutover smoke

Post-cutover dry-run was executed through the existing system wrapper:

- wrapper: `/usr/local/bin/cloudbot-larisa-daily-brief.sh`;
- mode: `TELEGRAM_DRY_RUN=1 LARISA_TELEGRAM_DRY_RUN=1`;
- result: OK;
- generated report:
  `/opt/cloudbot-runtime/larisa/current/reports/larisa_daily_brief_20260430_114202_MSK.txt`.

Smoke confirmed:

- Larisa imports OK;
- daily brief generation OK;
- calendar data present;
- Todo tasks present;
- Telegram route resolved to `larisa-ivanovna`;
- Telegram chat id resolved;
- delivery was dry-run, not live send;
- no immediate runtime/import error observed.

Report tail showed:

- calendar events for `2026-04-30`;
- overdue tasks;
- tasks for today;
- Telegram dry-run payload with `"route_key": "larisa-ivanovna"`.

## No-touch confirmation

Confirmed after cutover:

- `/opt/cloudbot-runtime/current`
  still resolves to
  `/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60`;
- `docker.service` is active;
- `cloudbot-bitrix-app.service` is active;
- `openclaw-openclaw-gateway-1` is still healthy;
- local Sales smoke still passes.

Wrapper and cron timestamps remained unchanged from Phase 0:

- `/usr/local/bin/cloudbot-larisa-daily-brief.sh`
  timestamp: `2026-03-26 12:27:44 +0300`;
- `/etc/cron.d/cloudbot-larisa-daily-brief`
  timestamp: `2026-04-23 09:24:53 +0300`.

## Rollback status

Rollback target remains available:

`/opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326`

Rollback was not executed because post-cutover smoke passed.

## Remaining validation

Still needs observation:

- next scheduled Larisa daily brief at `08:00 МСК`;
- live Telegram delivery from cron;
- logs after the next scheduled run.

## Gate conclusion

Larisa controlled cutover is complete.

Next recommended step:

Observe the next scheduled Larisa daily brief before starting Lev/Sales cutover work.
