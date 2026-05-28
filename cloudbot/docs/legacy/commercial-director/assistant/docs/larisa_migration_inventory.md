# Инвентаризация и миграция контура Ларисы Ивановны

## Что найдено в репозитории

### Группа A. Личный контур Ларисы Ивановны

| Сценарий | Где найден | Источник данных | Telegram-контур | Расписание |
| --- | --- | --- | --- | --- |
| `day_briefing` | `workflows/personal_assistant/workflow.yaml`, `agents/larisa_assistant/agent.yaml` | `calendar`, `todo`, `weather`, `news` | Явный sender не найден, Telegram-формат указан в legacy-контракте | Не найдено |
| `add_calendar_event` | `workflows/personal_assistant/workflow.yaml`, `agents/larisa_assistant/agent.yaml` | `calendar` | Явный sender не найден | Не найдено |
| `search_request` | `workflows/personal_assistant/workflow.yaml`, `agents/larisa_assistant/agent.yaml` | `search` | Явный sender не найден | Не найдено |
| `organize_day` | `agents/larisa_assistant/agent.yaml` | подразумевается personal assistant контур | Явный sender не найден | Не найдено |
| `get_day_brief` / `daily_brief` | `agents/larisa-ivanovna/commands/get_day_brief.ts`, `agents/larisa-ivanovna/workflows/daily_brief.workflow.ts` | `calendar`, `tasks`, `weather`, `news` | `ExistingTelegramRouteProvider` через route `larisa-ivanovna` | Не найдено |
| `create_event` | `agents/larisa-ivanovna/commands/create_event.ts`, `agents/larisa-ivanovna/workflows/create_event.workflow.ts` | `calendar` | `dispatchToTelegram` агента Ларисы Ивановны | Не найдено |
| `search` | `agents/larisa-ivanovna/commands/search.ts`, `agents/larisa-ivanovna/workflows/search.workflow.ts` | `search` | `dispatchToTelegram` агента Ларисы Ивановны | Не найдено |
| `plan_day` | `agents/larisa-ivanovna/commands/plan_day.ts`, `agents/larisa-ivanovna/workflows/plan_day.workflow.ts` | `daily_brief` stack | `dispatchToTelegram` агента Ларисы Ивановны | Не найдено |

### Группа B. Не относится к Ларисе Ивановне

В этом репозитории не найдено активной логики CRM, sales, сделок, финансов или коммерческой аналитики. Ограничения закреплены в `agents/larisa-ivanovna/policy.ts`.

### Группа C. Shared и спорные части

| Компонент | Где найден | Решение |
| --- | --- | --- |
| Telegram route bridge | `agents/larisa-ivanovna/providers/telegram.provider.ts` | Оставлен как shared adapter. Личный контур использует существующий route `larisa-ivanovna`. |
| Legacy workflow contract | `workflows/personal_assistant/workflow.yaml` | Оставлен как bridge совместимости, прямая логика отключена. |
| Legacy agent contract | `agents/larisa_assistant/agent.yaml` | Оставлен как alias/bridge на новый контур. |
| Provider abstractions | `agents/larisa-ivanovna/providers/*.provider.ts` | Оставлены в новом контуре как adapter layer. Общие инфраструктурные реализации в репозитории не найдены. |

## Фактические выводы по runtime

- В репозитории не найдено live scheduler/cron/job, который бы реально запускал daily brief.
- В репозитории не найдено прямого Telegram sender-а со встроенным bot token или отдельным новым routing для Ларисы.
- Найден только адаптер для переиспользования существующего Telegram route: `routeKey = larisa-ivanovna`.
- Поэтому миграция на этом шаге выполнена как архитектурное переключение источника правды и совместимый bridge, а не как перенос боевого scheduler-а из найденного runtime.

## Решение по миграции

### Перенесено в контур `agents/larisa-ivanovna`

- `day_briefing` -> `get_day_brief` / `daily_brief`
- `add_calendar_event` -> `create_event`
- `search_request` -> `search`
- `organize_day` -> `plan_day`

### Оставлено в shared

- Telegram route bridge через `ExistingTelegramRouteProvider`
- provider contracts как adapter layer

### Отключено как legacy

- прямое исполнение `agents/larisa_assistant/agent.yaml`
- прямое исполнение `workflows/personal_assistant/workflow.yaml`
- прямой legacy Telegram dispatch
- legacy scheduler-флаг для personal assistant workflow

## Новый единый источник правды

- агент: `agents/larisa-ivanovna/agent.ts`
- конфиг миграции: `agents/larisa-ivanovna/config.ts`
- daily brief: `agents/larisa-ivanovna/commands/get_day_brief.ts`
- orchestration: `agents/larisa-ivanovna/workflows/daily_brief.workflow.ts`
- Telegram route: `agents/larisa-ivanovna/providers/telegram.provider.ts`

## Ограничения инвентаризации

- Git-история и внешний runtime здесь недоступны: каталог не содержит `.git`.
- Логи, systemd unit-файлы, cron-конфиги и production `.env` в репозитории отсутствуют.
- Поэтому любые незафиксированные вне этого каталога запускатели надо проверить уже в основном runtime-репозитории или на сервере перед финальным включением расписания.
