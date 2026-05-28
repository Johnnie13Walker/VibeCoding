# Bitrix users + people resolver

Модуль для получения активных сотрудников Bitrix24, кэширования и fuzzy-поиска в диалоге создания встречи.

## Быстрый старт

```bash
cd bot
npm test
npm run smoke:notifications
```

## Конфиг

- `BITRIX_APP_STATE_DIR` — каталог с `install.latest.json` / `handler.latest.json` локального Bitrix app
- `BITRIX_APP_INSTALL_STATE_FILE` — явный путь к state-файлу, если нужен override
- `BITRIX_CLIENT_ID` — client id локального Bitrix app
- `BITRIX_CLIENT_SECRET` — client secret локального Bitrix app
- `BITRIX_OAUTH_TOKEN_URL` — override для OAuth refresh endpoint
- `BITRIX_WEBHOOK_URL` — полный входящий webhook Bitrix24 для fallback-режима
- `BITRIX_BASE_URL` / `BITRIX_TOKEN` — legacy fallback, если webhook URL пока не переведен
- `BITRIX_TIMEOUT_SEC` — timeout Bitrix REST в секундах
- `TELEGRAM_OWNER_ID` — владелец бота
- `TELEGRAM_ADMIN_IDS` — список админов через запятую
- `USERS_CACHE_FILE` — путь к файлу кэша (по умолчанию `bot/data/users-cache.json`)
- `USERS_CACHE_TTL_MS` — TTL кэша, по умолчанию 24 часа
- `USE_FIXTURE_USERS=1` — включить локальную фикстуру для smoke
- `TODO_PROVIDER` — провайдер задач (`todoist` по умолчанию)
- `TODO_TOKEN` — токен Todoist API (для боевых уведомлений)
- `USE_FIXTURE_TASKS=1` — включить локальную фикстуру задач вместо Todoist

## Команда синхронизации

- `/sync_users`
- `обнови сотрудников`

Команда доступна только owner/admin.

## Уведомления по задачам (МСК)

- Job `task_time_notifications` — `*/5 * * * *` (`Europe/Moscow`)
- Job `self_healing` — `0 */6 * * *` (`Europe/Moscow`)

Логика:
- если есть `dueDate` + `dueTime`, отправляется `T-10` и `T` (окно 5 минут)
- если только `dueDate` без `dueTime`, это дедлайн дня без time-notify
- если есть `dueTime` без `dueDate`, дата считается как \"сегодня\" в МСК

Команды:
- `/quiet on|off` или `тихий режим on|off`
- `уведомления`
- `тест уведомления`

Локальный запуск job’ов:
- `npm run jobs:run-once` — разовый прогон `task_time_notifications`
- Требует `TELEGRAM_OWNER_ID` и Telegram target: `TELEGRAM_CHAT_ID`, `JOBS_CHAT_ID` или `TELEGRAM_TARGETS` + `JOBS_CHAT_ALIAS`
- `npm run scheduler:daemon` — постоянный раннер scheduler (минутный цикл, МСК)
- Для автозапуска self-healing scheduler вызывает `python3 -m cloudbot.devops.self_healing --json`

Telegram transport:
- `TELEGRAM_BOT_TOKEN` — токен бота для реальной отправки
- `TELEGRAM_CHAT_ID` — чат по умолчанию для отправки
- `TELEGRAM_TARGETS` — именованные цели в формате `alias=chat_id,alias2=chat_id`
- `TELEGRAM_ALLOWED_CHAT_IDS` — дополнительный whitelist chat id через запятую
- `TELEGRAM_DRY_RUN=1` — не отправлять в сеть, только логировать
- `TELEGRAM_API_BASE_URL` — override API base (опционально)
- `JOBS_CHAT_ALIAS` — выбрать цель по alias для `npm run jobs:run-once` и `npm run scheduler:daemon`

Пример для личного чата и групп:

```env
TELEGRAM_CHAT_ID=123456789
TELEGRAM_TARGETS=owner=123456789,ops=-1001111111111,family=-1002222222222
```

Как подключить группу:
- добавить бота в группу;
- выдать право писать сообщения;
- если бот должен читать обычные сообщения, а не только команды и упоминания, отключить privacy mode через BotFather (`/setprivacy`);
- получить `chat_id` группы и добавить его в `TELEGRAM_TARGETS`.

Для одноразового выбора цели у job-скрипта:

```bash
cd bot
JOBS_CHAT_ALIAS=ops npm run jobs:run-once
```

Хранилища:
- `SETTINGS_FILE` (по умолчанию `bot/data/user-settings.json`) — per-user quiet mode
- `NOTIFICATION_LOG_FILE` (по умолчанию `bot/data/notification-log.json`) — дедуп уведомлений
- TTL notification log: `NOTIFICATION_LOG_TTL_MS` (по умолчанию 7 дней)
