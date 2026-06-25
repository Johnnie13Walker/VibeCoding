# Codex-промт — Деплой Global Sales Dashboard на Hetzner (rDNS-хостнейм, красивый домен позже)

> LIVE-ПРОД. MVP (Фазы 1-6) собран и отревьюен на ветке `feat/global-sales-dashboard`. Разворачиваем на ВЫДЕЛЕННОМ Hetzner-сервере. Действуй СТРОГО по шагам, с жёсткими стоп-условиями. Прод-write (БД, Telegram, nginx, перенос секретов) — твоя зона; при любой неоднозначности — СТОП и спроси.

## Целевой сервер
- **Hetzner Cloud**, server id **127630645**, имя сейчас `Amnezia`, IP **178.104.222.163**, тип **cx23** (2 vCPU / 4 ГБ / диск 40 ГБ), DC fsn1. Порты 80/443 свободны. (Подтверждено через Hetzner API 2026-06-02.)
- Сервер **ПОЛНОСТЬЮ репурпозим под дашборд**. На нём работал Amnezia VPN (docker `amnezia-awg2`, udp/45237, uptime ~5 нед) — **VPN больше не нужен, сносим безвозвратно** (подтверждено пользователем).
- **Способ сноса — РЕШЕНО пользователем: Hetzner Rebuild через API** (чистая Ubuntu 24.04 разом убирает Amnezia + docker + wg + firewall-правила VPN). Процедура — Шаг 1.
- **⚠️ Rebuild стирает диск целиком и сбрасывает SSH-доступ.** До запуска rebuild убедись, что доступ восстановим (SSH-ключ привязан к серверу ИЛИ перехватываешь `root_password` из ответа API). Детали — Шаг 1.
- При нехватке RAM/CPU — допустимо предложить рескейл плана Hetzner (не молча, предложи).

## Источник секретов
- Существующий **TimeWeb VPS «КлаудБот»** (доступ по `ssh cloudbot-ssh-proxy`) — оттуда переносим: OpenAI-ключ (`/opt/openclaw/.env`), токен бота «Лев Петрович», Bitrix-state. См. шаг 1.5.

## ⛔ ЖЁСТКИЕ СТОП-УСЛОВИЯ (нарушение = откат)
1. **НЕ выдумывай значения.** Пустое из «values» — стоп и спроси.
2. **Bitrix-токен: НЕ запускать на Hetzner конкурирующий OAuth-refresh** — TimeWeb cloudbot уже рефрешит тот же app, параллельный refresh ДЕСИНХРОНИТ refresh_token (подтверждённый риск). По умолчанию: Hetzner **синкает** install.latest.json с TimeWeb (read-only pull по cron, как делает мак через bitrix-sync-state.sh). Если хочешь чистого разделения — предложи отдельный Bitrix-вебхук/приложение, но это РЕШЕНИЕ пользователя, спроси.
3. **НЕ ломать ничего на TimeWeb** — только читать секреты (scp/cat), без изменений на cloudbot.
4. **Первая боевая рассылка — в группу «тестовая», НЕ в чат менеджеров.** Реальный чат — позже, по явному «go» с id.
5. **Сервис не публиковать, пока не проверен вход** (любой маршрут без сессии → /login; /day без сессии → 401).
6. **Секреты — только env-файлы вне git, chmod 600.** Не в репо/логах/истории.
7. **НЕ force-push, НЕ merge в main.** Деплой из `origin/feat/global-sales-dashboard`.
8. Rebuild/чистка сервера, создание БД, выпуск TLS, установка crontab, go-live — фиксировать в отчёте.

## ЗАПОЛНИТЬ ПЕРЕД ЗАПУСКОМ
```
HCLOUD_TOKEN=<Hetzner Cloud API token>   # для Шага 1 (rebuild). Передаётся через env, НЕ в файл/git. Токен засвечен в чате 2026-06-02 → СМЕНИТЬ после деплоя (Hetzner Console → Security → API Tokens). Скоуп Read&Write.
SCC_DOMAIN=static.163.222.104.178.clients.your-server.de   # СТАРТ: встроенный Hetzner reverse-DNS хостнейм, УЖЕ резолвится на 178.104.222.163 (проверено) — НИКАКИХ правок DNS не нужно, certbot выпускается сразу. Красивый домен (larisabot.ru или новый) — ПОЗЖЕ: сменить SCC_DOMAIN + SCC_BASE_URL в /etc/scc/scc.env, server_name в nginx, перевыпустить cert. Если Let's Encrypt упрётся в rate-limit на your-server.de — СТОП, сообщи (fallback: --staging для проверки, либо ждать/перейти на купленный домен).
SCC_TELEGRAM_CHAT_ID=<group «тестовая»>   # старт: слать сюда (владелец + бот Лев Петрович, бот сделан админом). Numeric id получи через getUpdates. Реальный чат менеджеров — ПОЗЖЕ.
SCC_ALERT_CHAT_ID=<group «тестовая»>      # алерты на старте — туда же.
SCC_TELEGRAM_BOT_TOKEN=<Лев Петрович>     # перенести с TimeWeb (commercial-director).
```
**chat_id «тестовой»:** бот Лев Петрович — админ группы → `curl https://api.telegram.org/bot<ТОКЕН>/getUpdates` → `chat.id` (отрицательный).

