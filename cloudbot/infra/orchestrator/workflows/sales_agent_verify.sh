#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

require_env PRIMARY_HOST SSH_USER SSH_KEY_PATH SSH_PORT

MODE="${1:-daily}"
RUNTIME_ROOT="${CLOUDBOT_RUNTIME_ROOT:-/opt/cloudbot-runtime}"
CURRENT_LINK="${CLOUDBOT_RUNTIME_CURRENT_LINK:-$RUNTIME_ROOT/current}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/sales_agent_verify_${MODE}_${STAMP}.txt"

mkdir -p "$REPORT_DIR"

case "$MODE" in
  daily)
    remote_command="sudo ${SALES_AGENT_SYSTEM_RUNNER_PATH:-/usr/local/bin/cloudbot-sales-daily-brief.sh}"
    ;;
  focus)
    remote_command="cd '${CURRENT_LINK}' && ./run_sales_focus_from_runtime_env.sh"
    ;;
  followup)
    remote_command="sudo ${SALES_AGENT_FOLLOWUP_RUNNER_PATH:-/usr/local/bin/cloudbot-sales-followup.sh}"
    ;;
  weekly)
    remote_command="sudo ${SALES_AGENT_WEEKLY_RUNNER_PATH:-/usr/local/bin/cloudbot-sales-weekly-review.sh}"
    ;;
  check)
    remote_command="sudo ${SALES_AGENT_CHECK_RUNNER_PATH:-/usr/local/bin/cloudbot-sales-morning-check.sh}"
    ;;
  *)
    fail "Неизвестный режим verify: ${MODE} (доступно: daily, focus, followup, weekly, check)"
    ;;
esac

log "sales_agent_verify: старт (mode=${MODE}, host=${PRIMARY_HOST})"

{
  echo "# Sales Agent Verify"
  echo "Время: $(date '+%F %T %Z')"
  echo "Хост: ${PRIMARY_HOST}"
  echo "Режим: ${MODE}"
  echo
  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
${remote_command}
echo '--- sales_agent.log tail ---'
tail -n 20 /home/ops/cloudbot-sales-agent/reports/sales_agent.log 2>/dev/null || true
"
} | tee "$REPORT_FILE"

log "sales_agent_verify: успешно, отчет=${REPORT_FILE}"
