#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKFLOW_DIR="$ROOT_DIR/infra/orchestrator/workflows"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/happ-vpn.env}"

if [[ $# -lt 1 ]]; then
  echo "Использование: $0 <audit|deploy|verify|rollback|security_profile|security_updates|openclaw_update|openclaw_update_permissions|openclaw_privileged_exec|openclaw_gateway_repair|openclaw_healthcheck_schedule|daily_ops|next_week_prep|context_snapshot|friction_scan|weekly_focus_review|high_leverage_24h|session_handoff|instruction_conflicts|post_change_verify|ops_intelligence|whoop_morning_report_check>"
  exit 1
fi

WORKFLOW_NAME="$1"
WORKFLOW_SCRIPT="$WORKFLOW_DIR/${WORKFLOW_NAME}.sh"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

: "${TZ:=Europe/Moscow}"
export TZ

if [[ ! -x "$WORKFLOW_SCRIPT" ]]; then
  echo "Workflow не найден или не исполняемый: $WORKFLOW_SCRIPT"
  exit 1
fi

exec "$WORKFLOW_SCRIPT" "${@:2}"
