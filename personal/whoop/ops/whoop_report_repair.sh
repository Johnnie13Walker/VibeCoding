#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

WHOOP_HOST="${WHOOP_HOST:-${PRIMARY_HOST:-}}"
MODE="${1:-full}"

require_env WHOOP_HOST SSH_USER SSH_KEY_PATH SSH_PORT

run_apply() {
  log "Применение фикса WHOOP report на ${WHOOP_HOST}"
  run_remote_script "$WHOOP_HOST" "$(cat <<'REMOTE'
set -euo pipefail
export TZ=Europe/Moscow

env_file="/etc/openclaw/whoop.env"
script_file="/usr/local/bin/send_whoop_report.py"
stamp="$(date "+%Y%m%d_%H%M%S_%Z")"

[ -f "$env_file" ] || { echo "ОШИБКА: env не найден: $env_file" >&2; exit 1; }
[ -f "$script_file" ] || { echo "ОШИБКА: script не найден: $script_file" >&2; exit 1; }

cp -a "$env_file" "${env_file}.bak-${stamp}"
cp -a "$script_file" "${script_file}.bak-${stamp}"

if grep -q "^LOOKBACK_DAYS=" "$env_file"; then
  sed -i "s/^LOOKBACK_DAYS=.*/LOOKBACK_DAYS=0/" "$env_file"
else
  printf "\nLOOKBACK_DAYS=0\n" >>"$env_file"
fi

if grep -q "^ACTIVITY_LOOKBACK_DAYS=" "$env_file"; then
  sed -i "s/^ACTIVITY_LOOKBACK_DAYS=.*/ACTIVITY_LOOKBACK_DAYS=0/" "$env_file"
else
  printf "ACTIVITY_LOOKBACK_DAYS=0\n" >>"$env_file"
fi

python3 -c 'from pathlib import Path; import sys; path = Path(sys.argv[1]); text = path.read_text(encoding="utf-8"); old = "lookback_raw = to_int(env(\"LOOKBACK_DAYS\", \"1\"))\n    lookback_days = 1 if lookback_raw is None else max(0, lookback_raw)"; new = "lookback_raw = to_int(env(\"LOOKBACK_DAYS\", \"0\"))\n    lookback_days = 0 if lookback_raw is None else max(0, lookback_raw)"; \
import sys as _sys; \
(_sys.exit("ОШИБКА: не найден ожидаемый блок LOOKBACK_DAYS в send_whoop_report.py") if old not in text else None); \
path.write_text(text.replace(old, new, 1), encoding="utf-8")' "$script_file"

echo "--- whoop.env ---"
grep -n "REPORT_TIMEZONE\|LOOKBACK_DAYS\|ACTIVITY_LOOKBACK_DAYS" "$env_file" || true
echo "--- send_whoop_report.py ---"
grep -n "LOOKBACK_DAYS\|lookback_days =\|ACTIVITY_LOOKBACK_DAYS" "$script_file" || true
REMOTE
)"
}

run_smoke() {
  log "Smoke-проверка WHOOP report на ${WHOOP_HOST}"
  run_remote_script "$WHOOP_HOST" "$(cat <<'REMOTE'
set -euo pipefail
export TZ=Europe/Moscow

env_file="/etc/openclaw/whoop.env"
script_file="/usr/local/bin/send_whoop_report.py"

echo "--- whoop.env ---"
grep -n "REPORT_TIMEZONE\|LOOKBACK_DAYS\|ACTIVITY_LOOKBACK_DAYS" "$env_file" || true
echo "--- send_whoop_report.py ---"
grep -n "LOOKBACK_DAYS\|lookback_days =\|ACTIVITY_LOOKBACK_DAYS" "$script_file" || true
echo "--- dry-run ---"
/usr/bin/env WHOOP_ENV_FILE="$env_file" "$script_file" send-report --dry-run --force | sed -n "1,80p"
REMOTE
)"
}

case "$MODE" in
  apply)
    run_apply
    ;;
  smoke)
    run_smoke
    ;;
  full)
    run_apply
    run_smoke
    ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: apply, smoke, full)"
    ;;
esac
