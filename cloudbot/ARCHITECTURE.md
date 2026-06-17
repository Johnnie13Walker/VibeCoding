# Cloudbot Architecture

Cloudbot построен как модульная система, где пользовательский интерфейс, orchestration-логика, автономные агенты и интеграции разделены по слоям. Целевой персональный контур сейчас сводится к единому контуру Ларисы Ивановны без отдельного News-агента.

## Структура

### `cloudbot/`
Главный пакет приложения.

- `cloudbot/bot/telegram` — Telegram-слой: принимает update, нормализует команды и передает их в orchestrator.
- `cloudbot/orchestrator` — центральная маршрутизация и запуск workflow.
- `cloudbot/workflows` — сценарии прикладной логики (`day_briefing`, `tasks_summary`, `system_health` и т.д.).
- `cloudbot/skills` — атомарные функции, которые могут переиспользоваться разными workflow и агентами.
- `cloudbot/providers` — адаптеры к внешним API и сервисам.
- `cloudbot/devops` — health-check, диагностика, мониторинг и эксплуатационные утилиты.

### `apps/`
Канонические application-модули верхнего уровня.

- Здесь живут изолированные приложения/агенты, которые подключаются через workflow-адаптер, не внедряясь напрямую в `providers` или `orchestrator`.
- `agents/*` остаётся compatibility layer для старых импортов и CLI entrypoint'ов.

## Роли слоев

### `orchestrator`
- Главный диспетчер системы.
- Принимает входящие события из Telegram и других точек входа.
- Выбирает нужный workflow по команде, тексту или intent.

### `workflows`
- Сценарии логики приложения.
- Оркестрируют конкретный пользовательский сценарий: `day_briefing`, `tasks_summary`, `system_health`.
- Содержат минимальную glue-логику между orchestrator и агентами/skills.

### `apps`
- Автономные модули с собственной внутренней логикой.
- Пример: `apps/larisa_ivanovna` собирает дневной brief, задачи, встречи и погодный блок через provider-слой.
- Агент должен подключаться через workflow-адаптер, а не напрямую из Telegram-слоя.

### `skills`
- Атомарные функции и небольшие действия.
- Не должны знать о Telegram и пользовательском UI.
- Могут вызываться из workflow и агентов как переиспользуемые кирпичики.

### `providers`
- Интеграции с внешними API.
- Отвечают только за доступ к внешнему сервису: Telegram, OpenAI, Bitrix, Todoist, WHOOP, Search.
- Не должны содержать пользовательские сценарии или сложную orchestration-логику.

### `telegram`
- Слой взаимодействия с пользователем.
- Нормализует входящие команды, не содержит бизнес-логики сценариев.
- Делегирует обработку в orchestrator и возвращает ответ пользователю.

## Базовый поток выполнения

```text
Telegram
  ↓
orchestrator
  ↓
workflow
  ↓
agent
  ↓
skills
  ↓
providers
  ↓
external APIs
```

## Практическое применение в текущем проекте

- Команды `/today`, `/brief`, `/day`, `/meetings`, `/tasks`, `/weather`, `/plan-day` и `/plan` идут в `cloudbot/bot/telegram`, затем в `cloudbot/orchestrator`, потом в workflow-адаптеры Ларисы.
- Workflow `day_briefing` вызывает canonical `apps/larisa_ivanovna`, при этом `agents/larisa_ivanovna` остаётся compatibility shim.
- Контур Ларисы:
  - собирает встречи из календаря;
  - собирает задачи;
  - добавляет погодный блок;
  - формирует итоговый brief и план дня.
- Команда `/health` идет тем же путем, но вызывает `cloudbot/workflows/system_health.py`, который использует `cloudbot/devops/system_health.py`.

## Архитектурные правила

- `apps/` не импортируют `cloudbot.providers` и `cloudbot.orchestrator` напрямую.
- Интеграция автономного агента в систему идет через `cloudbot/workflows/*`.
- `agents/*` не является местом для новой production-логики.
- `skills` и `providers` не должны зависеть от Telegram-слоя.
- Секреты не хранятся в коде и читаются только из env.
- Runtime-артефакты (`logs`, `cache`) не должны ломать git-историю и должны быть безопасны к пересозданию.
