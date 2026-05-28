#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICES="nginx docker"

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

echo "[1/3] health_check"
bash "$BASE_DIR/checks/health_check.sh" --services "$SERVICES"
echo "[2/3] daily_check"
bash "$BASE_DIR/checks/daily_check.sh" --services "$SERVICES"
echo "[3/3] weekly_check"
bash "$BASE_DIR/checks/weekly_check.sh" --services "$SERVICES"
echo "All checks completed."

