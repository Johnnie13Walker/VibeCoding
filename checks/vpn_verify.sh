#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/happ-vpn.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

: "${TZ:=Europe/Moscow}"
export TZ

status=0
ok(){ printf "[OK] %s\n" "$1"; }
warn(){ printf "[WARN] %s\n" "$1"; status=1; }

need() {
  local v="$1"
  [[ -n "${!v:-}" ]] || { warn "Не задана переменная $v"; return 1; }
}

printf "=== VERIFY HAPP VPN (%s) ===\n" "$(date '+%F %T %Z')"

need PRIMARY_HOST
need SUBSCRIPTION_URL
need SSH_USER
need SSH_KEY_PATH
need SSH_PORT

check_subscription() {
  local tmp_file="/tmp/happ_subscription_verify.txt"
  local curl_opts="-fsS --max-time 10"
  if [[ "${SUBSCRIPTION_INSECURE_TLS:-0}" == "1" ]]; then
    curl_opts="-k ${curl_opts}"
  fi
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    ok "DRY-RUN: проверка subscription URL пропущена"
    return 0
  fi

  if ! eval "curl ${curl_opts} \"$SUBSCRIPTION_URL\"" >"$tmp_file"; then
    if ssh -i "$SSH_KEY_PATH" -p "$SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${SSH_USER}@${PRIMARY_HOST}" \
      "curl -fsS --max-time 10 http://127.0.0.1${SUBSCRIPTION_PATH:-/subscription/happ.txt}" >"$tmp_file"; then
      ok "Subscription URL проверен через сервер (self-check)"
    else
      warn "Subscription URL недоступен: $SUBSCRIPTION_URL"
      return 0
    fi
  fi

  if grep -q "#${PRIMARY_NODE_NAME:-happ-main}" "$tmp_file"; then
    if [[ -n "${RESERVE_HOST:-}" ]] && ! grep -q "#${RESERVE_NODE_NAME:-happ-backup}" "$tmp_file"; then
      warn "Subscription URL доступен, но в выдаче не найдена резервная нода"
    else
      ok "Subscription URL доступен и содержит ожидаемые ноды"
    fi
  else
    warn "Subscription URL доступен, но primary-нода в выдаче не найдена"
  fi
}

check_tls() {
  if [[ -z "${TLS_HOST:-}" ]]; then
    ok "TLS_HOST не задан, проверка сертификата пропущена (режим без домена)"
    return 0
  fi

  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    ok "DRY-RUN: проверка TLS для ${TLS_HOST}"
    return 0
  fi

  local end_date epoch_end epoch_now days_left
  end_date="$(echo | openssl s_client -connect "${TLS_HOST}:443" -servername "${TLS_HOST}" 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2)"
  if [[ -z "$end_date" ]]; then
    warn "Не удалось получить срок действия TLS сертификата для ${TLS_HOST}"
    return 0
  fi

  epoch_end="$(date -j -f '%b %e %T %Y %Z' "$end_date" '+%s' 2>/dev/null || true)"
  if [[ -z "$epoch_end" ]]; then
    warn "Не удалось распарсить дату TLS сертификата: $end_date"
    return 0
  fi

  epoch_now="$(date '+%s')"
  days_left="$(( (epoch_end - epoch_now) / 86400 ))"

  if (( days_left >= ${TLS_MIN_VALID_DAYS:-14} )); then
    ok "TLS сертификат валиден еще ${days_left} дн."
  else
    warn "TLS сертификат истекает через ${days_left} дн."
  fi
}
check_remote_service() {
  local host="$1"
  local label="$2"

  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    ok "DRY-RUN: проверка ноды ${label} (${host})"
    return 0
  fi

  if ssh -i "$SSH_KEY_PATH" -p "$SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${SSH_USER}@${host}" \
    "systemctl is-active ${VPN_SERVICE:-sing-box} >/dev/null && ss -tuln | grep -q ':${VPN_PORT:-443} '"; then
    ok "Нода ${label} (${host}) активна и слушает порт ${VPN_PORT:-443}"
  else
    warn "Проблема на ноде ${label} (${host}): сервис/порт"
  fi
}

check_subscription
check_remote_service "$PRIMARY_HOST" "primary"
if [[ -n "${RESERVE_HOST:-}" ]]; then
  check_remote_service "$RESERVE_HOST" "reserve"
fi
check_tls

if [[ $status -eq 0 ]]; then
  printf "\nИтог: ОК\n"
else
  printf "\nИтог: есть проблемы\n"
fi

exit "$status"
