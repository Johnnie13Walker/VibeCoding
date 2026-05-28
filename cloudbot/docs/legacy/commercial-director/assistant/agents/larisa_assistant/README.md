# Агент `larisa_assistant`

## Статус

`larisa_assistant` сохранён как legacy bridge. Единый источник правды перенесён в `agents/larisa-ivanovna/`, а этот слой нужен только для совместимости со старыми entrypoint-ами и routing.

## Назначение

`larisa_assistant` — отдельный personal assistant агент для сценариев пользователя, связанных с календарём, задачами, погодой, новостями, поиском и организацией дня.

## Роль агента

- собрать личный daily brief;
- поддержать сценарий добавления встречи;
- поддержать сценарий поиска;
- не смешиваться с `commercial-director` и `sales_agent`.

## Входные сценарии

- `day_briefing`;
- `add_calendar_event`;
- `search_request`;
- `organize_day`.

## Делегирование

- `day_briefing` -> `get_day_brief`;
- `add_calendar_event` -> `create_event`;
- `search_request` -> `search`;
- `organize_day` -> `plan_day`.

## Требуемые входные данные

- дата и временная зона пользователя;
- данные календаря;
- данные задач;
- настройки новостных тем;
- пользовательский запрос для поиска или создания встречи.

## Ожидаемый результат

- короткий Telegram-friendly ответ;
- структурированный brief дня;
- подтверждение созданной встречи;
- краткий ответ по поисковому запросу;
- явное сообщение об ограничении, если источник недоступен.

## Границы агента

- не использовать sales-данные;
- не обращаться к CRM как к базовому источнику;
- не давать коммерческих рекомендаций;
- не запускать DevOps-сценарии;
- не хранить секреты и runtime-конфиги в этом контуре.

## Зависимости

- `providers/calendar`;
- `providers/todo`;
- `providers/weather`;
- `providers/news`;
- `providers/search`;
- `templates/day-brief.md`;
- `prompts/day_briefing.md`.
