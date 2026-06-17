# App Config Example Review

Дата фиксации: 2026-04-28 МСК.

Статус: read-only review result. Этот документ не переносит `configs/app_config.env.example` и не меняет env/runtime.

## 1. Reviewed file

```text
configs/app_config.env.example
```

Git status:

```text
M configs/app_config.env.example
```

## 2. Diff summary

Изменение относительно git baseline:

```text
removed:
BRAVE_API_KEY=

added:
SEARCH_PROVIDER=duckduckgo
SEARCH_BASE_URL=
SEARCH_ENGINE=duckduckgo
SEARCH_TIMEOUT_SECONDS=10
```

## 3. Secret review

Проверка secret-like patterns:

```text
no matches
```

Redacted review показал, что файл содержит variable names и example/default значения, но не реальные token/key values.

## 4. Coupling review

Новые переменные используются или упоминаются в:

```text
cloudbot/providers/search_provider.py
cloudbot/devops/system_health.py
cloudbot/skills/web_search.py
infra/orchestrator/workflows/openclaw_update.sh
.env.integrations.example
tests/test_system_health.py
```

Legacy `BRAVE_API_KEY` упоминается в cleanup контексте:

```text
infra/orchestrator/workflows/todo-digest-repair.sh
```

Вывод: замена `BRAVE_API_KEY` на `SEARCH_*` выглядит согласованной с текущим search-provider направлением, но затрагивает env contract semantics. Это безопасно как example baseline только после owner acceptance.

## 5. Test result

Проверка после review:

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
conditionally safe to accept as example baseline
```

Условия:

1. Владелец подтверждает, что удаление `BRAVE_API_KEY=` из example допустимо.
2. Владелец подтверждает, что `SEARCH_*` переменные являются новой правильной example-схемой.
3. Перенос выполняется без изменения содержимого файла.
4. `schedule_contract.env` и `schedules.cron` остаются no-touch.
5. Live env/runtime/deploy не трогаются.

## 7. Approval required for move

Для фактического переноса нужен отдельный approval:

```text
APPROVE W5-CONFIG-APP-EXAMPLE
Accept current configs/app_config.env.example as migration baseline.
Move only configs/app_config.env.example to config/env/examples/app_config.env.example.
No value changes.
No live env changes.
No runtime/deploy/cron/systemd/docker changes.
Do not touch schedule_contract.env or schedules.cron.
```

## 8. Current verdict

```text
review completed
move not executed
safe to approve if owner accepts SEARCH_* baseline
```
