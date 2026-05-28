#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${TZ:=Europe/Moscow}"
export TZ

status=0
ok() { printf "[OK] %s\n" "$1"; }
bad() { printf "[ПРОБЛЕМА] %s\n" "$1"; status=1; }

run_step() {
  local title="$1"
  shift
  if "$@" >/tmp/post_change_verify_last.log 2>&1; then
    ok "$title"
  else
    bad "$title"
    sed -n '1,120p' /tmp/post_change_verify_last.log || true
  fi
}

run_step "Синтаксис checks/*.sh" /usr/bin/env bash -lc "cd \"$ROOT_DIR\" && for f in checks/*.sh; do bash -n \"\$f\"; done"
run_step "Синтаксис scripts/*.sh" /usr/bin/env bash -lc "cd \"$ROOT_DIR\" && for f in scripts/*.sh; do bash -n \"\$f\"; done"
run_step "Синтаксис orchestrator workflows" /usr/bin/env bash -lc "cd \"$ROOT_DIR\" && for f in infra/orchestrator/workflows/*.sh; do bash -n \"\$f\"; done"

run_step "Контракт контекста актуален" /usr/bin/env bash -lc "cd \"$ROOT_DIR\" && bash checks/context_contract_verify.sh"
run_step "Конфликты инструкций отсутствуют" /usr/bin/env bash -lc "cd \"$ROOT_DIR\" && bash checks/instruction_conflicts.sh"

# В dry-run daily_ops должен завершаться успешно как проверочный контур,
# даже если внутри есть проблемные интеграции.
run_step "Dry-run daily_ops запускается" /usr/bin/env bash -lc "cd \"$ROOT_DIR\" && DRY_RUN=1 SEND_TELEGRAM_STATUS=never FAIL_ON_PROBLEMS=0 ./infra/orchestrator/run_workflow.sh daily_ops"
run_step "next_week_prep запускается" /usr/bin/env bash -lc "cd \"$ROOT_DIR\" && ./infra/orchestrator/run_workflow.sh next_week_prep"
run_step "context_snapshot запускается" /usr/bin/env bash -lc "cd \"$ROOT_DIR\" && ./infra/orchestrator/run_workflow.sh context_snapshot"
run_step "Sales runtime contract tests" /usr/bin/env bash -lc "cd \"$ROOT_DIR\" && python3 -m unittest tests.integration.test_lev_petrovich_runtime tests.integration.test_sales_dispatch_contract -q"
run_step "Dry-run morning_sales_dispatch contract smoke" /usr/bin/env bash -lc "cd \"$ROOT_DIR\" && python3 checks/sales_morning_dispatch_smoke.py"

if [[ "$status" -eq 0 ]]; then
  printf "Итог: ОК\n"
else
  printf "Итог: есть проблемы\n"
fi

exit "$status"
