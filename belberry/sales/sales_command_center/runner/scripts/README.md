# SCC runner scripts

Эти артефакты предназначены для VPS. Локально проверяются только синтаксис и статические свойства, без live cron, Telegram и `pg_dump`.

## Скрипты

- `run_daily.sh` — cron-обёртка для `daily_runner.py`: выставляет `TZ=Europe/Moscow`, берёт `flock` на `SCC_LOCK_PATH`, пишет лог в `SCC_LOG_DIR`.
- `backup_postgres.sh` — делает `pg_dump "$DATABASE_URL" | gzip` в `BACKUP_DIR` и удаляет `scc-*.sql.gz` старше `BACKUP_KEEP_DAYS`.
- `crontab.scc` — пример расписания: отчёт Пн–Пт в 09:00 МСК, backup ежедневно в 03:00 МСК.

## Env на VPS

- `DATABASE_URL` — Postgres DSN для runner и `pg_dump`.
- `TELEGRAM_BOT_TOKEN` — токен Telegram-бота.
- `TELEGRAM_CHAT_ID` — чат менеджеров для ссылки на отчёт.
- `TELEGRAM_ALERT_CHAT_ID` — чат алертов; можно тот же, что `TELEGRAM_CHAT_ID`.
- `SCC_BASE_URL` — базовый URL веб-приложения без завершающего `/`.
- `SCC_LOCK_PATH` — lock-файл, default `/tmp/scc-daily-runner.lock`.
- `SCC_LOG_DIR` — каталог логов, default `/var/log/scc`.
- `BACKUP_DIR` — каталог бэкапов, default `/var/backups/scc`.
- `BACKUP_KEEP_DAYS` — срок хранения бэкапов, default `7`.

## Установка на VPS

```bash
chmod +x runner/scripts/run_daily.sh runner/scripts/backup_postgres.sh
# отредактировать runner/scripts/crontab.scc: заменить /path/to/runner
crontab runner/scripts/crontab.scc
```

Секреты держать только в окружении VPS, не в git и не в `crontab.scc`.
