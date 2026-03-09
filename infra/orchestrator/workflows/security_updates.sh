#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

OPENCLAW_HOST="${OPENCLAW_HOST:-${PRIMARY_HOST:-}}"
MODE="${1:-inspect}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"

require_env OPENCLAW_HOST SSH_USER SSH_KEY_PATH SSH_PORT

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/security_updates_${STAMP}.txt"
mode_b64="$(printf '%s' "$MODE" | base64 | tr -d '\n')"

remote_script=$(cat <<REMOTE
set -euo pipefail
export TZ=Europe/Moscow

mode="\$(printf '%s' '${mode_b64}' | base64 -d)"

if ! command -v apt >/dev/null 2>&1; then
  echo "ОШИБКА: apt не найден на удаленном хосте" >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "ОШИБКА: apt-get не найден на удаленном хосте" >&2
  exit 1
fi

echo "host=\$(hostname -f 2>/dev/null || hostname)"
echo "time=\$(date '+%F %T %Z')"
echo "mode=\${mode}"
echo "--- upgradable_before ---"
apt list --upgradable 2>/dev/null || true

mapfile -t security_pkgs_before < <(apt list --upgradable 2>/dev/null | awk -F/ 'NR>1 && tolower(\$0) ~ /security/ {print \$1}' | sort -u)
before_count="\${#security_pkgs_before[@]}"
echo "security_count_before=\${before_count}"
if [ "\$before_count" -gt 0 ]; then
  echo "security_packages_before=\${security_pkgs_before[*]}"
fi

if [ "\$mode" = "apply" ] && [ "\$before_count" -gt 0 ]; then
  export DEBIAN_FRONTEND=noninteractive
  echo "apply_action=apt-get install --only-upgrade --allow-change-held-packages"
  apt-get install -y --only-upgrade --allow-change-held-packages "\${security_pkgs_before[@]}"
fi

echo "--- upgradable_after ---"
apt list --upgradable 2>/dev/null || true

mapfile -t security_pkgs_after < <(apt list --upgradable 2>/dev/null | awk -F/ 'NR>1 && tolower(\$0) ~ /security/ {print \$1}' | sort -u)
after_count="\${#security_pkgs_after[@]}"
echo "security_count_after=\${after_count}"
if [ "\$after_count" -gt 0 ]; then
  echo "security_packages_after=\${security_pkgs_after[*]}"
fi

if [ "\$mode" = "apply" ] && [ "\$after_count" -gt 0 ]; then
  echo "ОШИБКА: после применения security-обновлений остались пакеты: \${security_pkgs_after[*]}" >&2
  exit 1
fi
REMOTE
)

log "Запуск workflow security_updates: mode=${MODE}, host=${OPENCLAW_HOST}"
{
  echo "# Security Updates"
  echo "Время: $(date '+%F %T %Z')"
  echo "Хост: ${OPENCLAW_HOST}"
  echo "Режим: ${MODE}"
  echo
  run_remote_script "$OPENCLAW_HOST" "$remote_script"
} | tee "$REPORT_FILE"

log "Workflow security_updates завершён"
log "Отчет: ${REPORT_FILE}"
