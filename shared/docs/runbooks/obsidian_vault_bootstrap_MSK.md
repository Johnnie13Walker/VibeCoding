# Runbook: бутстрап Obsidian vault на сервере Cloudbot (MSK)

## Цель

Подключить Obsidian к серверу Cloudbot как файловый Markdown vault,
синхронизируемый через private GitHub repository.

Контракт: `shared/docs/integrations/obsidian_vault.md`.
Референсная реализация provider/skills: `shared/templates/cloudbot/obsidian/`.

Все шаги выполняются по МСК (`Europe/Moscow`).

## Предусловия

- На сервере доступен пользователь, под которым работает Cloudbot.
- Доступен SSH-доступ к серверу (см. `shared/integrations/ops/ssh_happ.sh`).
- Создан и подтверждён владельцем private GitHub repository
  `cloudbot-obsidian-vault`.
- Сгенерирован отдельный SSH/deploy key для сервера.

## Шаг 1. Подготовить SSH-доступ к GitHub

На сервере под пользователем Cloudbot:

```bash
ssh-keygen -t ed25519 -C "cloudbot-obsidian@server" -f ~/.ssh/obsidian_vault_ed25519
cat ~/.ssh/obsidian_vault_ed25519.pub
```

Опубличить ключ как deploy key с правом записи в private repo
`cloudbot-obsidian-vault`.

Добавить в `~/.ssh/config`:

```text
Host github.com-obsidian-vault
  HostName github.com
  User git
  IdentityFile ~/.ssh/obsidian_vault_ed25519
  IdentitiesOnly yes
```

Проверить:

```bash
ssh -T git@github.com-obsidian-vault
```

## Шаг 2. Развернуть vault

```bash
sudo install -d -o "$USER" -g "$USER" /srv/cloudbot
git clone git@github.com-obsidian-vault:USER/cloudbot-obsidian-vault.git /srv/cloudbot/obsidian-vault
cd /srv/cloudbot/obsidian-vault

git config user.name "Cloudbot"
git config user.email "cloudbot@example.local"
```

Если репозиторий пустой, создать базовую структуру и запушить:

```bash
mkdir -p Inbox Daily Projects Tasks Meetings Health Cloudbot Templates
cat > .gitignore <<'EOF'
.obsidian/workspace*
.trash/
.env
.env.*
*.pem
*.key
.cloudbot.lock
EOF
cat > README.md <<'EOF'
# Cloudbot Obsidian vault

Vault Cloudbot. В vault не хранятся секреты, токены, ключи и .env-файлы.
EOF
git add .
git commit -m "init: базовая структура vault"
git push -u origin main
```

## Шаг 3. Заполнить env-переменные на сервере

В боевом env Cloudbot (например `/opt/openclaw/.env` или его аналоге)
выставить переменные из `.env.integrations.example`:

```bash
OBSIDIAN_VAULT_PATH=/srv/cloudbot/obsidian-vault
OBSIDIAN_GIT_REMOTE=git@github.com-obsidian-vault:USER/cloudbot-obsidian-vault.git
OBSIDIAN_SYNC_ENABLED=true
OBSIDIAN_DEFAULT_INBOX=Inbox
OBSIDIAN_DAILY_DIR=Daily
OBSIDIAN_TIMEZONE=Europe/Moscow
OBSIDIAN_GIT_AUTHOR_NAME=Cloudbot
OBSIDIAN_GIT_AUTHOR_EMAIL=cloudbot@example.local
```

Реальный `OBSIDIAN_GIT_REMOTE` и логин владельца **не коммитить**.

## Шаг 4. Перенести provider/skills в runtime

Из workspace:

```bash
shared/templates/cloudbot/obsidian/obsidian_provider.py     -> cloudbot/providers/obsidian_provider.py
shared/templates/cloudbot/obsidian/obsidian_save_note.py    -> cloudbot/skills/obsidian_save_note.py
shared/templates/cloudbot/obsidian/obsidian_append_daily.py -> cloudbot/skills/obsidian_append_daily.py
shared/templates/cloudbot/obsidian/obsidian_search.py       -> cloudbot/skills/obsidian_search.py
shared/templates/cloudbot/obsidian/obsidian_create_task.py  -> cloudbot/skills/obsidian_create_task.py
```

После переноса:

1. Согласовать импорты `from .obsidian_provider import ...` с фактической
   структурой пакетов Cloudbot.
2. Подключить provider/skills в bootstrap по аналогии с `whoop_provider`,
   `bitrix_provider`, `search_provider`.
3. Зарегистрировать команды Telegram:
   - `запомни: ...` → `obsidian_save_note`
   - `добавь в дневник: ...` → `obsidian_append_daily`
   - `найди в обсидиане про ...` → `obsidian_search`
   - `создай задачу: ...` → `obsidian_create_task`

## Шаг 5. Подключить Obsidian desktop

На рабочей машине владельца:

```bash
git clone git@github.com:USER/cloudbot-obsidian-vault.git ~/Documents/Cloudbot-Vault
```

Открыть `~/Documents/Cloudbot-Vault` как Obsidian vault. Для двусторонней
синхронизации использовать любой git-плагин (например `obsidian-git`)
или ручной `git pull --rebase` / `git push` по расписанию.

## Шаг 6. Smoke-тест на сервере

```bash
cd /srv/cloudbot/obsidian-vault
git pull --rebase

cat > Inbox/2026-05-10-smoke.md <<'EOF'
# smoke
проверка коннекта Cloudbot vault.
EOF

git status --short
git add Inbox/2026-05-10-smoke.md
git -c user.name=Cloudbot -c user.email=cloudbot@example.local commit -m "obsidian: smoke"
git push
```

