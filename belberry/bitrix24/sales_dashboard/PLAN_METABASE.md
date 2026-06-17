# План: Belberry BI на Metabase (для Codex)

Документ создан Claude, исполняет Codex по этапам. После каждого этапа —
ревью со стороны Claude, потом следующий этап.

---

## Контекст

Дашборд продаж и телемаркетинга Belberry. Источник — Bitrix24 REST API.
Хостинг — собственный VPS (тот же где `cloudbot`). Визуализация — Metabase
OSS. Доступ — email + password с invite-flow ("magic link" для первичной
установки пароля).

Текущее состояние:
- ETL Bitrix → Google Sheets уже работает (legacy Looker-путь)
- Sheet ID: `1W11eS3q4ft_iCMECqpQZ4x_81GAeoBKE1Fx9EtXf3f8`
- Service account: `finance-director-sheets-bot@finance-director-sheets.iam.gserviceaccount.com`
- В Bitrix 65 активных юзеров с email, 6100 сделок, 699 звонков (на момент написания плана)

---

## Архитектура (целевая)

```
                    ┌─────────────────────────────────────────────┐
                    │              VPS (cloudbot)                  │
                    │                                              │
   bi.belberry.NET ─┼──▶ Caddy ──TLS──▶ Metabase :3000             │
                    │                       │                      │
                    │                       │ JDBC                 │
                    │                       ▼                      │
                    │                    Postgres :5432            │
                    │                    ├─ metabase_app (config)  │
                    │                    └─ belberry      (data)   │
                    │                       ▲                      │
                    │                       │ INSERT/UPSERT        │
                    │                       │                      │
                    │   ┌──────────────────┴────────────────┐     │
                    │   │ ETL container (cron */15)         │     │
                    │   │ • bitrix.crm.deal.list            │     │
                    │   │ • voximplant.statistic.get        │     │
                    │   │ • user.get                        │     │
                    │   └───────────────────────────────────┘     │
                    │                                              │
                    │   ┌───────────────────────────────────┐     │
                    │   │ user-sync container (cron */15)   │     │
                    │   │ Bitrix user.get → Metabase /api/  │     │
                    │   │   • ACTIVE=N → deactivate         │     │
                    │   │   • whitelist никогда не трогать  │     │
                    │   └───────────────────────────────────┘     │
                    │                                              │
                    │   SMTP outbound ───▶ user inbox             │
                    └─────────────────────────────────────────────┘
```

Источник правды:
- Сделки/звонки/юзеры → Bitrix24 REST
- Кому положен доступ → выдаёт админ вручную через Metabase UI (Admin → People → Invite)
- Кого деактивировать → Bitrix `user.get` ACTIVE=N (через user-sync)

Стек: Postgres 16 · Metabase OSS latest · Caddy 2 · Python 3.11 · Docker compose.

---

## Файловая структура

```
belberry/bitrix24/sales_dashboard/
├── README.md                                   ← обновить: убрать Looker, добавить Metabase
├── DEPLOY.md                                   ← NEW: runbook деплоя на VPS
├── PLAN_METABASE.md                            ← этот файл
├── LOOKER_GUIDE.md                             ← пометить deprecated в шапке
├── pyproject.toml                              ← добавить deps: psycopg[binary], requests
│
├── sales_dashboard/
│   ├── config.py                               ← + ENV-based для Postgres/Metabase
│   ├── bitrix_client.py                        ← без изменений
│   ├── sheets_client.py                        ← без изменений (legacy)
│   ├── postgres_loader.py                      ← NEW
│   ├── etl.py                                  ← MODIFY
│   ├── extractors/                             ← без изменений
│   ├── metabase/                               ← NEW package
│   │   ├── __init__.py
│   │   ├── client.py                           ← API wrapper
│   │   ├── provisioner.py                      ← создаёт DB connection + cards + dashboards
│   │   ├── cards.py                            ← SQL запросы для карточек
│   │   └── layout.py                           ← раскладка по дашбордам
│   ├── user_sync.py                            ← REWRITE: revoke-only через Metabase API
│   └── cli.py                                  ← + подкоманды metabase-provision, metabase-sync
│
├── tests/
│   ├── test_bitrix_helpers.py                  ← не трогать
│   ├── test_postgres_loader.py                 ← NEW
│   └── test_metabase_client.py                 ← NEW
│
└── deploy/                                     ← NEW
    ├── docker-compose.yml
    ├── Caddyfile
    ├── .env.example
    ├── .env                                    ← gitignored
    ├── Dockerfile.etl
    ├── crontab
    ├── postgres/
    │   └── init.sql
    └── README.md                               ← ops-guide
```

