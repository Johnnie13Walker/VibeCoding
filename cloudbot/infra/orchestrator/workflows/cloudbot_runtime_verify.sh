#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

TARGET_HOST="${LARISA_RUNTIME_HOST:-${CLOUDBOT_RUNTIME_HOST:-${PRIMARY_HOST:-}}}"
RUNTIME_ROOT="${LARISA_RUNTIME_ROOT:-${CLOUDBOT_RUNTIME_ROOT:-/opt/cloudbot-runtime/larisa}}"
CURRENT_LINK="${LARISA_RUNTIME_CURRENT_LINK:-${CLOUDBOT_RUNTIME_CURRENT_LINK:-$RUNTIME_ROOT/current}}"
REMOTE_LOCK_PATH="${LARISA_RUNTIME_LOCK_PATH:-${CLOUDBOT_RUNTIME_LOCK_PATH:-$RUNTIME_ROOT/.deploy.lock}}"
GENERIC_CURRENT_LINK="${GENERIC_RUNTIME_CURRENT_LINK:-/opt/cloudbot-runtime/current}"
LARISA_WRAPPER="${LARISA_SYSTEM_RUNNER_PATH:-/usr/local/bin/cloudbot-larisa-daily-brief.sh}"
NEWS_WRAPPER="${NEWS_AGENT_SYSTEM_RUNNER_PATH:-/usr/local/bin/cloudbot-news-digest-live.sh}"
LARISA_CRON_FILE="${LARISA_CRON_FILE_PATH:-/etc/cron.d/cloudbot-larisa-daily-brief}"
NEWS_CRON_FILE="${NEWS_AGENT_CRON_FILE_PATH:-/etc/cron.d/cloudbot-news-digest}"
NEWS_ENV_FILE="${NEWS_AGENT_ENV_FILE_PATH:-/etc/openclaw/news_agent.env}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/cloudbot_runtime_verify_${STAMP}.txt"

require_env TARGET_HOST SSH_USER SSH_KEY_PATH SSH_PORT
mkdir -p "$REPORT_DIR"

printf -v runtime_root_q '%q' "$RUNTIME_ROOT"
printf -v current_link_q '%q' "$CURRENT_LINK"
printf -v remote_lock_path_q '%q' "$REMOTE_LOCK_PATH"
printf -v generic_current_link_q '%q' "$GENERIC_CURRENT_LINK"
printf -v larisa_wrapper_q '%q' "$LARISA_WRAPPER"
printf -v news_wrapper_q '%q' "$NEWS_WRAPPER"
printf -v larisa_cron_file_q '%q' "$LARISA_CRON_FILE"
printf -v news_cron_file_q '%q' "$NEWS_CRON_FILE"
printf -v news_env_file_q '%q' "$NEWS_ENV_FILE"

remote_script=""
read -r -d '' remote_script <<'REMOTE' || true
set -euo pipefail
export TZ=Europe/Moscow

runtime_root=__RUNTIME_ROOT_Q__
current_link=__CURRENT_LINK_Q__
lock_path=__REMOTE_LOCK_PATH_Q__
generic_current_link=__GENERIC_CURRENT_LINK_Q__
larisa_wrapper=__LARISA_WRAPPER_Q__
news_wrapper=__NEWS_WRAPPER_Q__
larisa_cron_file=__LARISA_CRON_FILE_Q__
news_cron_file=__NEWS_CRON_FILE_Q__
news_env_file=__NEWS_ENV_FILE_Q__

status=0

ok() {
  printf '[OK] %s\n' "$1"
}

bad() {
  printf '[ПРОБЛЕМА] %s\n' "$1"
  status=1
}

current_target="$(readlink -f "${current_link}" 2>/dev/null || true)"
generic_current_target="$(readlink -f "${generic_current_link}" 2>/dev/null || true)"
current_release=""
if [[ -n "${current_target}" ]]; then
  current_release="$(basename "${current_target}")"
fi

echo "host=$(hostname -f 2>/dev/null || hostname)"
echo "time=$(date '+%F %T %Z')"
echo "runtime_root=${runtime_root}"
echo "current_link=${current_link}"
echo "current_target=${current_target:-<missing>}"
echo "current_release=${current_release:-<missing>}"
echo "generic_current_link=${generic_current_link}"
echo "generic_current_target=${generic_current_target:-<missing>}"

