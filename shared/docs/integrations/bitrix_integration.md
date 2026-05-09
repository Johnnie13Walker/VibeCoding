# Bitrix24 Integration for Sales Copilot

## Что сделано

- Добавлен безопасный env-путь через `BITRIX_WEBHOOK_URL`.
- Секрет не хранится в git: `.env`, `.env.*`, `.env.integrations` уже исключены через `.gitignore`.
- Полный webhook не печатается в коде, логах и диагностике.
- Разрешён только masked-формат: `https://portal/rest/***/***/`.

## Какие методы заложены в проверку

- `profile`
- `user.get`
- `crm.deal.list`
- `crm.lead.list`
- `crm.company.list`
- `crm.contact.list`
- `calendar.event.get`
- `tasks.task.list`
- `department.get`

Проверка реализована в adapter-слое и используется в `/bitrixcheck` и в `/health`.

## Какие scope реально используются

- `user`
- `crm`
- `calendar`
- `task` / `tasks`
- `department`

Минимально критичны для Sales Copilot:

- `profile`
- `user.get`
- `crm.deal.list`
- `crm.lead.list`

Желательны для следующего этапа:

- `crm.company.list`
- `crm.contact.list`
- `calendar.event.get`
- `tasks.task.list`
- `department.get`

## Какие данные уже доступны коду

Через `cloudbot/providers/bitrix/bitrix_sales_adapter.py` доступны:

- профиль техпользователя
- пользователи
- департаменты
- лиды
- сделки
- компании
- контакты
- события календаря
- задачи

Через `cloudbot/skills/bitrix_sales_data.py` собирается стартовый snapshot для Sales Copilot:

- количество лидов
- количество сделок
- последние лиды
- последние сделки
- ответственные
- встречи на сегодня
- задачи

## Ограничения

- В текущей локальной среде реальный `BITRIX_WEBHOOK_URL` не найден, поэтому live-аудит прав вебхука не был выполнен.
- До появления реального webhook проверка подтверждена только на fixture `tests/fixtures/bitrix_crm_fixtures.json`.
- `calendar.event.get` и `tasks.task.list` зависят от включённых scope у конкретного техпользователя Bitrix24.
- Старый fallback `BITRIX_BASE_URL` / `BITRIX_TOKEN` оставлен только для совместимости, но основным путём считается `BITRIX_WEBHOOK_URL`.

## Что нужно для следующего этапа

1. Заполнить gitignored `.env.integrations` переменной `BITRIX_WEBHOOK_URL=...`.
2. Выполнить живой прогон проверок методов и зафиксировать реальные статусы доступа.
3. При необходимости открыть недостающие scope у техпользователя Bitrix24.
4. После live-проверки подключить реальные данные Bitrix в production-режим Sales Copilot без fixture.