Что НЕ трогать:
- `belberry/bitrix24/crm_deal_merge/` — отдельный проект
- `mockup/dashboard.html` — статический мокап
- Существующие тесты должны pass'ить как были

---

## Этапы

### Этап 1 — Postgres-схема и docker-compose (скелет)

Файлы:
- `deploy/postgres/init.sql`
- `deploy/docker-compose.yml` (только сервис postgres пока)
- `deploy/.env.example`
- `deploy/README.md`

Содержание `init.sql`:
- `CREATE DATABASE metabase_app, belberry`
- `CREATE USER metabase, belberry_writer, belberry_reader` с правильными правами
- Привилегии: writer — INSERT/UPDATE/DELETE/SELECT, reader — только SELECT,
  metabase — owner на metabase_app

Acceptance:
- `docker compose up -d postgres` → healthy
- `psql -U belberry_writer -d belberry -c "\dt"` подключается (пусто, без таблиц)
- `psql -U metabase -d metabase_app` подключается

---

### Этап 2 — Postgres loader для ETL

Файлы:
- `sales_dashboard/postgres_loader.py`
- модификация `sales_dashboard/etl.py`
- модификация `sales_dashboard/config.py`
- `tests/test_postgres_loader.py`

Контракт `postgres_loader.PostgresLoader`:
```python
class PostgresLoader:
    def __init__(self, dsn: str): ...
    def ensure_schema(self) -> None:
        """Создаёт таблицы deals, calls, users, stages, categories, sync_log если их нет."""
    def upsert_deals(self, header: list[str], rows: list[list]) -> tuple[int, int]: ...
    def upsert_calls(self, header: list[str], rows: list[list]) -> tuple[int, int]: ...
    def replace_users(self, header: list[str], rows: list[list]) -> int: ...
    def replace_stages(self, header: list[str], rows: list[list]) -> int: ...
    def replace_categories(self, header: list[str], rows: list[list]) -> int: ...
    def append_sync_log(self, header: list[str], rows: list[list]) -> None: ...
```

Схема таблиц — типы выводятся из `extractors/*.py:HEADER`:
- `deals.deal_id BIGINT PK`, `opportunity NUMERIC`, `is_closed/is_won/is_lost BOOLEAN`,
  дата-поля `TIMESTAMPTZ`, остальное TEXT/BIGINT
- `calls.call_id BIGINT PK`, `is_answered BOOLEAN`, `call_duration INTEGER`, аналогично
- BOOLEAN'ы конвертируются из 'Y'/'N' в loader'е
- Indexes: на `(category_id, is_closed)`, `(assigned_by_id)` в deals;
  `(date)`, `(portal_user_id)` в calls

Config (`config.py` дополнения):
```python
import os
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "")
WRITE_TO_SHEETS = os.environ.get("WRITE_TO_SHEETS", "1") == "1"
WRITE_TO_POSTGRES = bool(POSTGRES_DSN)
```

ETL изменения: после каждого `replace_tab`/`upsert_tab` — если `WRITE_TO_POSTGRES`,
вызывать соответствующий метод loader'а. Sheets-выход остаётся (включается флагом),
но Postgres становится первичным.

Acceptance:
- `pytest tests/test_postgres_loader.py` — green (минимум 5 тестов)
- `WRITE_TO_SHEETS=0 POSTGRES_DSN=... python -m sales_dashboard.cli etl --full` заполняет Postgres
- `SELECT COUNT(*) FROM deals;` возвращает ~6100

---

### Этап 3 — Metabase API client + provisioner

