# claude-state-sync — автосинхрон память / Obsidian / git

Бэкап и воспроизводимая установка системы, которая не даёт «утечь» состоянию проекта:
чтобы итоги работы попадали в **память Claude** (`~/.claude/.../memory/`), **Obsidian**
(`STATUS.md` + `Daily/`) и **git** — и ничего не оставалось незаписанным.

Файлы живут в `~/.claude` / `~/Library/LaunchAgents` (вне git) — эта папка их версионирует.

## Состав

| Файл | Куда ставится | Что делает |
|---|---|---|
| `commands/wrap.md` | `~/.claude/commands/wrap.md` | команда `/wrap` — в конце работы сводит сессию в память + Obsidian + git-гигиену (опасное — merge/push в main, деплой — не делает сама) |
| `hooks/state-drift-check.sh` | `~/.claude/hooks/` | хук `SessionStart`: в начале сессии показывает дрейф (незакоммиченное/незапушенное) и маркер «не сведено». Также ядро сторожа (режим `full`) |
| `hooks/wrap-guard.sh` | `~/.claude/hooks/` | хук `SessionEnd`: если были код-коммиты, но память/Obsidian не трогались → ставит маркер `~/.claude/.wrap-pending` (его громко покажет следующий SessionStart) |
| `launchd/com.user.state-drift-watchdog.plist` | `~/Library/LaunchAgents/` | сторож: ежедневно **09:30 МСК** прогон `state-drift-check.sh full` → `~/.claude/drift-report.txt` + macOS-уведомление |

Хуки регистрируются в `~/.claude/settings.json` (см. `settings.hooks.json` — снимок наших
записей; `install.sh` мерджит их идемпотентно, не трогая прочие хуки).

## Как это закрывает «что не сохранено»
- **Ловит в момент:** `SessionEnd`-guard замечает «работали, но не свели» → маркер.
- **Напоминает:** следующий `SessionStart` громко («🔴 Предыдущая сессия не сведена») + сторож в 09:30.
- **Сводит:** ты запускаешь `/wrap` (одна команда) → пишет во все три слоя и снимает маркер.
- **Граница:** запись в память/Obsidian требует суждения LLM → `/wrap` ручная; автоматизирована
  только детекция/напоминание. Merge/push в `main` и деплой — никогда автоматически.

## Установка
```bash
bash tooling/claude-state-sync/install.sh
```
Идемпотентно (повторный запуск не дублирует). Откат: `bash tooling/claude-state-sync/uninstall.sh`.

## Портируемость
Пути ВНУТРИ хук-скриптов захардкожены под этого пользователя:
`REPO=/Users/pro2kuror/Desktop/VibeCoding`, `VAULT=…/Cloudbot-Vault`, `MEMDIR=…/memory`.
На другой машине/юзере поправь их в `hooks/state-drift-check.sh` и `hooks/wrap-guard.sh`
(в `settings.json` пути подставляются через `$HOME` автоматически).
