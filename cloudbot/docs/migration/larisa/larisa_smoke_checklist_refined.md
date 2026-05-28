# Larisa Smoke Checklist Refined

Дата фиксации: 2026-04-28 МСК.

Статус: checklist only. Этот документ не запускает live Telegram, Bitrix, Todo, search или runtime checks.

## 1. Purpose

Production-safe smoke checklist for future approved Larisa structural changes.

## 2. Owner checks after future approved move

| Check ID | What to verify | Expected healthy result | Where to check | Failure signal | Severity |
| --- | --- | --- | --- | --- | --- |
| LAR-SMOKE-01 | Telegram delivery alive | message/report delivered to Larisa target | Telegram owner view / logs | no delivery or wrong chat | critical |
| LAR-SMOKE-02 | Daily brief delivery | daily brief generated and delivered | report file / Telegram | missing brief | critical |
| LAR-SMOKE-03 | Morning timing | expected MSK schedule preserved | cron/report timestamp | wrong time window | high |
| LAR-SMOKE-04 | Calendar access | meetings section populated or graceful empty state | brief content | auth/data failure | high |
| LAR-SMOKE-05 | Tasks access | tasks section populated or graceful empty state | brief content | task fetch failure | high |
| LAR-SMOKE-06 | Weather/search response | command returns sane response | Telegram/report | empty/error response | medium |
| LAR-SMOKE-07 | Command routing | `/topics`, `/search`, `/draft`, brief commands route correctly | router/dry command | wrong workflow | high |
| LAR-SMOKE-08 | Formatter sanity | output is Telegram-safe and readable | report content | broken markup | medium |
| LAR-SMOKE-09 | Logs/reports freshness | new report/log appears | reports/logs | stale files | high |
| LAR-SMOKE-10 | Wrong token/chat fallback detection | no message goes to wrong chat | Telegram owner view | wrong recipient | critical |

## 3. Mandatory local tests before smoke

Before any owner smoke:

```bash
python3 -m unittest discover -s tests/unit
python3 -m unittest tests.test_larisa_agent
python3 -m unittest tests.test_larisa_search
```

Do not run live checks unless owner approved runtime access.

## 4. Immediate rollback triggers

Immediate rollback if:

- message goes to wrong chat;
- `python3 -m agents.larisa_ivanovna` entrypoint fails;
- daily brief disappears;
- calendar/tasks access fails unexpectedly;
- Telegram formatting breaks.

## 5. Verdict

```text
Larisa smoke checklist refined
live smoke not executed
runtime remains no-touch
```
