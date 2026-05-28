# Phase 0 runtime confirmation — 2026-04-30 МСК

## Status

Phase 0 выполнен в read-only режиме.

Не выполнялись:

- deploy;
- restart;
- изменение runtime pointers;
- изменение env;
- изменение cron;
- изменение systemd;
- изменение Docker;
- изменение файлов в `/opt`, `/etc`, `/root`, `/home/ops`.

## Local baseline

- Local repo: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- Branch: `dev`
- HEAD before server snapshot: `365857d`
- Working tree before server snapshot: clean
- Server snapshot time: `2026-04-30T11:26:43+0300`
- Server host: `ams-1-vm-76ds`

## Runtime pointers

| Path | Resolved target | Status |
| --- | --- | --- |
| `/opt/cloudbot-runtime/larisa/current` | `/opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326` | confirmed |
| `/opt/cloudbot-runtime/current` | `/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60` | confirmed |
| `/opt/openclaw` | `/opt/openclaw` | confirmed |
| `/etc/openclaw` | `/etc/openclaw` | confirmed |

Conclusion: production runtime is still on existing release directories, not on local `dev`.

## Relevant cron files

| Cron file | Status | Last modified МСК | Notes |
| --- | --- | --- | --- |
| `/etc/cron.d/cloudbot-larisa-daily-brief` | present | `2026-04-23 09:24:53 +0300` | runs `/usr/local/bin/cloudbot-larisa-daily-brief.sh` at `05:00 UTC`, equals `08:00 МСК` |
| `/etc/cron.d/cloudbot-sales-reports` | present | `2026-04-10 15:49:19 +0300` | runs Sales daily/check/followup/weekly scripts |
| `/etc/cron.d/openclaw-todo-digest` | present | `2026-04-18 07:22:13 +0300` | runs Todo sync/reminder/execution jobs inside OpenClaw container |
| `/etc/cron.d/openclaw-whoop-report` | present | `2026-03-04 16:44:56 +0300` | runs WHOOP report script with `/etc/openclaw/whoop.env` |

Cron contents were inspected only for schedule/linkage. Secret values were not printed.

## Relevant services

| Service | Active state | Sub state | Main PID | Unit path |
| --- | --- | --- | --- | --- |
| `cloudbot-bitrix-app.service` | active | running | `721` | `/etc/systemd/system/cloudbot-bitrix-app.service` |
| `docker.service` | active | running | `937` | `/usr/lib/systemd/system/docker.service` |

## Relevant containers

| Container | Image | Status |
| --- | --- | --- |
| `openclaw-openclaw-gateway-1` | `openclaw:ddg-searxng-20260412` | `Up 8 days (healthy)` |

## Env file paths only

Values were not read or printed.

Confirmed env files:

- `/etc/openclaw/larisa.env`
- `/etc/openclaw/marketing_dashboard.env`
- `/etc/openclaw/sales_agent.env`
- `/etc/openclaw/todo.env`
- `/etc/openclaw/whoop.env`
- `/opt/openclaw/.env`
- `/opt/openclaw/.env.example`
- `/opt/openclaw/.env.security_profile`
- `/opt/openclaw/openclaw.podman.env`
- `/root/.openclaw/workspace/todo-integration/.env.runtime`
- `/root/.openclaw/workspace/todo-integration/.env.example`
- `/root/.openclaw/workspaces/commercial-director/integrations/bitrix/.env`

There are also multiple `.env.bak*` files under `/opt/openclaw` and `/etc/openclaw`.

## Launcher wrappers

| Path | Status | Last modified МСК |
| --- | --- | --- |
| `/usr/local/bin/cloudbot-larisa-daily-brief.sh` | present, executable | `2026-03-26 12:27:44 +0300` |
| `/usr/local/bin/cloudbot-sales-daily-brief.sh` | present, executable | `2026-04-10 15:49:19 +0300` |
| `/usr/local/bin/cloudbot-sales-morning-check.sh` | present, executable | `2026-04-10 15:49:19 +0300` |
| `/usr/local/bin/cloudbot-sales-followup.sh` | present, executable | `2026-04-10 15:49:19 +0300` |
| `/usr/local/bin/cloudbot-sales-weekly-review.sh` | present, executable | `2026-04-10 15:49:19 +0300` |
| `/usr/local/bin/send_whoop_report.py` | present, executable | `2026-03-31 10:33:46 +0300` |

Wrapper contents were not changed.

## Larisa freshness

Latest confirmed Larisa runtime report:

- `/opt/cloudbot-runtime/larisa/current/reports/larisa_daily_brief_20260430_080001_MSK.txt`
- timestamp: `2026-04-30 08:00:18 +0300`

Latest confirmed Larisa cron log:

- `/home/ops/cloudbot-larisa-agent/reports/larisa_daily_brief_cron.log`
- timestamp: `2026-04-30 08:00:18 +0300`

Conclusion: Larisa daily brief cron path appears fresh for `2026-04-30 08:00 МСК`.

## Sales freshness

Latest confirmed Sales morning report:

- `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_20260430_093001_MSK.txt`
- timestamp: `2026-04-30 09:31:13 +0300`

Latest confirmed Sales morning check:

- `/home/ops/cloudbot-sales-agent/reports/sales_morning_report_check_20260430_094001_MSK.txt`
- timestamp: `2026-04-30 09:40:01 +0300`

Latest confirmed Sales log/history files:

- `/home/ops/cloudbot-sales-agent/reports/sales_agent.log`
- timestamp: `2026-04-30 09:31:13 +0300`
- `/home/ops/cloudbot-sales-agent/reports/sales_daily_history.json`
- timestamp: `2026-04-30 09:31:12 +0300`

Conclusion: Sales morning report/check paths appear fresh for `2026-04-30`.

## Server git state

`/opt/openclaw` is a separate server-only repo/runtime contour.

Read-only git snapshot:

- HEAD mode: detached `HEAD`
- commit: `61d171ab0b`
- status: dirty

Dirty tracked examples:

- `docker-compose.yml`
- `src/agents/openclaw-tools.ts`
- `src/agents/tools/web-search.ts`
- `src/commands/onboard-search.ts`
- `src/config/schema.labels.ts`
- `src/config/types.tools.ts`
- `src/config/zod-schema.agent-runtime.ts`
- `src/media-understanding/runner.video.test.ts`
- `src/secrets/runtime-web-tools.ts`

There are many untracked backup files under `/opt/openclaw`.

Conclusion: `/opt/openclaw` must remain no-touch until a separate server-only dependency and dirty-state review is approved.

## Not confirmed in Phase 0

Not tested in this phase:

- live Telegram delivery;
- manual Larisa command execution;
- manual Sales command execution;
- Bitrix live data pull;
- Todo live data pull;
- WHOOP live data pull;
- web search runtime behavior;
- cutover dry-run;
- rollback execution.

Reason: Phase 0 is read-only baseline confirmation only.

## Gate conclusion

Phase 0 read-only server confirmation is complete.

Confirmed:

- runtime pointer targets are known;
- cron linkage is known;
- relevant services are active;
- OpenClaw gateway container is running and healthy;
- Larisa report path is fresh;
- Sales report path is fresh;
- env file paths are identified without exposing secrets.

Risks before any runtime cutover:

- production runtime is not on `dev` commit `365857d`;
- `/opt/openclaw` is dirty and separate from the engineer repo;
- live Telegram/API behavior was not executed in Phase 0;
- rollback targets are identified by current symlink targets, but rollback was not tested.

Recommended next step:

Proceed only to Phase 1 Larisa dry-run release validation, still without switching runtime pointers, and only with explicit owner approval.
