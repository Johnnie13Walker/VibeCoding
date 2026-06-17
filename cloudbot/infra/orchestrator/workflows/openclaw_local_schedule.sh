#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

MODE="${1:-inspect}"
CRON_FILE="${CRON_FILE:-$ROOT_DIR/configs/schedules.cron}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
BLOCK_START="${BLOCK_START:-# BEGIN OPENCLAW_MANAGED_SCHEDULES}"
BLOCK_END="${BLOCK_END:-# END OPENCLAW_MANAGED_SCHEDULES}"

case "$MODE" in
  inspect|apply) ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, apply)"
    ;;
esac

[[ -f "$CRON_FILE" ]] || fail "Не найден файл расписания: $CRON_FILE"
mkdir -p "$REPORT_DIR"

current_cron="$(mktemp)"
stripped_cron="$(mktemp)"
desired_cron="$(mktemp)"
verified_cron="$(mktemp)"
managed_commands="$(mktemp)"
trap 'rm -f "$current_cron" "$stripped_cron" "$desired_cron" "$verified_cron" "$managed_commands"' EXIT

read_current_crontab() {
  if crontab -l >"$current_cron" 2>/dev/null; then
    return 0
  fi
  : >"$current_cron"
}

cron_command_part() {
  local cron_line="$1"
  printf '%s\n' "$cron_line" | awk '
    NF >= 6 {
      for (i = 6; i <= NF; i++) {
        printf "%s%s", $i, (i < NF ? OFS : ORS)
      }
    }
  '
}

build_managed_commands() {
  : >"$managed_commands"
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" == *=* && "$line" != *" "* ]] && continue
    command_part="$(cron_command_part "$line")"
    [[ -n "${command_part//[[:space:]]/}" ]] || continue
    printf '%s\n' "$command_part" >>"$managed_commands"
  done <"$CRON_FILE"
}

strip_managed_block() {
  local source_file="$1"
  local target_file="$2"
  local inside_block=0
  : >"$target_file"
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "$BLOCK_START" ]]; then
      inside_block=1
      continue
    fi
    if [[ "$line" == "$BLOCK_END" ]]; then
      inside_block=0
      continue
    fi
    if [[ "$inside_block" -eq 1 ]]; then
      continue
    fi
    command_part="$(cron_command_part "$line")"
    if [[ -n "${command_part//[[:space:]]/}" ]] && grep -Fqx -- "$command_part" "$managed_commands"; then
      continue
    fi
    printf '%s\n' "$line" >>"$target_file"
  done <"$source_file"
}

append_managed_block() {
  local base_file="$1"
  local target_file="$2"
  local line=""
  cp "$base_file" "$target_file"
  if [[ -s "$target_file" ]] && [[ "$(tail -c1 "$target_file" 2>/dev/null || true)" != $'\n' ]]; then
    printf '\n' >>"$target_file"
  fi
  {
    printf '%s\n' "$BLOCK_START"
    while IFS= read -r line || [[ -n "$line" ]]; do
      if [[ "$line" == *=* && "$line" != *" "* ]] && grep -Fqx -- "$line" "$base_file"; then
        continue
      fi
      printf '%s\n' "$line"
    done <"$CRON_FILE"
    printf '%s\n' "$BLOCK_END"
  } >>"$target_file"
}

show_managed_block() {
  local source_file="$1"
  awk -v start="$BLOCK_START" -v end="$BLOCK_END" '
    $0 == start { print; show = 1; next }
    $0 == end { print; show = 0; exit }
    show == 1 { print }
  ' "$source_file"
}

read_current_crontab
build_managed_commands
strip_managed_block "$current_cron" "$stripped_cron"
append_managed_block "$stripped_cron" "$desired_cron"

log "Локальное расписание OpenClaw: mode=${MODE}"
log "Источник расписания: ${CRON_FILE}"
log "Текущий managed block:"
show_managed_block "$current_cron" || true
log "Желаемый managed block:"
show_managed_block "$desired_cron" || true

if cmp -s "$current_cron" "$desired_cron"; then
  log "Изменений в локальном crontab не требуется"
  exit 0
fi

log "Найдено отличие между текущим и желаемым crontab"
diff -u "$current_cron" "$desired_cron" || true

if [[ "$MODE" == "inspect" ]]; then
  exit 0
fi

stamp="$(date '+%Y%m%d_%H%M%S_MSK')"
backup_file="$REPORT_DIR/local_crontab_backup_${stamp}.txt"
cp "$current_cron" "$backup_file"
log "Сохранён backup текущего crontab: ${backup_file}"

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  log "[DRY-RUN] crontab ${desired_cron}"
  exit 0
fi

crontab "$desired_cron"
log "Обновление crontab применено"

crontab -l >"$verified_cron" 2>/dev/null || fail "После apply не удалось прочитать локальный crontab"
if ! cmp -s "$verified_cron" "$desired_cron"; then
  fail "Проверка crontab после apply не прошла"
fi

log "Итоговый managed block:"
show_managed_block "$verified_cron" || true
log "Локальное расписание успешно обновлено"
