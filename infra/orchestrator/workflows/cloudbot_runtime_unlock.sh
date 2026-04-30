#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

TARGET_HOST="${LARISA_RUNTIME_HOST:-${CLOUDBOT_RUNTIME_HOST:-${PRIMARY_HOST:-}}}"
LOCK_PATH="${LARISA_RUNTIME_LOCK_PATH:-${CLOUDBOT_RUNTIME_LOCK_PATH:-/opt/cloudbot-runtime/larisa/.deploy.lock}}"
MODE="${1:-inspect}"
FORCE_FLAG="${2:-}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/cloudbot_runtime_unlock_${STAMP}.txt"

require_env TARGET_HOST SSH_USER SSH_KEY_PATH SSH_PORT
mkdir -p "$REPORT_DIR"

case "$MODE" in
  inspect|release) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, release)"
    ;;
esac

if [[ "$MODE" == "release" ]] && [[ "${ALLOW_LOCK_RELEASE:-0}" != "1" ]] && [[ "$FORCE_FLAG" != "--force" ]]; then
  fail "Для release нужен явный флаг --force или ALLOW_LOCK_RELEASE=1."
fi

printf -v lock_q '%q' "$LOCK_PATH"

{
  echo "# Cloudbot Runtime Lock"
  echo "Время: $(date '+%F %T %Z')"
  echo "Хост: ${TARGET_HOST}"
  echo "Lock path: ${LOCK_PATH}"
  echo "Режим: ${MODE}"
  echo

  if [[ "$MODE" == "inspect" ]]; then
    run_remote_script "$TARGET_HOST" "
set -euo pipefail
lock_path=${lock_q}
echo \"host=\$(hostname -f 2>/dev/null || hostname)\"
if [[ ! -e \"\$lock_path\" ]]; then
  echo 'lock=absent'
  exit 0
fi
echo 'lock=present'
if [[ -f \"\$lock_path/owner\" ]]; then
  echo \"owner=\$(cat \"\$lock_path/owner\")\"
fi
if [[ -f \"\$lock_path/acquired_at\" ]]; then
  echo \"acquired_at=\$(cat \"\$lock_path/acquired_at\")\"
fi
ls -la \"\$lock_path\"
"
  else
    run_remote_script "$TARGET_HOST" "
set -euo pipefail
lock_path=${lock_q}
echo \"host=\$(hostname -f 2>/dev/null || hostname)\"
if [[ ! -e \"\$lock_path\" ]]; then
  echo 'lock=absent'
  exit 0
fi
if [[ -f \"\$lock_path/owner\" ]]; then
  echo \"owner=\$(cat \"\$lock_path/owner\")\"
fi
if [[ -f \"\$lock_path/acquired_at\" ]]; then
  echo \"acquired_at=\$(cat \"\$lock_path/acquired_at\")\"
fi
rm -rf \"\$lock_path\"
echo 'lock=released'
"
  fi
} | tee "$REPORT_FILE"

log "cloudbot_runtime_unlock: отчет=${REPORT_FILE}"
