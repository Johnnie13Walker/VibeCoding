# Миграция Cloudbot-стека: TimeWeb → новый Hetzner

> Runbook. **Планирует Claude, live-операции исполняет Codex, ревью — Claude.**
> Дата составления: 2026-06-26 МСК. Все времена в плане — МСК.

## 1. Цель и зафиксированные решения

Перенести **весь Cloudbot/openclaw-стек** с TimeWeb VPS на **новый отдельный Hetzner-сервер**.

| Решение | Значение |
|---|---|
| Целевой сервер | **Новый Hetzner**, отдельный (только под TimeWeb-нагрузку) |
| GSD-дашборд | **НЕ трогаем** — остаётся на своём Hetzner (178.104.222.163) |
| Объём | Всё, **кроме sing-box / VPN** |
| Исполнитель | Claude планирует → **Codex исполняет live** → Claude ревьюит |
| Cutover | **Поэтапно, parallel-run**, TimeWeb выключаем как fallback на 1–2 недели |

## 2. Топология

**Источник — TimeWeb «КлаудБот»** `72.56.83.251` (id 6599101), 2 vCPU / 1.9 GB / 77 GB (29 GB занято), Ubuntu, TZ=Europe/Moscow.

**Приёмник — новый Hetzner: `CX23` (2 vCPU Intel/AMD / 4 GB / 40 GB, ~$7.72/мес)**, Ubuntu 24.04, fsn1/nbg1. Подтверждено пользователем 26.06.
Обоснование: рабочая нагрузка лёгкая — TimeWeb весь стек держит на 1.9 GB RAM (занято ~780 MB); CX23 даёт больше (4 GB). Диск: реально нужного ~12–15 GB (ОС ~4 + образ openclaw ~2.7 + searxng/redis ~0.3 + код/node_modules ~2 + cloudbot-runtime 0.2) — 40 GB хватает (29 GB на TimeWeb — это со старыми образами/`.bak`, которые НЕ переносим).
**amd64 обязателен** — docker-образы openclaw собраны под x86, ARM (cax*) потребует пересборки.
**Нюанс:** образ openclaw переносим готовым (`docker save | load`), НЕ собираем на сервере → лишний RAM не нужен. Если придётся пересобирать образ на месте (fallback §7) — на 4 GB добавить **2 GB swap**.

## 3. Реестр сервисов

### 3.1 Переносим

| # | Сервис | Тип | Где живёт на TimeWeb | Telegram-режим |
|---|---|---|---|---|
| A | **openclaw-gateway** (интерактивный TG-бот + поиск) | docker-compose `/opt/openclaw/docker-compose.yml` | образ `openclaw:ddg-searxng-20260412`, config-dir `/root/.openclaw`, vault-mount | **getUpdates (long-poll) → single-instance!** |
| B | **searxng + redis(valkey)** | docker-compose `/opt/searxng/` | порт 8088 | — |
| C | **cloudbot-bitrix-app** (OAuth Bitrix + Wazzup) | systemd, `/opt/openclaw/local/bitrix_app_server.py`, :8787 | state `/opt/openclaw/state/bitrix_app/` | **single-refresher!** |
| D | **Лариса** daily-brief 08:00 | cron `/etc/cron.d/cloudbot-larisa-daily-brief` → `/opt/cloudbot-runtime/larisa/current` | sendMessage (push) | дубль-риск |
| E | **Лев Петрович** sales-reports (09:30/09:40/17:00/пт18:30) | cron `/etc/cron.d/cloudbot-sales-reports` → `/opt/cloudbot-runtime/current` | sendMessage (push) | дубль-риск |
| F | **WHOOP** report 08:01 | cron `/etc/cron.d/openclaw-whoop-report` → `/usr/local/bin/send_whoop_report.py` | sendMessage | дубль-риск |
| G | **todo-digest / reminders** | cron `/etc/cron.d/openclaw-todo-digest` → `docker exec gateway … npm run sync/reminders:tick` | через gateway | зависит от A |
| H | **larisa-sales-kpi** (03/07/11/15) | cron → `/usr/local/bin/cloudbot-larisa-sales-kpi.sh` | — | — |
| I | **marketing-dashboard** 08:00 + TG-статус 08:15 | cron → `/opt/cloudbot-runtime/marketing-dashboard/current` | push | дубль-риск |
| J | **portfolio-clients** 09:05 | cron → `/opt/cloudbot-runtime/portfolio-clients/current` | push | дубль-риск |
| K | **empty_companies** weekly(пн 06:30) + score(утро/вечер) | cron `empty_companies_weekly` + root crontab | push | дубль-риск |
| L | **dup_watchdog** (ежечасно) + **dup_sheet_sync** (3×/день) | root crontab → `/opt/openclaw/scripts/dup_watchdog.sh`, `belberry/bitrix24/dup_sheet_sync.py` | Sheets-write | дубль-риск |
| M | **cloudbot-health-api** (Apple Health → state) | systemd, `/opt/cloudbot-health-api/server.py`, :8765 локально | — | low-risk |
| N | **agent-dashboard** (FastAPI) | systemd, `/root/projects/dashboard`, :8765 локально | — | low-risk |
| O | **openclaw-update-maintenance**, **openclaw-backup**, **acme.sh/certbot** | root crontab / cron.d | — | инфра |

