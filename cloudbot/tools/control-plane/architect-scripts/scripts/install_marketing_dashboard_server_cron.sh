#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="${MARKETING_DASHBOARD_RUNTIME_ROOT:-/opt/cloudbot-runtime/marketing-dashboard/current}"
ENGINEER_ROOT="${MARKETING_DASHBOARD_ENGINEER_ROOT:-/home/ops/cloudbot-larisa-agent}"
ENV_FILE="${MARKETING_DASHBOARD_SERVER_ENV:-/etc/openclaw/marketing_dashboard.env}"
SA_SOURCE="${MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON:-${GOOGLE_SERVICE_ACCOUNT_JSON:-}}"
SA_RUNTIME="${MARKETING_DASHBOARD_SERVICE_ACCOUNT_RUNTIME_PATH:-/etc/openclaw/finance-director-sheets-903611b799c3.json}"
CRON_FILE="${MARKETING_DASHBOARD_CRON_FILE:-/etc/cron.d/cloudbot-marketing-dashboard}"
TMP_DIR="${ROOT_DIR}/tmp"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Серверная установка должна запускаться от root: нужны /etc/openclaw и /etc/cron.d" >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/scripts" "$TMP_DIR" "$(dirname "$ENV_FILE")" "$(dirname "$SA_RUNTIME")"
chmod 755 "$ROOT_DIR" "$ROOT_DIR/scripts" "$TMP_DIR"

copy_script() {
  local name="$1"
  cp "${SOURCE_ROOT}/scripts/${name}" "${ROOT_DIR}/scripts/${name}"
}

copy_script "bitrix_field_audit_gd324.py"
copy_script "refresh_marketing_dashboard_live.py"
copy_script "build_cohort_filter_sheet.mjs"
copy_script "build_event_filter_sheet.mjs"
copy_script "build_ceo_dashboard.mjs"
copy_script "build_support_sheets.mjs"
copy_script "build_operational_sheets.mjs"
copy_script "build_source_dynamics_sheet.mjs"
copy_script "build_spam_source_sheet.mjs"
copy_script "beautify_dashboard_tabs.mjs"
copy_script "compact_dashboard_tabs.mjs"
copy_script "verify_marketing_dashboard_live.mjs"
copy_script "run_marketing_dashboard_daily.sh"
copy_script "send_marketing_dashboard_telegram_status.py"
copy_script "install_marketing_dashboard_server_cron.sh"

chmod +x \
  "${ROOT_DIR}/scripts/run_marketing_dashboard_daily.sh" \
  "${ROOT_DIR}/scripts/send_marketing_dashboard_telegram_status.py" \
  "${ROOT_DIR}/scripts/refresh_marketing_dashboard_live.py"

if [[ ! -f "$SA_RUNTIME" ]]; then
  if [[ -z "$SA_SOURCE" || ! -f "$SA_SOURCE" ]]; then
    echo "Не найден Google service account JSON. Задайте MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON или положите файл в ${SA_RUNTIME}" >&2
    exit 1
  fi
  cp "$SA_SOURCE" "$SA_RUNTIME"
  chmod 600 "$SA_RUNTIME"
fi

if [[ ! -f "$SA_RUNTIME" ]]; then
  echo "Не найден runtime Google service account JSON: $SA_RUNTIME" >&2
  exit 1
fi

chmod 600 "$SA_RUNTIME"

if [[ ! -f "$ENV_FILE" ]]; then
  cat >"$ENV_FILE" <<ENV
TZ=Europe/Moscow
MARKETING_DASHBOARD_ROOT_DIR=${ROOT_DIR}
MARKETING_DASHBOARD_ENGINEER_ROOT=${ENGINEER_ROOT}
MARKETING_DASHBOARD_ENGINEER_ENV=${ENV_FILE}
MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON=${SA_RUNTIME}
GOOGLE_SERVICE_ACCOUNT_JSON=${SA_RUNTIME}
BITRIX_ENV_FILE=/opt/openclaw/.env
BITRIX_APP_STATE_DIR=/opt/openclaw/state/bitrix_app
BITRIX_TIMEOUT_SEC=90
MARKETING_DASHBOARD_STEP_ATTEMPTS=3
MARKETING_DASHBOARD_RETRY_SLEEP_SECONDS=20
ENV
  chmod 600 "$ENV_FILE"
