#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="${PORTFOLIO_CLIENTS_RUNTIME_ROOT:-/opt/cloudbot-runtime/portfolio-clients/current}"
ENV_FILE="${PORTFOLIO_CLIENTS_SERVER_ENV:-/etc/openclaw/portfolio_clients.env}"
SA_SOURCE="${PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON:-${MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON:-${GOOGLE_SERVICE_ACCOUNT_JSON:-}}}"
SA_RUNTIME="${PORTFOLIO_CLIENTS_SERVICE_ACCOUNT_RUNTIME_PATH:-/etc/openclaw/finance-director-sheets-903611b799c3.json}"
CRON_FILE="${PORTFOLIO_CLIENTS_CRON_FILE:-/etc/cron.d/cloudbot-portfolio-clients}"
TMP_DIR="${ROOT_DIR}/tmp"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Серверная установка должна запускаться от root: нужны /etc/openclaw и /etc/cron.d" >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/scripts" "$TMP_DIR" "$(dirname "$ENV_FILE")" "$(dirname "$SA_RUNTIME")"
chmod 755 "$ROOT_DIR" "$ROOT_DIR/scripts" "$TMP_DIR"

cp "${SOURCE_ROOT}/scripts/portfolio_clients_sync.mjs" "${ROOT_DIR}/scripts/portfolio_clients_sync.mjs"
cp "${SOURCE_ROOT}/scripts/run_portfolio_clients_daily.sh" "${ROOT_DIR}/scripts/run_portfolio_clients_daily.sh"
chmod +x \
  "${ROOT_DIR}/scripts/portfolio_clients_sync.mjs" \
  "${ROOT_DIR}/scripts/run_portfolio_clients_daily.sh"

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
PORTFOLIO_CLIENTS_ROOT_DIR=${ROOT_DIR}
PORTFOLIO_CLIENTS_LOG_DIR=${TMP_DIR}
PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON=${SA_RUNTIME}
GOOGLE_SERVICE_ACCOUNT_JSON=${SA_RUNTIME}
PORTFOLIO_SOURCE_SHEET_URL=https://docs.google.com/spreadsheets/d/17SBisFgKrf3hRP_zjVPC2e4wMzlq8j8HDC2bvkyS74Y/edit?gid=1482533080#gid=1482533080
PORTFOLIO_CLIENTS_SHEET_URL=https://docs.google.com/spreadsheets/d/1TSEei_ncr3SQmiYT074Q17HOzmxxtrPV447j27N_BZw/edit?gid=1955270606#gid=1955270606
PORTFOLIO_CLIENTS_SHEET_TITLE=Клиенты
PORTFOLIO_CLIENTS_SEND_TELEGRAM=1
PORTFOLIO_CLIENTS_EXCLUDE_SERVICES=agency,service,services,эдженси,сервисес
ENV
chmod 600 "$ENV_FILE"

cat >"${ROOT_DIR}/run_portfolio_clients_from_server_env.sh" <<WRAPPER
#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow
for env_file in '${ENV_FILE}' /etc/openclaw/larisa.env /opt/openclaw/.env; do
  if [[ -f "\$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "\$env_file"
    set +a
  fi
done

export PORTFOLIO_CLIENTS_ROOT_DIR="\${PORTFOLIO_CLIENTS_ROOT_DIR:-${ROOT_DIR}}"
export PORTFOLIO_CLIENTS_LOG_DIR="\${PORTFOLIO_CLIENTS_LOG_DIR:-${TMP_DIR}}"
export PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON="\${PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON:-${SA_RUNTIME}}"
export GOOGLE_SERVICE_ACCOUNT_JSON="\${GOOGLE_SERVICE_ACCOUNT_JSON:-${SA_RUNTIME}}"

cd '${ROOT_DIR}'
exec "\$@"
WRAPPER
chmod +x "${ROOT_DIR}/run_portfolio_clients_from_server_env.sh"

cat >"$CRON_FILE" <<CRON
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Ежедневная синхронизация клиентского портфолио и отбивка через Ларису Ивановну.
# Production Debian cron исполняет /etc/cron.d по системному UTC.
# 09:05 МСК = 06:05 UTC.
5 6 * * * root '${ROOT_DIR}/run_portfolio_clients_from_server_env.sh' /bin/bash '${ROOT_DIR}/scripts/run_portfolio_clients_daily.sh' >> '${TMP_DIR}/portfolio_clients_daily.cron.log' 2>&1
CRON
chmod 644 "$CRON_FILE"

echo "Установлен server cron: $CRON_FILE"
cat "$CRON_FILE"
