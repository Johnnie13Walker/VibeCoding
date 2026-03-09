#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/happ-vpn.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

: "${TZ:=Europe/Moscow}"
export TZ

mkdir -p "${HEALTH_REPORT_DIR:-$ROOT_DIR/reports}"
report_file="${HEALTH_REPORT_DIR:-$ROOT_DIR/reports}/happ_vpn_morning_$(date '+%Y%m%d_%H%M%S_MSK').txt"

status="ОК"
if ! bash "$ROOT_DIR/checks/vpn_verify.sh" >/tmp/happ_vpn_last_verify.log 2>&1; then
  status="есть проблемы"
fi

{
  echo "Дата: $(date '+%F %T %Z')"
  echo "Статус: $status"
  if [[ "$status" != "ОК" ]]; then
    echo "Детали:"
    sed -n '1,120p' /tmp/happ_vpn_last_verify.log
  fi
} >"$report_file"

echo "Сформирован утренний health-отчет: $report_file"