Проверить, что заметка появилась в private GitHub repo и в Obsidian
desktop после `git pull`.

## Шаг 7. Smoke-тест из Cloudbot

В Telegram:

1. Отправить `запомни: тестовая заметка для smoke`.
   Ожидание: появится файл в `Inbox/`, push в GitHub.
2. Отправить `добавь в дневник: проверка дневника`.
   Ожидание: запись в `Daily/2026-05-10.md`.
3. Отправить `найди в обсидиане про smoke`.
   Ожидание: бот вернёт ссылку на тестовую заметку.
4. Отправить `создай задачу: проверить vault`.
   Ожидание: запись в `Tasks/_index.md` и отдельный файл в `Tasks/`.

## Шаг 8. Логи и устойчивость

После smoke-тестов проверить:

- Логи Cloudbot — нет ошибок git/permission.
- `git status` в `/srv/cloudbot/obsidian-vault` — чистый.
- Файл `.cloudbot.lock` снят.
- В private repo появились smoke-коммиты.

## Откат

В случае проблем:

1. Отключить интеграцию: `OBSIDIAN_SYNC_ENABLED=false`.
2. Удалить регистрацию skills из bootstrap Cloudbot.
3. Vault остаётся на диске, никакие данные не теряются.
4. По необходимости — сделать `git revert` лишних коммитов в private repo.

## Ограничения

- В vault **не хранятся** секреты, токены, private keys, `.env`.
- Любая запись делается под file-lock, чтобы параллельные Telegram-запросы
  не конфликтовали при `git push`.
- Все даты, заголовки и ответы пользователю — в МСК.

## Фактический production status на 2026-05-10 МСК

Интеграция включена в живом OpenClaw/Larisa runtime.

Фактическая схема:

- Vault на сервере: `/srv/cloudbot/obsidian-vault`.
- Vault в контейнере: `/home/node/cloudbot-obsidian-vault`.
- Runtime workspace: `/root/.openclaw/workspace`.
- Obsidian CLI: `/root/.openclaw/workspace/obsidian-integration/obsidian_cli.py`.
- Obsidian provider: `/root/.openclaw/workspace/obsidian-integration/obsidian_provider.py`.
- Deterministic gateway router: `/root/.openclaw/extensions/obsidian-router/`.
- Router включён в `/root/.openclaw/openclaw.json` через `plugins.entries.obsidian-router.enabled=true`.
- Trust pin: `plugins.allow=["obsidian-router"]`.
- Telegram owner id: `81681699`.

Почему добавлен `obsidian-router`:

- Инструкция через `AGENTS.md` оказалась недостаточной: Telegram-сессия Larisa пыталась вызвать shell/process tool и получила ошибку `sessionId is required for this action`.
- Для стабильности Obsidian-команды теперь перехватываются gateway plugin-ом до модели.
- Plugin вызывает `obsidian_cli.py`, сохраняет stdout и подменяет исходящий ответ на подтверждение CLI.
- Общий shell/exec доступ Larisa не включался.

Production backup-и:

- `/opt/openclaw/docker-compose.yml.bak.20260510_075226_UTC.obsidian-bind-mount`
- `/root/.openclaw/workspace/AGENTS.md.bak.20260510_081002_UTC.obsidian-section`
- `/root/.openclaw/workspace/AGENTS.md.bak.20260510_084204_UTC.obsidian-plugin-router`
- `/root/.openclaw/workspace/obsidian-integration/obsidian_cli.py.bak.20260510_081423_UTC.strftime-fix`
- `/root/.openclaw/openclaw.json.bak.20260510_085646_UTC.post-obsidian-router-stable` — стабильный rollback snapshot после включения plugin
- `/root/.openclaw/openclaw.json.bak` — автоматический snapshot OpenClaw, перезаписывается при каждом сохранении конфига; не считать стабильным

Проверенный результат:

- `запомни: проверка через бот obsidian 2` создал
  `Inbox/2026-05-10-1143-проверка-через-бот-obsidian-2.md`.
- `дневник ...` добавил запись в `Daily/2026-05-10.md`.
- `задача ...` создал `Tasks/2026-05-10-1147-проверить-obsidian-task-router.md` и обновил `Tasks/_index.md`.
- `обсидиан проверка` вернул результаты поиска по vault.
- GitHub получил commits:
  - `2a1ed2c obsidian: новая заметка Inbox/2026-05-10-1143-проверка-через-бот-obsidian-2.md`
  - `126f644 obsidian: новая задача Tasks/2026-05-10-1147-проверить-obsidian-task-router.md`
  - `5ddff2e obsidian: запись в дневник Daily/2026-05-10.md`
- Локальный клон Mac `~/Documents/Cloudbot-Vault` обновлён через `git pull --ff-only`.

Операционная проверка:

```bash
ssh cloudbot-ssh-proxy 'docker ps --format "{{.Names}} {{.Status}}" | grep openclaw'
ssh cloudbot-ssh-proxy 'docker exec openclaw-openclaw-gateway-1 node dist/index.js plugins list 2>/dev/null | grep -i obsidian -C2'
ssh cloudbot-ssh-proxy 'sudo -u ops git -C /srv/cloudbot/obsidian-vault status -s'
```

Ожидание:

- `openclaw-openclaw-gateway-1` в статусе `healthy`.
- `obsidian-router` в статусе `loaded`.
- `git status -s` пустой.

Технический долг:

- Оформить `obsidian-router` как tracked локальный plugin/package, чтобы убрать warning `loaded without install/load-path provenance`.
- Добавить ежедневный health-check: plugin loaded, CLI syntax ok, vault writable, git push ok.
- Не включать общий `exec`/`process` для Telegram-сессии без отдельного security review.
