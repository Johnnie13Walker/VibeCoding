#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"
load_schedule_contract "$ROOT_DIR"

require_env PRIMARY_HOST SSH_USER SSH_KEY_PATH SSH_PORT

LEGACY_REPORT_DIR="${LARISA_REMOTE_DIR:-/home/ops/cloudbot-larisa-agent}"
SYSTEM_RUNNER_PATH="${LARISA_SYSTEM_RUNNER_PATH:-/usr/local/bin/cloudbot-larisa-daily-brief.sh}"
CRON_FILE_PATH="${LARISA_CRON_FILE_PATH:-/etc/cron.d/cloudbot-larisa-daily-brief}"
RUNTIME_ROOT="${LARISA_RUNTIME_ROOT:-${CLOUDBOT_RUNTIME_ROOT:-/opt/cloudbot-runtime/larisa}}"
CURRENT_LINK="${LARISA_RUNTIME_CURRENT_LINK:-${CLOUDBOT_RUNTIME_CURRENT_LINK:-$RUNTIME_ROOT/current}}"
REMOTE_LOCK_PATH="${LARISA_RUNTIME_LOCK_PATH:-${CLOUDBOT_RUNTIME_LOCK_PATH:-$RUNTIME_ROOT/.deploy.lock}}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/larisa_agent_deploy_${STAMP}.txt"
RELEASE_BRANCH="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD)"
RELEASE_COMMIT="$(git -C "$ROOT_DIR" rev-parse HEAD)"
RELEASE_SHA_SHORT="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"
RELEASE_BRANCH_SLUG="$(printf '%s' "$RELEASE_BRANCH" | LC_ALL=C tr -c 'A-Za-z0-9._-' '_')"
RELEASE_ID="${RELEASE_BRANCH_SLUG}_${RELEASE_SHA_SHORT}"
STAGING_RELEASE_DIR="$RUNTIME_ROOT/releases/.${RELEASE_ID}.staging"
TARGET_RELEASE_DIR="$RUNTIME_ROOT/releases/${RELEASE_ID}"
RELEASED_AT_MSK="$(date '+%F %T %Z')"
LOCK_OWNER="larisa_agent_deploy:${RELEASE_ID}:$(hostname):$$"
LOCK_HELD=0
LARISA_DAILY_CRON_EXPR="${LARISA_DAILY_CRON_EXPR:-${LARISA_DAILY_CRON_EXPR_UTC:-0 5 * * *}}"

mkdir -p "$REPORT_DIR"
require_clean_release_checkout "$ROOT_DIR"
require_release_on_origin "$ROOT_DIR" "$RELEASE_BRANCH" "$RELEASE_COMMIT"

FILES_TO_SYNC=()
while IFS= read -r path; do
  FILES_TO_SYNC+=("$path")
done < <(cloudbot_runtime_files)

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

log "larisa_agent_deploy: старт (host=${PRIMARY_HOST}, runtime_root=${RUNTIME_ROOT}, release_id=${RELEASE_ID})"

