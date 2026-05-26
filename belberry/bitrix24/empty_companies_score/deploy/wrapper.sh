#!/usr/bin/env bash
# Wrapper для cron-job empty_companies_score (см. ../README.md).
#
# Source-ит общие env-файлы Cloudbot, как это делают larisa-jobs:
#   /opt/openclaw/.env       — TELEGRAM_BOT_TOKEN (общий)
#   /etc/openclaw/larisa.env — LARISA_TELEGRAM_CHAT_ID
#
# Передаёт все CLI-аргументы дальше в python -m empty_companies_score
# (используется флаг --notify для утреннего прогона).
#
# Этот wrapper кладётся install.sh в /usr/local/bin/cloudbot-empty-companies-score.sh.

set -euo pipefail
export TZ=Europe/Moscow

if [[ -f /opt/openclaw/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source /opt/openclaw/.env
  set +a
fi

if [[ -f /etc/openclaw/larisa.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source /etc/openclaw/larisa.env
  set +a
fi

# Маппинг: общий TELEGRAM_BOT_TOKEN → LARISA_TELEGRAM_BOT_TOKEN, как у larisa-runner.
if [[ -z "${LARISA_TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  export LARISA_TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"
fi

export BITRIX_STATE_PATH="${BITRIX_STATE_PATH:-/opt/openclaw/state/bitrix_app/install.latest.json}"
export GOOGLE_SERVICE_ACCOUNT_JSON="${GOOGLE_SERVICE_ACCOUNT_JSON:-/opt/openclaw/secrets/finance-director-sheets.json}"
export EMPTY_CO_DATA_DIR="${EMPTY_CO_DATA_DIR:-/opt/openclaw/data/empty_co}"

PYTHON="/opt/openclaw/venvs/crm_company_merge/bin/python"
exec "$PYTHON" -m empty_companies_score "$@"
