# providers

Канонический реестр внешних интеграций Cloudbot.

Этот документ нужен не как абстрактное описание слоя, а как рабочий контракт для диагностики, health-check и архитектуры. Если интеграция реально заведена в production/server-only контуре, она не должна попадать в сводке в `Не настроено` только потому, что текущий локальный workspace не видит её env напрямую.

## Базовые правила

Для каждого провайдера должны быть понятны:

- точка входа в коде;
- источник конфигурации без секретов в git;
- где живёт боевой runtime-контур: локальный repo, server-only env, OpenClaw runtime или отдельный сервис;
- какой health-check считается каноническим;
- какие ограничения у локального диагностического контура допустимы.

## Канонический реестр провайдеров

### Telegram

- Назначение: пользовательский интерфейс Ларисы Ивановны.
- Код: инженерный контур `cloudbot/providers/telegram*`, telegram bot/runtime.
- Статус: обязательная активная интеграция.
- Health-check: доставка и обработка команд в Telegram.

### OpenAI

- Назначение: интеллект агента и генерация ответов.
- Код: orchestrator/workflows/OpenClaw runtime.
- Статус: обязательная активная интеграция.
- Health-check: успешный upstream API probe без раскрытия секретов.

### Bitrix24

- Назначение: календарь, встречи, CRM/app-state, webhook path.
- Код: `cloudbot/providers/bitrix_provider.py`, `cloudbot/providers/bitrix/`.
- Статус: обязательная активная интеграция.
- Runtime: часть параметров может жить в server-side env/OpenClaw runtime, а не только в локальном `.env`.
- Health-check: отдельно различать `Bitrix portal`, `Bitrix OAuth` и `WEBHOOK`.

### Google Calendar OAuth

- Назначение: вспомогательный OAuth-контур календарной синхронизации там, где он реально используется в server-side сценариях.
- Код: в текущем инженерном контуре подтверждён не как отдельный Python provider, а как server-side command/API path в runtime-скриптах.
- Статус: если контур используется на бою, он должен быть задокументирован как отдельная интеграция, а не всплывать только в operational report.
- Runtime: server-only/auxiliary contour; не считать отсутствие локального provider-модуля доказательством, что интеграции нет.
- Health-check: до появления канонического live-probe не маркировать автоматически как `OK`, но и не выводить в отчёты как будто это неизвестная или “случайно появившаяся” сущность.

### Todoist / Todo

- Назначение: задачи и повестка.
- Код: `cloudbot/providers/todo_provider.py`, `cloudbot/providers/todoist/`.
- Статус: обязательная активная интеграция.
- Health-check: live API probe Todoist.

### WHOOP

- Назначение: health-данные и утренний/операционный контур WHOOP.
- Код: `cloudbot/providers/whoop_provider.py`, `cloudbot/skills/get_whoop_data.py`.
- Статус: интеграция считается заведённой, даже если её боевой OAuth/env живёт в server-only контуре вне локального workspace.
- Runtime: server-only contour, включая `whoop.env`, cron и report scripts.
- Health-check: не считать отсутствие локального WHOOP env доказательством `Не настроено`, если server runtime подтверждён; в таком случае допустим статус `Предупреждение` или `Не проверено`, но не ложный `Не настроено`.

### WAZZUP

- Назначение: WhatsApp bridge и связанные webhook-потоки Sales/Bitrix app.
- Код: `cloudbot/providers/wazzup_provider.py`, bitrix app bridge.
- Статус: интеграция считается заведённой, если подтверждён server runtime/OpenClaw env.
- Runtime: чаще всего server-side `/opt/openclaw/.env` и `bitrix_app_server`.
- Health-check: отдельно различать `WAZZUP`, `WAZZUP_WEBHOOK_FORWARD` и архив/state-контур.

### Web Search

- Назначение: внешний веб-поиск для skills и пользовательских сценариев.
- Код: `cloudbot/providers/search_provider.py`, `cloudbot/skills/web_search.py`.
- Статус: обязательная активная интеграция.
- Health-check: отдельно различать `Web Search provider`, `web_search skill` и `Web search для Ларисы`.

## Правило для health-check

Если интеграция документирована здесь как активная и подтверждается server runtime, health-check не должен по умолчанию маркировать её как `Не настроено` только из-за отсутствия локального env или невозможности выполнить live-probe из текущего диагностического контура.
