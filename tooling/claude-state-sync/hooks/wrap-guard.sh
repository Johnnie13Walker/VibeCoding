#!/usr/bin/env bash
# SessionEnd-хук: если сегодня были коммиты кода, но память и Obsidian не обновлялись
# (т.е. работа была, а сведе́ния /wrap не было) — ставит маркер. Маркер громко показывает
# следующий SessionStart (state-drift-check.sh), снимается командой /wrap или сам, когда
# сведе́ние сделано. Только ставит/снимает маркер, ничего больше (exit 0).
set -uo pipefail

REPO="/Users/pro2kuror/Desktop/VibeCoding"
VAULT="/Users/pro2kuror/Documents/Cloudbot-Vault"
MEMDIR="$HOME/.claude/projects/-Users-pro2kuror-Desktop-VibeCoding/memory"
MARK="$HOME/.claude/.wrap-pending"

today=$(date +%Y-%m-%d)
midnight="$HOME/.claude/.midnight-ref"
touch -t "$(date +%Y%m%d)0000" "$midnight" 2>/dev/null

# 1) код-коммиты сегодня на любом worktree (vault отдельно)
code_commits=0
while IFS= read -r wt; do
  [ -d "$wt" ] || continue
  n=$(git -C "$wt" log --since="$today 00:00" --oneline 2>/dev/null | grep -c . || true)
  code_commits=$(( code_commits + n ))
done < <(git -C "$REPO" worktree list 2>/dev/null | awk '{print $1}')

# 2) обновлялись ли сегодня память или vault
mem_today=$(find "$MEMDIR" -name '*.md' ! -name 'MEMORY.md' -newer "$midnight" 2>/dev/null | grep -c . || true)
vault_today=$(git -C "$VAULT" log --since="$today 00:00" --oneline 2>/dev/null | grep -c . || true)

if [ "${code_commits:-0}" -gt 0 ] && [ "${mem_today:-0}" -eq 0 ] && [ "${vault_today:-0}" -eq 0 ]; then
  echo "Сегодня было ${code_commits} код-коммитов, но память и Obsidian не обновлялись — сведе́ния не было. Запусти /wrap." > "$MARK"
else
  rm -f "$MARK"  # работы не было ИЛИ уже сведено → маркер не нужен
fi
exit 0
