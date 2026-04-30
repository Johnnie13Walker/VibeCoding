#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_BRANCH="${1:-${GIT_PUSH_BRANCH:-}}"
ALLOW_MAIN_PUSH="${ALLOW_MAIN_PUSH:-0}"

cd "$ROOT_DIR"

current_branch="$(git branch --show-current)"
if [[ -z "$current_branch" ]]; then
    echo "ОШИБКА: backup.sh нельзя запускать из detached HEAD." >&2
    exit 1
fi

if [[ -z "$TARGET_BRANCH" ]]; then
    TARGET_BRANCH="$current_branch"
fi

if [[ "$TARGET_BRANCH" != "$current_branch" ]]; then
    echo "ОШИБКА: backup.sh не будет пушить в $TARGET_BRANCH из текущей ветки $current_branch." >&2
    echo "Сначала переключись на нужную ветку или передай согласованный branch." >&2
    exit 1
fi

if [[ "$TARGET_BRANCH" == "main" && "$ALLOW_MAIN_PUSH" != "1" ]]; then
    echo "ОШИБКА: прямой push в main заблокирован. Используй feature/dev ветку." >&2
    exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
    echo "ОШИБКА: remote origin не настроен, backup commit отменён." >&2
    exit 1
fi

if ! git ls-remote --exit-code origin >/dev/null 2>&1; then
    echo "ОШИБКА: origin недоступен, backup commit отменён до создания локального commit." >&2
    exit 1
fi

git add -A

if git diff --cached --quiet; then
    echo "Нет изменений для backup commit."
    exit 0
fi

git commit -m "backup: snapshot $(date '+%Y-%m-%d %H:%M %Z')"
git push -u origin "$TARGET_BRANCH"
