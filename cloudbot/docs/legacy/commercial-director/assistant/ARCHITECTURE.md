# Архитектура контура Ларисы Ивановны

## Назначение

Файл фиксирует архитектурное положение personal assistant контура внутри Cloudbot/OpenClaw и его границы относительно других ролей.

## Слои

### `agent`

- `agents/larisa-ivanovna/agent.ts`
- точка входа отдельного агента роли;
- собирает registry команд;
- умеет dispatch в существующий Telegram route Ларисы Ивановны;
- не создает новый runtime-контур поверх sales-агента.

### `config` и `policy`

- `agents/larisa-ivanovna/config.ts`
- `agents/larisa-ivanovna/policy.ts`
- фиксируют идентичность агента, границы доступа, alias старого контура и primary Telegram route.

### `commands`

- `agents/larisa-ivanovna/commands/`
- только входные точки и маршрутизация;
- не содержат business logic и не ходят во внешние API напрямую.

### `workflows`

- `agents/larisa-ivanovna/workflows/`
- отдельные сценарии `daily_brief`, `create_event`, `weather`, `news`, `search`, `plan_day`;
- связывают commands и providers;
- не маршрутизируют запросы в sales-контур.

### `providers`

- `agents/larisa-ivanovna/providers/`
- `calendar.provider.ts`
- `tasks.provider.ts`
- `weather.provider.ts`
- `news.provider.ts`
- `search.provider.ts`
- `telegram.provider.ts`

Каждый provider описан как adapter layer. Workflow работает только через эти интерфейсы. Для неподключенных интеграций используются null-реализации с явным ограничением.

### `formatters`

- `agents/larisa-ivanovna/formatters/`
- отдельное Telegram-friendly форматирование brief, погоды и новостей;
- не содержит orchestration и вызовов providers.

### `schemas`

- `agents/larisa-ivanovna/schemas/`
- DTO и контракты для календаря, задач, новостей и brief дня;
- единый слой типизации между commands, workflows и providers.

### `templates` и `prompts`

- `templates/day-brief.md`
- `prompts/day_briefing.md`

Эти файлы определяют единый формат MVP brief дня и правила его сборки.

## Схема потока

1. Shared orchestrator Cloudbot определяет, что запрос относится к personal assistant сценарию.
2. Запрос уходит в `agents/larisa-ivanovna/agent.ts`.
3. Registry команд выбирает нужный command entrypoint.
4. Command запускает профильный workflow.
5. Workflow запрашивает нужные providers по сценарию.
6. Formatter собирает Telegram-friendly ответ.
7. Telegram provider использует существующий route Ларисы Ивановны.

## Legacy-слой

- `agents/larisa_assistant/`
- `workflows/personal_assistant/`

Эти артефакты оставлены как legacy bridge совместимости. Они больше не являются отдельным источником бизнес-логики и должны только делегировать в `agents/larisa-ivanovna/`, не отправляя собственные Telegram-сообщения и не поднимая отдельные scheduler-ы.

## Границы с другими контурами

### Не входит в `commercial-director`

- личный календарь;
- личные задачи;
- погода;
- новости по личным темам;
- пользовательский поиск;
- организация дня.

### Не входит в `larisa-ivanovna`

- CRM;
- продажи;
- сделки;
- коммерческие сигналы;
- финансы;
- DevOps и инфраструктурные runbooks.

## Принцип интеграции

- личный контур должен подключаться к shared orchestrator как отдельный workflow;
- роли не должны импортировать смысл друг друга;
- общие integrations допустимы только как shared provider layer;
- Telegram должен переиспользоваться через существующий route, а не через новый bot token;
- production routing и live integrations подключаются только после отдельного подтверждения.
