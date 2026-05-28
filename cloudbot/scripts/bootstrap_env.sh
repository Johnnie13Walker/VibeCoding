#!/usr/bin/env bash
set -euo pipefail

if [[ -f ".env.integrations" ]]; then
  echo ".env.integrations уже существует"
  exit 0
fi

cp .env.integrations.example .env.integrations
echo "Создан .env.integrations. Заполни значения и запусти: make preflight && make verify"
