# Sales Command Center DB

`web/src/db/schema.ts` — источник истины для схемы. Python-runner пишет в те же таблицы напрямую через snake_case имена колонок.

## Локальный Postgres 16

```bash
docker run --name scc-postgres \
  -e POSTGRES_USER=scc \
  -e POSTGRES_PASSWORD=scc \
  -e POSTGRES_DB=scc \
  -p 5432:5432 \
  postgres:16
```

## Применение миграции

```bash
export DATABASE_URL=postgresql://scc:scc@localhost:5432/scc
psql "$DATABASE_URL" -f db/migrations/0000_init.sql
```

Альтернатива после установки npm-зависимостей:

```bash
cd web
npm run db:migrate
```

## Проверка

```bash
psql "$DATABASE_URL" -c '\dt'
```

Ожидается 9 таблиц: `users`, `login_codes`, `sessions`, `reports`, `deals_snapshot`, `meetings`, `manager_activity`, `kp_briefs`, `plans`.