> ⚠️ Конфликт портов M и N оба на :8765 — на TimeWeb health-api на 8766/8765? проверить при переносе (`ss -tlnp`: uvicorn=8765 → agent-dashboard; python3=8766 → health-api). Сохранить раздельные порты.

### 3.2 НЕ переносим (явное решение)

- **sing-box** (VPN/прокси :2443) и образ `amneziavpn/amneziawg-go` — пропускаем.
- `*.bak*` файлы cron/env/скриптов, старые docker-образы (`openclaw:patched-*`, `*-backup-*`), `current.backup-*`.
- GSD/sales_command_center (на другом сервере).

## 4. Реестр секретов и состояния (КОПИРОВАТЬ, не в git)

Всё ниже — **через `rsync -e ssh` напрямую TimeWeb→Hetzner или scp**, права `chmod 600`, владелец root. **Значения в git/чат не кладём.**

**Секреты:**
- `/opt/openclaw/.env` (33 ключа: BITRIX_CLIENT_ID/SECRET, OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, WAZZUP_API_KEY, OPENCLAW_GATEWAY_TOKEN, OBSIDIAN_*, OPENCLAW_CONFIG_DIR/WORKSPACE_DIR)
- `/opt/openclaw/secrets/finance-director-sheets*.json` (2 файла, Google SA)
- `/etc/openclaw/{larisa,sales_agent,whoop,marketing_dashboard,portfolio_clients,todo,health-api}.env`
- Telegram-токены по ссылкам `*_BOT_TOKEN_FILE` (Лев: `/root/.openclaw/telegram/commercial-director.bot_token` — **проверить актуальный путь**, на дереве `/root/.openclaw` не виден; найти `grep -r BOT_TOKEN_FILE /etc/openclaw`)
- `/root/.openclaw/credentials/*.json`, `identity/*.json`, `openclaw.json` (живой, не .bak)

**Состояние (критично — не пересоздаётся):**
- `/opt/openclaw/state/bitrix_app/install.latest.json` — **Bitrix OAuth refresh-токен** (см. §5.1)
- `/opt/openclaw/state/dup_watchdog/state.json`, `/opt/openclaw/state/bitrix_app/wazzup.*.json` (архив)
- `/etc/openclaw/whoop-state.json` + `WHOOP_REFRESH_TOKEN` в whoop.env
- `/root/.openclaw/cron/jobs.json`, `subagits/runs.json`, `workspace/MEMORY.md`
- `/srv/cloudbot/obsidian-vault/` (544 KB, bind-mount в gateway)
- `/opt/searxng/searxng/` (settings.yml — содержит `secret_key`)
- История отчётов (по желанию): `/home/ops/cloudbot-sales-agent/reports/`, `/home/ops/cloudbot-larisa-agent/reports/`

