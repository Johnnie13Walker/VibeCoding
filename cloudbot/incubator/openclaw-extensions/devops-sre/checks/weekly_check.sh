#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"

SERVICES="nginx docker postgresql redis-server"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --services)
      SERVICES="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

STAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
TEXT_REPORT="$LOG_DIR/weekly-$STAMP.txt"
HEALTH_REPORT="$LOG_DIR/health-$(hostname)-$STAMP.json"

{
  echo "== WEEKLY AUDIT ($(date -u +"%Y-%m-%dT%H:%M:%SZ")) =="
  echo "Host: $(hostname)"
  echo
  echo "[1] Uptime and load"
  uptime || true
  echo
  echo "[2] Top CPU processes"
  if ps aux >/dev/null 2>&1; then
    ps aux | awk 'NR==1 || NR<=15 {print}'
  else
    echo "SKIP: ps not permitted in current environment"
  fi
  echo
  echo "[3] Top memory processes"
  if ps aux >/dev/null 2>&1; then
    ps aux --sort=-%mem | awk 'NR==1 || NR<=15 {print}'
  else
    echo "SKIP: ps not permitted in current environment"
  fi
  echo
  echo "[4] Open ports"
  if command -v ss >/dev/null 2>&1; then
    ss -tuln 2>/dev/null || echo "SKIP: ss not permitted in current environment"
  elif command -v netstat >/dev/null 2>&1; then
    netstat -tuln 2>/dev/null || echo "SKIP: netstat not permitted in current environment"
  else
    echo "SKIP: ss/netstat not available"
  fi
  echo
  echo "[5] SSL certificates (if nginx exists)"
  if command -v nginx >/dev/null 2>&1; then
    nginx -t || true
  else
    echo "SKIP: nginx not installed"
  fi
  echo
  echo "[6] Service status snapshot"
  if command -v systemctl >/dev/null 2>&1; then
    for svc in $SERVICES; do
      echo "$svc: $(systemctl is-active "$svc" 2>/dev/null || true)"
    done
  else
    echo "SKIP: systemctl not available"
  fi
} >"$TEXT_REPORT"

"$BASE_DIR/checks/health_check.sh" --services "$SERVICES" --output "$HEALTH_REPORT"
echo "Weekly report: $TEXT_REPORT"

MSG="Weekly audit OK
Host: $(hostname)
UTC: $(date -u +"%Y-%m-%d %H:%M:%S")
Services: $SERVICES
Report: $TEXT_REPORT
Health: $HEALTH_REPORT"

bash "$BASE_DIR/scripts/notify_telegram.sh" "$MSG"
