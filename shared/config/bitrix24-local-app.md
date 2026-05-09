# Bitrix24: единый контур доступа

## Правило

С Bitrix24 работаем только через локальное приложение OAuth.

Запрещённые переменные:

- `BITRIX_WEBHOOK_URL`
- `BITRIX_BASE_URL`
- `BITRIX_TOKEN`

Эти переменные не использовать в новых workflows, agents, scripts и env examples.

## Разрешённые переменные

```env
BITRIX_APP_STATE_DIR=/opt/openclaw/state/bitrix_app
BITRIX_CLIENT_ID=
BITRIX_CLIENT_SECRET=
# Необязательно, только если нужен явный override:
# BITRIX_OAUTH_TOKEN_URL=https://oauth.bitrix24.tech/oauth/token/
```

## Как работает доступ

1. Локальное приложение Bitrix24 хранит OAuth state в `BITRIX_APP_STATE_DIR`.
2. Runtime читает `install.latest.json` или другой актуальный state-файл.
3. Если `access_token` истёк, runtime обновляет его через `refresh_token`.
4. API-вызовы идут через `client_endpoint` из OAuth state.

## Проверочный read-only набор

Для smoke-test использовать только read-only методы:

- `profile`
- `user.get`
- `crm.deal.list`
- `crm.lead.list`
- `crm.company.list`
- `crm.contact.list`
- `tasks.task.list`
- `department.get`

Секреты и OAuth tokens нельзя печатать в логах, чатах и отчётах.