Файлы:
- `sales_dashboard/metabase/client.py`
- `sales_dashboard/metabase/cards.py`
- `sales_dashboard/metabase/layout.py`
- `sales_dashboard/metabase/provisioner.py`
- `tests/test_metabase_client.py`

`client.py` — обёртка над REST:
```python
class MetabaseClient:
    def __init__(self, url: str, email: str, password: str): ...
    def login(self) -> None: ...
    def ensure_database(self, name, engine, details) -> int: ...
    def sync_database_schema(self, db_id: int) -> None: ...
    def ensure_card(self, spec: CardSpec, database_id: int) -> int: ...
    def ensure_dashboard(self, name: str) -> int: ...
    def set_dashboard_cards(self, dash_id: int, cards: list[dict]) -> None: ...
    def list_users(self) -> list[dict]: ...
    def invite_user(self, email, first_name, last_name) -> int: ...
    def deactivate_user(self, user_id: int) -> None: ...
    def reactivate_user(self, user_id: int) -> None: ...
    def set_settings(self, **kwargs) -> None: ...
```

Все ensure-методы — идемпотентны (ищут существующее по имени, обновляют или создают).

`cards.py` — карточки декларативно:
```python
@dataclass(frozen=True)
class CardSpec:
    name: str
    query: str               # SQL для belberry DB
    display: str             # scalar | bar | row | line | table | pie | pivot
    visualization_settings: dict[str, Any] = field(default_factory=dict)
```

Минимальный набор карточек (Codex реализует все 25+ из плана):

**Продажи (8 карточек):**
1. Scorecard "Открытых сделок" — `SELECT COUNT(*) FROM deals WHERE is_closed = FALSE`
2. Scorecard "Pipeline" — `SELECT SUM(opportunity) FROM deals WHERE is_closed = FALSE`
3. Scorecard "Выиграно (шт)" — `SELECT COUNT(*) FROM deals WHERE is_won`
4. Scorecard "Выручка закрыто" — `SELECT SUM(opportunity) FROM deals WHERE is_won`
5. Bar (horizontal) "Открытые по стадиям" — `SELECT stage_name, COUNT(*) FROM deals WHERE is_closed = FALSE GROUP BY stage_name ORDER BY 2 DESC LIMIT 10`
6. Pie "По воронкам" — `SELECT category_name, COUNT(*) FROM deals GROUP BY 1 ORDER BY 2 DESC`
7. Line "Создано сделок по дням" — `SELECT date_trunc('day', date_create)::date AS d, COUNT(*) FROM deals WHERE date_create > now() - interval '30 days' GROUP BY 1 ORDER BY 1`
8. Table "Разрез по воронкам" — категория × кол-во/выиграно/win rate/сумма

**Телемаркетинг (7 карточек):** аналогично — scorecards + line по дням + pie по типам +
heatmap (pivot table dow × hour) + таблица топ-менеджеров.

**KPI менеджеров (3 карточки):** табличный обзор всех менеджеров + leaderboard.

`layout.py` — раскладка дашбордов в виде декларативного списка с координатами
карточек (Metabase использует grid 24×N, h = высота в ячейках, w = ширина):
```python
DASHBOARDS = [
    {
        "name": "Продажи",
        "cards": [
            {"card": "Открытых сделок", "x": 0, "y": 0, "w": 6, "h": 4},
            ...
        ],
    },
    ...
]
```

`provisioner.py` — main script:
1. Login as admin (из env)
2. `set_settings`: SMTP, signup-enabled=false, enable-password-login=true
3. `ensure_database(name="Belberry data", engine="postgres", details={host, port, dbname, user=belberry_reader, password})`
4. `sync_database_schema` чтобы Metabase увидел таблицы
5. Для каждой CardSpec — `ensure_card`
6. Для каждого Dashboard — `ensure_dashboard` + `set_dashboard_cards`

Acceptance:
- `python -m sales_dashboard.cli metabase-provision` запускается дважды подряд
  без ошибок (идемпотентность)
- В UI Metabase появляются 3 дашборда с корректными виджетами
- Цифры на дашборде совпадают с прямыми SQL-запросами к Postgres
- SMTP сохранён, можно отправить test email из Admin → Email → Send test email

