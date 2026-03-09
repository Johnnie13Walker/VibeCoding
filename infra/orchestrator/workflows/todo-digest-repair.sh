#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

require_env PRIMARY_HOST

MODE="${1:-inspect}"
PROJECT_PATH="${TODO_PROJECT_PATH:-/root/.openclaw/workspace/todo-integration}"
CONTAINER_NAME="${TODO_CONTAINER_NAME:-openclaw-openclaw-gateway-1}"
CRON_FILE="${TODO_CRON_FILE:-/etc/cron.d/openclaw-todo-digest}"
MORNING_LOG="${TODO_MORNING_LOG:-/var/log/openclaw-todo-morning.log}"
WEB_SEARCH_CONFIG_PATHS="${WEB_SEARCH_CONFIG_PATHS:-/root/.openclaw/openclaw.json /home/node/.openclaw/openclaw.json}"
WEB_SEARCH_PROVIDER_TARGET="${WEB_SEARCH_PROVIDER_TARGET:-duckduckgo}"
WEB_SEARCH_QUERY="${WEB_SEARCH_QUERY:-latest AI news}"
OPENCLAW_GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"

run_inspect() {
  log "Диагностика todo-digest на ${PRIMARY_HOST}"
  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
export TZ=Europe/Moscow

project_path='${PROJECT_PATH}'
container_name='${CONTAINER_NAME}'
cron_file='${CRON_FILE}'
morning_log='${MORNING_LOG}'

echo '=== TODO DIGEST DIAGNOSTICS ==='
echo \"Время: \$(date '+%F %T %Z')\"
echo \"Хост: \$(hostname)\"
echo

echo '--- Container state ---'
docker ps -a --filter \"name=^/\${container_name}\$\" --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
if docker inspect \"\${container_name}\" >/dev/null 2>&1; then
  docker inspect --format 'State={{.State.Status}} Restarting={{.State.Restarting}} RestartCount={{.RestartCount}} ExitCode={{.State.ExitCode}} StartedAt={{.State.StartedAt}} FinishedAt={{.State.FinishedAt}} Error={{.State.Error}}' \"\${container_name}\"
  echo
  echo '--- Container mounts ---'
  docker inspect --format '{{range .Mounts}}{{println .Source \"->\" .Destination}}{{end}}' \"\${container_name}\"
  echo
  echo '--- Container logs (tail 120) ---'
  docker logs --tail 120 \"\${container_name}\" 2>&1 || true
else
  echo \"Контейнер не найден: \${container_name}\"
fi
echo

echo '--- Openclaw config candidates ---'
for p in /root/.openclaw/openclaw.json /home/node/.openclaw/openclaw.json; do
  if [ -f \"\$p\" ]; then
    echo \"Файл: \$p\"
    sed -n '1,180p' \"\$p\"
  fi
done
echo

echo '--- Cron file ---'
if [ -f \"\${cron_file}\" ]; then
  nl -ba \"\${cron_file}\"
else
  echo \"Cron файл не найден: \${cron_file}\"
fi
echo

if [ -d \"\${project_path}\" ]; then
  cd \"\${project_path}\"
  echo '--- Project revision ---'
  git rev-parse --short HEAD 2>/dev/null || true
  git status --short 2>/dev/null || true
  echo
  echo '--- src/send-digest.mjs ---'
  if [ -f src/send-digest.mjs ]; then
    nl -ba src/send-digest.mjs | sed -n '1,260p'
  else
    echo 'Файл не найден: src/send-digest.mjs'
  fi
  echo
  echo '--- src/providers/todoist-provider.mjs ---'
  if [ -f src/providers/todoist-provider.mjs ]; then
    nl -ba src/providers/todoist-provider.mjs | sed -n '1,260p'
  else
    echo 'Файл не найден: src/providers/todoist-provider.mjs'
  fi
else
  echo \"Каталог проекта не найден: \${project_path}\"
fi
echo

echo '--- Morning log (tail 200) ---'
if [ -f \"\${morning_log}\" ]; then
  tail -n 200 \"\${morning_log}\"
else
  echo \"Лог не найден: \${morning_log}\"
fi
"
}

run_inspect_code() {
  log "Расширенная инспекция кода todo-digest на ${PRIMARY_HOST}"
  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
export TZ=Europe/Moscow

project_path='${PROJECT_PATH}'
if [ ! -d \"\${project_path}\" ]; then
  echo \"Каталог проекта не найден: \${project_path}\"
  exit 1
fi
cd \"\${project_path}\"

show_file() {
  local p=\"\$1\"
  local max_lines=\"\$2\"
  echo
  echo \"--- \${p} ---\"
  if [ -f \"\${p}\" ]; then
    nl -ba \"\${p}\" | sed -n \"1,\${max_lines}p\"
  else
    echo \"Файл не найден: \${p}\"
  fi
}

show_file package.json 220
show_file src/provider-factory.mjs 220
show_file src/agenda/aggregate.mjs 260
show_file src/agenda/freeSlots.mjs 260
show_file src/agenda/providers/bitrixCalendar.mjs 320
show_file src/agenda/providers/googleCalendar.mjs 320
show_file src/reports/morningSecretaryDigest.mjs 300
show_file src/telegram.mjs 220
show_file src/config.mjs 260
show_file src/reports/executiveDigestFormatter.mjs 320
show_file src/service.mjs 260
"
}

run_show_file() {
  local rel_path="${2:-}"
  local max_lines="${3:-260}"
  [[ -n "$rel_path" ]] || fail "show-file требует аргумент <relative-path>"

  log "Показ файла ${rel_path} на ${PRIMARY_HOST}"
  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
export TZ=Europe/Moscow
project_path='${PROJECT_PATH}'
rel_path='${rel_path}'
max_lines='${max_lines}'

cd \"\${project_path}\"
if [ ! -f \"\${rel_path}\" ]; then
  echo \"Файл не найден: \${rel_path}\"
  exit 1
fi
echo \"--- \${rel_path} ---\"
nl -ba \"\${rel_path}\" | sed -n \"1,\${max_lines}p\"
"
}

run_list_files() {
  local pattern="${2:-src}"
  log "Список файлов ${pattern} на ${PRIMARY_HOST}"
  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
export TZ=Europe/Moscow
project_path='${PROJECT_PATH}'
pattern='${pattern}'
cd \"\${project_path}\"
if [ -d \"\${pattern}\" ]; then
  find \"\${pattern}\" -maxdepth 4 -type f | sort
elif [ -n \"\${pattern}\" ]; then
  find . -maxdepth 5 -type f | grep -E \"\${pattern}\" | sort || true
else
  find . -maxdepth 5 -type f | sort
fi
"
}

run_grep() {
  local pattern="${2:-}"
  [[ -n "$pattern" ]] || fail "grep требует аргумент <pattern>"
  log "Поиск по коду: ${pattern}"
  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
export TZ=Europe/Moscow
project_path='${PROJECT_PATH}'
pattern='${pattern}'
cd \"\${project_path}\"
if command -v rg >/dev/null 2>&1; then
  rg -n \"\${pattern}\" src || true
else
  grep -RInE \"\${pattern}\" src || true
fi
"
}

run_remote_exec() {
  local raw_cmd="${2:-}"
  [[ -n "$raw_cmd" ]] || fail "remote-exec требует аргумент <command>"
  local cmd_b64
  cmd_b64="$(printf '%s' "$raw_cmd" | base64 | tr -d '\n')"
  log "Удалённое выполнение команды на ${PRIMARY_HOST}"
  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
export TZ=Europe/Moscow
cmd=\"\$(printf '%s' '${cmd_b64}' | base64 -d)\"
eval \"\$cmd\"
"
}

run_web_search_provider() {
  local action="${1:-inspect}"
  local config_paths_b64 provider_b64 query_b64 container_b64 port_b64
  config_paths_b64="$(printf '%s' "$WEB_SEARCH_CONFIG_PATHS" | base64 | tr -d '\n')"
  provider_b64="$(printf '%s' "$WEB_SEARCH_PROVIDER_TARGET" | base64 | tr -d '\n')"
  query_b64="$(printf '%s' "$WEB_SEARCH_QUERY" | base64 | tr -d '\n')"
  container_b64="$(printf '%s' "$CONTAINER_NAME" | base64 | tr -d '\n')"
  port_b64="$(printf '%s' "$OPENCLAW_GATEWAY_PORT" | base64 | tr -d '\n')"

  log "Диагностика/фиксация web_search (${action}) на ${PRIMARY_HOST}"
  run_remote_script "$PRIMARY_HOST" "
set -euo pipefail
export TZ=Europe/Moscow

mode='${action}'
config_paths_raw=\"\$(printf '%s' '${config_paths_b64}' | base64 -d)\"
provider_target=\"\$(printf '%s' '${provider_b64}' | base64 -d)\"
search_query=\"\$(printf '%s' '${query_b64}' | base64 -d)\"
container_name=\"\$(printf '%s' '${container_b64}' | base64 -d)\"
gateway_port=\"\$(printf '%s' '${port_b64}' | base64 -d)\"

if ! command -v jq >/dev/null 2>&1; then
  echo 'ОШИБКА: на хосте не найден jq' >&2
  exit 1
fi

echo '=== OPENCLAW WEB SEARCH ==='
echo \"mode=\${mode}\"
echo \"time=\$(date '+%F %T %Z')\"
echo \"host=\$(hostname)\"

grep_targets=()
for p in /root/.openclaw/openclaw.json /home/node/.openclaw/openclaw.json /etc/openclaw /opt/openclaw/.env /opt/openclaw/.env.gateway /opt/openclaw/.env.local /opt/openclaw/docker-compose.yml /opt/openclaw/docker-compose.yaml; do
  if [ -e \"\$p\" ]; then
    grep_targets+=(\"\$p\")
  fi
done

grep_cfg() {
  local pattern=\"\$1\"
  for target in \"\${grep_targets[@]}\"; do
    if [ -d \"\$target\" ]; then
      grep -RIn --exclude-dir=.git --binary-files=without-match \"\$pattern\" \"\$target\" 2>/dev/null || true
    elif [ -f \"\$target\" ]; then
      grep -n --binary-files=without-match \"\$pattern\" \"\$target\" 2>/dev/null || true
    fi
  done | head -n 200
}

echo
echo '--- grep -R \"brave\" -n ---'
if [ \"\${#grep_targets[@]}\" -gt 0 ]; then
  grep_cfg 'brave'
else
  echo 'grep_targets_empty=1'
fi

echo
echo '--- grep -R \"web_search\" -n ---'
if [ \"\${#grep_targets[@]}\" -gt 0 ]; then
  grep_cfg 'web_search'
fi

echo
echo '--- grep -R \"search_provider\" -n ---'
if [ \"\${#grep_targets[@]}\" -gt 0 ]; then
  grep_cfg 'search_provider'
fi

echo
echo '--- printenv | grep -i brave ---'
printenv | grep -i brave || true
echo
echo '--- printenv | grep -i search ---'
printenv | grep -i search || true
echo
echo '--- printenv | grep -i openclaw ---'
printenv | grep -i openclaw || true

container_exists=0
container_env_raw=''
if command -v docker >/dev/null 2>&1 && docker inspect \"\$container_name\" >/dev/null 2>&1; then
  container_exists=1
  container_env_raw=\"\$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \"\$container_name\" 2>/dev/null || true)\"
fi

echo
echo \"--- container env (\$container_name): brave/search/openclaw ---\"
if [ \"\$container_exists\" -eq 1 ]; then
  printf '%s\n' \"\$container_env_raw\" | grep -i brave || true
  printf '%s\n' \"\$container_env_raw\" | grep -i search || true
  printf '%s\n' \"\$container_env_raw\" | grep -i openclaw || true
  echo
  echo '--- openclaw --help (container, first 120 lines) ---'
  docker exec \"\$container_name\" sh -lc 'openclaw --help | sed -n \"1,120p\"' 2>&1 || true
  echo
  echo '--- openclaw agent --help (container, first 160 lines) ---'
  docker exec \"\$container_name\" sh -lc 'openclaw agent --help | sed -n \"1,160p\"' 2>&1 || true
else
  echo \"container_missing=\$container_name\"
fi

IFS=' ' read -r -a config_paths <<< \"\$config_paths_raw\"
found_cfgs=()
for cfg in \"\${config_paths[@]}\"; do
  if [ -f \"\$cfg\" ]; then
    found_cfgs+=(\"\$cfg\")
  fi
done

if [ \"\${#found_cfgs[@]}\" -eq 0 ]; then
  echo \"ОШИБКА: не найден ни один конфиг из списка: \$config_paths_raw\" >&2
  exit 1
fi

echo
echo '--- Конфиги web.search ---'
for cfg in \"\${found_cfgs[@]}\"; do
  provider_now=\"\$(jq -r '.tools.web.search.provider // empty' \"\$cfg\" 2>/dev/null || true)\"
  enabled_now=\"\$(jq -r '.tools.web.search.enabled // empty' \"\$cfg\" 2>/dev/null || true)\"
  brave_key_cfg=\"\$(jq -r '.tools.web.search.brave.apiKey // empty' \"\$cfg\" 2>/dev/null || true)\"
  echo \"config_file=\$cfg provider=\${provider_now:-<empty>} enabled=\${enabled_now:-<empty>} brave_key_in_cfg=\$( [ -n \"\$brave_key_cfg\" ] && echo yes || echo no )\"
done

if [ \"\$mode\" = 'inspect' ]; then
  exit 0
fi

echo
echo \"--- Применение: provider => \$provider_target ---\"
for cfg in \"\${found_cfgs[@]}\"; do
  before_provider=\"\$(jq -r '.tools.web.search.provider // empty' \"\$cfg\" 2>/dev/null || true)\"
  owner_group=\"\$(stat -c '%u:%g' \"\$cfg\" 2>/dev/null || true)\"
  mode_bits=\"\$(stat -c '%a' \"\$cfg\" 2>/dev/null || true)\"
  ts=\"\$(date '+%Y%m%d_%H%M%S_%Z')\"
  backup=\"\${cfg}.bak.\${ts}.web-search\"
  cp -a \"\$cfg\" \"\$backup\"

  tmp=\"\$(mktemp)\"
  if [ \"\$provider_target\" = 'duckduckgo' ] || [ \"\$provider_target\" = 'ddg' ]; then
    jq '
      .tools = (.tools // {}) |
      .tools.web = (.tools.web // {}) |
      .tools.web.search = (.tools.web.search // {}) |
      .tools.web.search.enabled = true |
      del(.tools.web.search.provider) |
      del(.tools.web.search.brave.apiKey)
    ' \"\$cfg\" > \"\$tmp\"
  else
    jq --arg provider \"\$provider_target\" '
      .tools = (.tools // {}) |
      .tools.web = (.tools.web // {}) |
      .tools.web.search = (.tools.web.search // {}) |
      .tools.web.search.enabled = true |
      .tools.web.search.provider = \$provider |
      del(.tools.web.search.brave.apiKey)
    ' \"\$cfg\" > \"\$tmp\"
  fi
  jq -e . \"\$tmp\" >/dev/null
  mv \"\$tmp\" \"\$cfg\"
  [ -n \"\$owner_group\" ] && chown \"\$owner_group\" \"\$cfg\" || true
  [ -n \"\$mode_bits\" ] && chmod \"\$mode_bits\" \"\$cfg\" || true

  after_provider=\"\$(jq -r '.tools.web.search.provider // empty' \"\$cfg\" 2>/dev/null || true)\"
  if [ -z \"\$after_provider\" ]; then
    after_provider='<auto-fallback>'
  fi
  echo \"config_updated=\$cfg from=\${before_provider:-<empty>} to=\${after_provider:-<empty>} backup=\$backup\"
done

echo
echo '--- Очистка BRAVE_API_KEY / SEARCH_PROVIDER=brave в env-файлах ---'
mapfile -t env_files < <(grep -RIl -E '(^|[[:space:]])(BRAVE_API_KEY|SEARCH_PROVIDER|search_provider)[[:space:]]*[:=]' /etc/openclaw /opt/openclaw /root/.openclaw 2>/dev/null || true)
echo \"env_files_found=\${#env_files[@]}\"
edited_env_files=0
for f in \"\${env_files[@]}\"; do
  [ -f \"\$f\" ] || continue
  ts=\"\$(date '+%Y%m%d_%H%M%S_%Z')\"
  backup=\"\${f}.bak.\${ts}.web-search-env\"
  cp -a \"\$f\" \"\$backup\"
  tmp=\"\$(mktemp)\"
  perl -0pe '
    s/^[ \t]*BRAVE_API_KEY[ \t]*[:=].*\n//mg;
    s/^[ \t]*SEARCH_PROVIDER[ \t]*[:=].*\n//mg;
    s/^[ \t]*search_provider[ \t]*[:=].*\n//mg;
  ' \"\$f\" > \"\$tmp\"
  if ! cmp -s \"\$f\" \"\$tmp\"; then
    mv \"\$tmp\" \"\$f\"
    edited_env_files=\$((edited_env_files + 1))
    echo \"env_updated=\$f backup=\$backup\"
  else
    rm -f \"\$tmp\"
    rm -f \"\$backup\"
  fi
done
echo \"env_files_edited=\$edited_env_files\"

echo
echo '--- Проверка runtime web_search (duckduckgo support) ---'
if [ \"\$container_exists\" -eq 1 ]; then
  host_supports_duck=0
  src_supports_duck=0
  dist_supports_duck=0
  container_supports_build=0
  host_src_web_search='/opt/openclaw/src/agents/tools/web-search.ts'
  container_root=\"\$(docker exec \"\$container_name\" sh -lc 'p=\$(command -v openclaw 2>/dev/null || true); if [ -n \"\$p\" ]; then readlink -f \"\$p\" | xargs dirname; fi' 2>/dev/null || true)\"
  container_src_web_search=\"\${container_root}/src/agents/tools/web-search.ts\"
  container_src_dir=\"\$(dirname \"\$container_src_web_search\")\"
  container_dist_glob=\"\${container_root}/dist/redact-snapshot-*.js\"
  container_package_json=\"\${container_root}/package.json\"

  if [ -f \"\$host_src_web_search\" ] && grep -nE 'SEARCH_PROVIDERS.*duckduckgo' \"\$host_src_web_search\" >/dev/null 2>&1; then
    host_supports_duck=1
  fi

  if docker exec \"\$container_name\" sh -lc \"[ -f '\$container_src_web_search' ] && grep -nE 'SEARCH_PROVIDERS.*duckduckgo' '\$container_src_web_search' >/dev/null 2>&1\"; then
    src_supports_duck=1
  fi

  if docker exec \"\$container_name\" sh -lc \"grep -RInE 'tools\\.web\\.search\\.provider.*duckduckgo' \$container_dist_glob >/dev/null 2>&1\"; then
    dist_supports_duck=1
  fi

  if docker exec \"\$container_name\" sh -lc \"[ -f '\$container_package_json' ]\"; then
    container_supports_build=1
  fi

  echo \"container_root=\${container_root:-<unknown>}\"
  echo \"host_supports_duck=\$host_supports_duck\"
  echo \"src_supports_duck=\$src_supports_duck\"
  echo \"dist_supports_duck=\$dist_supports_duck\"
  echo \"container_supports_build=\$container_supports_build\"

  if [ \"\$src_supports_duck\" -eq 0 ] && [ \"\$host_supports_duck\" -eq 1 ] && [ -n \"\$container_root\" ]; then
    echo 'runtime_sync=copy_host_web-search.ts_to_container'
    docker exec \"\$container_name\" sh -lc \"mkdir -p '\$container_src_dir'\"
    docker cp \"\$host_src_web_search\" \"\$container_name:\$container_src_web_search\"
    src_supports_duck=1
  fi

  if [ \"\$src_supports_duck\" -eq 1 ] && [ \"\$dist_supports_duck\" -eq 0 ] && [ \"\$container_supports_build\" -eq 1 ]; then
    echo 'rebuild_reason=dist_outdated_for_duckduckgo'
    build_log=\"\$(mktemp)\"
    set +e
    docker exec \"\$container_name\" sh -lc \"cd '\$container_root' && if command -v pnpm >/dev/null 2>&1; then pnpm build; else npm run build; fi\" >\"\$build_log\" 2>&1
    build_rc=\$?
    set -e
    echo \"rebuild_rc=\$build_rc\"
    if [ \"\$build_rc\" -ne 0 ]; then
      echo 'ОШИБКА: rebuild OpenClaw внутри контейнера завершился ошибкой' >&2
      tail -n 220 \"\$build_log\" || true
      exit 1
    fi
    tail -n 80 \"\$build_log\" || true
  fi
else
  echo 'runtime_check_skipped=container_absent'
fi

echo
echo '--- Перезапуск gateway ---'
restart_method=''
restart_since=\"\$(date -u '+%Y-%m-%dT%H:%M:%SZ')\"
if [ \"\$container_exists\" -eq 1 ]; then
  docker restart \"\$container_name\" >/dev/null
  restart_method=\"docker:\$container_name\"
  stable=0
  for i in \$(seq 1 40); do
    state=\"\$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} {{.RestartCount}}' \"\$container_name\" 2>/dev/null || true)\"
    echo \"container_probe_\${i}=\${state}\"
    st=\"\$(printf '%s' \"\$state\" | awk '{print \$1}')\"
    health=\"\$(printf '%s' \"\$state\" | awk '{print \$2}')\"
    if [ \"\$st\" = 'running' ] && { [ \"\$health\" = 'healthy' ] || [ \"\$health\" = 'none' ] || [ -z \"\$health\" ]; }; then
      stable=1
      break
    fi
    sleep 2
  done
  if [ \"\$stable\" -ne 1 ]; then
    echo 'ОШИБКА: контейнер gateway не вышел в running/healthy после рестарта' >&2
    docker logs --tail 120 \"\$container_name\" 2>&1 || true
    exit 1
  fi
elif command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q '^openclaw'; then
  systemctl restart openclaw
  systemctl is-active --quiet openclaw
  restart_method='systemd:openclaw'
elif command -v pm2 >/dev/null 2>&1; then
  pm2_target=\"\$(pm2 jlist 2>/dev/null | jq -r '.[] | select((.name // \"\" | test(\"openclaw|gateway\"; \"i\")) or (.pm2_env.pm_exec_path // \"\" | test(\"openclaw|gateway\"; \"i\"))) | .name' | head -n1)\"
  if [ -n \"\$pm2_target\" ]; then
    pm2 restart \"\$pm2_target\" >/dev/null
    restart_method=\"pm2:\$pm2_target\"
  fi
fi

if [ -z \"\$restart_method\" ]; then
  echo 'ОШИБКА: не удалось определить способ перезапуска OpenClaw gateway' >&2
  exit 1
fi
echo \"restart_method=\$restart_method\"

echo
echo '--- Тест web_search(\"latest AI news\") ---'
agent_prompt=\"Сделай web_search по запросу: \${search_query}. Верни только provider и 3 URL. Обязательно используй tool web_search.\"
agent_out=\"\$(mktemp)\"
set +e
if [ \"\$container_exists\" -eq 1 ]; then
  docker exec \"\$container_name\" openclaw agent --to +10000000001 --message \"\$agent_prompt\" --json --timeout 180 >\"\$agent_out\" 2>&1
  agent_rc=\$?
else
  openclaw agent --to +10000000001 --message \"\$agent_prompt\" --json --timeout 180 >\"\$agent_out\" 2>&1
  agent_rc=\$?
fi
set -e
echo \"web_search_test_agent_rc=\$agent_rc\"

if [ \"\$agent_rc\" -ne 0 ]; then
  echo 'ОШИБКА: тестовый вызов openclaw agent завершился с ошибкой' >&2
  sed -n '1,200p' \"\$agent_out\" || true
  exit 1
fi

agent_json=\"\$(sed -n '/^[[:space:]]*{/,\$p' \"\$agent_out\")\"
if [ -z \"\$agent_json\" ]; then
  agent_json=\"\$(cat \"\$agent_out\")\"
fi

if printf '%s\n' \"\$agent_json\" | grep -qi 'missing_brave_api_key'; then
  echo 'ОШИБКА: web_search вернул missing_brave_api_key после фикса' >&2
  printf '%s\n' \"\$agent_json\" | sed -n '1,200p'
  exit 1
fi

if ! printf '%s\n' \"\$agent_json\" | grep -qi 'web_search'; then
  echo 'ОШИБКА: openclaw agent не вызвал tool web_search в тестовом прогоне' >&2
  printf '%s\n' \"\$agent_json\" | sed -n '1,200p'
  exit 1
fi

provider_seen=\"\$(printf '%s\n' \"\$agent_json\" | jq -r '.. | .provider? // empty' 2>/dev/null | grep -E 'duckduckgo|brave|perplexity|grok|gemini|kimi' | head -n1 || true)\"
urls_from_json=\"\$(printf '%s\n' \"\$agent_json\" | jq -r '.. | .url? // empty' 2>/dev/null | sed '/^$/d' | head -n 5 || true)\"
if [ -z \"\$urls_from_json\" ]; then
  urls_from_json=\"\$(printf '%s\n' \"\$agent_json\" | grep -Eo 'https?://[^\"[:space:]]+' | head -n 5 || true)\"
fi
if [ -z \"\$urls_from_json\" ]; then
  echo 'ОШИБКА: web_search не вернул валидные ссылки в ответе агента' >&2
  printf '%s\n' \"\$agent_json\" | sed -n '1,220p'
  exit 1
fi

echo \"web_search_test_provider=\${provider_seen:-<unknown>}\"
echo 'web_search_test_status=ok'
echo 'web_search_test_urls_begin'
printf '%s\n' \"\$urls_from_json\"
echo 'web_search_test_urls_end'

if [ \"\$container_exists\" -eq 1 ]; then
  if docker logs --since \"\$restart_since\" --tail 300 \"\$container_name\" 2>&1 | grep -qi 'missing_brave_api_key'; then
    echo 'ОШИБКА: в логах после рестарта найден missing_brave_api_key' >&2
    docker logs --since \"\$restart_since\" --tail 300 \"\$container_name\" 2>&1 | grep -i 'missing_brave_api_key' || true
    exit 1
  fi
fi

echo
echo '--- Итоговая конфигурация ---'
for cfg in \"\${found_cfgs[@]}\"; do
  provider_now=\"\$(jq -r '.tools.web.search.provider // empty' \"\$cfg\" 2>/dev/null || true)\"
  if [ -z \"\$provider_now\" ]; then
    provider_now='<auto-fallback>'
  fi
  echo \"provider_final=\${provider_now:-<empty>} config_file=\$cfg\"
done
"
}

case "$MODE" in
  inspect)
    run_inspect
    ;;
  inspect-code)
    run_inspect_code
    ;;
  show-file)
    run_show_file "$@"
    ;;
  list-files)
    run_list_files "$@"
    ;;
  grep)
    run_grep "$@"
    ;;
  remote-exec)
    run_remote_exec "$@"
    ;;
  web-search-inspect)
    run_web_search_provider inspect
    ;;
  web-search-apply|web-search-fix)
    run_web_search_provider apply
    ;;
  *)
    fail "Неизвестный режим: $MODE (доступно: inspect, inspect-code, show-file, list-files, grep, remote-exec, web-search-inspect, web-search-apply, web-search-fix)"
    ;;
esac
