#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[install] Подготовка зависимостей проекта..."
if [ -f "bot/package.json" ]; then
  cd bot
  npm install --no-audit --no-fund
  echo "[install] npm зависимости для bot установлены"
else
  echo "[install] bot/package.json не найден, шаг пропущен"
fi