**Код (через git, не rsync):**
- `/opt/openclaw` — repo `github.com/openclaw/openclaw`, **detached @ `61d171ab`** (есть локальные патчи → образ переносим save/load, см. §6)
- `/opt/openclaw/repos/vibecoding` — `github.com/Johnnie13Walker/VibeCoding`, ветка `feature/crm_company_merge`
- `/opt/openclaw/repos/vibecoding-enrich` — отдельный clone (проверить ветку)
- `/opt/cloudbot-runtime/*` — release-деревья (Лев/Лариса/marketing/portfolio). Можно rsync целиком (194 MB) ИЛИ пересобрать deploy-пайплайном `cloudbot/infra/orchestrator/workflows/sales_agent_deploy.sh`. **На первом этапе — rsync** (детерминированно), чистый redeploy — потом.
- Wrapper-скрипты `/usr/local/bin/cloudbot-*.sh`, `send_whoop_report.py`, `send_whoop_checkin_prompt.py`, `whoop_oauth_setup.sh`
- venv'ы **пересоздать** на Hetzner (НЕ rsync — пути/линковка): `/opt/cloudbot-runtime/larisa/sales-kpi-dashboard/.venv`, `/opt/openclaw/venvs/crm_company_merge`, и др. — по requirements/uv.

## 5. Два жёстких ограничения (читать до cutover!)

### 5.1 Bitrix OAuth — только ОДИН refresher одновременно
`install.latest.json` содержит **rotating refresh-токен**: при каждом refresh Bitrix выдаёт новый и инвалидирует старый. Если bitrix-app + sync-скрипт работают на ОБОИХ серверах и оба рефрешат — один сервер получит `invalid_grant`, контур ляжет.

**Правило parallel-run:** рефрешит только TimeWeb. На Hetzner до cutover — либо bitrix-app **выключен**, либо джобы гоняем в dry/read-only без refresh. В момент cutover §8: остановить bitrix-app+sync на TimeWeb → скопировать свежий `install.latest.json` → запустить на Hetzner. Это **самая хрупкая точка** всей миграции.

### 5.2 Telegram getUpdates — single-instance
**openclaw-gateway** (A) и todo (G) общаются с Telegram через long-polling. Два инстанса на одном токене = `409 Conflict`, бот мечется. **Нельзя** держать gateway запущенным на обоих серверах с одним `TELEGRAM_BOT_TOKEN`.
- Для теста на Hetzner — **отдельный тестовый бот-токен** для gateway, ИЛИ тестировать только в момент cutover (стоп TimeWeb → старт Hetzner).
- Push-боты (D/E/F/I/J/K/L) шлют `sendMessage` — у них не 409, а **дубль-сообщение**. Тестируем с пустым `*_TELEGRAM_BOT_TOKEN`/в тестовый чат, затем «вкл на Hetzner + выкл на TimeWeb» по одному.

## 6. Phase 0 — Провижининг нового Hetzner (Codex)

**Сервер уже создан пользователем 26.06:** CX23 «ClaudBot», id `145299522`, проект `14273654`, IPv4 `188.34.206.115`, IPv6 `2a01:4f8:c0c:6ea4::/64`, Ubuntu. SSH-ключ добавляется через веб-консоль (`scc_hetzner.pub`).

1. ~~Создать сервер~~ — сделано. Добавить SSH-ключ `~/.ssh/scc_hetzner` в `authorized_keys` root (через веб-консоль Hetzner). Вход: `ssh -i ~/.ssh/scc_hetzner root@188.34.206.115`.
2. ✅ Базовая настройка (Claude, 26.06): TZ=Europe/Moscow; apt upgrade; `ufw` (22/80/443, deny incoming); `PasswordAuthentication no` (SSH только по ключу — пароль root, светившийся в чате, больше не вектор для SSH); `fail2ban` active.
3. ✅ Установлено: docker 29.6 + compose v5.2, `uv` 0.11 + **uv-managed Python 3.12.13**, git, certbot, nginx, rsync, jq. (nodejs на хост пока НЕ ставили — gateway/todo работают в docker; добавим если хост-сервису понадобится.)
4. ✅ Раскладка каталогов создана: `/opt/openclaw{,/repos,/secrets,/state,/venvs}`, `/opt/searxng`, `/opt/cloudbot-runtime`, `/opt/cloudbot-health-api`, `/srv/cloudbot`, `/etc/openclaw`, `/root/.openclaw`, `/home/ops`.
5. **DNS пока НЕ трогаем** — для теста использовать встроенный Hetzner rDNS-хостнейм нового IP (резолвится сразу, certbot работает). `larisabot.ru` остаётся на TimeWeb до §9.

