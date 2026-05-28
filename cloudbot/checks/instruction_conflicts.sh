#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNBOOK_FILE="$ROOT_DIR/docs/architecture/schedule_contract.md"
SCHEDULE_WORKFLOW="$ROOT_DIR/infra/orchestrator/workflows/openclaw_healthcheck_schedule.sh"
SCHEDULE_CONTRACT_FILE="${SCHEDULE_CONTRACT_FILE:-$ROOT_DIR/configs/schedule_contract.env}"
ORCHESTRATOR_POLICY="$ROOT_DIR/AGENTS.md"
if [[ ! -f "$ORCHESTRATOR_POLICY" && -f "$ROOT_DIR/../AGENTS.md" ]]; then
  ORCHESTRATOR_POLICY="$ROOT_DIR/../AGENTS.md"
fi

: "${TZ:=Europe/Moscow}"
export TZ

status=0
ok() { printf "[OK] %s\n" "$1"; }
bad() { printf "[ПРОБЛЕМА] %s\n" "$1"; status=1; }

EXPECTED_HEALTH_CRON="0 9 * * *"
EXPECTED_STATUS_CRON="30 9 * * *"

if [[ -f "$SCHEDULE_CONTRACT_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$SCHEDULE_CONTRACT_FILE"
  set +a
fi

EXPECTED_HEALTH_CRON="${OPENCLAW_HEALTH_CRON_MSK:-$EXPECTED_HEALTH_CRON}"
EXPECTED_STATUS_CRON="${OPENCLAW_STATUS_CRON_MSK:-$EXPECTED_STATUS_CRON}"

if [[ -f "$RUNBOOK_FILE" ]]; then
  if grep -q "09:30" "$RUNBOOK_FILE"; then
    ok "Runbook фиксирует SLA отчета 09:30 МСК"
  else
    bad "Runbook не фиксирует время 09:30 МСК"
  fi
else
  bad "Не найден runbook: $RUNBOOK_FILE"
fi

if [[ -f "$SCHEDULE_WORKFLOW" ]]; then
  if grep -Fq "OPENCLAW_HEALTH_CRON_MSK:-$EXPECTED_HEALTH_CRON" "$SCHEDULE_WORKFLOW"; then
    ok "Health cron по умолчанию 09:00 МСК"
  else
    bad "Health cron по умолчанию не 09:00 МСК"
  fi

  if grep -Fq "OPENCLAW_STATUS_CRON_MSK:-$EXPECTED_STATUS_CRON" "$SCHEDULE_WORKFLOW"; then
    ok "Status cron по умолчанию 09:30 МСК"
  else
    bad "Status cron по умолчанию не 09:30 МСК"
  fi

  if grep -Fq "Если свежий run ещё running, не объявляй старый error активной проблемой до завершения текущего run" "$SCHEDULE_WORKFLOW"; then
    ok "Status prompt учитывает более свежий run в состоянии running"
  else
    bad "Status prompt не защищает от ложной эскалации при более свежем run=running"
  fi
else
  bad "Не найден workflow расписания: $SCHEDULE_WORKFLOW"
fi

if [[ -f "$ORCHESTRATOR_POLICY" ]]; then
  if grep -qiE "через (orchestrator workflow|оркестратор)" "$ORCHESTRATOR_POLICY"; then
    ok "Политика orchestrator зафиксирована"
  else
    bad "Политика orchestrator не обнаружена в AGENTS.md"
  fi
else
  bad "Не найден AGENTS.md в корне проекта"
fi

if [[ "$status" -eq 0 ]]; then
  printf "Итог: ОК\n"
else
  printf "Итог: есть проблемы\n"
fi

exit "$status"
