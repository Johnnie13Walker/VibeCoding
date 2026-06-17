#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow

ROOT_DIR="${PORTFOLIO_CLIENTS_ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LOG_DIR="${PORTFOLIO_CLIENTS_LOG_DIR:-${ROOT_DIR}/tmp}"
REPORT_JSON="${PORTFOLIO_CLIENTS_REPORT_JSON:-${LOG_DIR}/portfolio_clients_sync.latest.json}"
SA_PATH="${PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON:-${MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON:-${GOOGLE_SERVICE_ACCOUNT_JSON:-/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json}}}"
SEND_TELEGRAM="${PORTFOLIO_CLIENTS_SEND_TELEGRAM:-1}"

mkdir -p "$LOG_DIR"

load_env_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$file"
    set +a
  fi
}

load_env_file /etc/openclaw/portfolio_clients.env
load_env_file /etc/openclaw/larisa.env
load_env_file /opt/openclaw/.env

if [[ -z "${LARISA_TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  export LARISA_TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
fi
if [[ -z "${LARISA_TELEGRAM_CHAT_ID:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]; then
  export LARISA_TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID"
fi

cd "$ROOT_DIR"

GOOGLE_SERVICE_ACCOUNT_JSON="$SA_PATH" \
PORTFOLIO_GOOGLE_SERVICE_ACCOUNT_JSON="$SA_PATH" \
PORTFOLIO_CLIENTS_REPORT_JSON="$REPORT_JSON" \
  node "${ROOT_DIR}/scripts/portfolio_clients_sync.mjs" \
  >> "${LOG_DIR}/portfolio_clients_sync.log" 2>&1

build_message() {
  node - "$REPORT_JSON" <<'NODE'
const { readFileSync } = require("node:fs");
const report = JSON.parse(readFileSync(process.argv[2], "utf8"));
const lines = ["Портфолио клиентов обновлено"];
if (!report.plannedAddCount) {
  lines.push("", "Новых проектов для добавления нет.");
} else {
  lines.push("", `Добавлены проекты: ${report.plannedAddCount}`);
  for (const item of report.addedProjects.slice(0, 20)) {
    lines.push(`- ${item.project} — ${item.category} / ${item.subcategory}, сайт: ${item.siteActive}`);
  }
  if (report.addedProjects.length > 20) {
    lines.push(`- ещё ${report.addedProjects.length - 20}`);
  }
}
if (report.unknownProjects.length) {
  lines.push("", `Требуют ручной классификации: ${report.unknownProjects.join(", ")}`);
}
if (report.inactiveSites.length) {
  lines.push("", `Сайт не подтверждён: ${report.inactiveSites.join(", ")}`);
}
console.log(lines.join("\n"));
NODE
}

send_telegram() {
  local text="$1"
  if [[ "${LARISA_TELEGRAM_DRY_RUN:-${TELEGRAM_DRY_RUN:-0}}" == "1" ]]; then
    printf '%s\n' "$text" > "${LOG_DIR}/portfolio_clients_telegram.dry_run.txt"
    return 0
  fi
  if [[ -z "${LARISA_TELEGRAM_BOT_TOKEN:-}" || -z "${LARISA_TELEGRAM_CHAT_ID:-}" ]]; then
    echo "Не заданы LARISA_TELEGRAM_BOT_TOKEN/LARISA_TELEGRAM_CHAT_ID для отбивки Ларисы Ивановны" >&2
    return 1
  fi
  local api_base="${TELEGRAM_API_BASE_URL:-https://api.telegram.org}"
  curl -fsS \
    -X POST "${api_base%/}/bot${LARISA_TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d "chat_id=${LARISA_TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${text}" \
    -d "disable_web_page_preview=true" \
    > "${LOG_DIR}/portfolio_clients_telegram.response.json"
}

if [[ "$SEND_TELEGRAM" == "1" ]]; then
  message="$(build_message)"
  send_telegram "$message" >> "${LOG_DIR}/portfolio_clients_telegram.log" 2>&1
fi
