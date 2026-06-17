#!/usr/bin/env bash
set -euo pipefail

export TZ=Europe/Moscow

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="${MARKETING_DASHBOARD_RUNTIME_ROOT:-/Users/pro2kuror/.local/share/cloudbot/marketing-dashboard/architect}"
ENGINEER_ENV="${MARKETING_DASHBOARD_ENGINEER_ENV:-/Users/pro2kuror/Desktop/Cloudbot/engineer/.env.integrations}"
SA_SOURCE="${MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON:-${GOOGLE_SERVICE_ACCOUNT_JSON:-/Users/pro2kuror/Downloads/finance-director-sheets-903611b799c3.json}}"
SA_RUNTIME="${MARKETING_DASHBOARD_SERVICE_ACCOUNT_RUNTIME_PATH:-/Users/pro2kuror/.config/openclo/assistant/secrets/finance-director-sheets-903611b799c3.json}"
TMP_DIR="${ROOT_DIR}/tmp"
CRON_TZ_LINE="CRON_TZ=Europe/Moscow"
BEGIN_MARKER="# BEGIN MARKETING_DASHBOARD_DAILY"
END_MARKER="# END MARKETING_DASHBOARD_DAILY"

mkdir -p "$ROOT_DIR/scripts" "$TMP_DIR" "$(dirname "$SA_RUNTIME")"

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

chmod +x "${ROOT_DIR}/scripts/run_marketing_dashboard_daily.sh" "${ROOT_DIR}/scripts/send_marketing_dashboard_telegram_status.py" "${ROOT_DIR}/scripts/refresh_marketing_dashboard_live.py"

if [[ ! -f "$SA_SOURCE" ]]; then
  echo "Не найден Google service account JSON: $SA_SOURCE" >&2
  exit 1
fi
if [[ ! -f "$SA_RUNTIME" ]] || ! cmp -s "$SA_SOURCE" "$SA_RUNTIME"; then
  cp "$SA_SOURCE" "$SA_RUNTIME"
  chmod 600 "$SA_RUNTIME"
fi

current_cron="$(mktemp)"
desired_cron="$(mktemp)"
stripped_cron="$(mktemp)"
trap 'rm -f "$current_cron" "$desired_cron" "$stripped_cron"' EXIT

crontab -l >"$current_cron" 2>/dev/null || : >"$current_cron"

awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" '
  $0 == begin {skip=1; next}
  $0 == end {skip=0; next}
  skip != 1 {print}
' "$current_cron" >"$stripped_cron"

cp "$stripped_cron" "$desired_cron"
if ! grep -Fxq "$CRON_TZ_LINE" "$desired_cron"; then
  {
    printf '%s\n' "$CRON_TZ_LINE"
    cat "$desired_cron"
  } >"${desired_cron}.next"
  mv "${desired_cron}.next" "$desired_cron"
fi

cat >>"$desired_cron" <<CRON

${BEGIN_MARKER}
0 8 * * * cd '${ROOT_DIR}' && MARKETING_DASHBOARD_ROOT_DIR='${ROOT_DIR}' MARKETING_DASHBOARD_ENGINEER_ENV='${ENGINEER_ENV}' MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON='${SA_RUNTIME}' /bin/bash '${ROOT_DIR}/scripts/run_marketing_dashboard_daily.sh' >> '${TMP_DIR}/marketing_dashboard_daily.cron.log' 2>&1
15 8 * * * cd '${ROOT_DIR}' && MARKETING_DASHBOARD_ROOT_DIR='${ROOT_DIR}' MARKETING_DASHBOARD_ENGINEER_ENV='${ENGINEER_ENV}' MARKETING_GOOGLE_SERVICE_ACCOUNT_JSON='${SA_RUNTIME}' python3 '${ROOT_DIR}/scripts/send_marketing_dashboard_telegram_status.py' >> '${TMP_DIR}/marketing_dashboard_telegram.cron.log' 2>&1
${END_MARKER}
CRON

crontab "$desired_cron"
crontab -l | sed -n "/${BEGIN_MARKER}/,/${END_MARKER}/p"
