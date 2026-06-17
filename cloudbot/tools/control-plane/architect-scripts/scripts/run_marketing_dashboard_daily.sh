#!/usr/bin/env bash
set -u -o pipefail

export TZ=Europe/Moscow

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${MARKETING_DASHBOARD_ROOT_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
ENGINEER_ENV="${MARKETING_DASHBOARD_ENGINEER_ENV:-/Users/pro2kuror/Desktop/Cloudbot/engineer/.env.integrations}"
TMP_DIR="${ROOT_DIR}/tmp"
STATUS_FILE="${TMP_DIR}/marketing_dashboard_daily_status.json"
LATEST_LOG="${TMP_DIR}/marketing_dashboard_daily_latest.log"
VERIFY_JSON="${TMP_DIR}/marketing_dashboard_daily_verify.json"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
RUN_LOG="${TMP_DIR}/marketing_dashboard_daily_${STAMP}.log"
STARTED_AT="$(date '+%Y-%m-%d %H:%M:%S %Z')"

mkdir -p "$TMP_DIR"
: >"$RUN_LOG"
ln -sf "$RUN_LOG" "$LATEST_LOG"

if [[ -f "$ENGINEER_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENGINEER_ENV"
  set +a
fi

: "${BITRIX_TIMEOUT_SEC:=90}"
export BITRIX_TIMEOUT_SEC

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*" | tee -a "$RUN_LOG"
}

write_status() {
  local run_status="$1"
  local failed_step="${2:-}"
  local exit_code="${3:-0}"
  local ended_at
  ended_at="$(date '+%Y-%m-%d %H:%M:%S %Z')"

  python3 - "$STATUS_FILE" "$run_status" "$STARTED_AT" "$ended_at" "$RUN_LOG" "$failed_step" "$exit_code" "$VERIFY_JSON" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

status_file, status, started_at, ended_at, log_path, failed_step, exit_code, verify_path = sys.argv[1:]
payload = {
    "status": status,
    "started_at": started_at,
    "ended_at": ended_at,
    "timezone": "Europe/Moscow",
    "log_path": log_path,
    "failed_step": failed_step,
    "exit_code": int(exit_code),
    "dashboard_url": "https://docs.google.com/spreadsheets/d/11LWdg8HGOHyDh3QlEEJlD4yfrMTVkUAzEdVxnyvfRZM/edit",
}

verify_file = Path(verify_path)
if verify_file.exists():
    try:
        payload["verification"] = json.loads(verify_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload["verification_parse_error"] = True

Path(status_file).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
PY
}

run_step() {
  local title="$1"
  shift
  local attempts="${MARKETING_DASHBOARD_STEP_ATTEMPTS:-3}"
  local retry_sleep="${MARKETING_DASHBOARD_RETRY_SLEEP_SECONDS:-20}"
  local rc=0

  for attempt in $(seq 1 "$attempts"); do
    log "Старт: ${title}, попытка ${attempt}/${attempts}"
    "$@" >>"$RUN_LOG" 2>&1
    rc=$?
    if [[ "$rc" -eq 0 ]]; then
      log "ОК: ${title}"
      return 0
    fi
    log "Ошибка: ${title}, попытка ${attempt}/${attempts}, код=${rc}"
    if [[ "$attempt" -lt "$attempts" ]]; then
      sleep "$retry_sleep"
    fi
  done

  write_status "FAIL" "$title" "$rc"
  exit "$rc"
}

run_verify() {
  local title="Проверка согласованности Google Sheets"
  log "Старт: ${title}"
  node "${ROOT_DIR}/scripts/verify_marketing_dashboard_live.mjs" >"$VERIFY_JSON" 2>>"$RUN_LOG"
  local rc=$?
  cat "$VERIFY_JSON" >>"$RUN_LOG"
  printf '\n' >>"$RUN_LOG"
  if [[ "$rc" -ne 0 ]]; then
    log "Ошибка: ${title}, код=${rc}"
    write_status "FAIL" "$title" "$rc"
    exit "$rc"
  fi
  log "ОК: ${title}"
}

cd "$ROOT_DIR" || exit 1
rm -f "$VERIFY_JSON"

log "Ежедневное обновление маркетингового дашборда запущено"
run_step "Загрузка live-данных из Bitrix24" python3 "${ROOT_DIR}/scripts/refresh_marketing_dashboard_live.py"
run_step "Сборка вкладки Когортный фильтр" node "${ROOT_DIR}/scripts/build_cohort_filter_sheet.mjs"
run_step "Сборка вкладки Событийный фильтр" node "${ROOT_DIR}/scripts/build_event_filter_sheet.mjs"
run_step "Сборка SEO Dashboard" node "${ROOT_DIR}/scripts/build_ceo_dashboard.mjs"
run_step "Сборка служебных вкладок" node "${ROOT_DIR}/scripts/build_support_sheets.mjs"
run_step "Сборка операционных вкладок" node "${ROOT_DIR}/scripts/build_operational_sheets.mjs"
run_step "Сборка вкладки Динамика источников 2026" node "${ROOT_DIR}/scripts/build_source_dynamics_sheet.mjs"
run_step "Сборка вкладки Спам по источникам" node "${ROOT_DIR}/scripts/build_spam_source_sheet.mjs"
run_step "Визуальное оформление вкладок" node "${ROOT_DIR}/scripts/beautify_dashboard_tabs.mjs"
run_step "Компактное отображение вкладок" node "${ROOT_DIR}/scripts/compact_dashboard_tabs.mjs"
run_step "Проверка отсутствия жёстко прошитых месяцев" node "${ROOT_DIR}/scripts/check_marketing_dashboard_month_literals.mjs"
run_verify
write_status "OK" "" 0
log "Ежедневное обновление маркетингового дашборда завершено"
