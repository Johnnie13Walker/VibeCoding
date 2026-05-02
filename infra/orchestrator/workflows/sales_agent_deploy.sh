#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"
load_schedule_contract "$ROOT_DIR"

require_env PRIMARY_HOST SSH_USER SSH_KEY_PATH SSH_PORT

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
if [[ -f "$ENV_INTEGRATIONS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_INTEGRATIONS_FILE"
  set +a
fi

require_env SALES_TELEGRAM_CHAT_ID

LEGACY_REPORT_DIR="${SALES_AGENT_REMOTE_DIR:-/home/ops/cloudbot-sales-agent}"
SYSTEM_DAILY_RUNNER_PATH="${SALES_AGENT_SYSTEM_RUNNER_PATH:-/usr/local/bin/cloudbot-sales-daily-brief.sh}"
SYSTEM_FOLLOWUP_RUNNER_PATH="${SALES_AGENT_FOLLOWUP_RUNNER_PATH:-/usr/local/bin/cloudbot-sales-followup.sh}"
SYSTEM_WEEKLY_RUNNER_PATH="${SALES_AGENT_WEEKLY_RUNNER_PATH:-/usr/local/bin/cloudbot-sales-weekly-review.sh}"
SYSTEM_CHECK_RUNNER_PATH="${SALES_AGENT_CHECK_RUNNER_PATH:-/usr/local/bin/cloudbot-sales-morning-check.sh}"
CRON_FILE_PATH="${SALES_AGENT_CRON_FILE_PATH:-/etc/cron.d/cloudbot-sales-reports}"
DAILY_CRON_EXPR_UTC="${SALES_DAILY_CRON_EXPR_UTC:-30 6 * * 1-5}"
CHECK_CRON_EXPR_UTC="${SALES_CHECK_CRON_EXPR_UTC:-40 6 * * 1-5}"
FOLLOWUP_CRON_EXPR_UTC="${SALES_FOLLOWUP_CRON_EXPR_UTC:-0 14 * * *}"
WEEKLY_CRON_EXPR_UTC="${SALES_WEEKLY_CRON_EXPR_UTC:-30 15 * * 5}"
REMOTE_ENV_FILE="${SALES_AGENT_REMOTE_ENV_FILE:-/etc/openclaw/sales_agent.env}"
RUNTIME_ROOT="${CLOUDBOT_RUNTIME_ROOT:-/opt/cloudbot-runtime}"
CURRENT_LINK="${CLOUDBOT_RUNTIME_CURRENT_LINK:-$RUNTIME_ROOT/current}"
REMOTE_LOCK_PATH="${CLOUDBOT_RUNTIME_LOCK_PATH:-$RUNTIME_ROOT/.deploy.lock}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/sales_agent_deploy_${STAMP}.txt"
RELEASE_BRANCH="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo working-tree)"
RELEASE_COMMIT="$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || echo working-tree)"
RELEASE_SHA_SHORT="$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo working)"
RELEASE_BRANCH_SLUG="$(printf '%s' "$RELEASE_BRANCH" | LC_ALL=C tr -c 'A-Za-z0-9._-' '_')"
RELEASE_ID="${RELEASE_BRANCH_SLUG}_${RELEASE_SHA_SHORT}"
STAGING_RELEASE_DIR="$RUNTIME_ROOT/releases/.${RELEASE_ID}.staging"
TARGET_RELEASE_DIR="$RUNTIME_ROOT/releases/${RELEASE_ID}"
RELEASED_AT_MSK="$(date '+%F %T %Z')"
LOCK_OWNER="sales_agent_deploy:${RELEASE_ID}:$(hostname):$$"
LOCK_HELD=0

mkdir -p "$REPORT_DIR"

FILES_TO_SYNC=()
while IFS= read -r path; do
  FILES_TO_SYNC+=("$path")
done < <(cloudbot_runtime_files)

TRACKED_RUNTIME_FILES=()
for path in "${FILES_TO_SYNC[@]}"; do
  if git -C "$ROOT_DIR" ls-files --error-unmatch "$path" >/dev/null 2>&1; then
    TRACKED_RUNTIME_FILES+=("$path")
  fi
done

WORKING_TREE_OVERLAY_FILES=()
WORKING_TREE_DELETED_FILES=()
if [[ "${ALLOW_DIRTY_DEPLOY:-0}" == "1" || "${ALLOW_UNPUSHED_RELEASE:-0}" == "1" ]]; then
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    if [[ -e "$ROOT_DIR/$path" ]]; then
      WORKING_TREE_OVERLAY_FILES+=("$path")
    else
      WORKING_TREE_DELETED_FILES+=("$path")
    fi
  done < <(
    {
      git -C "$ROOT_DIR" diff --name-only --relative HEAD -- "${FILES_TO_SYNC[@]}" || true
      git -C "$ROOT_DIR" ls-files --others --exclude-standard -- "${FILES_TO_SYNC[@]}" || true
    } | awk 'NF && !seen[$0]++'
  )
fi

if [[ -z "${ALLOW_DIRTY_DEPLOY:-}" && -z "${ALLOW_UNPUSHED_RELEASE:-}" ]]; then
  require_clean_release_checkout "$ROOT_DIR"
  require_release_on_origin "$ROOT_DIR" "$RELEASE_BRANCH" "$RELEASE_COMMIT"
fi

if [[ "${#WORKING_TREE_DELETED_FILES[@]}" -gt 0 ]]; then
  fail "Dirty deploy содержит удалённые runtime-файлы: ${WORKING_TREE_DELETED_FILES[*]}. Сначала зафиксируй удаление в git или убери его из рабочего дерева."
fi

weekly_chat_id="${SALES_WEEKLY_TELEGRAM_CHAT_ID:-$SALES_TELEGRAM_CHAT_ID}"
sales_owner_chat_id="${SALES_TELEGRAM_OWNER_ID:-${SALES_TELEGRAM_DM_CHAT_ID:-}}"
sales_log_file="${SALES_LOG_FILE:-$LEGACY_REPORT_DIR/reports/sales_agent.log}"
sales_daily_history_file="${SALES_DAILY_HISTORY_FILE:-$LEGACY_REPORT_DIR/reports/sales_daily_history.json}"
sales_bot_token_file="${SALES_TELEGRAM_BOT_TOKEN_FILE:-/root/.openclaw/telegram/commercial-director.bot_token}"
sales_department_ids="${SALES_DEPARTMENT_IDS:-}"
sales_department_names="${SALES_DEPARTMENT_NAMES:-Группа продаж Belberry,Группа продаж Acoola Team,Телемаркетинг}"
sales_excluded_user_ids="${SALES_EXCLUDED_USER_IDS:-}"
sales_excluded_user_names="${SALES_EXCLUDED_USER_NAMES:-}"
sales_excluded_user_markers="${SALES_EXCLUDED_USER_MARKERS:-}"

cleanup_remote_lock() {
  local exit_code=$?
  if [[ "$LOCK_HELD" == "1" ]]; then
    release_remote_lock "$PRIMARY_HOST" "$REMOTE_LOCK_PATH" || true
  fi
  return "$exit_code"
}

trap cleanup_remote_lock EXIT
acquire_remote_lock "$PRIMARY_HOST" "$REMOTE_LOCK_PATH" "$LOCK_OWNER"
LOCK_HELD=1

log "sales_agent_deploy: старт (host=${PRIMARY_HOST}, runtime_root=${RUNTIME_ROOT}, release_id=${RELEASE_ID})"

{
  echo "# Sales Agent Deploy"
  echo "Время: $(date '+%F %T %Z')"
  echo "Хост: ${PRIMARY_HOST}"
  echo "Runtime root: ${RUNTIME_ROOT}"
  echo "Current link: ${CURRENT_LINK}"
  echo "Release branch: ${RELEASE_BRANCH}"
  echo "Release commit: ${RELEASE_COMMIT}"
  echo "Release id: ${RELEASE_ID}"
  echo "Remote lock: ${REMOTE_LOCK_PATH}"
  echo "Lock owner: ${LOCK_OWNER}"
  echo "Legacy report dir: ${LEGACY_REPORT_DIR}"
  echo "Remote env file: ${REMOTE_ENV_FILE}"
  echo "Sales chat: configured"
  echo "Weekly chat: configured"
  echo
  echo "Файлы:"
  printf -- "- %s\n" "${FILES_TO_SYNC[@]}"
  echo
  echo "Dirty overlay:"
  if [[ "${#WORKING_TREE_OVERLAY_FILES[@]}" -gt 0 ]]; then
    printf -- "- %s\n" "${WORKING_TREE_OVERLAY_FILES[@]}"
  else
    echo "- нет"
  fi
  echo

  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
mkdir -p '${LEGACY_REPORT_DIR}' '${LEGACY_REPORT_DIR}/reports' '${RUNTIME_ROOT}/releases'
rm -rf '${STAGING_RELEASE_DIR}'
mkdir -p '${STAGING_RELEASE_DIR}'
sudo mkdir -p \"\$(dirname '${REMOTE_ENV_FILE}')\"
"

  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "[DRY-RUN] tar sync -> ${PRIMARY_HOST}:${STAGING_RELEASE_DIR}"
  elif [[ "${ALLOW_DIRTY_DEPLOY:-0}" == "1" || "${ALLOW_UNPUSHED_RELEASE:-0}" == "1" ]]; then
    git -C "$ROOT_DIR" archive --format=tar "$RELEASE_COMMIT" "${TRACKED_RUNTIME_FILES[@]}" | gzip -c | ssh -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
      -o BatchMode=yes \
      -o StrictHostKeyChecking=accept-new \
      -o ConnectTimeout=10 \
      "${SSH_USER}@${PRIMARY_HOST}" \
      "mkdir -p '${STAGING_RELEASE_DIR}' && tar xzf - -C '${STAGING_RELEASE_DIR}'"
    if [[ "${#WORKING_TREE_OVERLAY_FILES[@]}" -gt 0 ]]; then
      tar -C "$ROOT_DIR" -czf - "${WORKING_TREE_OVERLAY_FILES[@]}" | ssh -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
        -o BatchMode=yes \
        -o StrictHostKeyChecking=accept-new \
        -o ConnectTimeout=10 \
        "${SSH_USER}@${PRIMARY_HOST}" \
        "mkdir -p '${STAGING_RELEASE_DIR}' && tar xzf - -C '${STAGING_RELEASE_DIR}'"
      echo "tar_sync=ok (source=git:${RELEASE_COMMIT} + local overlay:${#WORKING_TREE_OVERLAY_FILES[@]})"
    else
      echo "tar_sync=ok (source=git:${RELEASE_COMMIT}; local overlay empty)"
    fi
  else
    git -C "$ROOT_DIR" archive --format=tar "$RELEASE_COMMIT" "${FILES_TO_SYNC[@]}" | gzip -c | ssh -i "$SSH_KEY_PATH" -p "$SSH_PORT" \
      -o BatchMode=yes \
      -o StrictHostKeyChecking=accept-new \
      -o ConnectTimeout=10 \
      "${SSH_USER}@${PRIMARY_HOST}" \
      "mkdir -p '${STAGING_RELEASE_DIR}' && tar xzf - -C '${STAGING_RELEASE_DIR}'"
    echo "tar_sync=ok (source=git:${RELEASE_COMMIT})"
  fi

  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
cat > '${STAGING_RELEASE_DIR}/run_sales_morning_report_from_runtime_env.sh' <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=\"\$(cd \"\$(dirname \"\${BASH_SOURCE[0]}\")\" && pwd)\"
export TZ=Europe/Moscow

if [[ -f /opt/openclaw/.env ]]; then
  set -a
  source /opt/openclaw/.env
  set +a
fi

if [[ -f '${REMOTE_ENV_FILE}' ]]; then
  set -a
  source '${REMOTE_ENV_FILE}'
  set +a
fi

export BITRIX_APP_STATE_DIR=\"\${BITRIX_APP_STATE_DIR:-/opt/openclaw/state/bitrix_app}\"
export SALES_RUNTIME_ENV_FILE='${REMOTE_ENV_FILE}'
export SALES_LOG_FILE=\"\${SALES_LOG_FILE:-${sales_log_file}}\"
export REPORT_DIR=\"\${REPORT_DIR:-${LEGACY_REPORT_DIR}/reports}\"
export SALES_TRIGGER=\"\${SALES_TRIGGER:-scheduled}\"
export SALES_JOB_NAME=\"\${SALES_JOB_NAME:-morning_sales_dispatch}\"

cd \"\$ROOT_DIR\"
exec ./infra/orchestrator/workflows/sales_morning_report.sh \"\$@\"
SCRIPT

cat > '${STAGING_RELEASE_DIR}/run_sales_focus_from_runtime_env.sh' <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=\"\$(cd \"\$(dirname \"\${BASH_SOURCE[0]}\")\" && pwd)\"
export TZ=Europe/Moscow

if [[ -f /opt/openclaw/.env ]]; then
  set -a
  source /opt/openclaw/.env
  set +a
fi

if [[ -f '${REMOTE_ENV_FILE}' ]]; then
  set -a
  source '${REMOTE_ENV_FILE}'
  set +a
fi

export BITRIX_APP_STATE_DIR=\"\${BITRIX_APP_STATE_DIR:-/opt/openclaw/state/bitrix_app}\"
export SALES_LOG_FILE=\"\${SALES_LOG_FILE:-${sales_log_file}}\"
export SALES_TRIGGER=\"\${SALES_TRIGGER:-manual}\"
export SALES_JOB_NAME=\"\${SALES_JOB_NAME:-manual_focus_dispatch}\"
export SALES_WORKFLOW_NAME=\"\${SALES_WORKFLOW_NAME:-run_sales_focus_from_runtime_env.sh}\"

cd \"\$ROOT_DIR\"
exec python3 -m agents.lev_petrovich --report focus --send
SCRIPT

cat > '${STAGING_RELEASE_DIR}/run_sales_followup_from_runtime_env.sh' <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=\"\$(cd \"\$(dirname \"\${BASH_SOURCE[0]}\")\" && pwd)\"
export TZ=Europe/Moscow

if [[ -f /opt/openclaw/.env ]]; then
  set -a
  source /opt/openclaw/.env
  set +a
fi

if [[ -f '${REMOTE_ENV_FILE}' ]]; then
  set -a
  source '${REMOTE_ENV_FILE}'
  set +a
fi

export BITRIX_APP_STATE_DIR=\"\${BITRIX_APP_STATE_DIR:-/opt/openclaw/state/bitrix_app}\"
export SALES_RUNTIME_ENV_FILE='${REMOTE_ENV_FILE}'
export SALES_LOG_FILE=\"\${SALES_LOG_FILE:-${sales_log_file}}\"
export REPORT_DIR=\"\${REPORT_DIR:-${LEGACY_REPORT_DIR}/reports}\"

cd \"\$ROOT_DIR\"
exec ./infra/orchestrator/workflows/sales_followup.sh
SCRIPT

cat > '${STAGING_RELEASE_DIR}/run_sales_weekly_review_from_runtime_env.sh' <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=\"\$(cd \"\$(dirname \"\${BASH_SOURCE[0]}\")\" && pwd)\"
export TZ=Europe/Moscow

if [[ -f /opt/openclaw/.env ]]; then
  set -a
  source /opt/openclaw/.env
  set +a
fi

if [[ -f '${REMOTE_ENV_FILE}' ]]; then
  set -a
  source '${REMOTE_ENV_FILE}'
  set +a
fi

export BITRIX_APP_STATE_DIR=\"\${BITRIX_APP_STATE_DIR:-/opt/openclaw/state/bitrix_app}\"
export SALES_RUNTIME_ENV_FILE='${REMOTE_ENV_FILE}'
export SALES_LOG_FILE=\"\${SALES_LOG_FILE:-${sales_log_file}}\"
export REPORT_DIR=\"\${REPORT_DIR:-${LEGACY_REPORT_DIR}/reports}\"

cd \"\$ROOT_DIR\"
exec ./infra/orchestrator/workflows/sales_weekly_review.sh
SCRIPT

cat > '${STAGING_RELEASE_DIR}/run_sales_morning_report_check_from_runtime_env.sh' <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=\"\$(cd \"\$(dirname \"\${BASH_SOURCE[0]}\")\" && pwd)\"
export TZ=Europe/Moscow

if [[ -f /opt/openclaw/.env ]]; then
  set -a
  source /opt/openclaw/.env
  set +a
fi

if [[ -f '${REMOTE_ENV_FILE}' ]]; then
  set -a
  source '${REMOTE_ENV_FILE}'
  set +a
fi

export SALES_RUNTIME_ENV_FILE='${REMOTE_ENV_FILE}'
export SALES_LOG_FILE=\"\${SALES_LOG_FILE:-${sales_log_file}}\"
export REPORT_DIR=\"\${REPORT_DIR:-${LEGACY_REPORT_DIR}/reports}\"
export SALES_JOB_NAME=\"\${SALES_JOB_NAME:-morning_sales_dispatch}\"
export SALES_MORNING_ALERT=\"\${SALES_MORNING_ALERT:-1}\"

cd \"\$ROOT_DIR\"
exec ./infra/orchestrator/workflows/sales_morning_report_check.sh
SCRIPT

mkdir -p '${STAGING_RELEASE_DIR}/reports'
printf '%s\n' '${RELEASE_COMMIT}' > '${STAGING_RELEASE_DIR}/RELEASE_COMMIT'
printf '%s\n' '${RELEASE_BRANCH}' > '${STAGING_RELEASE_DIR}/RELEASE_BRANCH'
printf '%s\n' '${RELEASE_ID}' > '${STAGING_RELEASE_DIR}/RELEASE_ID'
printf '%s\n' '${RELEASED_AT_MSK}' > '${STAGING_RELEASE_DIR}/RELEASED_AT_MSK'
find '${STAGING_RELEASE_DIR}' -type f \\( -name '._*' -o -name '.DS_Store' \\) -delete
chmod +x '${STAGING_RELEASE_DIR}/run_sales_morning_report_from_runtime_env.sh'
chmod +x '${STAGING_RELEASE_DIR}/run_sales_focus_from_runtime_env.sh'
chmod +x '${STAGING_RELEASE_DIR}/run_sales_followup_from_runtime_env.sh'
chmod +x '${STAGING_RELEASE_DIR}/run_sales_weekly_review_from_runtime_env.sh'
chmod +x '${STAGING_RELEASE_DIR}/run_sales_morning_report_check_from_runtime_env.sh'
bash -n '${STAGING_RELEASE_DIR}/run_sales_morning_report_from_runtime_env.sh'
bash -n '${STAGING_RELEASE_DIR}/run_sales_focus_from_runtime_env.sh'
bash -n '${STAGING_RELEASE_DIR}/run_sales_followup_from_runtime_env.sh'
bash -n '${STAGING_RELEASE_DIR}/run_sales_weekly_review_from_runtime_env.sh'
bash -n '${STAGING_RELEASE_DIR}/run_sales_morning_report_check_from_runtime_env.sh'
python3 -m compileall -q '${STAGING_RELEASE_DIR}/agents' '${STAGING_RELEASE_DIR}/apps' '${STAGING_RELEASE_DIR}/cloudbot' '${STAGING_RELEASE_DIR}/shared'
rm -rf '${TARGET_RELEASE_DIR}'
mv '${STAGING_RELEASE_DIR}' '${TARGET_RELEASE_DIR}'
ln -sfn '${TARGET_RELEASE_DIR}' '${CURRENT_LINK}'
echo 'remote_runner=ok'
echo \"python=\$(python3 --version 2>&1)\"
echo \"current_release=\$(readlink -f '${CURRENT_LINK}')\"
"

  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
sudo -n tee '${REMOTE_ENV_FILE}' >/dev/null <<'ENV'
SALES_TELEGRAM_CHAT_ID=${SALES_TELEGRAM_CHAT_ID}
SALES_WEEKLY_TELEGRAM_CHAT_ID=${weekly_chat_id}
SALES_TELEGRAM_OWNER_ID=${sales_owner_chat_id}
SALES_TELEGRAM_DM_CHAT_ID=${sales_owner_chat_id}
SALES_ALERT_TELEGRAM_CHAT_ID=${SALES_TELEGRAM_CHAT_ID}
SALES_TELEGRAM_BOT_TOKEN_FILE=${sales_bot_token_file}
SALES_LOG_FILE=${sales_log_file}
SALES_DAILY_HISTORY_FILE=${sales_daily_history_file}
SALES_DEPARTMENT_IDS='${sales_department_ids}'
SALES_DEPARTMENT_NAMES='${sales_department_names}'
SALES_EXCLUDED_USER_IDS='${sales_excluded_user_ids}'
SALES_EXCLUDED_USER_NAMES='${sales_excluded_user_names}'
SALES_EXCLUDED_USER_MARKERS='${sales_excluded_user_markers}'
ENV
sudo -n chmod 640 '${REMOTE_ENV_FILE}'

sudo -n tee '${SYSTEM_DAILY_RUNNER_PATH}' >/dev/null <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow
cd '${CURRENT_LINK}'
exec ./run_sales_morning_report_from_runtime_env.sh \"\$@\"
SCRIPT
sudo -n chmod 755 '${SYSTEM_DAILY_RUNNER_PATH}'
sudo -n bash -n '${SYSTEM_DAILY_RUNNER_PATH}'

sudo -n tee '${SYSTEM_FOLLOWUP_RUNNER_PATH}' >/dev/null <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow
cd '${CURRENT_LINK}'
exec ./run_sales_followup_from_runtime_env.sh \"\$@\"
SCRIPT
sudo -n chmod 755 '${SYSTEM_FOLLOWUP_RUNNER_PATH}'
sudo -n bash -n '${SYSTEM_FOLLOWUP_RUNNER_PATH}'

sudo -n tee '${SYSTEM_WEEKLY_RUNNER_PATH}' >/dev/null <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow
cd '${CURRENT_LINK}'
exec ./run_sales_weekly_review_from_runtime_env.sh \"\$@\"
SCRIPT
sudo -n chmod 755 '${SYSTEM_WEEKLY_RUNNER_PATH}'
sudo -n bash -n '${SYSTEM_WEEKLY_RUNNER_PATH}'

sudo -n tee '${SYSTEM_CHECK_RUNNER_PATH}' >/dev/null <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow
cd '${CURRENT_LINK}'
exec ./run_sales_morning_report_check_from_runtime_env.sh \"\$@\"
SCRIPT
sudo -n chmod 755 '${SYSTEM_CHECK_RUNNER_PATH}'
sudo -n bash -n '${SYSTEM_CHECK_RUNNER_PATH}'

sudo -n tee '${CRON_FILE_PATH}' >/dev/null <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# В production Debian cron исполняет /etc/cron.d по системному UTC и здесь не дал
# нужного SLA через CRON_TZ=Europe/Moscow, поэтому фиксируем UTC-выражения явно.
# 09:30 МСК = 06:30 UTC
${DAILY_CRON_EXPR_UTC} root ${SYSTEM_DAILY_RUNNER_PATH} >> ${LEGACY_REPORT_DIR}/reports/sales_daily_cron.log 2>&1
# 09:40 МСК = 06:40 UTC
${CHECK_CRON_EXPR_UTC} root ${SYSTEM_CHECK_RUNNER_PATH} >> ${LEGACY_REPORT_DIR}/reports/sales_morning_check_cron.log 2>&1
# 17:00 МСК = 14:00 UTC
${FOLLOWUP_CRON_EXPR_UTC} root ${SYSTEM_FOLLOWUP_RUNNER_PATH} >> ${LEGACY_REPORT_DIR}/reports/sales_followup_cron.log 2>&1
# 18:30 МСК = 15:30 UTC
${WEEKLY_CRON_EXPR_UTC} root ${SYSTEM_WEEKLY_RUNNER_PATH} >> ${LEGACY_REPORT_DIR}/reports/sales_weekly_cron.log 2>&1
CRON
sudo -n chmod 644 '${CRON_FILE_PATH}'
echo 'system_runner=ok'
echo 'cron=ok'
"
} | tee "$REPORT_FILE"

release_remote_lock "$PRIMARY_HOST" "$REMOTE_LOCK_PATH"
LOCK_HELD=0
trap - EXIT

log "sales_agent_deploy: успешно, отчет=${REPORT_FILE}"
