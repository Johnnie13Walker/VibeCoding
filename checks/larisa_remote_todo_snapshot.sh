#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/larisa_remote_snapshot_check.XXXXXX")"
trap 'rm -rf "$tmp_root"; cleanup_larisa_remote_todo_snapshot' EXIT

mkdir -p "$tmp_root/ops"
cat > "$tmp_root/ops/ssh_happ.sh" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

target="${1:-}"
shift || true
cmd="$*"

[[ "$target" == "primary" ]] || exit 10
[[ "$cmd" == *'host_state_dir="/root${state_dir#/home/node}"'* ]] || exit 11
[[ "$cmd" == *'snapshot_path="$host_state_dir/tasks_snapshot.json"'* ]] || exit 12

printf '%s\n' '{"generatedAt":"2026-04-14T05:00:11.393Z","timezone":"Europe/Moscow","today":"2026-04-14","tasks":[]}'
SCRIPT
chmod +x "$tmp_root/ops/ssh_happ.sh"

unset LARISA_TODO_SNAPSHOT_FILE TODO_TASKS_SNAPSHOT_FILE LARISA_TODO_STATE_DIR TODO_STATE_DIR LARISA_TODO_TOKEN TODO_TOKEN || true
prepare_larisa_remote_todo_snapshot "$tmp_root"

if [[ -z "${LARISA_TODO_STATE_DIR:-}" ]]; then
  echo "LARISA_TODO_STATE_DIR не установлен" >&2
  exit 20
fi

snapshot_file="$LARISA_TODO_STATE_DIR/tasks_snapshot.json"
[[ -f "$snapshot_file" ]] || { echo "snapshot не создан" >&2; exit 21; }
grep -Fq '"today":"2026-04-14"' "$snapshot_file" || { echo "snapshot содержит неожиданные данные" >&2; exit 22; }

echo "Итог: ОК"