if [[ -L "${current_link}" && -d "${current_target}" ]]; then
  ok "current указывает на существующий release"
else
  bad "current не указывает на существующий release"
fi

release_commit=""
release_branch=""
release_id=""
for meta_name in RELEASE_COMMIT RELEASE_BRANCH RELEASE_ID; do
  meta_value=""
  if [[ -f "${current_link}/${meta_name}" ]]; then
    meta_value="$(cat "${current_link}/${meta_name}")"
  fi
  printf '%s=%s\n' "${meta_name}" "${meta_value:-<missing>}"
  if [[ -z "${meta_value}" ]]; then
    bad "metadata ${meta_name} отсутствует"
  fi
  case "${meta_name}" in
    RELEASE_COMMIT) release_commit="${meta_value}" ;;
    RELEASE_BRANCH) release_branch="${meta_value}" ;;
    RELEASE_ID) release_id="${meta_value}" ;;
  esac
done

if [[ -n "${release_id}" && -n "${current_release}" && "${release_id}" == "${current_release}" ]]; then
  ok "RELEASE_ID совпадает с каталогом current release"
else
  bad "RELEASE_ID не совпадает с каталогом current release"
fi

if [[ -e "${lock_path}" ]]; then
  bad "runtime lock присутствует: ${lock_path}"
  if [[ -f "${lock_path}/owner" ]]; then
    echo "lock_owner=$(cat "${lock_path}/owner")"
  fi
else
  ok "runtime lock отсутствует"
fi

if [[ -f "${larisa_wrapper}" ]]; then
  ok "larisa wrapper присутствует"
  bash -n "${larisa_wrapper}" && ok "larisa wrapper проходит bash -n" || bad "larisa wrapper не проходит bash -n"
  grep -Fq "${current_link}" "${larisa_wrapper}" && ok "larisa wrapper использует scoped current link" || bad "larisa wrapper не использует scoped current link"
else
  bad "larisa wrapper отсутствует"
fi

runner="${current_link}/run_larisa_daily_brief_from_runtime_env.sh"
if [[ -f "${runner}" ]]; then
  ok "runtime runner присутствует: ${runner}"
  bash -n "${runner}" && ok "runtime runner проходит bash -n: ${runner}" || bad "runtime runner не проходит bash -n: ${runner}"
else
  bad "runtime runner отсутствует: ${runner}"
fi

if [[ -f "${larisa_cron_file}" ]]; then
  ok "larisa cron присутствует"
  grep -Fq "${larisa_wrapper}" "${larisa_cron_file}" && ok "larisa cron указывает на system wrapper" || bad "larisa cron не указывает на system wrapper"
  grep -Eq '^0 5 \* \* \* root ' "${larisa_cron_file}" && ok "larisa cron использует явное UTC-выражение для 08:00 МСК" || bad "larisa cron не зафиксирован на 05:00 UTC / 08:00 МСК"
else
  bad "larisa cron отсутствует"
fi

if [[ -f "${news_wrapper}" ]]; then
  bad "news wrapper все еще присутствует"
else
  ok "news wrapper отсутствует"
fi

if [[ -f "${news_cron_file}" ]]; then
  bad "news cron все еще присутствует"
else
  ok "news cron отсутствует"
fi

if [[ -f "${news_env_file}" ]]; then
  bad "news env path все еще присутствует"
else
  ok "news env path отсутствует"
fi

if grep -RInE 'news_agent|news_digest|/etc/openclaw/news_agent.env' \
  "${current_link}/run_larisa_daily_brief_from_runtime_env.sh" \
  "${current_link}/infra/orchestrator/workflows" \
  "${current_link}/agents/larisa_ivanovna" \
  "${current_link}/cloudbot" >/tmp/cloudbot_runtime_verify_news_refs.log 2>&1; then
  bad "в larisa runtime остались ссылки на news"
  sed -n '1,60p' /tmp/cloudbot_runtime_verify_news_refs.log
else
  ok "larisa runtime не содержит ссылок на news"
fi

