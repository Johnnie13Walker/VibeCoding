#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTRACT_FILE="${CONTRACT_FILE:-$ROOT_DIR/ops/owner_operating_contract_MSK.md}"
MAX_AGE_DAYS="${MAX_AGE_DAYS:-21}"

: "${TZ:=Europe/Moscow}"
export TZ

status=0
ok() { printf "[OK] %s\n" "$1"; }
bad() { printf "[ПРОБЛЕМА] %s\n" "$1"; status=1; }

if [[ ! -f "$CONTRACT_FILE" ]]; then
  bad "Не найден контракт контекста: $CONTRACT_FILE"
  exit 1
fi

required_headers=(
  "## Цель"
  "## Приоритеты"
  "## SLA отчетов"
  "## Обязательные интеграции"
  "## Границы допущений"
)

for header in "${required_headers[@]}"; do
  if grep -qF "$header" "$CONTRACT_FILE"; then
    ok "Найден раздел: $header"
  else
    bad "Отсутствует обязательный раздел: $header"
  fi
done

review_date="$(sed -n 's/^Обновлено:[[:space:]]*//p' "$CONTRACT_FILE" | head -n1)"
if [[ -z "$review_date" ]]; then
  bad "Не найдена строка 'Обновлено: YYYY-MM-DD'"
else
  if ! [[ "$review_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    bad "Некорректный формат даты обновления: $review_date"
  else
    now_epoch="$(date '+%s')"
    review_epoch="$(date -j -f '%Y-%m-%d' "$review_date" '+%s' 2>/dev/null || true)"
    if [[ -z "$review_epoch" ]]; then
      bad "Не удалось распарсить дату обновления: $review_date"
    else
      age_days="$(( (now_epoch - review_epoch) / 86400 ))"
      if (( age_days <= MAX_AGE_DAYS )); then
        ok "Контракт актуален (${age_days} дн. с последнего обновления)"
      else
        bad "Контракт устарел (${age_days} дн., лимит ${MAX_AGE_DAYS})"
      fi
    fi
  fi
fi

if [[ "$status" -eq 0 ]]; then
  printf "Итог: ОК\n"
else
  printf "Итог: есть проблемы\n"
fi

exit "$status"
