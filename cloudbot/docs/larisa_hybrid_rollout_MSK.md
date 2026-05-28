# Гибридное внедрение (я + Лариса) — MSK

Время и отчеты ведем только в `Europe/Moscow`.

## Цель
Полностью запустить и проверить набор:
- `gh-fix-ci`
- `gh-address-comments`
- `sentry`
- `playwright`
- `openai-docs`
- `security-best-practices`
- `security-threat-model`
- `notion-spec-to-implementation`
- `skill-creator` (системный)

## Что делаю я (Codex)
1. Проверяю наличие скиллов и инструментов.
2. Поднимаю preflight/health-check скрипты.
3. Проверяю интеграции и формирую отчет `ОК/есть проблемы`.
4. Вношу технические правки до зеленого статуса.

## Что делает Лариса
1. Регистрирует тех. аккаунты/почты, где это допустимо.
2. Готовит токены с минимальными правами (read-only, где возможно).
3. Добавляет переменные окружения на целевой сервер/в CI.
4. Передает статус без секретов: «добавлено/не добавлено».

## Что подтверждаешь ты
1. 2FA/SMS/email подтверждения.
2. ToS/биллинг.
3. Админские решения по доступам.

## Минимальные переменные
См. файл: `/.env.integrations.example`

Обязательные:
- `SENTRY_AUTH_TOKEN`
- `SENTRY_ORG`
- `SENTRY_PROJECT`
- `OPENAI_API_KEY`
- `NOTION_TOKEN`

## Команды проверки
```bash
make preflight
make verify
```

## Критерий готовности
1. `make preflight` без `WARN`.
2. `make verify` завершился с `ОК`.
3. Создан отчет в `reports/health_*_MSK.txt`.
