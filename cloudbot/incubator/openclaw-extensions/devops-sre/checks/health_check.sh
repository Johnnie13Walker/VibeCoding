#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/logs"
mkdir -p "$OUT_DIR"

SERVICES="nginx docker"
OUTPUT_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --services)
      SERVICES="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT_FILE="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
host="$(hostname)"

if [[ -z "${OUTPUT_FILE}" ]]; then
  OUTPUT_FILE="$OUT_DIR/health-${host}-$(date -u +"%Y%m%dT%H%M%SZ").json"
fi

check_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1
}

disk_root="$(df -h / | awk 'NR==2{print $5}')"
load_avg="$(uptime | awk -F'load averages?: ' '{print $2}' | tr -d ' ')"
mem_summary="n/a"
if check_cmd free; then
  mem_summary="$(free -h | awk 'NR==2{print $3 "/" $2}')"
elif check_cmd vm_stat; then
  mem_summary="vm_stat_available"
fi

services_json=""
for svc in $SERVICES; do
  status="unknown"
  detail=""
  if check_cmd systemctl; then
    if systemctl is-active --quiet "$svc"; then
      status="active"
      detail="running"
    else
      status="inactive"
      detail="$(systemctl is-active "$svc" 2>/dev/null || true)"
    fi
  elif check_cmd docker && [[ "$svc" == "docker" ]]; then
    if docker info >/dev/null 2>&1; then
      status="active"
      detail="docker daemon reachable"
    else
      status="inactive"
      detail="docker daemon not reachable"
    fi
  else
    status="skipped"
    detail="systemctl not available"
  fi

  if [[ -n "$services_json" ]]; then
    services_json+=","
  fi
  services_json+="{\"name\":\"${svc}\",\"status\":\"${status}\",\"detail\":\"${detail}\"}"
done

cat >"$OUTPUT_FILE" <<JSON
{
  "timestamp_utc": "$ts",
  "host": "$host",
  "disk_root_used": "$disk_root",
  "memory": "$mem_summary",
  "load_avg": "$load_avg",
  "services": [$services_json]
}
JSON

echo "Health report: $OUTPUT_FILE"

