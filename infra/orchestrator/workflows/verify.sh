#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

log "Запуск комплексной проверки Happ VPN"
run_cmd "bash \"$ROOT_DIR/checks/vpn_verify.sh\""
run_cmd "bash \"$ROOT_DIR/checks/vpn_smoke_happ.sh\""
run_cmd "bash \"$ROOT_DIR/checks/morning_health_report.sh\""
log "Verify workflow завершен"
