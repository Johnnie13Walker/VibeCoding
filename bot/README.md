# Bitrix users + people resolver

Модуль для получения активных сотрудников Bitrix24, кэширования и fuzzy-поиска в диалоге создания встречи.

## Быстрый старт

```bash
cd bot
npm test
npm run smoke:notifications
```

## Конфиг

- `BITRIX_BASE_URL` — базовый URL Bitrix24
- `BITRIX_TOKEN` — входящий webhook token
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
- Job `evening_reminder` — `0 19 * * *` (`Europe/Moscow`)

Логика:
- если есть `dueDate` + `dueTime`, отправляется `T-10` и `T` (окно 5 минут)
- если только `dueDate` без `dueTime`, это дедлайн дня без time-notify
- если есть `dueTime` без `dueDate`, дата считается как \"сегодня\" в МСК

Команды:
- `/quiet on|off` или `тихий режим on|off`
- `уведомления`
- `тест уведомления`

Локальный запуск job’ов:
- `npm run jobs:run-once` — разовый прогон `task_time_notifications` и `evening_reminder`
- Требует `TELEGRAM_OWNER_ID` и `TELEGRAM_CHAT_ID` (или `JOBS_USER_ID/JOBS_CHAT_ID`)
- `npm run scheduler:daemon` — постоянный раннер scheduler (минутный цикл, МСК)

Telegram transport:
- `TELEGRAM_BOT_TOKEN` — токен бота для реальной отправки
- `TELEGRAM_CHAT_ID` — чат для отправки
- `TELEGRAM_DRY_RUN=1` — не отправлять в сеть, только логировать
- `TELEGRAM_API_BASE_URL` — override API base (опционально)

Хранилища:
- `SETTINGS_FILE` (по умолчанию `bot/data/user-settings.json`) — per-user quiet mode
- `NOTIFICATION_LOG_FILE` (по умолчанию `bot/data/notification-log.json`) — дедуп уведомлений
- TTL notification log: `NOTIFICATION_LOG_TTL_MS` (по умолчанию 7 дней)
