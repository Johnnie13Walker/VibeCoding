#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="${PORTFOLIO_DATABASE_RUNTIME_ROOT:-/opt/cloudbot-runtime/portfolio-database/current}"
ENV_FILE="${PORTFOLIO_DATABASE_SERVER_ENV:-/etc/openclaw/portfolio_database.env}"
SA_SOURCE="${PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON:-${MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON:-${GOOGLE_SERVICE_ACCOUNT_JSON:-}}}"
SA_RUNTIME="${PORTFOLIO_DATABASE_SERVICE_ACCOUNT_RUNTIME_PATH:-/etc/openclaw/finance-director-sheets-903611b799c3.json}"
CRON_FILE="${PORTFOLIO_DATABASE_CRON_FILE:-/etc/cron.d/cloudbot-portfolio-database}"
TMP_DIR="${ROOT_DIR}/tmp"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Серверная установка должна запускаться от root: нужны /etc/openclaw и /etc/cron.d" >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/scripts" "$TMP_DIR" "$(dirname "$ENV_FILE")" "$(dirname "$SA_RUNTIME")"
chmod 755 "$ROOT_DIR" "$ROOT_DIR/scripts" "$TMP_DIR"

cp "${SOURCE_ROOT}/scripts/portfolio_database_refresh.mjs" "${ROOT_DIR}/scripts/portfolio_database_refresh.mjs"
cp "${SOURCE_ROOT}/scripts/portfolio_dashboard_refresh.mjs" "${ROOT_DIR}/scripts/portfolio_dashboard_refresh.mjs"
cp "${SOURCE_ROOT}/scripts/run_portfolio_database_daily.sh" "${ROOT_DIR}/scripts/run_portfolio_database_daily.sh"
chmod +x \
  "${ROOT_DIR}/scripts/portfolio_database_refresh.mjs" \
  "${ROOT_DIR}/scripts/portfolio_dashboard_refresh.mjs" \
  "${ROOT_DIR}/scripts/run_portfolio_database_daily.sh"

if [[ ! -f "$SA_RUNTIME" ]]; then
  if [[ -z "$SA_SOURCE" || ! -f "$SA_SOURCE" ]]; then
    echo "Не найден Google service account JSON. Задайте PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SERVICE_ACCOUNT_JSON или положите файл в ${SA_RUNTIME}" >&2
    exit 1
  fi
  cp "$SA_SOURCE" "$SA_RUNTIME"
fi
chmod 600 "$SA_RUNTIME"

cat >"$ENV_FILE" <<ENV
TZ=Europe/Moscow
PORTFOLIO_DATABASE_ROOT_DIR=${ROOT_DIR}
PORTFOLIO_DATABASE_LOG_DIR=${TMP_DIR}
PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON=${SA_RUNTIME}
GOOGLE_SERVICE_ACCOUNT_JSON=${SA_RUNTIME}
PORTFOLIO_SOURCE_SHEET_URL=https://docs.google.com/spreadsheets/d/17SBisFgKrf3hRP_zjVPC2e4wMzlq8j8HDC2bvkyS74Y/edit?gid=1482533080#gid=1482533080
PORTFOLIO_TARGET_SHEET_URL=https://docs.google.com/spreadsheets/d/1TgWlFHOvSDtW0e60fCLNvWDW7ADwOimHpypbQG7GI9E/edit
PORTFOLIO_DATABASE_SHEET_URL=https://docs.google.com/spreadsheets/d/1TgWlFHOvSDtW0e60fCLNvWDW7ADwOimHpypbQG7GI9E/edit
PORTFOLIO_DASHBOARD_SHEET_URL=https://docs.google.com/spreadsheets/d/1om_oGYvDZrADYbAbznZOyk7InhHF7kKs5MrMzzAJC2A/edit
ENV
chmod 600 "$ENV_FILE"

cat >"${ROOT_DIR}/run_portfolio_database_from_server_env.sh" <<WRAPPER
#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow
if [[ -f '${ENV_FILE}' ]]; then
  set -a
  # shellcheck disable=SC1090
  source '${ENV_FILE}'
  set +a
fi

export PORTFOLIO_DATABASE_ROOT_DIR="\${PORTFOLIO_DATABASE_ROOT_DIR:-${ROOT_DIR}}"
export PORTFOLIO_DATABASE_LOG_DIR="\${PORTFOLIO_DATABASE_LOG_DIR:-${TMP_DIR}}"
export PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON="\${PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON:-${SA_RUNTIME}}"
export GOOGLE_SERVICE_ACCOUNT_JSON="\${GOOGLE_SERVICE_ACCOUNT_JSON:-${SA_RUNTIME}}"

cd '${ROOT_DIR}'
exec "\$@"
WRAPPER
chmod +x "${ROOT_DIR}/run_portfolio_database_from_server_env.sh"

cat >"$CRON_FILE" <<CRON
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Ежедневное обновление закрытой базы портфолио.
# 06:30 МСК = 03:30 UTC на production Debian cron.
30 3 * * * root '${ROOT_DIR}/run_portfolio_database_from_server_env.sh' /bin/bash '${ROOT_DIR}/scripts/run_portfolio_database_daily.sh' >> '${TMP_DIR}/portfolio_database_daily.cron.log' 2>&1
CRON
chmod 644 "$CRON_FILE"

echo "Установлен server cron: $CRON_FILE"
cat "$CRON_FILE"
