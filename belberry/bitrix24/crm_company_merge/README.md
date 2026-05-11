# crm_company_merge

`crm_company_merge` — workflow-сервис для безопасного слияния дублей компаний Bitrix24 по ИНН: он ведёт очередь групп дублей в Google Sheets, собирает inventory связей, готовит план переноса, выполняет перенос и merge только после ручного approve, пишет логи и отправляет короткие Telegram-статусы.

## Структура папок

```text
crm_company_merge/
├── pyproject.toml
├── README.md
├── crm_company_merge/
│   ├── config.py
│   ├── cli.py
│   └── stages/
├── tests/
└── deploy/
```

## Установка на VPS

```bash
sudo mkdir -p /opt/openclaw/repos
sudo chown -R $USER /opt/openclaw/repos
git clone https://github.com/Johnnie13Walker/VibeCoding.git /opt/openclaw/repos/vibecoding
cd /opt/openclaw/repos/vibecoding && git checkout feature/crm_company_merge
python3 -m venv /opt/openclaw/venvs/crm_company_merge
source /opt/openclaw/venvs/crm_company_merge/bin/activate
pip install --upgrade pip
pip install google-api-python-client google-auth tzdata
```

Для установки entry point из модуля:

```bash
cd /opt/openclaw/repos/vibecoding/belberry/bitrix24/crm_company_merge
deploy/install_on_vps.sh
```

Скрипт делает `pip install -e` в `/opt/openclaw/venvs/crm_company_merge`, создаёт `/opt/openclaw/state/` и ставит симлинк `/usr/local/bin/crm-company-merge`. Симлинк выбран вместо записи в `.bashrc`, чтобы cron и ручные команды использовали один стабильный путь.

## Использование CLI

```bash
crm-company-merge --help
crm-company-merge discover --dry-run
crm-company-merge inventory --limit 3
crm-company-merge classify --limit 3
crm-company-merge transfer --limit 3 --dry-run
crm-company-merge merge --limit 3 --dry-run
crm-company-merge verify
crm-company-merge rollback --dry-run
crm-company-merge status
crm-company-merge migrate-pilot
crm-company-merge pause
crm-company-merge resume
```

На Шаге 1 все стадии являются заглушками и возвращают `NotImplementedError`.

## Google Sheet

Рабочая таблица: `1WaCtF2BeBorGXkZa0a53Bi6T_lKHeZZwQPEO8qIzmFU` — «Дубли сделок Bitrix24 — Реанимация». В ней уже есть листы «Анализ дублей», «План merge», «Дубли компаний ИНН».

## Bitrix OAuth Sync

Перед каждым Bitrix REST-вызовом клиент проверяет срок жизни OAuth state. Если токен истекает меньше чем через 5 минут, вызывается `shared/scripts/bitrix-sync-state.sh`. На VPS этот скрипт читает `BITRIX_CLIENT_ID` и `BITRIX_CLIENT_SECRET` из `/opt/openclaw/.env`, делает `refresh_token` flow через `https://oauth.bitrix24.tech/oauth/token/`, атомарно обновляет `/opt/openclaw/state/bitrix_app/install.latest.json`, ставит права `600` и проверяет результат через `/profile`.

## Конфигурация

Пример окружения лежит в `deploy/env.example`. Обязательные переменные:

- `BITRIX_STATE_PATH`
- `SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`

Telegram для пилота использует `TELEGRAM_CHAT_ID=81681699`. Все таймстампы модуля должны быть в `Europe/Moscow`.

## Codex prompt

Стартовый промт ревьюера находится в `belberry/bitrix24/tmp/codex_prompt_crm_company_merge.md`. Это временный документ: после завершения всех 11 шагов и финального принятого прогона его нужно удалить.
