#!/usr/bin/env bash
# Установка автосинхрона память/Obsidian/git в ~/.claude (+ launchd-сторож).
# Идемпотентно: повторный запуск не дублирует хуки. Пути ВНУТРИ хук-скриптов
# (REPO=/Users/pro2kuror/Desktop/VibeCoding, VAULT, MEMDIR) захардкожены под этого
# пользователя — на другой машине/юзере поправь их в state-drift-check.sh и wrap-guard.sh.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="$HOME/.claude"
LA="$HOME/Library/LaunchAgents"

mkdir -p "$CLAUDE/commands" "$CLAUDE/hooks" "$LA"
cp "$HERE/commands/wrap.md" "$CLAUDE/commands/"
cp "$HERE/hooks/state-drift-check.sh" "$HERE/hooks/wrap-guard.sh" "$CLAUDE/hooks/"
chmod +x "$CLAUDE/hooks/state-drift-check.sh" "$CLAUDE/hooks/wrap-guard.sh"
cp "$HERE/launchd/com.user.state-drift-watchdog.plist" "$LA/"

# Идемпотентный мердж хуков в settings.json (прочие хуки не трогаем)
node - "$CLAUDE/settings.json" <<'NODE'
const fs = require('fs'); const p = process.argv[2];
let c = {}; try { c = JSON.parse(fs.readFileSync(p, 'utf8')); } catch {}
c.hooks = c.hooks || {};
const ensure = (evt, file, timeout) => {
  c.hooks[evt] = c.hooks[evt] || [];
  if (JSON.stringify(c.hooks[evt]).includes(file)) return;
  c.hooks[evt].push({ hooks: [{ type: 'command', command: `bash "${process.env.HOME}/.claude/hooks/${file}"`, timeout }] });
};
ensure('SessionStart', 'state-drift-check.sh', 10);
ensure('SessionEnd', 'wrap-guard.sh', 15);
fs.writeFileSync(p, JSON.stringify(c, null, 2));
console.log('settings.json: хуки SessionStart/SessionEnd добавлены (идемпотентно)');
NODE

# launchd-сторож (ежедневно 09:30 МСК)
launchctl unload "$LA/com.user.state-drift-watchdog.plist" 2>/dev/null || true
launchctl load -w "$LA/com.user.state-drift-watchdog.plist" 2>/dev/null || true

echo "✓ Установлено: /wrap + SessionStart-дрейф-хук + SessionEnd-guard + launchd-сторож (09:30 МСК)."
echo "  Тест сторожа:  launchctl start com.user.state-drift-watchdog && cat ~/.claude/drift-report.txt"
echo "  Тест дрейфа:   bash ~/.claude/hooks/state-drift-check.sh"