## ШАГИ

**0. Ветка.** Запушить (одобрено пользователем) `git push -u origin feat/global-sales-dashboard` с машины разработки. На Hetzner — клонировать репо и `git checkout feat/global-sales-dashboard` (main НЕ мёржить). `.planning/` gitignored (на VPS не нужен); промты `CODEX-*.md` — контекст, не код.

**1. Снос Amnezia через Hetzner Rebuild (API) + база.** `export HCLOUD_TOKEN=...` (из values, не в файл). Все вызовы к `https://api.hetzner.cloud/v1`, заголовок `Authorization: Bearer $HCLOUD_TOKEN`.

  **1a. Сохранить доступ ПЕРЕД rebuild (критично — иначе потеряешь сервер).** Локальный ключ — `temp_migration_key` (им Codex ходит на TimeWeb), публичную часть взять из `~/.ssh/temp_migration_key.pub`.
  - Проверь, есть ли ключ в проекте: `GET /ssh_keys`. Если нашего fingerprint нет — загрузи: `POST /ssh_keys {name, public_key}`, запомни его `id`.
  - **Важно:** action `rebuild` НЕ принимает ssh_keys в теле и НЕ переназначает ключи. Поэтому страховка двойная: (i) ключ должен быть привязан к серверу, либо (ii) перехвати `root_password` из ответа rebuild (возвращается, только если у сервера нет привязанных ключей) и зайди по паролю. Выбери надёжный путь и зафиксируй какой.

  **1b. Rebuild.** Подтверди что это именно id `127630645` (`GET /servers/127630645` → name `Amnezia`, ip `178.104.222.163`). Затем:
  `POST /servers/127630645/actions/rebuild` с телом `{"image":"ubuntu-24.04"}`.
  - Дождись завершения action (`GET /actions/<id>` → status `success`). Если в ответе пришёл `root_password` — сохрани его в env (не в файл), это твой вход.
  - Сервер пересоздан — Amnezia, docker, wg, VPN-firewall стёрты вместе с диском.

  **1c. Восстановить вход и закрепить ключ.** SSH на 178.104.222.163 (по ключу или с `root_password`). Сразу: добавить `temp_migration_key.pub` в `~/.ssh/authorized_keys`, проверить вход по ключу, затем `PasswordAuthentication no` + `systemctl reload sshd`. Сменить выданный root-пароль.

  **1d. Переименовать сервер:** `PUT /servers/127630645 {"name":"sales-dashboard"}` (опционально, для порядка).

  **1e. База ПО.** Node ≥18.18 (nvm/apt), Python 3.11+, PostgreSQL 16, nginx, certbot, PM2 (`npm i -g pm2`), git.

**1.5. Перенос секретов с TimeWeb (read-only).** Через `ssh cloudbot-ssh-proxy`:
- **OpenAI-ключ:** `OPENAI_API_KEY` лежит на TimeWeb в **`/opt/openclaw/.env`** (источник — vault REGISTRY; НЕ `/etc/openclaw/sales_agent.env`, там пусто). `ssh cloudbot-ssh-proxy "grep '^OPENAI_API_KEY=' /opt/openclaw/.env"` → положить в `/etc/scc/scc.env` как OPENAI_API_KEY (+ LLM_PROVIDER=openai, LLM_MODEL=gpt-4o). Anthropic-ключ не нужен (старт на OpenAI).
- Токен бота «Лев Петрович» (`/root/.openclaw/telegram/commercial-director.bot_token`) → на Hetzner.
- Bitrix-state: настроить на Hetzner **синк** install.latest.json с TimeWeb (адаптировать bitrix-sync-state.sh: scp latest с cloudbot по cron каждые ~15 мин) — БЕЗ локального refresh (см. стоп-условие 2). Проверить /profile → токен живой, владелец = Лариса 2812 (коды входа пойдут «от Ларисы»).
НИЧЕГО на TimeWeb не менять.

