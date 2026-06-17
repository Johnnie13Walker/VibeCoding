#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

OPENCLAW_HOST="${OPENCLAW_HOST:-${PRIMARY_HOST:-}}"
OPENCLAW_DIR="${OPENCLAW_DIR:-/opt/openclaw}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/openclaw}"
BACKUP_SCRIPT_PATH="${BACKUP_SCRIPT_PATH:-/usr/local/sbin/openclaw-backup.sh}"
BACKUP_LOG_PATH="${BACKUP_LOG_PATH:-/var/log/openclaw-backup.log}"
OPENCLAW_COMPILE_CACHE_DIR="${OPENCLAW_COMPILE_CACHE_DIR:-/var/tmp/openclaw-compile-cache}"
OPENCLAW_NO_RESPAWN="${OPENCLAW_NO_RESPAWN:-1}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
BACKUP_CRON_EXPR="${BACKUP_CRON_EXPR:-15 7 * * *}"
MODE="${1:-inspect}"

require_env OPENCLAW_HOST SSH_USER SSH_KEY_PATH SSH_PORT

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

openclaw_dir_b64="$(printf '%s' "$OPENCLAW_DIR" | base64 | tr -d '\n')"
backup_dir_b64="$(printf '%s' "$BACKUP_DIR" | base64 | tr -d '\n')"
backup_script_b64="$(printf '%s' "$BACKUP_SCRIPT_PATH" | base64 | tr -d '\n')"
backup_log_b64="$(printf '%s' "$BACKUP_LOG_PATH" | base64 | tr -d '\n')"
retention_b64="$(printf '%s' "$RETENTION_DAYS" | base64 | tr -d '\n')"
cron_expr_b64="$(printf '%s' "$BACKUP_CRON_EXPR" | base64 | tr -d '\n')"
mode_b64="$(printf '%s' "$MODE" | base64 | tr -d '\n')"

remote_script=""
read -r -d '' remote_script <<'REMOTE' || true
set -euo pipefail
export TZ=Europe/Moscow

openclaw_dir="$(printf '%s' '__OPENCLAW_DIR_B64__' | base64 -d)"
backup_dir="$(printf '%s' '__BACKUP_DIR_B64__' | base64 -d)"
backup_script_path="$(printf '%s' '__BACKUP_SCRIPT_B64__' | base64 -d)"
backup_log_path="$(printf '%s' '__BACKUP_LOG_B64__' | base64 -d)"
retention_days="$(printf '%s' '__RETENTION_DAYS_B64__' | base64 -d)"
backup_cron_expr="$(printf '%s' '__CRON_EXPR_B64__' | base64 -d)"
mode="$(printf '%s' '__MODE_B64__' | base64 -d)"
compile_cache_dir="${OPENCLAW_COMPILE_CACHE_DIR:-/var/tmp/openclaw-compile-cache}"
no_respawn="${OPENCLAW_NO_RESPAWN:-1}"

print_backup_state() {
  echo "--- backup_dirs ---"
  ls -lah "$backup_dir" 2>/dev/null || echo "missing $backup_dir"
  echo "--- backup_files_tail ---"
  find "$backup_dir" -maxdepth 1 -type f -name '*-openclaw-backup.tar.gz' -printf '%TY-%Tm-%Td %TH:%TM %p\n' 2>/dev/null | sort | tail -n 10 || true
  echo "--- backup_script ---"
  if [ -f "$backup_script_path" ]; then
    stat -c '%a %U:%G %n' "$backup_script_path"
    sed -n '1,200p' "$backup_script_path"
  else
    echo "missing $backup_script_path"
  fi
  echo "--- cron_lines ---"
  crontab -l 2>/dev/null | grep -F "$backup_script_path" || echo "missing cron entry"
}

echo "host=$(hostname -f 2>/dev/null || hostname)"
echo "time=$(date '+%F %T %Z')"
echo "mode=${mode}"
echo "openclaw_dir=${openclaw_dir}"
echo "backup_dir=${backup_dir}"
echo "backup_script_path=${backup_script_path}"
echo "backup_log_path=${backup_log_path}"
echo "backup_cron_expr=${backup_cron_expr}"

print_backup_state

if [ "$mode" = "apply" ]; then
  install -d -m 750 "$(dirname "$backup_script_path")" "$backup_dir"
  install -d -m 755 "$(dirname "$backup_log_path")"

  cat >"$backup_script_path" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
export TZ=Europe/Moscow

OPENCLAW_DIR="${openclaw_dir}"
BACKUP_DIR="${backup_dir}"
RETENTION_DAYS="${retention_days}"
OPENCLAW_COMPILE_CACHE_DIR="${compile_cache_dir}"
OPENCLAW_NO_RESPAWN="${no_respawn}"

mkdir -p "\$BACKUP_DIR"
mkdir -p "\$OPENCLAW_COMPILE_CACHE_DIR"
cd "\$OPENCLAW_DIR"
if command -v openclaw >/dev/null 2>&1; then
  NODE_COMPILE_CACHE="\$OPENCLAW_COMPILE_CACHE_DIR" OPENCLAW_NO_RESPAWN="\$OPENCLAW_NO_RESPAWN" OPENCLAW_RUNNER_LOG=0 openclaw backup create --output "\$BACKUP_DIR" --verify --json
else
  NODE_COMPILE_CACHE="\$OPENCLAW_COMPILE_CACHE_DIR" OPENCLAW_NO_RESPAWN="\$OPENCLAW_NO_RESPAWN" OPENCLAW_RUNNER_LOG=0 node dist/entry.js backup create --output "\$BACKUP_DIR" --verify --json
fi
find "\$BACKUP_DIR" -maxdepth 1 -type f -name '*-openclaw-backup.tar.gz' -mtime +"$retention_days" -delete
SCRIPT
  chmod 750 "$backup_script_path"

  current_cron="$(mktemp)"
  desired_cron="$(mktemp)"
  crontab -l 2>/dev/null | grep -Fv "$backup_script_path" >"$current_cron" || true
  cat "$current_cron" >"$desired_cron"
  if ! grep -q '^CRON_TZ=' "$desired_cron" 2>/dev/null; then
    printf 'CRON_TZ=Europe/Moscow\n' >>"$desired_cron"
  fi
  printf '%s %s >> %s 2>&1\n' "$backup_cron_expr" "$backup_script_path" "$backup_log_path" >>"$desired_cron"
  crontab "$desired_cron"
  rm -f "$current_cron" "$desired_cron"

  echo "--- backup_run_apply ---"
  "$backup_script_path"
fi

echo "--- backup_state_after ---"
print_backup_state
REMOTE

remote_script="${remote_script/__OPENCLAW_DIR_B64__/$openclaw_dir_b64}"
remote_script="${remote_script/__BACKUP_DIR_B64__/$backup_dir_b64}"
remote_script="${remote_script/__BACKUP_SCRIPT_B64__/$backup_script_b64}"
remote_script="${remote_script/__BACKUP_LOG_B64__/$backup_log_b64}"
remote_script="${remote_script/__RETENTION_DAYS_B64__/$retention_b64}"
remote_script="${remote_script/__CRON_EXPR_B64__/$cron_expr_b64}"
remote_script="${remote_script/__MODE_B64__/$mode_b64}"

log "Запуск workflow openclaw_backup_schedule: mode=${MODE}, host=${OPENCLAW_HOST}"
run_remote_script "$OPENCLAW_HOST" "$remote_script"
log "Workflow openclaw_backup_schedule завершён"
