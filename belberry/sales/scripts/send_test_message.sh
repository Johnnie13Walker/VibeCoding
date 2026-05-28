#!/usr/bin/env bash
# Тестовое сообщение через бот Льва Петровича (icom_dir_Belberry_bot).
# Не запускает sales-pipeline, шлёт plain-text в указанный чат.
#
# Использование на проде:
#   SALES_TEST_CHAT_ID=<your_chat_id> bash send_test_message.sh
# или:
#   bash send_test_message.sh <chat_id>
#
# Требует доступ к токен-файлу /root/.openclaw/telegram/commercial-director.bot_token

set -eu

CHAT_ID="${1:-${SALES_TEST_CHAT_ID:-}}"
if [ -z "$CHAT_ID" ]; then
  echo "ERROR: укажи chat_id первым аргументом или через SALES_TEST_CHAT_ID env" >&2
  exit 2
fi

TOKEN_FILE="${SALES_TELEGRAM_BOT_TOKEN_FILE:-/root/.openclaw/telegram/commercial-director.bot_token}"
if [ ! -f "$TOKEN_FILE" ]; then
  echo "ERROR: token file not found: $TOKEN_FILE" >&2
  exit 3
fi

TOKEN=$(tr -d ' \n\r\t' < "$TOKEN_FILE")
if [ -z "$TOKEN" ]; then
  echo "ERROR: token file empty" >&2
  exit 4
fi

NOW=$(TZ=Europe/Moscow date '+%Y-%m-%d %H:%M:%S %Z')
TEXT=$(printf '🧪 <b>Тестовое сообщение</b> от Льва Петровича\n\nИсточник: <code>belberry/sales/scripts/send_test_message.sh</code>\nВремя: <code>%s</code>\nХост: <code>%s</code>\n\nЕсли сообщение пришло — Telegram-маршрут и токен в порядке.\nЭто <i>не</i> утренний sales-отчёт, sales-pipeline не запускался.' "$NOW" "$(hostname)")

# Telegram /sendMessage. HTML parse_mode. Все три поля url-encoded,
# чтобы реальные \n в text не превратились в литералы.
RESP=$(curl -sS --max-time 10 \
  --data-urlencode "chat_id=${CHAT_ID}" \
  --data-urlencode "parse_mode=HTML" \
  --data-urlencode "text=${TEXT}" \
  "https://api.telegram.org/bot${TOKEN}/sendMessage")

echo "$RESP" | python3 -c '
import json, sys
data = json.load(sys.stdin)
ok = data.get("ok")
print("ok=", ok)
if not ok:
    print("error_code =", data.get("error_code"))
    print("description=", data.get("description"))
    sys.exit(5)
res = data.get("result", {})
print("message_id =", res.get("message_id"))
print("chat       =", res.get("chat", {}).get("id"), res.get("chat", {}).get("title") or res.get("chat", {}).get("username"))
'
