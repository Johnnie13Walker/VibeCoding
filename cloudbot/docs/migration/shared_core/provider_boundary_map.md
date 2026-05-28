# Provider Boundary Map

Дата фиксации: 2026-04-28 МСК.

Статус: read-only provider boundary map. Этот документ не меняет providers or integrations.

## 1. Current provider paths

```text
cloudbot/providers/bitrix_provider.py
cloudbot/providers/bitrix/bitrix_app_auth.py
cloudbot/providers/bitrix/bitrix_sales_adapter.py
cloudbot/providers/search_provider.py
cloudbot/providers/telegram_provider.py
cloudbot/providers/todo_provider.py
cloudbot/providers/whoop_provider.py
cloudbot/providers/wazzup_provider.py
```

## 2. Boundary classification

| Provider | External surface | Migration risk |
| --- | --- | --- |
| Bitrix provider | Bitrix webhook/app auth, CRM, calendar | high |
| Bitrix sales adapter | Sales/Lev reports | high |
| Search provider | web search, SearxNG/DuckDuckGo env | medium |
| Telegram provider | Telegram delivery | critical |
| Todo provider | JS bridge / Todoist | medium/high |
| WHOOP provider | JS bridge / health data | medium/high |
| Wazzup provider | Sales communication archive | high |

## 3. Tests currently covering providers

```text
tests/unit/test_search_provider.py
tests/unit/test_bitrix_app_auth.py
tests/unit/test_bitrix_sales_adapter.py
tests/test_system_health.py
tests/test_larisa_agent.py
tests/test_lev_petrovich_runtime.py
```

## 4. Blocked moves

Blocked:

- moving provider modules to `shared/providers`;
- rewriting provider imports;
- changing env variable names;
- changing external API behavior;
- changing Telegram delivery behavior;
- changing JS bridge providers.

## 5. Required before provider migration

Required:

1. Provider-by-provider candidate selection.
2. Import compatibility strategy.
3. Env contract validation.
4. Provider-specific tests.
5. Smoke checklist for affected contour.
6. Rollback plan.

## 6. Verdict

```text
provider move blocked
boundary map completed
next safe step: workflow boundary map
```
