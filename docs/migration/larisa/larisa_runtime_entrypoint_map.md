# Larisa Runtime Entrypoint Map

Дата фиксации: 2026-04-28 МСК.

Статус: read-only runtime entrypoint map. Этот документ не меняет runtime, cron, env или deploy.

## 1. Local workflow entrypoints

Confirmed local workflow commands:

```text
infra/orchestrator/workflows/larisa_daily_brief.sh
  python3 -m agents.larisa_ivanovna --command get_day_brief

infra/orchestrator/workflows/larisa_evening_review.sh
  python3 -m agents.larisa_ivanovna --command get_evening_review

infra/orchestrator/workflows/larisa_content_topics.sh
  python3 -m agents.larisa_ivanovna --command get_content_topics

infra/orchestrator/workflows/larisa_midday_replan.sh
  python3 -m agents.larisa_ivanovna --command get_midday_replan
```

## 2. Server/runtime pointers documented

Confirmed from docs and snapshots:

```text
/opt/cloudbot-runtime/larisa/current
/opt/cloudbot-runtime/larisa/releases/<release_id>
/opt/cloudbot-runtime/larisa/.deploy.lock
/etc/cron.d/cloudbot-larisa-daily-brief
/usr/local/bin/cloudbot-larisa-daily-brief.sh
```

All are no-touch in current migration work.

## 3. Fallback risk

Larisa workflows currently contain fallback patterns like:

```text
LARISA_TELEGRAM_BOT_TOKEN fallback to TELEGRAM_BOT_TOKEN
LARISA_TELEGRAM_CHAT_ID fallback to TELEGRAM_CHAT_ID
```

These are runtime-sensitive. Do not change during structural migration.

## 4. Migration risk

Moving Larisa code without compatibility would affect:

- local workflow commands;
- server runtime wrapper;
- cron runner;
- Telegram delivery routing;
- report generation;
- smoke validation.

## 5. Blocked changes

Blocked:

- moving `agents/larisa_ivanovna`;
- changing `python3 -m agents.larisa_ivanovna`;
- changing `/opt/cloudbot-runtime/larisa/current`;
- changing `/etc/cron.d/cloudbot-larisa-daily-brief`;
- changing Telegram token/chat fallback;
- changing deploy/rollback/verify scripts.

## 6. Verdict

```text
Larisa runtime entrypoints mapped
Larisa code move blocked
runtime no-touch remains active
```
