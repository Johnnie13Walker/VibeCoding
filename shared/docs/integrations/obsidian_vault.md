# Obsidian vault для Cloudbot

## Назначение

Obsidian подключается к Cloudbot как файловая Markdown-база знаний. Vault живёт на сервере Cloudbot и синхронизируется с Obsidian пользователя через private GitHub repository.

Целевая схема:

```text
Obsidian desktop
  -> git push / pull
GitHub private repo: cloudbot-obsidian-vault
  -> git pull / push
Cloudbot server: /srv/cloudbot/obsidian-vault
```

## Статус

Статус: проектный контракт.

В текущем локальном репозитории нет runtime-кода `cloudbot/providers` и `cloudbot/skills`, поэтому этот документ фиксирует безопасный контракт подключения. Реализация должна добавляться в серверный runtime-контур Cloudbot после подтверждения расположения кода.

## Конфигурация

Переменные окружения:

```bash
OBSIDIAN_VAULT_PATH=/srv/cloudbot/obsidian-vault
OBSIDIAN_GIT_REMOTE=git@github.com:USER/cloudbot-obsidian-vault.git
OBSIDIAN_SYNC_ENABLED=true
OBSIDIAN_DEFAULT_INBOX=Inbox
OBSIDIAN_DAILY_DIR=Daily
OBSIDIAN_TIMEZONE=Europe/Moscow
OBSIDIAN_GIT_AUTHOR_NAME=Cloudbot
OBSIDIAN_GIT_AUTHOR_EMAIL=cloudbot@example.local
```

Реальные значения не коммитятся. Секреты, токены, private keys и `.env*` должны оставаться только на сервере.

## Структура vault

Новый vault создаётся с минимальной структурой:

```text
Inbox/
Daily/
Projects/
Tasks/
Meetings/
Health/
Cloudbot/
Templates/
```

Назначение каталогов:

- `Inbox/` — быстрые заметки из Telegram и входящие мысли.
- `Daily/` — ежедневные заметки в МСК.
- `Projects/` — проектные заметки.
- `Tasks/` — задачи и списки действий.
- `Meetings/` — встречи, итоги и follow-up.
- `Health/` — WHOOP и health-отчёты.
- `Cloudbot/` — системные заметки Cloudbot, runbooks, решения.
- `Templates/` — шаблоны заметок.

## Runtime-контракт

Provider:

```text
cloudbot/providers/obsidian_provider.py
```

Минимальные операции provider:

- `ensure_vault()` — проверить доступность vault и создать базовые каталоги.
- `sync_pull()` — выполнить `git pull --rebase` перед чтением или записью.
- `sync_push(message)` — выполнить `git add`, `git commit`, `git push` после изменения.
- `write_note(path, content)` — создать или перезаписать Markdown-файл внутри vault.
- `append_note(path, content)` — добавить блок в существующую заметку.
- `read_note(path)` — прочитать заметку.
- `search_notes(query, limit)` — найти заметки по содержимому и имени файла.

Skills:

```text
cloudbot/skills/obsidian_save_note.py
cloudbot/skills/obsidian_append_daily.py
cloudbot/skills/obsidian_search.py
cloudbot/skills/obsidian_create_task.py
```

Минимальные пользовательские сценарии:

- `запомни: ...` -> создать заметку в `Inbox/`.
- `добавь в дневник: ...` -> добавить запись в `Daily/YYYY-MM-DD.md` по МСК.
- `найди в обсидиане про ...` -> найти релевантные Markdown-файлы.
- `создай задачу: ...` -> создать запись в `Tasks/`.

## Правила синхронизации Git

Перед любой операцией чтения или записи:

```bash
git pull --rebase
```

После записи:

```bash
git add .
git commit -m "obsidian: обновить заметки"
git push
```

Требования:

- GitHub repository должен быть private.
- Для доступа используется deploy key или отдельный SSH key на сервере.
- Commit author задаётся через `OBSIDIAN_GIT_AUTHOR_NAME` и `OBSIDIAN_GIT_AUTHOR_EMAIL`.
- Операции записи выполняются под file lock, чтобы параллельные запросы Telegram не конфликтовали при `git push`.
- Если `git pull --rebase` или `git push` завершился ошибкой, Cloudbot должен вернуть пользователю понятное сообщение и залогировать причину.

## Безопасность

В vault запрещено хранить:

- `.env`
- `.env.*`
- API-ключи
- токены
- VPN-конфиги
- private keys

Перед коммитом provider должен игнорировать служебные файлы Obsidian и локальные секреты, если они появятся в vault:

```text
.obsidian/workspace*
.trash/
.env
.env.*
*.pem
*.key
```

## Проверка после подключения

Проверка выполняется в МСК.

1. Проверить, что `/srv/cloudbot/obsidian-vault` существует и является git-репозиторием.
2. Проверить `git remote -v` и доступ к private GitHub repo.
3. Выполнить `git pull --rebase`.
4. Создать тестовую заметку в `Inbox/`.
5. Выполнить `git status --short`.
6. Выполнить `git add`, `git commit`, `git push`.
7. Проверить, что заметка появилась в GitHub.
8. Открыть Obsidian desktop и выполнить pull/sync.
9. Проверить Telegram-сценарии: сохранить заметку, добавить daily note, найти заметку.
10. Проверить логи Cloudbot на ошибки синхронизации.

## Открытые параметры

Перед реализацией в runtime нужно подтвердить:

- GitHub owner для `cloudbot-obsidian-vault`.
- Точный SSH/deploy key для сервера.
- Фактический путь к runtime-коду Cloudbot на сервере.
- Нужно ли хранить Obsidian plugin config `.obsidian/` в Git или исключить полностью.
