#!/usr/bin/env bash
set -euo pipefail

export TZ="${TZ:-Europe/Moscow}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/scc}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"

: "${DATABASE_URL:?DATABASE_URL required}"

mkdir -p "$BACKUP_DIR"

pg_dump "$DATABASE_URL" | gzip >"$BACKUP_DIR/scc-$(date +%F).sql.gz"
find "$BACKUP_DIR" -name 'scc-*.sql.gz' -mtime +"$BACKUP_KEEP_DAYS" -delete
