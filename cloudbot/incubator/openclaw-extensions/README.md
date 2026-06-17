# OpenClaw Extensions: Contacts (Telegram CRM-lite) + Search + Steps

В репозитории три независимых модуля:
- `contacts/` - мини-контактная книга для Telegram-бота: `/contact_*`, `/msg`, handshake через `/start <token>`.
- `search/` - интернет-поиск с fallback (`Serper -> SerpAPI -> DDG`).
- `steps/` - прогноз шагов и `steps_insights`.

Архитектура Telegram-входа:
- `contacts/telegram.js` - тонкий Telegram-адаптер (`update -> normalize -> orchestrator.handleIncoming -> sendReply`).
- `orchestrator.js` - единая точка обработки входящих сообщений.
- `router.js` - маршрутизация по командам.
- `workflow.*.js` - сценарии (`dayBriefing`, `tasks`, `meetings`, `diag`, `legacyContacts`).
- `provider.*.js` - провайдеры внешних источников (`bitrix`, `todo`, `gcal`, `whoop`).

## Требования
- Node.js 20+
- npm

## Быстрый старт
1. Скопировать env:
   - `cp .env.example .env`
2. Заполнить переменные в `.env`.
3. Запустить selftest контактов:
   - `npm run selftest`
4. Запустить smoke по оркестратору:
   - `npm run smoke:telegram`

## ENV
```env
SERPER_API_KEY=
SERPAPI_API_KEY=
SAFE_MODE=1

TELEGRAM_BOT_TOKEN=
TELEGRAM_OWNER_ID=
BOT_USERNAME=
CONTACTS_DB_PATH=./data/contacts.sqlite
INVITE_TTL_DAYS=7

STEPS_GOAL=10000
STEPS_TIMEZONE=Europe/Moscow
STEPS_DATA_FILE=./data/steps-history.json
```

## Contacts: команды
- `/contact_add` - пошаговое добавление контакта.
- Быстрое добавление: `добавь контакт: Вася @vasya маркетолог, знакомый Димы`.
- `/contact_list [page]` - список (по 10 на страницу).
- `/contact_find <запрос>` - поиск по имени/username/заметке.
- `/contact_show <имя|@username>` - карточка.
- `/contact_delete <имя|@username>` - удаление.
- `/contact_update <имя|@username>` - диалог обновления полей.
- `/msg <кому> <текст>` - отправка одному/нескольким контактам.
- `/diag` - диагностика (TZ, статусы токенов и пинги Bitrix/TODO).
- `/day_briefing [дата]` - краткий дневной брифинг.
- `/meetings [дата]` - встречи на дату (через календарный провайдер).
- `/tasks` - статус подключения провайдера задач.

## Ограничение Telegram (first contact)
Бот не может писать первым пользователю.

Реализация:
- Если у контакта есть `chat_id` -> сообщение отправляется через Telegram Bot API.
- Если `chat_id` нет -> бот не отправляет, генерирует invite-ссылку:
  - `https://t.me/<BOT_USERNAME>?start=<invite_token>`
  - и возвращает текст, который владелец может переслать вручную.

## Handshake `/start <token>`
- При `/start <token>`:
  - токен ищется по `hash(token)`;
  - проверяются TTL и одноразовость;
  - в контакт записывается `chat_id`.
- Токен в БД хранится только как `token_hash`.

## Owner-only права
Операции доступны только владельцу (`TELEGRAM_OWNER_ID`):
- add/update/delete/list/find/show
- `/msg`

Исключение: обычный пользователь может выполнить только `/start <token>` для привязки.

## Хранилище
В модуле используется файл БД по пути `CONTACTS_DB_PATH` (JSON-формат с атомарной записью).

Схема данных соответствует полям:
- `contacts`: `id`, `display_name`, `tg_username`, `tg_link`, `chat_id`, `note`, `created_at`, `updated_at`
- `invites`: `token_hash`, `contact_id`, `expires_at`, `used_at`, `created_at`

## Selftest
`npm run selftest` делает:
1. Создание тестового контакта.
2. Генерацию invite-link.
3. Локальную имитацию `/start <token>`.
4. Проверку привязки `chat_id`.
5. Проверку отправки сообщения (мок Telegram API).

PASS: когда `chat_id` успешно привязан и отправка считается успешной.

## Интеграция в OpenClaw/Telegram webhook loop

### 1) Обработка входящего update
```js
import { handleTelegramUpdate } from './contacts/index.js';

await handleTelegramUpdate(update, {
  dbPath: process.env.CONTACTS_DB_PATH || './data/contacts.sqlite',
  ownerId: process.env.TELEGRAM_OWNER_ID,
  botUsername: process.env.BOT_USERNAME,
  botToken: process.env.TELEGRAM_BOT_TOKEN,
  safeMode: process.env.SAFE_MODE || '1',
  // необязательно: свой транспорт отправки ответа
  sendReply: async (chatId, text) => {
    // ваш метод sendMessage
  },
});
```

### 2) Прямой API-командный вызов
```js
import { runContactBookCommand } from './contacts/index.js';

const res = await runContactBookCommand('contact_add', {
  display_name: 'Вася',
  tg_username: '@vasya',
  note: 'маркетолог',
}, {
  dbPath: './data/contacts.sqlite',
});

console.log(res.id);
```

## Demo
- Локальный сценарий команд:
  - `npm run contacts:demo`
- Selftest web-search:
  - `npm run selftest:websearch`
## Оркестратор: обязательный режим
Все операционные действия запускаются через orchestrator workflow.

Команды:
- `npm run whoop:report` — ежедневный WHOOP-отчет (включая шаги за вчера).
- `npm run whoop:test:telegram` — тестовая отправка Telegram для WHOOP.
- `npm run whoop:discover` — авто-поиск необходимых WHOOP/Telegram данных через оркестратор.
- `npm run health:daily` — ежедневный health-check.
- `npm run orchestrator:run -- whoop-daily-report-with-steps --dry-run --force` — ручной прогон с флагами.

Поддерживаемые workflow id:
- `whoop-daily-report-with-steps`
- `whoop-telegram-test`
- `daily-health-check`
