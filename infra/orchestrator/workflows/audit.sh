#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

require_env PRIMARY_HOST HEALTH_REPORT_DIR

mkdir -p "$ROOT_DIR/${HEALTH_REPORT_DIR}"
OUT_FILE="$ROOT_DIR/${HEALTH_REPORT_DIR}/vpn_audit_$(date '+%Y%m%d_%H%M%S_MSK').txt"

collect_host_audit() {
  local host="$1"
  local label="$2"

  log "Аудит узла ${label} (${host})"

  run_remote_script "$host" "
set -euo pipefail
export TZ=Europe/Moscow
echo '---'
echo \"Узел: ${label}\"
echo \"Время: \$(date '+%F %T %Z')\"
source /etc/os-release 2>/dev/null || true
echo \"OS: \${PRETTY_NAME:-unknown}\"
echo \"Kernel: \$(uname -r)\"
echo 'CPU/RAM:'
free -h || true
nproc || true
echo 'Disk:'
df -h / || true
echo 'Открытые порты:'
ss -tuln || true
echo 'Сервисы VPN/subscription:'
systemctl --no-pager --type=service | grep -E 'sing-box|xray|happ-subscription|nginx' || true
echo 'Firewall:'
(ufw status || true) 2>/dev/null
echo 'DNS:'
(getent hosts ${HAPP_DOMAIN:-localhost} || true)
"
}

{
  echo "# Аудит Happ VPN"
  echo "Дата: $(date '+%F %T %Z')"
  echo
  collect_host_audit "$PRIMARY_HOST" "primary"
  if [[ -n "${RESERVE_HOST:-}" ]]; then
    collect_host_audit "$RESERVE_HOST" "reserve"
  fi
} | tee "$OUT_FILE"

log "Аудит завершен: $OUT_FILE"