> **ОТКЛОНЕНИЕ от плана:** сервер создан как **Ubuntu 26.04 LTS** (не 24.04), системный Python **3.14**. Решение: все venv'ы и при необходимости хост-сервисы — на **uv-managed Python 3.12** (паритет с TimeWeb), docker-контейнеры от версии хоста не зависят. Rebuild не требуется.

## 7. Phase 1 — Перенос артефактов (✅ ВЫПОЛНЕНО Claude, 26.06)

Перенос напрямую TimeWeb→Hetzner через временный ключ `~/.ssh/tw_migrate` на Hetzner (его pubkey добавлен в authorized_keys TimeWeb — **убрать после cutover**).

1. ✅ **Образ openclaw**: `docker save openclaw:ddg-searxng-20260412 | gzip` стримом → `docker load` на Hetzner (5.7 GB на диске, патчи сохранены).
2. ✅ **Код** (rsync, исключены node_modules/.venv/dist/__pycache__/*.bak): `/opt/openclaw` (compose, local/, scripts/, repos/), `/opt/cloudbot-runtime` (32 MB), `/opt/searxng`, `/opt/cloudbot-health-api`, `/root/projects/dashboard`, wrapper-скрипты `/usr/local/bin/cloudbot-*.sh`+whoop. Ветки: vibecoding `feature/crm_company_merge`@9cac3b3, vibecoding-enrich `main`@2804f53.
3. ✅ **searxng**: rsync + `SEARXNG_BASE_URL` → `http://188.34.206.115:8088/`. Образы valkey/searxng спулены.
4. ✅ **Секреты/состояние** (§4): `/opt/openclaw/.env`, `/opt/openclaw/secrets/`, `/opt/openclaw/state/` (вкл. `install.latest.json` — СНИМОК, рефреш на Hetzner НЕ запускаем, §5.1), `/etc/openclaw/*`, `/root/.openclaw/` целиком (вкл. `telegram/` с токенами), obsidian-vault. Права 600.
5. ✅ **venv'ы** (uv, Python 3.12.13) пересобраны из `pip freeze` + editable из репо, импорты проверены: `crm_company_merge`(+empty_companies_score), `crm_company_enrich`, `sales-kpi-dashboard/.venv`(sales_dashboard+sales_kpi_dashboard), `dashboard/.venv`(fastapi/uvicorn).
6. ✅ **systemd-юниты** (bitrix-app, health-api, agent-dashboard) скопированы, `daemon-reload`, **disabled+inactive**. cron.d/wrappers перенесены, **cron НЕ установлен** (включаем пофазно в §8).
7. ⏳ **Smoke** — отложено: gateway требует ТЕСТОВЫЙ бот-токен (с боевым = 409 против живого TimeWeb, §5.2); searxng up можно безопасно при cutover.

> **НАХОДКА (упрощает план):** runtime-агенты Льва/Ларисы, `bitrix_app_server.py`, health-api — **чистая stdlib + локальные пакеты**, импортируются на системном **Python 3.14** без venv (проверено). Отдельный venv для runtime НЕ нужен — работают на `/usr/bin/python3`. venv нужны только 4 belberry/dashboard-модулям (собраны на 3.12).

## 8. Phase 2 — Поэтапный cutover (по одному сервису)

Каждый шаг: **вкл на Hetzner → проверить ближайший прогон/лог → выкл на TimeWeb** (cron: переименовать файл; systemd: `disable --now`). Порядок от низкого риска к высокому:

1. **M, N** (health-api, agent-dashboard) — локальные :876x, побочек нет. Перенос в любой момент.
2. **H** (larisa-sales-kpi) — нет Telegram. Выкл на TimeWeb → вкл на Hetzner → проверить лог следующего слота.
3. **L** (dup_watchdog, dup_sheet_sync) — Sheets-write, риск дубля. По одному.
4. **I, J, K** (marketing-dashboard, portfolio-clients, empty_companies) — push-боты. По одному: выкл TimeWeb → вкл Hetzner → проверить отчёт.
5. **D, E, F** (Лариса, Лев, WHOOP) — push-боты, основные. По одному, с проверкой следующего планового сообщения.
6. **C + state ownership** (bitrix-app) — §5.1: стоп bitrix-app+sync на TimeWeb → свежая копия `install.latest.json` → старт на Hetzner. Сразу проверить, что джобы (3,4,5), зависящие от Bitrix, видят валидный токен.
7. **A + G** (openclaw-gateway + todo) — финал, single-instance (§5.2): стоп gateway на TimeWeb → переключить `TELEGRAM_BOT_TOKEN` на боевой на Hetzner → `docker compose up -d` → проверить, что бот отвечает в Telegram, todo sync идёт.

## 9. Phase 3 — DNS cutover

1. Заранее (за сутки) снизить TTL A-записей `larisabot.ru`, `api.larisabot.ru` на TimeWeb-DNS до 300с.
2. После §8.7: переключить A-записи на новый Hetzner IP.
3. `certbot` перевыпуск под `larisabot.ru` + `api.larisabot.ru` на Hetzner, обновить nginx-конфиги.
4. Проверить TLS (`curl -vI https://larisabot.ru`), вебхуки (Wazzup `WAZZUP_WEBHOOK_FORWARD_URL` если указывает на домен).

## 10. Phase 4 — Валидация и вывод TimeWeb

1. 1–2 недели parallel-наблюдения; на TimeWeb все cron/сервисы выключены, сервер **выключен (не удалён)** как fallback.
2. Чек-лист «всё работает на Hetzner»: каждое плановое сообщение пришло один раз, Bitrix-контур жив, дашборды/Sheets обновляются, gateway отвечает.
3. Через 1–2 недели — удалить TimeWeb VPS (id 6599101) через панель/API.

## 10b. Верификация Codex (26.06) — PASS, ложные срабатывания разобраны
Codex read-only прогон по CODEX-VERIFY-PROMPT.md дал PASS-with-issues; ревью Claude переоценило:
- gai.conf «нет фикса» — ЛОЖНО (в файле два пробела `/96  100`, grep Codex искал один; Python резолвит Google по IPv4 ✓).
- gateway EACCES/obsidian-router — СТАРЫЕ логи краш-лупа ДО chown; сейчас 0 EACCES, healthy ✓.
- нет dup_sheet_sync.log/whoop.log — ОЖИДАЕМО (cron установлены после их слотов; первые прогоны 22:30 и завтра 08:01).
**Реальных дефектов нет.** Гигиена выполнена: `/root/.ssh/tw_migrate` удалён, `uv`→/usr/local/bin (+profile.d), оба домена HTTPS 200, cert до 24.09. **Cutover завершён.**

## 11. Ротация секретов (в момент cutover)

Засветились в чате/устарели — сменить: **Hetzner API-токен** (после провижининга), при возможности — Telegram bot-токены (Лариса/Лев/основной), OpenAI-ключ, Bitrix client secret. Минимум — Hetzner-токен сразу.

## 12. Открытые вопросы к пользователю

1. Размер Hetzner: согласовать **cx32** (или достаточно cx22?).
2. `vibecoding-enrich` — какая ветка/назначение (отдельный clone — уточнить при переносе).
3. История отчётов `/home/ops/...` — переносить или начать с чистого листа?
4. Точный путь живого токена Льва (`*_BOT_TOKEN_FILE`) — подтвердить на сервере.
5. Wazzup webhook — указывает на IP или домен? (влияет на момент DNS-cutover).