{
  echo "# Larisa Agent Deploy"
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
  echo "Daily runner: ${SYSTEM_RUNNER_PATH}"
  echo
  echo "Файлы:"
  printf -- "- %s\n" "${FILES_TO_SYNC[@]}"
  echo

  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
mkdir -p '${LEGACY_REPORT_DIR}' '${LEGACY_REPORT_DIR}/reports' '${RUNTIME_ROOT}/releases'
rm -rf '${STAGING_RELEASE_DIR}'
mkdir -p '${STAGING_RELEASE_DIR}'
"

  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "[DRY-RUN] tar sync -> ${PRIMARY_HOST}:${STAGING_RELEASE_DIR}"
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
cat > '${STAGING_RELEASE_DIR}/run_larisa_daily_brief_from_runtime_env.sh' <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=\"\$(cd \"\$(dirname \"\${BASH_SOURCE[0]}\")\" && pwd)\"
export TZ=Europe/Moscow

if [[ -f /etc/openclaw/larisa.env ]]; then
  set -a
  source /etc/openclaw/larisa.env
  set +a
fi

if [[ -f /opt/openclaw/.env ]]; then
  set -a
  source /opt/openclaw/.env
  set +a
fi

if [[ -f /etc/openclaw/whoop.env ]]; then
  set -a
  source /etc/openclaw/whoop.env
  set +a
fi

export BITRIX_APP_STATE_DIR=\"\${BITRIX_APP_STATE_DIR:-/opt/openclaw/state/bitrix_app}\"

if [[ -z \"\${LARISA_TELEGRAM_BOT_TOKEN:-}\" && -n \"\${TELEGRAM_BOT_TOKEN:-}\" ]]; then
  export LARISA_TELEGRAM_BOT_TOKEN=\"\${TELEGRAM_BOT_TOKEN}\"
fi

if [[ -z \"\${LARISA_TELEGRAM_CHAT_ID:-}\" && -n \"\${TELEGRAM_CHAT_ID:-}\" ]]; then
  export LARISA_TELEGRAM_CHAT_ID=\"\${TELEGRAM_CHAT_ID}\"
fi

cd \"\$ROOT_DIR\"
exec ./infra/orchestrator/workflows/larisa_daily_brief.sh \"\$@\"
SCRIPT
mkdir -p '${STAGING_RELEASE_DIR}/reports'
printf '%s\n' '${RELEASE_COMMIT}' > '${STAGING_RELEASE_DIR}/RELEASE_COMMIT'
printf '%s\n' '${RELEASE_BRANCH}' > '${STAGING_RELEASE_DIR}/RELEASE_BRANCH'
printf '%s\n' '${RELEASE_ID}' > '${STAGING_RELEASE_DIR}/RELEASE_ID'
printf '%s\n' '${RELEASED_AT_MSK}' > '${STAGING_RELEASE_DIR}/RELEASED_AT_MSK'
find '${STAGING_RELEASE_DIR}' -type f \\( -name '._*' -o -name '.DS_Store' \\) -delete
chmod +x '${STAGING_RELEASE_DIR}/run_larisa_daily_brief_from_runtime_env.sh'
bash -n '${STAGING_RELEASE_DIR}/run_larisa_daily_brief_from_runtime_env.sh'
python3 -m compileall -q '${STAGING_RELEASE_DIR}/agents' '${STAGING_RELEASE_DIR}/apps' '${STAGING_RELEASE_DIR}/cloudbot' '${STAGING_RELEASE_DIR}/shared'
rm -rf '${TARGET_RELEASE_DIR}'
mv '${STAGING_RELEASE_DIR}' '${TARGET_RELEASE_DIR}'
ln -sfn '${TARGET_RELEASE_DIR}' '${CURRENT_LINK}'
echo 'remote_runner=ok'
echo \"python=\$(python3 --version 2>&1)\"
echo \"node=\$(node --version 2>&1)\"
echo \"current_release=\$(readlink -f '${CURRENT_LINK}')\"
"

  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
sudo -n tee '${SYSTEM_RUNNER_PATH}' >/dev/null <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow
cd '${CURRENT_LINK}'
exec ./run_larisa_daily_brief_from_runtime_env.sh \"\$@\"
SCRIPT
sudo -n chmod 755 '${SYSTEM_RUNNER_PATH}'
sudo -n bash -n '${SYSTEM_RUNNER_PATH}'
sudo -n rm -f '/usr/local/bin/cloudbot-larisa-evening-review.sh'

sudo -n tee '${CRON_FILE_PATH}' >/dev/null <<'CRON'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# Production Debian cron исполняет /etc/cron.d по системному UTC.
# 08:00 МСК = 05:00 UTC.
${LARISA_DAILY_CRON_EXPR} root ${SYSTEM_RUNNER_PATH} >> ${LEGACY_REPORT_DIR}/reports/larisa_daily_brief_cron.log 2>&1
CRON
sudo -n chmod 644 '${CRON_FILE_PATH}'
echo 'system_runner=ok'
echo 'cron=ok'
"
} | tee "$REPORT_FILE"

release_remote_lock "$PRIMARY_HOST" "$REMOTE_LOCK_PATH"
LOCK_HELD=0
trap - EXIT

log "larisa_agent_deploy: успешно, отчет=${REPORT_FILE}"
