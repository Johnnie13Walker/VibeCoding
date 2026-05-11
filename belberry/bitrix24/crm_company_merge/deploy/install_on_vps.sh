#!/usr/bin/env bash

set -euo pipefail

MODULE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="/opt/openclaw/venvs/crm_company_merge"
STATE_DIR="/opt/openclaw/state"
BIN_LINK="/usr/local/bin/crm-company-merge"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -e "$MODULE_DIR"

mkdir -p "$STATE_DIR"

# Симлинк удобнее активации venv в .bashrc: cron и ручные команды получают один стабильный binary path.
ln -sfn "$VENV_DIR/bin/crm-company-merge" "$BIN_LINK"

echo "✓ installed at $(which crm-company-merge)"
