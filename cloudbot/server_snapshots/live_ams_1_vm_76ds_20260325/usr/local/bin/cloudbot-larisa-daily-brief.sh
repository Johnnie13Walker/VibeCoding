#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow
cd '/opt/cloudbot-runtime/current'
exec ./run_larisa_daily_brief_from_runtime_env.sh "$@"
