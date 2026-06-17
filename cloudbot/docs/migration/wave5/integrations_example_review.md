# Integrations Env Example Review

Дата фиксации: 2026-04-28 МСК.

Статус: read-only review result. Этот документ не переносит `configs/integrations.env.example` и не меняет env/runtime.

## 1. Reviewed file

```text
configs/integrations.env.example
```

Git diff:

```text
empty
```

Вывод: файл не имеет незакоммиченных изменений относительно git baseline.

## 2. Redacted content profile

Файл содержит example variables для:

- Sentry;
- OpenAI;
- Notion;
- Bitrix app auth;
- Telegram delivery targets;
- Sales Telegram targets;
- Wazzup;
- GitHub token.

Значения проверялись в redacted-виде.

## 3. Secret review

Secret-like pattern scan:

```text
no matches
```

Вывод: реальные token/key/private-key значения не обнаружены.

## 4. Coupling review

Переменные из файла используются или упоминаются в:

```text
scripts/run_sales_copilot.py
cloudbot/devops/system_health.py
cloudbot/devops/sales_dispatch_health.py
cloudbot/providers/bitrix/bitrix_app_auth.py
cloudbot/providers/wazzup_provider.py
agents/sales_agent/*
infra/orchestrator/workflows/*
scripts/verify_integrations.sh
docs/*
tests/*
```

Это подтверждает, что файл является важным integration env example. Его можно переносить только как example-файл, без изменения значений и без изменения env loading.

## 5. Test result

Проверка:

```bash
python3 -m unittest discover -s tests/unit
```

Результат:

```text
Ran 12 tests
OK
```

## 6. Recommendation

Рекомендация:

```text
safe to move as example file
```

Условия:

1. Переносить без изменения содержимого.
2. Не менять live env.
3. Не менять env loading.
4. Не менять runtime/deploy/cron/systemd/docker.
5. Не трогать `schedule_contract.env` и `schedules.cron`.

## 7. Approved next move candidate

```text
configs/integrations.env.example -> config/env/examples/integrations.env.example
```

Move остается structural only.
