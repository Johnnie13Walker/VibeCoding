# Конфигурация доступов

Эта папка описывает доступы процесса `belberry/bitrix24` к Google и Bitrix24.

В git хранятся только шаблоны. Реальные секреты, webhook URL, OAuth client secret, service account JSON и выгрузки не коммитятся.

## Локальная схема

```text
belberry/bitrix24/config/
  .env.example                         # безопасный шаблон переменных
  google-service-account.example.json  # безопасный пример структуры JSON
  .env                                 # реальный локальный файл, не коммитится
  google-service-account.json          # реальный ключ, не коммитится
```

## Google

Основной вариант для процессов и отчётов — Google service account JSON.

Переменная:

```bash
BELBERRY_BITRIX24_GOOGLE_SERVICE_ACCOUNT_JSON=belberry/bitrix24/config/google-service-account.json
```

Требования:

- service account должен иметь доступ только к нужным Google Sheets/Drive-файлам
- доступ выдаётся на email из поля `client_email`
- ключ JSON не хранится в git
- если доступ нужен на сервере, JSON кладётся в защищённый server-side path и путь задаётся через env

## Bitrix24

Для первичного аудита и наведения порядка допустим webhook техпользователя с ограниченными правами.

Основная переменная:

```bash
BELBERRY_BITRIX24_WEBHOOK_URL=https://portal.bitrix24.ru/rest/USER_ID/WEBHOOK_TOKEN/
```

Если нужен OAuth local app, использовать:

```bash
BELBERRY_BITRIX24_CLIENT_ID=
BELBERRY_BITRIX24_CLIENT_SECRET=
BELBERRY_BITRIX24_APP_STATE_DIR=belberry/bitrix24/state/bitrix-oauth
```

Минимальные scope для работы по сделкам и задачам:

- `crm`
- `task` / `tasks`
- `user`
- `department`

## Проверка доступа

Перед запуском автоматизаций нужно проверить:

1. Google service account видит нужные таблицы.
2. Bitrix24 webhook отвечает на `profile`.
3. Доступны `crm.deal.list`, `tasks.task.list`, `user.get`, `department.get`.
4. В логах не печатаются webhook URL, токены и содержимое JSON-ключей.
5. Любая запись в Bitrix24 сначала проходит в dry-run режиме, если сценарий поддерживает dry-run.
