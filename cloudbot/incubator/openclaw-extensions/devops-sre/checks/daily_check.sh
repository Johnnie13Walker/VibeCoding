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
TEXT_REPORT="$LOG_DIR/daily-$STAMP.txt"
HEALTH_REPORT="$LOG_DIR/health-$(hostname)-$STAMP.json"

{
  echo "== DAILY CHECK ($(date -u +"%Y-%m-%dT%H:%M:%SZ")) =="
  echo "Host: $(hostname)"
  echo
  echo "[1] Service status"
  if command -v systemctl >/dev/null 2>&1; then
    for svc in $SERVICES; do
      if systemctl is-active --quiet "$svc"; then
        echo "OK: $svc active"
      else
        echo "FAIL: $svc inactive ($(systemctl is-active "$svc" 2>/dev/null || true))"
      fi
    done
  else
    echo "SKIP: systemctl not available"
  fi
  echo
  echo "[2] Disk usage"
  df -h /
  echo
  echo "[3] Memory"
  if command -v free >/dev/null 2>&1; then
    free -h
  else
    vm_stat | head -n 15
  fi
  echo
  echo "[4] Last critical log lines"
  if command -v journalctl >/dev/null 2>&1; then
    journalctl -p 3 -n 50 --no-pager || true
  else
    echo "SKIP: journalctl not available"
  fi
} >"$TEXT_REPORT"

"$BASE_DIR/checks/health_check.sh" --services "$SERVICES" --output "$HEALTH_REPORT"
echo "Daily report: $TEXT_REPORT"

MSG="Daily check OK
Host: $(hostname)
UTC: $(date -u +"%Y-%m-%d %H:%M:%S")
Services: $SERVICES
Report: $TEXT_REPORT
Health: $HEALTH_REPORT"

bash "$BASE_DIR/scripts/notify_telegram.sh" "$MSG"
