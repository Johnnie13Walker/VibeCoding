set -euo pipefail
export TZ=Europe/Moscow

container_name='openclaw-openclaw-gateway-1'
container_project='/home/node/.openclaw/workspace/todo-integration'
host_project='/root/.openclaw/workspace/todo-integration'
runtime_env="$container_project/.env.runtime"
morning_log='/var/log/openclaw-todo-morning.log'

echo '--- Container status ---'
docker ps --filter "name=^/${container_name}$" --format 'table {{.Names}}\t{{.Status}}'
docker inspect --format 'State={{.State.Status}} Restarting={{.State.Restarting}} RestartCount={{.RestartCount}}' "$container_name"

echo '--- npm run selftest ---'
selftest_log=$(mktemp)
set +e
docker exec "$container_name" sh -lc "cd '$container_project' && TODO_ENV_PATH='$container_project/.env.runtime' npm run selftest" >"$selftest_log" 2>&1
selftest_rc=$?
set -e
sed -n '1,160p' "$selftest_log"
if [ "$selftest_rc" -ne 0 ]; then
  echo '--- selftest tail (failure) ---'
  tail -n 120 "$selftest_log"
  echo "selftest_failed_rc=$selftest_rc"
  exit 1
fi
if grep -q 'create_test_single: created' "$selftest_log"; then
  echo 'selftest_write_check_failed=todoist_write_detected'
  exit 1
fi
if ! grep -q 'create_test_single: disabled' "$selftest_log"; then
  echo 'selftest_write_check_failed=missing_disabled_marker'
  exit 1
fi

echo '--- calendarDailyRenderer smoke ---'
docker exec "$container_name" sh -lc "cd '$container_project' && TODO_ENV_PATH='$container_project/.env.runtime' node src/selftests/calendarDailyRenderer.smoke.mjs"

echo '--- /diag preview ---'
diag_out=$(docker exec "$container_name" sh -lc "cd '$container_project' && TODO_ENV_PATH='$container_project/.env.runtime' node src/agenda-query.mjs diag" 2>&1)
printf '%s\n' "$diag_out" | sed -n '1,120p'
if ! printf '%s\n' "$diag_out" | grep -q '<b>timezone:</b>'; then
  echo 'diag_check_failed=missing_timezone'
  exit 1
fi
if ! printf '%s\n' "$diag_out" | grep -q '<b>timezone:</b> Europe/Moscow'; then
  echo 'diag_check_failed=timezone_not_moscow'
  exit 1
fi
if ! printf '%s\n' "$diag_out" | grep -q '<b>classified:</b>'; then
  echo 'diag_check_failed=missing_classified'
  exit 1
fi

echo '--- Scenario flag ---'
scenario_flag=$(docker exec "$container_name" sh -lc "sed -n 's/^DAY_SCENARIO_MESSAGE_ENABLED=//p' '$runtime_env' | tail -n1" 2>/dev/null || true)
printf 'DAY_SCENARIO_MESSAGE_ENABLED=%s\n' "${scenario_flag:-<missing>}"
if [ "${scenario_flag:-}" != "0" ]; then
  echo 'scenario_flag_failed=expected_0'
  exit 1
fi

echo '--- Manual digest:morning ---'
temp_state_dir=$(mktemp -d)
smoke_digest_file="$host_project/src/send-digest.smoke.mjs"
smoke_telegram_file="$host_project/src/telegram.smoke.mjs"
cleanup_smoke_files() {
  rm -rf "$temp_state_dir" "$smoke_digest_file" "$smoke_telegram_file"
}
trap cleanup_smoke_files EXIT

cp "$host_project/src/send-digest.mjs" "$smoke_digest_file"
perl -0pi -e 's@import \{ sendTelegramMessage \} from "\./telegram\.mjs";@import { sendTelegramMessage } from "./telegram.smoke.mjs";@' "$smoke_digest_file"
cat >"$smoke_telegram_file" <<'EOF_SMOKE_TELEGRAM'
export async function sendTelegramMessage(botToken, chatId, text, options = {}) {
  console.log(`mock_telegram chat=${chatId} len=${String(text || "").length} parse_mode=${options.parseMode || "HTML"}`);
  return { ok: true, result: { message_id: 1 } };
}
EOF_SMOKE_TELEGRAM

set +e
manual_out=$(docker exec "$container_name" sh -lc "cd '$container_project' && TODO_ENV_PATH='$runtime_env' TODO_STATE_DIR='$temp_state_dir' node src/send-digest.smoke.mjs morning" 2>&1)
manual_rc=$?
set -e
printf '%s\n' "$manual_out" | tee -a "$morning_log"
if [ "$manual_rc" -ne 0 ]; then
  echo "Ручной запуск digest:morning завершился с ошибкой (rc=$manual_rc)."
  exit 1
fi

if printf '%s\n' "$manual_out" | grep -q 'sent slot=morning'; then
  echo 'telegram_delivery=ok'
elif printf '%s\n' "$manual_out" | grep -q 'skip_duplicate slot=morning'; then
  echo 'telegram_delivery=skip_duplicate'
else
  echo 'telegram_delivery=unknown'
  exit 1
fi

if ! printf '%s\n' "$manual_out" | grep -q 'SCENARIO_ABSENT'; then
  echo 'scenario_check_failed=missing_SCENARIO_ABSENT'
  exit 1
fi
echo 'scenario_check=disabled'

echo '--- Morning log tail ---'
tail -n 160 "$morning_log"
