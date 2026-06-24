#!/usr/bin/env bash
# Дрейф-чек состояния: незакоммиченное / untracked / незапушенное по всем worktree
# репозитория VibeCoding + Obsidian-vault, плюс устаревшие STATUS.md.
#
# Режимы:
#   state-drift-check.sh          # fast: без сети, тихо если дрейфа нет (для SessionStart-хука)
#   state-drift-check.sh full     # + устаревшие STATUS + macOS-уведомление + отчёт (для cron)
#
# Принцип: только ИНФОРМИРУЕТ, ничего не меняет и не блокирует (всегда exit 0).
set -uo pipefail

REPO="/Users/pro2kuror/Desktop/VibeCoding"
VAULT="/Users/pro2kuror/Documents/Cloudbot-Vault"
REPORT="$HOME/.claude/drift-report.txt"
MODE="${1:-fast}"
IGNORE='\.preview/|/node_modules/|/\.next|\.pyc$|/__pycache__/|/\.venv/|\.DS_Store'
STALE_DAYS=10

lines=()

scan() { # $1=path  $2=label
  local p="$1" label="$2" st nonempty untr dirty br ahead f
  git -C "$p" rev-parse --git-dir >/dev/null 2>&1 || return
  st=$(git -C "$p" status --porcelain 2>/dev/null | grep -vE "$IGNORE" || true)
  nonempty=$(printf '%s' "$st" | grep -cE '.' || true)
  untr=$(printf '%s' "$st" | grep -cE '^\?\?' || true)
  dirty=$(( nonempty - untr ))
  br=$(git -C "$p" branch --show-current 2>/dev/null || echo '?')
  ahead=$(git -C "$p" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
  f=""
  [ "${dirty:-0}" -gt 0 ] && f="$f ${dirty} незакоммич."
  [ "${ahead:-0}" -gt 0 ] && f="$f ${ahead} незапуш."
  # untracked шумит (давний мусор) — показываем только в full-режиме (дневной сторож)
  [ "$MODE" = "full" ] && [ "${untr:-0}" -gt 0 ] && f="$f ${untr} untracked"
  [ -n "$f" ] && lines+=("• ${label} [${br}]:$f")
}

# 1) все worktree репозитория
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
  while IFS= read -r wt; do
    [ -d "$wt" ] || continue
    scan "$wt" "$(basename "$wt")"
  done < <(git -C "$REPO" worktree list 2>/dev/null | awk '{print $1}')
fi

# 2) Obsidian vault
scan "$VAULT" "vault"

# 3) устаревшие STATUS.md (только full)
stale=()
if [ "$MODE" = "full" ] && [ -d "$VAULT/09-Projects" ]; then
  cutoff=$(date -v-"${STALE_DAYS}"d +%Y-%m-%d 2>/dev/null || date -d "-${STALE_DAYS} days" +%Y-%m-%d)
  while IFS= read -r f; do
    upd=$(grep -m1 '^updated:' "$f" 2>/dev/null | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -1)
    [ -n "$upd" ] && [ "$upd" \< "$cutoff" ] && stale+=("• $(echo "$f" | sed 's#.*09-Projects/##; s#/STATUS.md##') — STATUS от $upd")
  done < <(find "$VAULT/09-Projects" -iname STATUS.md 2>/dev/null)
fi

# ── вывод ─────────────────────────────────────────────────────────────────────
mark=""
[ -f "$HOME/.claude/.wrap-pending" ] && mark=$(cat "$HOME/.claude/.wrap-pending" 2>/dev/null)

total=$(( ${#lines[@]} + ${#stale[@]} ))
if [ "$total" -eq 0 ] && [ -z "$mark" ]; then
  [ "$MODE" = "full" ] && : > "$REPORT"
  exit 0
fi

emit() {
  if [ -n "$mark" ]; then
    echo "## 🔴 Предыдущая сессия НЕ сведена в память/Obsidian"
    echo ""
    echo "$mark"
    echo ""
  fi
  if [ "$total" -gt 0 ]; then
    echo "## ⚠️ Дрейф состояния (несохранённое/несинхронизированное)"
    echo ""
    [ ${#lines[@]} -gt 0 ] && { echo "**Git:**"; printf '%s\n' "${lines[@]}"; echo ""; }
    [ ${#stale[@]} -gt 0 ] && { echo "**STATUS старше ${STALE_DAYS} дней:**"; printf '%s\n' "${stale[@]}"; echo ""; }
  fi
  echo "→ запусти \`/wrap\` чтобы свести в память/Obsidian/git."
}

emit
if [ "$MODE" = "full" ]; then
  emit > "$REPORT"
  note="${total} мест с дрейфом"
  [ -n "$mark" ] && note="прошлая сессия не сведена + $note"
  osascript -e "display notification \"${note} — /wrap или см. ~/.claude/drift-report.txt\" with title \"Дрейф состояния\" sound name \"\"" 2>/dev/null || true
fi
exit 0
