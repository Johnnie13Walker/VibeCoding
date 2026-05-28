#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[restart] Перезапуск Cloudbot..."
if command -v docker >/dev/null 2>&1 && [ -f "docker-compose.yml" ]; then
  docker compose restart
  echo "[restart] docker compose restart выполнен"
else
  echo "[restart] docker-compose.yml не найден, перезапуск контейнеров пропущен"
fi
