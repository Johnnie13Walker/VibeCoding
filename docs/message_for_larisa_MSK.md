# Сообщение для Ларисы (MSK)

Выполни задачу полностью в каталоге:
`/Users/pro2kuror/Documents/Персональный ассистент/Инженер`

## Цель
Довести интеграции до статуса `ОК`:
- GitHub (`gh-fix-ci`, `gh-address-comments`)
- Sentry (`sentry`)
- Notion (`notion-spec-to-implementation`)
- OpenAI (`openai-docs`)
- Общие проверки (`playwright`, security skills)

## Действия
1. Запусти:
```bash
cd "/Users/pro2kuror/Documents/Персональный ассистент/Инженер"
chmod +x ./scripts/larisa_finalize.sh
./scripts/larisa_finalize.sh
```
2. Если скрипт остановится:
- при `gh auth` — выполни `gh auth login`;
- при незаполненных переменных — заполни `.env.integrations`;
- после исправления повтори `./scripts/larisa_finalize.sh`.

## Что заполнить в `.env.integrations`
- `SENTRY_AUTH_TOKEN`
- `SENTRY_ORG`
- `SENTRY_PROJECT`
- `OPENAI_API_KEY`
- `NOTION_TOKEN`

## Формат отчета владельцу
1. `ОК` или `есть проблемы`.
2. Если проблемы: что именно, причина, что уже сделано, когда следующий чек (время MSK).