---

### Этап 4 — user-sync через Metabase API

Файлы:
- переписать `sales_dashboard/user_sync.py`
- `state/user_sync_state.json` — оставить whitelist
- обновить `scripts/cron_user_sync.sh`

Логика (revoke-only):
```python
metabase_users = client.list_users(active=True)
bitrix_users = {row[email]: row[active] for row in extract_users(bx)}

for user in metabase_users:
    if user.email in whitelist:
        continue
    if user.is_superuser:
        continue
    bitrix_active = bitrix_users.get(user.email.lower())
    if bitrix_active is None:
        continue          # внешний — не трогаем
    if not bitrix_active:
        client.deactivate_user(user.id)
        log_revoked(user)
```

Никаких invite автоматом — выдача доступа только через UI Metabase (или
отдельная команда `metabase-invite <email> <name>` для админа).

Acceptance:
- `python -m sales_dashboard.cli metabase-sync --dry-run` — план без изменений
- Без `--dry-run` — деактивирует только Bitrix-inactive юзеров
- Whitelist `eshchemelev@gmail.com` никогда не деактивируется
- Test: вручную деактивировать тестового юзера в Bitrix, через 15 мин он
  деактивирован в Metabase

---

### Этап 5 — Docker сервисы и Caddy

Файлы:
- `deploy/docker-compose.yml` (дополнить полностью)
- `deploy/Caddyfile`
- `deploy/Dockerfile.etl`
- `deploy/crontab`

`Caddyfile`:
```caddyfile
{$DOMAIN} {
    reverse_proxy metabase:3000
    encode gzip zstd
    log {
        output file /var/log/caddy/access.log
    }
}
```

`Dockerfile.etl`:
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron curl tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml .
COPY sales_dashboard ./sales_dashboard
RUN pip install --no-cache-dir -e .
COPY deploy/crontab /etc/cron.d/sales_dashboard
RUN chmod 0644 /etc/cron.d/sales_dashboard && crontab /etc/cron.d/sales_dashboard
ENV TZ=Europe/Moscow
CMD ["cron", "-f"]
```

`crontab`:
```
*/15 * * * * cd /app && /usr/local/bin/python -m sales_dashboard.cli etl >> /var/log/etl.log 2>&1
5,20,35,50 * * * * cd /app && /usr/local/bin/python -m sales_dashboard.cli metabase-sync >> /var/log/user_sync.log 2>&1
```

`docker-compose.yml` (полный):
```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_ROOT_PASS}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
    restart: unless-stopped

  metabase:
    image: metabase/metabase:latest
    environment:
      MB_DB_TYPE: postgres
      MB_DB_HOST: postgres
      MB_DB_PORT: 5432
      MB_DB_DBNAME: metabase_app
      MB_DB_USER: metabase
      MB_DB_PASS: ${METABASE_DB_PASS}
      MB_SITE_URL: https://${DOMAIN}
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    environment:
      DOMAIN: ${DOMAIN}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
      - caddy_log:/var/log/caddy
    depends_on:
      - metabase
    restart: unless-stopped

  etl:
    build:
      context: ..
      dockerfile: deploy/Dockerfile.etl
    environment:
      POSTGRES_DSN: postgresql://belberry_writer:${BELBERRY_WRITER_PASS}@postgres:5432/belberry
      METABASE_URL: http://metabase:3000
      METABASE_ADMIN_EMAIL: ${METABASE_ADMIN_EMAIL}
      METABASE_ADMIN_PASSWORD: ${METABASE_ADMIN_PASSWORD}
      WRITE_TO_SHEETS: "0"
      BITRIX_STATE_PATH: /state/install.latest.json
    volumes:
      - /var/lib/cloudbot/bitrix24-state:/state:ro
      - etl_logs:/var/log
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pgdata:
  caddy_data:
  caddy_config:
  caddy_log:
  etl_logs:
