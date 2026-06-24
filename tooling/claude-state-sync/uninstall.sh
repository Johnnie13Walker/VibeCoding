#!/usr/bin/env bash
# Откат автосинхрона: выгружает launchd, убирает наши хуки из settings.json,
# удаляет скопированные файлы. Прочие (GSD-фреймворк) хуки не трогает.
set -euo pipefail
CLAUDE="$HOME/.claude"
LA="$HOME/Library/LaunchAgents"

launchctl unload "$LA/com.user.state-drift-watchdog.plist" 2>/dev/null || true
rm -f "$LA/com.user.state-drift-watchdog.plist"
rm -f "$CLAUDE/commands/wrap.md" "$CLAUDE/hooks/state-drift-check.sh" "$CLAUDE/hooks/wrap-guard.sh"
rm -f "$CLAUDE/.wrap-pending" "$CLAUDE/.midnight-ref" "$CLAUDE/drift-report.txt"

node - "$CLAUDE/settings.json" <<'NODE'
const fs = require('fs'); const p = process.argv[2];
let c = {}; try { c = JSON.parse(fs.readFileSync(p, 'utf8')); } catch { process.exit(0); }
const strip = (evt) => {
  if (!c.hooks || !c.hooks[evt]) return;
  c.hooks[evt] = c.hooks[evt].filter(e => !JSON.stringify(e).match(/state-drift-check\.sh|wrap-guard\.sh/));
  if (c.hooks[evt].length === 0) delete c.hooks[evt];
};
strip('SessionStart'); strip('SessionEnd');
fs.writeFileSync(p, JSON.stringify(c, null, 2));
console.log('settings.json: наши хуки убраны');
NODE

echo "✓ Удалено. /wrap, дрейф-хук, guard и сторож сняты."
