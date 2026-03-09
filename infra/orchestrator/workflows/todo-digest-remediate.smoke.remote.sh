set -euo pipefail
export TZ=Europe/Moscow

container_name='openclaw-openclaw-gateway-1'
container_project='/home/node/.openclaw/workspace/todo-integration'
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

echo '--- calendarDailyRenderer smoke ---'
docker exec "$container_name" sh -lc "cd '$container_project' && TODO_ENV_PATH='$container_project/.env.runtime' node src/selftests/calendarDailyRenderer.smoke.mjs"

echo '--- /diag preview ---'
diag_out=$(docker exec "$container_name" sh -lc "cd '$container_project' && TODO_ENV_PATH='$container_project/.env.runtime' node src/agenda-query.mjs diag" 2>&1)
printf '%s\n' "$diag_out" | sed -n '1,120p'
if ! printf '%s\n' "$diag_out" | grep -q '<b>timezone:</b>'; then
  echo 'diag_check_failed=missing_timezone'
  exit 1
fi
if ! printf '%s\n' "$diag_out" | grep -q '<b>classified:</b>'; then
  echo 'diag_check_failed=missing_classified'
  exit 1
fi

echo '--- Manual digest:morning ---'
set +e
manual_out=$(docker exec "$container_name" sh -lc "cd '$container_project' && TODO_ENV_PATH='$container_project/.env.runtime' npm run digest:morning" 2>&1)
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

echo '--- Morning log tail ---'
tail -n 160 "$morning_log"
