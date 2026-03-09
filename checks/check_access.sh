#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/happ-vpn.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

: "${TZ:=Europe/Moscow}"
export TZ

status=0
ok(){ printf "[OK] %s\n" "$1"; }
bad(){ printf "[ПРОБЛЕМА] %s\n" "$1"; status=1; }

if [[ ! -x "$ROOT_DIR/ops/ssh_happ.sh" ]]; then
  bad "Не найден исполняемый скрипт ops/ssh_happ.sh"
fi

check_one() {
  local target="$1"
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    ok "DRY-RUN: проверка ${target} пропущена"
    return 0
  fi

  if out="$("$ROOT_DIR/ops/ssh_happ.sh" "$target" "id && hostname && TZ=Europe/Moscow date '+%F %T %Z'" 2>&1)"; then
    ok "${target}: доступ по SSH подтвержден"
    printf "%s\n" "$out"
  else
    bad "${target}: нет доступа по SSH"
    printf "%s\n" "$out"
  fi
}

printf "=== CHECK ACCESS (%s) ===\n" "$(date '+%F %T %Z')"
check_one primary
check_one reserve

if [[ $status -eq 0 ]]; then
  echo "Итог: ОК"
else
  echo "Итог: есть проблемы"
fi

exit "$status"

