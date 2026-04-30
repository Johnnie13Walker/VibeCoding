#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_BRANCH="${1:-${DEPLOY_BRANCH:-}}"

cd "$ROOT_DIR"

current_branch="$(git branch --show-current)"
if [[ -z "$TARGET_BRANCH" ]]; then
    if [[ -z "$current_branch" ]]; then
        echo "ОШИБКА: не удалось определить branch для deploy. Передай DEPLOY_BRANCH или первый аргумент." >&2
        exit 1
    fi
    TARGET_BRANCH="$current_branch"
fi

if [[ -n "$(git status --porcelain)" && "$current_branch" != "$TARGET_BRANCH" ]]; then
    echo "ОШИБКА: рабочее дерево грязное, нельзя переключать deploy на ветку $TARGET_BRANCH." >&2
    exit 1
fi

echo "Updating repository from branch: $TARGET_BRANCH"
git fetch origin "$TARGET_BRANCH"

if [[ "$current_branch" != "$TARGET_BRANCH" ]]; then
    git checkout "$TARGET_BRANCH"
fi

git pull --ff-only origin "$TARGET_BRANCH"

echo "Restarting services..."

if command -v docker >/dev/null 2>&1; then
    docker compose down || true
    docker compose up -d --build
fi

echo "Deploy complete."
