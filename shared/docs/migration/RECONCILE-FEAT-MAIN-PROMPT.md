# Сведение feat/global-sales-dashboard ↔ main (план + промт для другого треда)

> Снято 2026-06-26. Задача — финально свести feat-линию с main. **Раньше это был «монстр» (179/23 коммита, 1631 файл), но reconcile уже частично сделан** (ветка `chore/reconcile-main-feat` влита в main ~17.06). Сейчас расхождение маленькое и мержится чисто.

## Текущая картина (факты на 26.06)
- merge-base `main ↔ feat/global-sales-dashboard` = `f29c61b` (24.06).
- **feat впереди main на 38 коммитов** — все SCC (движок аудита сделок: умные задачи, радар застрявших, калибровка score, внешний контекст, терминальные статусы встреч).
- **main впереди feat на 8** — repoint TimeWeb→Hetzner (#124), cce-INN-фикс (#118), claude-state-sync, merge-коммиты.
- **Тестовый мерж в ОБЕ стороны: 0 конфликтов** (`git merge --no-commit` exit 0).
- Репо использует **merge-commit** для feat→main (PR #110/111/119 — не squash).

## План (3 шага)
1. **feat → main** (основное): PR `feat/global-sales-dashboard` → `main`, влить **merge-commit** (не squash — сохранить 38 коммитов SCC-истории).
2. **Догнать TimeWeb-репоинт на feat-only файлах**: PR #124 чинил только файлы, что были в main. Feat-only файлы (как `belberry/sales/sales_command_center/PART-B-LEV-DEPLOY-RUNBOOK.md`) приедут в main **со старыми ссылками на TimeWeb** (72.56.83.251 / cloudbot-ssh-proxy). После мержа — пересвипнуть main и репойтнуть остатки на `188.34.206.115` / `cloudbot-hz`. (Готовая правка PART-B лежит в ветке `chore/repoint-timeweb-hetzner`.)
3. **Синхронизировать feat с main** обратно (чтобы не копить новую дивергенцию): после п.1 либо fast-forward `feat` к `main`, либо мерж `main→feat`. Дальше вести SCC прямо в main или держать feat синхронной.

## Подводные камни
- **Деплой-пайплайн Льва/Ларисы** (`cloudbot/infra/orchestrator/workflows/sales_agent_deploy.sh`) собирает релиз из **RELEASE_BRANCH = feat/global-sales-dashboard** (см. память `project-belberry-global-sales-dashboard`, Часть B). После сведения — решить: переключить деплой на `main` или держать feat в синхроне. Не ломать живой деплой (раннтайм Льва — релиз `feat_global-sales-dashboard_*`).
- **SCC/GSD-сервер** (178.104.222.163) и **cloudbot-сервер** (188.34.206.115) рантайм уже исправлены живьём — это про source-of-truth, не про рантайм.
- Другие feat-линии (`fix/cce-foreign-inn-guard`, `fix/cce-foreign-inn-guard-main`) — отдельные мелкие ветки, не блокируют это сведение.
- `chore/reconcile-main-feat` и `feat/marketing-dashboard-to-main` — уже влиты/устарели (0 ahead), не трогать.

---

## ПРОМТ ДЛЯ ИСПОЛНИТЕЛЯ (другой тред / Codex / свежий Claude)

```
Задача: финально свести ветку feat/global-sales-dashboard в main (репо Johnnie13Walker/VibeCoding). Reconcile уже почти сделан — осталось влить 38 SCC-коммитов; мерж ЧИСТЫЙ (проверено: git merge --no-commit в обе стороны = 0 конфликтов на 26.06).

Контекст и подводные камни — в shared/docs/migration/RECONCILE-FEAT-MAIN-PROMPT.md (прочитай целиком).

Сделай по шагам, с подтверждением после каждого:

1. Свежесть: git fetch origin. Перепроверь, что merge feat→main всё ещё чист:
   git worktree add --detach /tmp/mt origin/main && cd /tmp/mt
   git merge --no-commit --no-ff origin/feat/global-sales-dashboard ; git diff --name-only --diff-filter=U
   (0 файлов = чисто; git merge --abort; git worktree remove --force /tmp/mt)
   Если появились конфликты — СТОП, выведи список, не разрешай вслепую.

2. Влей feat→main MERGE-коммитом (НЕ squash — сохрани историю 38 коммитов):
   gh pr create --base main --head feat/global-sales-dashboard --title "chore: свести feat/global-sales-dashboard в main (SCC audit)" --body "..."
   gh pr merge <N> --merge --delete-branch=false

3. После мержа — пересвипни main на остатки TimeWeb (feat-only файлы приехали со старыми ссылками):
   git fetch origin && git grep -nE "72\.56\.83\.251|cloudbot-ssh-proxy" origin/main -- '*.sh' '*.py' '*.md' '*.env'
   Репойтни в ИСПОЛНЯЕМЫХ файлах/гайдах: 72.56.83.251 → 188.34.206.115, cloudbot-ssh-proxy → cloudbot-hz.
   (Прежде всего PART-B-LEV-DEPLOY-RUNBOOK.md — готовая правка есть в ветке chore/repoint-timeweb-hetzner, можно cherry-pick'нуть её коммит правки PART-B.)
   НЕ трогай историч. записи: shared/docs/migration/*, CODEX-DEPLOY-PROMPT.md, incident_*, *_audit_*MSK.md, Daily/Logs/Archive.
   Коммит атомарный, PR в main, merge.

4. Синхронизируй feat обратно к main (чтобы не копить дивергенцию):
   git merge main → feat (или fast-forward), push feat.

ОГРАНИЧЕНИЯ:
- НЕ ломать живой деплой Льва/Ларисы (sales_agent_deploy.sh, RELEASE_BRANCH=feat/global-sales-dashboard). Если будешь менять RELEASE_BRANCH на main — отдельно и явно, с проверкой.
- Конфликты разрешать осмысленно (SCC-код feat — приоритет для SCC-файлов; main — для belberry/cce/инфра). При сомнении — СТОП.
- gh pr merge в main — если харнесс блокирует, дай команду пользователю на paste.
- Все времена МСК. Секреты не печатать.
- Отчёт блоком ВЫХОД: что влито (SHA merge-коммита), что репойтнуто, состояние feat vs main после (ahead/behind), что отложено.
```
