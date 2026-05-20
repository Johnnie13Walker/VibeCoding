#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate
python -m sales_kpi_dashboard.cli refresh --dry-run
