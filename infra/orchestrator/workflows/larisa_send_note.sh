#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

ENV_INTEGRATIONS_FILE="${ENV_INTEGRATIONS_FILE:-$ROOT_DIR/.env.integrations}"
WHOOP_ENV_FILE="${WHOOP_ENV_FILE:-$ROOT_DIR/../whoop/.env}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/reports}"

if [[ -f "$ENV_INTEGRATIONS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_INTEGRATIONS_FILE"
  set +a
fi

if [[ -f "$WHOOP_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$WHOOP_ENV_FILE"
  set +a
fi

: "${TZ:=Europe/Moscow}"
export TZ

NOTE_B64="${NOTE_B64:-}"
if [[ -z "$NOTE_B64" && "$#" -gt 0 ]]; then
  NOTE_B64="$(printf '%s' "$*" | /usr/bin/base64 | tr -d '\n')"
fi
[[ -n "$NOTE_B64" ]] || fail "Не задан текст сообщения: передай NOTE_B64 или аргументы workflow."

mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d_%H%M%S_MSK')"
REPORT_FILE="$REPORT_DIR/larisa_send_note_${STAMP}.txt"

log "larisa_send_note: старт"

set +e
(
  cd "$ROOT_DIR"
  NOTE_B64="$NOTE_B64" python3 - <<'PY'
import base64
import json
import os
import sys

from agents.larisa_ivanovna.providers.telegram_provider import SharedTelegramRouteProvider


def main() -> int:
    note_b64 = os.environ.get("NOTE_B64", "").strip()
    if not note_b64:
        raise SystemExit("NOTE_B64 не задан")
    text = base64.b64decode(note_b64.encode("utf-8")).decode("utf-8")
    provider = SharedTelegramRouteProvider()
    result = provider.send(text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("delivered"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY
) >"$REPORT_FILE" 2>&1
rc=$?
set -e

if [[ "$rc" -ne 0 ]]; then
  log "larisa_send_note: ошибка (rc=${rc}), отчет=${REPORT_FILE}"
  tail -n 120 "$REPORT_FILE" || true
  exit "$rc"
fi

log "larisa_send_note: успешно, отчет=${REPORT_FILE}"