**2. PostgreSQL.** БД `scc` + пользователь с паролем. **Канон миграций = psql, НЕ `drizzle-kit migrate`** (журнал Drizzle `meta/_journal.json` содержит только 0000 — migrate пропустит 0001/0002 и колонки transcript_*/attempts не создадутся). Применить ВСЕ файлы по порядку через psql: `for f in db/migrations/0000_init.sql db/migrations/0001_*.sql db/migrations/0002_*.sql; do psql "$DATABASE_URL" -f "$f"; done`. **Проверка колонок** (иначе записи/логин молча падают): `psql "$DATABASE_URL" -c "\d meetings"` — должны быть transcript_url/transcript_text/transcript_ok/analysis_status; `\d login_codes` — должен быть attempts. Проверить 9 таблиц + TIMESTAMPTZ. Сформировать DATABASE_URL.

**3. Python runner.** venv, `pip install -r requirements.txt`, `pytest -q` (≈73 passed) как smoke.

**4. Next.js web.** `npm ci`, `npm run build` (на 4 ГБ следи за памятью — при OOM добавь swap или собери с NODE_OPTIONS). PM2 `instances: 1` на внутренний порт (напр. 3010).

**5. env-файлы (вне git, chmod 600).** DATABASE_URL, SESSION_SECRET (`openssl rand -hex 32`), SCC_BASE_URL=https://static.163.222.104.178.clients.your-server.de, SCC_TELEGRAM_BOT_TOKEN, SCC_TELEGRAM_CHAT_ID (тестовая), SCC_ALERT_CHAT_ID (тестовая), **LLM_PROVIDER=openai + OPENAI_API_KEY=<ключ> + LLM_MODEL=gpt-4o** (стартуем на OpenAI — Anthropic-ключа пока нет; переключение назад: LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY, без правок кода), BITRIX_STATE_PATH (на синкаемый файл), BACKUP_KEEP_DAYS=14. НЕ NEXT_PUBLIC_ для секретов. Перед прогоном: `pip install -r requirements.txt` (добавлен openai).

**6. nginx + TLS.** `server_name static.163.222.104.178.clients.your-server.de` → reverse-proxy на 3010. Certbot TLS на этот хостнейм (DNS уже валиден). Проверить robots.txt Disallow + X-Robots-Tag noindex.

**7. Smoke (без чата менеджеров).**
- Вход: `https://static.163.222.104.178.clients.your-server.de/` → редирект /login → ввести активный email → **код приходит сообщением от Ларисы в Bitrix24** → войти в календарь.
- Ручной прогон: `daily_runner.py --date <последний раб. день>` → запись в reports, LLM-секции наполнились (Anthropic ок) → `/day/<date>` открывается «рич»-отчётом (с разбором встреч).
- Telegram: cron_entry → ссылка пришла в **«тестовую»** и открывается у залогиненного.

**8. Расписание + бэкапы.** Установить crontab (поправить пути): daily `0 9 * * 1-5` TZ Europe/Moscow + backup `0 3 * * *` + синк Bitrix-токена (каждые 15 мин). Проверить flock, тестовый pg_dump + ротацию.

**9. GO-LIVE.** На старте боевая доставка — в «тестовую» (отдельный «go» не нужен). Дождаться штатного прогона по расписанию, убедиться: ссылка в «тестовой», отчёт открывается. **Переключение SCC_TELEGRAM_CHAT_ID на реальный чат менеджеров — ПОЗЖЕ, только по явному «go» пользователя с id.**

## ВЫХОД (отчёт)
```
# DEPLOY REPORT — Global Sales Dashboard @ Hetzner rDNS (178.104.222.163)
## СЕРВЕР — что было (Amnezia?), как очищен/rebuild, переименование, рескейл?
## ВЕТКА — push origin/feat/global-sales-dashboard ✓, checkout на Hetzner
## СЕКРЕТЫ — перенос с TimeWeb (Anthropic/Lev token), Bitrix-синк настроен (без refresh), /profile=Лариса 2812 ✓
## БД — миграции (9 таблиц), DATABASE_URL (без пароля в тексте)
## RUNNER — pytest N passed; WEB — build ok, PM2; NGINX/TLS — rDNS-хостнейм, cert, noindex ✓
## SMOKE — вход (код от Ларисы) ✓/✗, ручной отчёт + LLM ✓/✗, /day ✓/✗, Telegram в «тестовую» ✓/✗
## CRON/BACKUP — daily+backup+bitrix-sync установлены, flock ✓, дамп+ротация ✓
## GO-LIVE — доставка в «тестовую»; чат менеджеров ждёт «go»
## РИСКИ / ОТКРЫТЫЕ ВОПРОСЫ — DNS-распространение, RAM/4GB, Bitrix-токен-стратегия
## КОМАНДЫ ОТКАТА — pm2 stop, удалить cron-фрагмент, и т.д.
```
