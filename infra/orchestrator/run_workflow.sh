#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKFLOW_DIR="$ROOT_DIR/infra/orchestrator/workflows"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/remote-ops.env}"

if [[ $# -lt 1 ]]; then
  echo "Использование: $0 <security_profile|security_updates|openclaw_update|openclaw_update_permissions|openclaw_privileged_exec|openclaw_gateway_repair|openclaw_healthcheck_schedule|todo_digest_schedule|openclaw_backup_schedule|openclaw_local_schedule|daily_ops|next_week_prep|context_snapshot|friction_scan|weekly_focus_review|high_leverage_24h|session_handoff|instruction_conflicts|post_change_verify|ops_intelligence|whoop_morning_report_check|whoop_report_repair|sales_brief|sales_morning_report|sales_morning_report_check|sales_agent_deploy|sales_agent_verify|bitrix_check|bitrix_task_load_review|bitrix_sync_deal_contacts|bitrix_bizproc_sync_contacts|bitrix_app_server_deploy|bitrix_sales_enrichment_candidates|bitrix_sales_data_quality_report|bitrix_deal_enrichment_inspect|bitrix_deal_company_enrich|bitrix_fill_rusprofile_link|bitrix_fill_deal_client_fields|bitrix_merge_company_duplicate|bitrix_link_deal_existing_company|larisa_daily_brief|larisa_evening_review|larisa_content_topics|larisa_agent_deploy|larisa_send_note|cloudbot_runtime_unlock|cloudbot_runtime_rollback|cloudbot_runtime_verify>"
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