fi

if ! grep -q '^MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON=' "$ENV_FILE"; then
  {
    echo "MARKETING_DASHBOARD_ROOT_DIR=${ROOT_DIR}"
    echo "MARKETING_DASHBOARD_ENGINEER_ROOT=${ENGINEER_ROOT}"
    echo "MARKETING_DASHBOARD_ENGINEER_ENV=${ENV_FILE}"
    echo "MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON=${SA_RUNTIME}"
    echo "GOOGLE_SERVICE_ACCOUNT_JSON=${SA_RUNTIME}"
    echo "BITRIX_ENV_FILE=/opt/openclaw/.env"
    echo "BITRIX_APP_STATE_DIR=/opt/openclaw/state/bitrix_app"
    echo "BITRIX_TIMEOUT_SEC=90"
  } >>"$ENV_FILE"
fi

chmod 600 "$ENV_FILE"

cat >"${ROOT_DIR}/run_marketing_dashboard_from_server_env.sh" <<WRAPPER
#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow
for env_file in /etc/openclaw/larisa.env /opt/openclaw/.env /etc/openclaw/whoop.env '${ENV_FILE}'; do
  if [[ -f "\$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "\$env_file"
    set +a
  fi
done

export MARKETING_DASHBOARD_ROOT_DIR="\${MARKETING_DASHBOARD_ROOT_DIR:-${ROOT_DIR}}"
export MARKETING_DASHBOARD_ENGINEER_ROOT="\${MARKETING_DASHBOARD_ENGINEER_ROOT:-${ENGINEER_ROOT}}"
export MARKETING_DASHBOARD_ENGINEER_ENV="\${MARKETING_DASHBOARD_ENGINEER_ENV:-${ENV_FILE}}"
export MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON="\${MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON:-${SA_RUNTIME}}"
export GOOGLE_SERVICE_ACCOUNT_JSON="\${GOOGLE_SERVICE_ACCOUNT_JSON:-${SA_RUNTIME}}"
export BITRIX_ENV_FILE="\${BITRIX_ENV_FILE:-/opt/openclaw/.env}"
export BITRIX_APP_STATE_DIR="\${BITRIX_APP_STATE_DIR:-/opt/openclaw/state/bitrix_app}"

if [[ -z "\${LARISA_TELEGRAM_BOT_TOKEN:-}" && -n "\${TELEGRAM_BOT_TOKEN:-}" ]]; then
  export LARISA_TELEGRAM_BOT_TOKEN="\${TELEGRAM_BOT_TOKEN}"
fi
if [[ -z "\${LARISA_TELEGRAM_CHAT_ID:-}" && -n "\${TELEGRAM_CHAT_ID:-}" ]]; then
  export LARISA_TELEGRAM_CHAT_ID="\${TELEGRAM_CHAT_ID}"
fi

cd '${ROOT_DIR}'
exec "\$@"
WRAPPER
chmod +x "${ROOT_DIR}/run_marketing_dashboard_from_server_env.sh"

cat >"$CRON_FILE" <<CRON
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Production Debian cron исполняет /etc/cron.d по системному UTC.
# 08:00 МСК = 05:00 UTC, 08:15 МСК = 05:15 UTC.
0 5 * * * root '${ROOT_DIR}/run_marketing_dashboard_from_server_env.sh' /bin/bash '${ROOT_DIR}/scripts/run_marketing_dashboard_daily.sh' >> '${TMP_DIR}/marketing_dashboard_daily.cron.log' 2>&1
15 5 * * * root '${ROOT_DIR}/run_marketing_dashboard_from_server_env.sh' python3 '${ROOT_DIR}/scripts/send_marketing_dashboard_telegram_status.py' >> '${TMP_DIR}/marketing_dashboard_telegram.cron.log' 2>&1
CRON

chmod 644 "$CRON_FILE"

echo "Установлен server cron: $CRON_FILE"
cat "$CRON_FILE"
