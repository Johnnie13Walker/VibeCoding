#!/usr/bin/env bash
set -euo pipefail

TZ=Europe/Moscow
export TZ

CODEX_ROOT="${CODEX_ROOT:-/Users/pro2kuror/Desktop/CODEX}"
ENGINEER_TARGET="${ENGINEER_TARGET:-/Users/pro2kuror/Desktop/OpenClo/projects/engineer}"
CONTROL_PLANE_TARGET="${CONTROL_PLANE_TARGET:-/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane}"
PAPERCLIP_TARGET="${PAPERCLIP_TARGET:-/Users/pro2kuror/Desktop/tools/paperclip}"
CLOUDBOT_TARGET="${CLOUDBOT_TARGET:-/Users/pro2kuror/Desktop/Cloudbot}"

echo "Проверка CODEX workspace ($(date '+%F %T %Z'))"

require_symlink() {
  local path="$1"
  local expected="$2"

  if [[ ! -L "$path" ]]; then
    echo "[ПРОБЛЕМА] $path не является symlink" >&2
    exit 1
  fi

  local actual
  actual="$(readlink "$path")"
  if [[ "$actual" != "$expected" ]]; then
    echo "[ПРОБЛЕМА] $path указывает на $actual, ожидалось $expected" >&2
    exit 1
  fi

  echo "[OK] $path -> $actual"
}

if [[ ! -d "$CODEX_ROOT" ]]; then
  echo "[ПРОБЛЕМА] отсутствует $CODEX_ROOT" >&2
  exit 1
fi

require_symlink "$CODEX_ROOT/engineer" "$ENGINEER_TARGET"
require_symlink "$CODEX_ROOT/control-plane" "$CONTROL_PLANE_TARGET"
require_symlink "$CODEX_ROOT/tools/paperclip" "$PAPERCLIP_TARGET"
require_symlink "$CODEX_ROOT/wrappers/Cloudbot" "$CLOUDBOT_TARGET"

if [[ ! -f "$CODEX_ROOT/README.md" ]]; then
  echo "[ПРОБЛЕМА] отсутствует $CODEX_ROOT/README.md" >&2
  exit 1
fi
echo "[OK] $CODEX_ROOT/README.md"

git -C "$CODEX_ROOT/engineer" rev-parse --is-inside-work-tree >/dev/null
echo "[OK] CODEX/engineer git-контур доступен"

git -C "$CODEX_ROOT/tools/paperclip" rev-parse --is-inside-work-tree >/dev/null
echo "[OK] CODEX/tools/paperclip git-контур доступен"

echo "Готово: CODEX workspace navigation root корректен"
