# cloudbot-obsidian-vault

Markdown vault для Cloudbot. Используется как файловая база знаний:
быстрые заметки, дневник, задачи, проекты, встречи, health-данные,
системные заметки бота.

## Схема синхронизации

```text
Obsidian desktop  <->  private GitHub repo  <->  Cloudbot server
                                              /srv/cloudbot/obsidian-vault
```

- На сервере Cloudbot vault лежит в `/srv/cloudbot/obsidian-vault`.
- Cloudbot перед чтением/записью делает `git pull --rebase`,
  после записи — `git add && git commit && git push`.
- Записи выполняются под file-lock, чтобы параллельные запросы
  Telegram не конфликтовали.

## Структура

```text
Inbox/      быстрые заметки
Daily/      ежедневные заметки (МСК, YYYY-MM-DD.md)
Projects/   проектные заметки
Tasks/      задачи и списки действий
Meetings/   встречи и follow-up
Health/     WHOOP и health-отчёты
Cloudbot/   системные заметки бота
Templates/  шаблоны заметок
```

## Безопасность

В vault **запрещено** хранить:

- `.env`, `.env.*`
- API-ключи и токены
- VPN-конфиги
- private keys (`*.pem`, `*.key`)

См. `.gitignore` и контракт интеграции в основном workspace
Cloudbot: `shared/docs/integrations/obsidian_vault.md`.

## Часовой пояс

Все даты, заголовки дневника и сообщения — `Europe/Moscow` (МСК).