if grep -RInE '/home/ops/cloudbot-(larisa|news)-agent' \
  "${current_link}/run_larisa_daily_brief_from_runtime_env.sh" \
  "${current_link}/infra/orchestrator/workflows" \
  "${current_link}/agents/larisa_ivanovna" \
  "${current_link}/cloudbot" >/tmp/cloudbot_runtime_verify_legacy.log 2>&1; then
  bad "найдены legacy runtime path внутри текущего release"
  sed -n '1,40p' /tmp/cloudbot_runtime_verify_legacy.log
else
  ok "larisa code path не содержит legacy source of truth"
fi

current_reports_dir="${current_link}/reports"
if [[ -d "${current_reports_dir}" ]]; then
  ok "current/reports присутствует"
else
  bad "current/reports отсутствует"
fi

if [[ ! -e "${lock_path}" ]]; then
  larisa_before="$(ls -1dt "${current_reports_dir}"/larisa_daily_brief_*.txt 2>/dev/null | head -n1 || true)"
  if TELEGRAM_DRY_RUN=1 LARISA_TELEGRAM_DRY_RUN=1 "${larisa_wrapper}" >/tmp/cloudbot_runtime_verify_larisa.log 2>&1; then
    ok "manual dry-run larisa завершился успешно"
  else
    bad "manual dry-run larisa завершился ошибкой"
    sed -n '1,120p' /tmp/cloudbot_runtime_verify_larisa.log || true
  fi

  larisa_after="$(ls -1dt "${current_reports_dir}"/larisa_daily_brief_*.txt 2>/dev/null | head -n1 || true)"
  if [[ -n "${larisa_after}" && "${larisa_after}" != "${larisa_before}" ]]; then
    ok "создан свежий отчет larisa в current/reports"
    tail -n 20 "${larisa_after}" || true
  else
    bad "не найден новый отчет larisa в current/reports"
  fi
else
  echo "manual_dry_run_skipped=yes"
fi

echo "latest_reports_begin"
ls -1dt "${current_reports_dir}"/* 2>/dev/null | head -n 10 || true
echo "latest_reports_end"

if [[ "$status" -eq 0 ]]; then
  echo "Итог: ОК"
else
  echo "Итог: есть проблемы"
fi

exit "$status"
REMOTE

remote_script="${remote_script/__RUNTIME_ROOT_Q__/$runtime_root_q}"
remote_script="${remote_script/__CURRENT_LINK_Q__/$current_link_q}"
remote_script="${remote_script/__REMOTE_LOCK_PATH_Q__/$remote_lock_path_q}"
remote_script="${remote_script/__GENERIC_CURRENT_LINK_Q__/$generic_current_link_q}"
remote_script="${remote_script/__LARISA_WRAPPER_Q__/$larisa_wrapper_q}"
remote_script="${remote_script/__NEWS_WRAPPER_Q__/$news_wrapper_q}"
remote_script="${remote_script/__LARISA_CRON_FILE_Q__/$larisa_cron_file_q}"
remote_script="${remote_script/__NEWS_CRON_FILE_Q__/$news_cron_file_q}"
remote_script="${remote_script/__NEWS_ENV_FILE_Q__/$news_env_file_q}"

log "cloudbot_runtime_verify: старт (host=${TARGET_HOST}, runtime_root=${RUNTIME_ROOT})"

{
  echo "# Cloudbot Runtime Verify"
  echo "Время: $(date '+%F %T %Z')"
  echo "Хост: ${TARGET_HOST}"
  echo "Runtime root: ${RUNTIME_ROOT}"
  echo "Current link: ${CURRENT_LINK}"
  echo "Remote lock: ${REMOTE_LOCK_PATH}"
  echo "Larisa wrapper: ${LARISA_WRAPPER}"
  echo "News wrapper: ${NEWS_WRAPPER}"
  echo "Larisa cron: ${LARISA_CRON_FILE}"
  echo "News cron: ${NEWS_CRON_FILE}"
  echo "News env: ${NEWS_ENV_FILE}"
  echo
  run_remote_script "$TARGET_HOST" "$remote_script"
} | tee "$REPORT_FILE"

log "cloudbot_runtime_verify: завершен, отчет=${REPORT_FILE}"