```

Acceptance:
- `docker compose up -d` → 4 контейнера healthy
- В логах ETL — успешный запуск каждые 15 мин
- TLS выпускается Caddy автоматически
- https://${DOMAIN} → Metabase login page

---

### Этап 6 — DEPLOY.md

Файл: `belberry/bitrix24/sales_dashboard/DEPLOY.md`

Содержит:
1. Pre-requisites: VPS с Docker, домен с A-записью, SMTP creds
2. Step-by-step:
   - `git clone` / `git pull` на VPS
   - `cd deploy/`, заполнить `.env` (см. `.env.example`)
   - DNS — добавить A `bi.<domain>` → IP VPS
   - `docker compose up -d postgres` → подождать healthcheck
   - `docker compose up -d` → все сервисы
   - Открыть `https://bi.<domain>` → Metabase setup wizard:
     - Email = METABASE_ADMIN_EMAIL из .env
     - Password = METABASE_ADMIN_PASSWORD из .env (или сгенерировать)
     - SMTP — пропустить (provisioner настроит сам)
     - Add data — пропустить (provisioner настроит сам)
   - `docker compose exec etl python -m sales_dashboard.cli metabase-provision`
   - Verify: открыть дашборды
3. Verification checklist
4. Troubleshooting:
   - Caddy не выпускает TLS — DNS не успел распространиться
   - ETL не пишет — проверить POSTGRES_DSN
   - SMTP не шлёт — проверить app-password и 2FA
   - Provisioner падает — Metabase ещё не готов к API
5. Day-2 ops:
   - Логи: `docker compose logs <service>`
   - Бэкап Postgres: `docker compose exec postgres pg_dump ...`
   - Обновление Metabase: `docker compose pull metabase && docker compose up -d metabase`

---

## Контракты между этапами

| От | Кому | Что |
|---|---|---|
| 1 | 2 | `POSTGRES_DSN` доступен, schema БД готова |
| 2 | 3 | В Postgres есть данные, Metabase их видит через JDBC |
| 3 | 4 | `MetabaseClient.list_users/deactivate_user` работают |
| 5 | 6 | Все контейнеры стартуют, образы собраны |

Идемпотентность: `docker compose up && metabase-provision` повторно — без ломки.

---

## Конвенции для Codex

- **Идемпотентность:** все ensure/upsert операции повторно безопасны
- **Логирование:** stdout/stderr, формат `[YYYY-MM-DD HH:MM:SS] level: msg`,
  в Postgres-loader — лог в `sync_log` таблицу
- **Секреты:** только через `.env`, никогда не коммитить
- **Тесты:** минимум 3 unit-теста на новый модуль (happy + edge + error)
- **Не трогать** существующие тесты в `tests/test_bitrix_helpers.py`
- **Python 3.11+**, `from __future__ import annotations` в каждом файле
- **Тип-аннотации обязательны**
- **Без AI-комментариев** в коде
- **PR per этап** — каждый = отдельный commit с понятным сообщением
  (`feat(etl): postgres_loader`, `feat(metabase): provisioner` и т.д.)
- **Остановка после каждого этапа** для ревью Claude

---

## Что ревьюит Claude

| Этап | Точки внимания |
|---|---|
| 1 | SQL init корректен, права минимальные, compose валиден |
| 2 | Типы колонок, атомарность upsert, locale numeric парсинг |
| 3 | API-вызовы соответствуют актуальной Metabase docs, идемпотентность |
| 4 | Только revoke, whitelist работает, никаких массовых invite |
| 5 | TLS auto-renews, ETL контейнер видит Postgres, Caddy headers |
| 6 | Runbook воспроизводим |

После каждого этапа — diff, комментарии, потом следующий.

---

## Параметры от пользователя

| Что | Значение |
|---|---|
| SMTP host | `smtp.gmail.com` |
| SMTP port | `587` |
| SMTP user | `eshchemelev@gmail.com` |
| SMTP password | Gmail app-password (создаётся вручную, кладётся в `.env`) |
| EMAIL_FROM | `eshchemelev@gmail.com` |
| Домен | `bi.<belberry.net или .ru — уточнить>` |
| VPS | тот же где `cloudbot` |
| Admin email | `eshchemelev@gmail.com` |
| Bitrix state path | `/var/lib/cloudbot/bitrix24-state/install.latest.json` (на VPS) |
