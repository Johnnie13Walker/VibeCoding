# OpenClaw server-only audit — 2026-04-30 МСК

## Цель

Зафиксировать текущее состояние `/opt/openclaw` как отдельного server-only runtime/repo contour после cutover Cloudbot runtime.

Аудит выполнен в read-only режиме. Никакие файлы, symlink, cron, systemd, Docker, env и runtime pointers не изменялись.

## Контекст Cloudbot runtime

- Время проверки: `2026-04-30 12:59 МСК`
- Engineer `dev`: `828b5a5 docs: record lev sales live observation`
- Lev/Sales runtime:
  - `/opt/cloudbot-runtime/current`
  - target: `/opt/cloudbot-runtime/releases/dev_0c76cdf`
- Larisa runtime:
  - `/opt/cloudbot-runtime/larisa/current`
  - target: `/opt/cloudbot-runtime/larisa/releases/dev_2bb6635`

## OpenClaw git state

- Repo: `/opt/openclaw`
- Branch state: detached `HEAD`
- Commit: `61d171ab0b`
- Tag: `v2026.3.13-1`
- Status: dirty

Tracked modified files:

- `docker-compose.yml`
- `src/agents/openclaw-tools.ts`
- `src/agents/tools/web-search.ts`
- `src/commands/onboard-search.ts`
- `src/config/schema.labels.ts`
- `src/config/types.tools.ts`
- `src/config/zod-schema.agent-runtime.ts`
- `src/media-understanding/runner.video.test.ts`
- `src/secrets/runtime-web-tools.ts`

Untracked server files include:

- `.env`
- `.env.bak.*`
- `.env.dedupe-bak.*`
- `.env.example.bak.*`
- `.env.security_profile`
- `docker-compose.yml.bak.*`
- source/docs backups with `codex-web-search-env` / `codex-duckduckgo` suffixes
- `state/bitrix_app/*.json`

These untracked files are server-local state/backups and must not be copied into the engineer repo or committed.

## Tracked dirty changes classification

### Likely active web-search / SearXNG / DuckDuckGo runtime work

- `docker-compose.yml`
  - adds runtime variables such as `NODE_COMPILE_CACHE` and `OPENCLAW_NO_RESPAWN`
  - binds OpenClaw gateway/bridge to `127.0.0.1`
  - connects OpenClaw to external `searxng_default` Docker network
- `src/agents/tools/web-search.ts`
  - extends web-search providers
  - adds DuckDuckGo and local SearXNG configuration paths
  - includes OpenAI Responses web-search handling and citation extraction
- `src/commands/onboard-search.ts`
  - adds DuckDuckGo provider onboarding flow
- `src/config/schema.labels.ts`
- `src/config/types.tools.ts`
- `src/config/zod-schema.agent-runtime.ts`
- `src/secrets/runtime-web-tools.ts`
  - extend config/schema/runtime-secret handling for DuckDuckGo/SearXNG/OpenAI web-search providers

### Runtime integration support

- `src/agents/openclaw-tools.ts`
  - passes `agentDir` into tool creation options.

### Test-only / incidental change

- `src/media-understanding/runner.video.test.ts`
  - removes one explicit `MOONSHOT_API_KEY: undefined` test env line.

## Runtime and service snapshot

Docker containers:

- `openclaw-openclaw-gateway-1`
  - image: `openclaw:ddg-searxng-20260412`
  - status: `Up 8 days (healthy)`
  - ports: `127.0.0.1:18789-18790->18789-18790/tcp`
- `searxng`
  - image: `searxng/searxng:latest`
  - status: `Up 11 days`
  - port: `0.0.0.0:8088->8080/tcp`
- `searxng-redis`
  - image: `valkey/valkey:8-alpine`
  - status: `Up 11 days`

Services:

- `docker.service`: active
- `cloudbot-bitrix-app.service`: active
- OpenClaw gateway Docker health: `healthy`

## Cron snapshot

### `/etc/cron.d/openclaw-todo-digest`

Observed jobs:

- Todo sync every 30 minutes
- Additional Todo sync pre-slots
- Todo reminders every minute
- Execution tick every 15 minutes
- Morning/midday/evening Todo digest jobs are commented as disabled after Larisa cutover

### `/etc/cron.d/openclaw-whoop-report`

- Schedule: `1 5 * * *` UTC
- Effective time: `08:01 МСК`
- Command: `WHOOP_ENV_FILE=/etc/openclaw/whoop.env /usr/local/bin/send_whoop_report.py send-report`

## Log snapshot

Latest observed log timestamps were fresh around `2026-04-30 13:00 МСК`.

Todo logs:

- `/var/log/openclaw-todo-sync.log`
  - snapshot saved
  - `tasks=137`
  - transient Todo API `503` retries observed
- `/var/log/openclaw-todo-reminders.log`
  - `reminders_ok`
  - transient Todo API `503` retries observed
- `/var/log/openclaw-execution-tick.log`
  - `execution_ok`
  - transient Todo API `503` retry observed

WHOOP log:

- `/var/log/openclaw-whoop-report.log`
  - latest run at `2026-04-30 08:01 МСК`
  - recovery/sleep/cycle data present
  - Telegram delivery line present: `Отчёт отправлен в Telegram`

## State and backup volume

- `/opt/openclaw/state`: `17M`
- `/opt/openclaw`: `4.2G`
- `state/bitrix_app` contains fresh install/Wazzup JSON snapshots up to `2026-04-30 12:45 МСК`
- `.env` and multiple `.env*.bak` files exist in the repo directory

No secret values were copied into this report. Env/state files remain server-local and must be treated as sensitive.

## Findings

1. `/opt/openclaw` is not a clean deploy checkout. It is a detached, dirty, server-only runtime with active local modifications.
2. The tracked modifications look primarily related to OpenClaw web-search provider work: SearXNG, DuckDuckGo, OpenAI web-search configuration and onboarding.
3. Docker runtime currently depends on the SearXNG contour, including the external `searxng_default` network and the `openclaw:ddg-searxng-20260412` image.
4. `/opt/openclaw/state` and `.env*` files are operational state/secrets/backups, not migration source material.
5. OpenClaw Todo/WHOOP cron contours are active and separate from the Cloudbot Larisa and Lev/Sales runtime cutover.
6. Todo integration saw transient `503` retries, but latest observed logs still ended with successful sync/reminder/execution status.

## Recommendations

1. Do not merge or copy `/opt/openclaw` wholesale into `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`.
2. Keep `/opt/openclaw` out of the Cloudbot runtime cutover scope until a separate OpenClaw migration/cleanup approval.
3. If the web-search/SearXNG/DuckDuckGo work is needed in engineer, extract it later as a reviewed patch from tracked diffs only.
4. Never copy `.env*`, `state/`, Bitrix snapshots, backup files, or runtime-generated files into git.
5. Do not archive or delete OpenClaw backup files without a separate explicit approval and a rollback note.
6. Treat OpenClaw as a separate server-only contour for the final Cloudbot migration checklist.

## Verdict

OpenClaw is operational but dirty and server-specific.

It should remain no-touch for the Cloudbot apps migration completion. The Cloudbot migration can continue with Larisa and Lev/Sales scheduled observation, while OpenClaw requires a separate controlled cleanup/extraction track later.
