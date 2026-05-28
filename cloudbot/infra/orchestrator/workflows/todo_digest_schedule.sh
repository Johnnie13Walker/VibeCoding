#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"
load_schedule_contract "$ROOT_DIR"

require_env PRIMARY_HOST SSH_USER SSH_KEY_PATH SSH_PORT

MODE="${1:-inspect}"
CRON_FILE="${TODO_CRON_FILE:-/etc/cron.d/openclaw-todo-digest}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/todo_digest_schedule_${STAMP}.txt"
DISABLE_MORNING_DIGEST="${DISABLE_MORNING_DIGEST:-$(( 1 - ${TODO_DIGEST_MORNING_ENABLED:-0} ))}"
DISABLE_MIDDAY_DIGEST="${DISABLE_MIDDAY_DIGEST:-$(( 1 - ${TODO_DIGEST_MIDDAY_ENABLED:-0} ))}"
DISABLE_EVENING_DIGEST="${DISABLE_EVENING_DIGEST:-$(( 1 - ${TODO_DIGEST_EVENING_ENABLED:-0} ))}"

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

mkdir -p "$REPORT_DIR"

remote_script=$(cat <<REMOTE
set -euo pipefail
export TZ=Europe/Moscow

mode='${MODE}'
cron_file='${CRON_FILE}'
disable_morning='${DISABLE_MORNING_DIGEST}'
disable_midday='${DISABLE_MIDDAY_DIGEST}'
disable_evening='${DISABLE_EVENING_DIGEST}'
stamp_human="\$(date '+%F %T %Z')"

[ -f "\$cron_file" ] || { echo "ОШИБКА: cron файл не найден: \$cron_file" >&2; exit 1; }

active_state() {
  local needle="\$1"
  if grep -n "\$needle" "\$cron_file" | awk -F: '\$2 !~ /^[[:space:]]*#/' | grep -q .; then
    printf 'active'
    return 0
  fi
  if grep -n "\$needle" "\$cron_file" >/dev/null 2>&1; then
    printf 'commented'
    return 0
  fi
  printf 'missing'
}

show_matches() {
  local label="\$1"
  local needle="\$2"
  echo "--- \${label} ---"
  grep -n "\$needle" "\$cron_file" || true
}

comment_out_active_lines() {
  local needle="\$1"
  local reason="\$2"
  local tmp_file
  local changed=0
  tmp_file="\$(mktemp)"
  while IFS= read -r line || [[ -n "\$line" ]]; do
    if [[ ! "\$line" =~ ^[[:space:]]*# ]] && [[ "\$line" == *"\$needle"* ]]; then
      printf '# %s (%s)\n' "\$reason" "\$stamp_human" >>"\$tmp_file"
      printf '# %s\n' "\$line" >>"\$tmp_file"
      changed=1
    else
      printf '%s\n' "\$line" >>"\$tmp_file"
    fi
  done < <(sudo -n cat "\$cron_file")

  if [[ "\$changed" == "1" ]]; then
    sudo -n cp -a "\$cron_file" "\$backup_file"
    sudo -n install -m 644 "\$tmp_file" "\$cron_file"
  fi
  rm -f "\$tmp_file"
  return 0
}

echo "Хост: \$(hostname)"
echo "Время: \$stamp_human"
echo "Файл cron: \$cron_file"
echo "disable_morning=\$disable_morning"
echo "disable_midday=\$disable_midday"
echo "disable_evening=\$disable_evening"
echo

morning_state_before="\$(active_state 'digest:morning')"
midday_state_before="\$(active_state 'digest:midday')"
evening_state_before="\$(active_state 'digest:evening')"
echo "before.morning=\$morning_state_before"
echo "before.midday=\$midday_state_before"
echo "before.evening=\$evening_state_before"
show_matches "digest:morning" "digest:morning"
show_matches "digest:midday" "digest:midday"
show_matches "digest:evening" "digest:evening"

if [[ "\$mode" == "inspect" ]]; then
  exit 0
fi

backup_file="\${cron_file}.bak-\$(date '+%Y%m%d_%H%M%S_MSK')"
echo
echo "backup=\$backup_file"

if [[ "\$disable_morning" == "1" ]]; then
  comment_out_active_lines 'digest:morning' 'disabled after Larisa morning cutover'
fi

if [[ "\$disable_midday" == "1" ]]; then
  comment_out_active_lines 'digest:midday' 'disabled after Larisa midday cutover'
fi

if [[ "\$disable_evening" == "1" ]]; then
  comment_out_active_lines 'digest:evening' 'disabled after Larisa evening cutover'
fi

morning_state_after="\$(active_state 'digest:morning')"
midday_state_after="\$(active_state 'digest:midday')"
evening_state_after="\$(active_state 'digest:evening')"
echo "after.morning=\$morning_state_after"
echo "after.midday=\$midday_state_after"
echo "after.evening=\$evening_state_after"

if [[ "\$disable_morning" == "1" && "\$morning_state_after" == "active" ]]; then
  echo "ОШИБКА: active digest:morning остался после apply" >&2
  exit 1
fi

if [[ "\$disable_midday" == "1" && "\$midday_state_after" == "active" ]]; then
  echo "ОШИБКА: active digest:midday остался после apply" >&2
  exit 1
fi

if [[ "\$disable_evening" == "1" && "\$evening_state_after" == "active" ]]; then
  echo "ОШИБКА: active digest:evening остался после apply" >&2
  exit 1
fi

show_matches "digest:morning (after)" "digest:morning"
show_matches "digest:midday (after)" "digest:midday"
show_matches "digest:evening (after)" "digest:evening"
REMOTE
)

log "todo_digest_schedule: старт (mode=${MODE}, host=${PRIMARY_HOST}, cron_file=${CRON_FILE})"
{
  echo "# Todo Digest Schedule"
  echo "Время: $(date '+%F %T %Z')"
  echo "Хост: ${PRIMARY_HOST}"
  echo "Файл cron: ${CRON_FILE}"
  echo "MODE: ${MODE}"
  echo "DISABLE_MORNING_DIGEST: ${DISABLE_MORNING_DIGEST}"
  echo "DISABLE_MIDDAY_DIGEST: ${DISABLE_MIDDAY_DIGEST}"
  echo "DISABLE_EVENING_DIGEST: ${DISABLE_EVENING_DIGEST}"
  echo
  run_remote_script "$PRIMARY_HOST" "$remote_script"
} | tee "$REPORT_FILE"

log "todo_digest_schedule: завершен, отчет=${REPORT_FILE}"
