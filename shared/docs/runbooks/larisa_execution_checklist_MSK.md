# Чек-лист Ларисы (MSK)

## 1) Подготовка окружения
```bash
cd "/Users/pro2kuror/Desktop/VibeCoding/cloudbot"
./scripts/bootstrap_env.sh
```

## 2) Заполнить `.env.integrations`
Нужно заполнить:
- `SENTRY_AUTH_TOKEN`
- `SENTRY_ORG`
- `SENTRY_PROJECT`
- `OPENAI_API_KEY` (если токен только на сервере, перенести в локальное окружение этого агента)
- `NOTION_TOKEN`

## 3) GitHub CLI авторизация
```bash
gh auth login
gh auth status
```

## 4) Финальная проверка
```bash
make preflight
make verify
```

## 5) Ожидаемый результат
1. `preflight` без `WARN`.
2. `verify` с итогом `ОК`.
3. Отчет создан в `reports/health_*_MSK.txt`.
