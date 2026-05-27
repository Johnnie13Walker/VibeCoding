# AGENTS.md — crm_company_enrich (Belberry CRM Enrichment)

> **Module-specific instructions для AI-агентов.** Дополняет и **переопределяет** общий `AGENTS.md` в корне репо для этого модуля.

## TL;DR — bootstrap

1. Канонический путь работы: **`~/work-crm-enrich/belberry/bitrix24/crm_company_enrich/`** (через symlink). НЕ оригинальный длинный путь с кириллицей.
2. Прочитай **в этом порядке** перед любыми действиями:
   - `~/work-crm-enrich/WORKSPACE.md` — paths, venv, git workflow, базовая ветка `main`, output column layout
   - `~/work-crm-enrich/CODEX_PROMPT_PREFIX.md` — формат промта и шаблон отчёта
   - `/Users/pro2kuror/Documents/Cloudbot-Vault/09-Projects/belberry-crm-enrichment/STATUS.md` — текущий sprint
   - `/Users/pro2kuror/Documents/Cloudbot-Vault/09-Projects/belberry-crm-enrichment/AI-AGENTS-SETUP.md` — полная карта правил
3. Python — **ТОЛЬКО venv**: `~/work-crm-enrich/belberry/bitrix24/crm_company_enrich/.venv/bin/python` (3.11.15 через uv). НЕ системный `/usr/bin/python3` (3.9).
4. Никаких `find /Users/...` если потерял контекст после compression — вернись к `WORKSPACE.md`.

## Override общих правил для этого модуля

В корневом `/Users/pro2kuror/Desktop/VibeCoding/AGENTS.md` есть фраза «`main` — стабильная версия, `dev` — ветка разработки, работа через feature-ветки». **Для модуля `crm_company_enrich` правило отличается:**

- **Ветки `dev` нет.** Работа ведётся через feature/fix-ветки **прямо от `main`**, PR base = `main`.
- **Squash merge** обязателен (каждый PR = 1 коммит в main). По образцу всех PR #10-#22.
- **`--delete-branch=false`** — feature-ветка сохраняется как backup точка после merge.
- **Backup-ветки (исторические, НЕ трогать):** `feature/telemarketing-automations`, `feature/enrich-from-sheet`, `feature/director-inn-enrichment`, `*-backup`.

## Canonical paths

| Имя | Path |
|-----|------|
| Модуль | `~/work-crm-enrich/belberry/bitrix24/crm_company_enrich/` |
| Venv | `~/work-crm-enrich/belberry/bitrix24/crm_company_enrich/.venv/` |
| Worktree root | `~/work-crm-enrich/` (symlink на `/Users/pro2kuror/Desktop/VibeCoding/belberry/bitrix24/.worktrees/Обогащение данных CRM`) |
| OAuth state Bitrix | `/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json` |
| OAuth refresh script | `/Users/pro2kuror/Desktop/VibeCoding/shared/scripts/bitrix-sync-state.sh` |
| Service account (Sheets) | `/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json` |
| Production logs | `~/work-crm-enrich/belberry/bitrix24/logs/` |
| Batch state JSON | `~/work-crm-enrich/belberry/bitrix24/logs/enrich_from_sheet_inplace_state.json` |
| Tmp dir batch | `/tmp/enrich_inplace/` |
| STATUS.md в vault | `/Users/pro2kuror/Documents/Cloudbot-Vault/09-Projects/belberry-crm-enrichment/STATUS.md` |

## Production system

- **Bitrix portal:** `belberrycrm.bitrix24.ru`
- **Sheet ID:** `13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4`
- **Главный таб задачи:** `Телемаркетинг без реквизитов` (gid=1318170868, 1207 строк)
- **OAuth Bitrix expires ~8h** — перед длинным batch обязательно:
  `bash /Users/pro2kuror/Desktop/VibeCoding/shared/scripts/bitrix-sync-state.sh`

## Ручной workflow: бренд и сфера в company + deal

При ручном качественном обогащении строк из Google Sheets обязательно
синхронизировать бренд проекта и сферу деятельности на обоих уровнях:

- компания: `UF_CRM_1737098476975` / `UF_CRM_684FE59BA3C8C` + `INDUSTRY`
- сделка C50: `UF_CRM_1721661506` + `UF_CRM_6179712C57A4D`

Перед удалением строки из Sheet сделать read-back компании и сделки и явно
проверить, что бренд/сфера заполнены одинаково по смыслу. Если заполнена только
компания или только сделка — строка не считается обработанной.

Классификация:

- медклиника / стоматология / ветклиника → бренд `Belberry`, сфера `Медицина`
- медицинские товары / оборудование / реабилитационные товары → сфера
  `Медицинские товары и оборудование` в компании и сделке
- если связь сайт ↔ юрлицо сомнительна или компания закрыта/ликвидируется —
  бренд и сферу не угадывать; строку оставить красной с причиной

Удалять обработанную строку нужно только через guard-команду:

```bash
cd ~/work-crm-enrich/belberry/bitrix24/crm_company_enrich
.venv/bin/python -m crm_company_enrich.cli delete-sheet-row-guarded \
  --row-number <N> --deal-id <deal_id> --company-id <company_id> --live
```

Прямой `deleteDimension` допустим только для аварийного ручного ремонта после
явного read-back brand/industry parity.

## Git workflow для этого модуля

```bash
# 1. Свежий main
cd ~/work-crm-enrich
git checkout main && git pull --ff-only origin main

# 2. Новая ветка (префикс fix|feat|chore|test|docs|refactor)
git checkout -b <type>/<short-kebab-name>

# 3. Правки + тесты
cd ~/work-crm-enrich/belberry/bitrix24/crm_company_enrich
.venv/bin/python -m pytest -q     # должно быть зелёное

# 4. Коммит
git add <конкретные файлы>
git commit -m "<type>(<scope>): <imperative summary>

<body — why, не what; references на memory/issues>

Co-Authored-By: <agent-name> <noreply@anthropic.com>"

# 5. Push + PR + squash merge
cd ~/work-crm-enrich
git push -u origin <branch-name>
gh pr create --base main --head <branch-name> \
  --title "..." --body "..."
gh pr merge $(gh pr list --head <branch-name> --json number -q '.[0].number') \
  --squash --delete-branch=false

# 6. Обратно на main + pull
git checkout main && git pull --ff-only origin main
```

**Запрещено:**
- `git push --force` в main или feature-ветки которые в активных PR
- `git reset --hard` без stash, если есть uncommitted работа
- `gh pr merge --merge` или `--rebase` — только `--squash`
- Удаление backup-веток
- Push если `pytest` red

## Main CLI subcommand

```bash
cd ~/work-crm-enrich/belberry/bitrix24/crm_company_enrich
.venv/bin/python -m crm_company_enrich.cli enrich-from-sheet-inplace \
  --sheet-id 13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4 \
  --tab 'Телемаркетинг без реквизитов' \
  --skip-bp --live --max-duration-min 360
```

- По умолчанию dry-run; `--live` — реальный write в Bitrix + Sheets.
- `--skip-bp` — без запуска BP-шаблонов (быстрый mode, ~14s/строка).
- `--cron` — kill switch вне окна 00:00-08:00 MSK.
- Resume-safe: пропускает строки с заполненным col K status.

## Output column layout (для in-place writeback)

```
A  Сделка (название + hyperlink на Bitrix-сделку)
E  Компания в сделке (или 'Сделка без привязки к компании')
F  ИНН (изначально пусто)
G  Оборот компании
H  Причина / результат (human-readable)
I  deal_id (output)
J  enriched_at
K  status (ENRICHED/PARTIAL/SKIPPED/FAILED/REJECTED/EXCEPTION)
L  updated_fields
M  company_id
N  company_title
O  company_inn
P  company_revenue
Q  deal_stage
R  deal_assignee
S  director_inn
T  rejected_reason
U  error
```

Цвета строк по `final_status`:
- `ENRICHED`/`PARTIAL` → светло-зелёный (`#d9ead3`)
- `FAILED`/`REJECTED`/`EXCEPTION` → светло-красный (`#f4cccc`)
- `SKIPPED`/`UNKNOWN` → светло-жёлтый (`#fff2cc`)

## Production safety rules

1. **Smoke перед full batch обязателен.** Никаких 1000+-строковых `--live` запусков без предварительного:
   - `--limit 5 --live --skip-bp` (5 строк)
   - **ОТКРЫТЬ Bitrix UI** глазами, проверить что enrichment реальный (ИНН в карточке, не `DRY_RUN_COMPANY`)
2. **Background batch** запускать через `nohup` + сохранять PID в `/tmp/enrich_inplace/full_batch.pid`.
3. **Kill batch при обнаружении проблем:**
   ```bash
   kill $(cat /tmp/enrich_inplace/full_batch.pid)
   ```
4. **Мониторинг live batch** — через state JSON каждые 15-30 минут, не чаще:
   ```bash
   cat ~/work-crm-enrich/belberry/bitrix24/logs/enrich_from_sheet_inplace_state.json \
     | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'processed={d.get(\"processed\")}/{d.get(\"to_process\")} failed={d.get(\"failed\")} status={d.get(\"status_counts\")}')"
   ```
5. **При баге на проде → kill batch → fix локально → PR → cleanup мусора → relaunch.**

## Pipeline architecture (для контекста)

Orchestrator `enrich_company_full.run()` — 19-step pipeline:

```
RESOLVE → FIND_SITE → FIND_INN → CHECK_INN_DUPLICATE → APPLY_INN →
RUN_BP → VERIFY → SYNC_COMPANY → ADDRESS_SYNC → CHECK_BANKRUPTCY →
RANK_DEAL_VIABILITY → RESOLVE_DEAL → CREATE_DEAL → SYNC_DEAL →
REVIVE_DEAL → DEDUPE_CONTACTS → ENRICH_DIRECTOR_INN →
TELEMARKETING_DEDUPE_SCOPED → WRITE_AUDIT → RETURN_OUTCOME
```

**Inputs (любой из/несколько):** `company_id`, `deal_id`, `inn`, `url`.
**Защиты:** не создавать пустую компанию без ИНН, директорские контакты protected, dry-run полностью read-only.

## Common pitfalls (что НЕ делать)

1. **`find /Users/...`** для поиска файлов после context compression.
   → Вернись к `~/work-crm-enrich/WORKSPACE.md`.
2. **`brew install python@X`** или другая работа с системным Python.
   → Venv в `~/work-crm-enrich/.../crm_company_enrich/.venv/` имеет 3.11.15 — используй его.
3. **PR base=`feature/telemarketing-automations` (или другая backup ветка)**.
   → Base всегда `main`.
4. **`git cherry-pick` с brushen ветки** — даст 30+ конфликтов.
   → File-by-file через `git checkout <branch> -- <path>`, потом адаптация.
5. **Mock-driven dev** — написать модуль с тестами на mocks, не запускать на real API.
   → Spike-prototype первым на real API (30 минут observation), потом структурированный код.
6. **Phase C smoke пропустить** под давлением «давай быстрее».
   → 5-строковый live + Bitrix UI глазами обязателен. Без этого не запускать full batch.
7. **`dry_run=True` + writeback в Sheets** — засирает prod-таб мусором.
   → Dry-run должен быть полностью read-only в ВСЕХ output sink'ах. Регрессионный тест есть.
8. **Создать "Компания без названия"** когда orchestrator не находит ИНН.
   → Запрет в `_step_resolve`: без ИНН → SKIPPED/`no_inn_no_company`, компания не создаётся.

## Тесты — обязательное условие

- pytest зелёный **до** push: `cd ~/work-crm-enrich/belberry/bitrix24/crm_company_enrich && .venv/bin/python -m pytest -q`
- На момент 2026-05-17: 534+ тестов
- Новый функционал = новые тесты в `tests/test_<имя>.py`
- При адаптации существующих тестов под новое поведение — explicit reason в commit body

## Финальный отчёт после задачи — обязательный формат

```markdown
# REVIEW — <branch-name>

## КОНТЕКСТ
- Worktree: ~/work-crm-enrich (canonical)
- Базовая ветка: main @ <SHA>
- Дата/время: <ISO start> → <ISO end>

## КОММИТЫ
1. `<SHA>` <commit message subject>

## ЧТО ИЗМЕНЕНО
- file1.py — что изменилось, почему
- file2.py — ...

## ТЕСТЫ
До: N passed
После: M passed (+K новых)

## КОМАНДЫ ВОСПРОИЗВЕДЕНИЯ
- pytest: cd ~/work-crm-enrich/belberry/bitrix24/crm_company_enrich && .venv/bin/python -m pytest -q
- smoke: <CLI команда если применимо>

## ЧТО НЕ ЗАПУСКАЛОСЬ
- <explicit list>

## ОТКРЫТЫЕ ВОПРОСЫ / РИСКИ
- <TODO в коде>
- <блокеры>

## git log -3
<копия>

## PR URL
<https://github.com/Johnnie13Walker/VibeCoding/pull/N>
```

Этот блок пользователь копирует в Claude для финального ревью до merge.

## Связано

- `~/work-crm-enrich/WORKSPACE.md` — paths + git workflow + output cols + правила (читать ПЕРВЫМ)
- `~/work-crm-enrich/CODEX_PROMPT_PREFIX.md` — короткий prefix-блок + шаблон задачи
- `/Users/pro2kuror/Documents/Cloudbot-Vault/09-Projects/belberry-crm-enrichment/STATUS.md` — текущий sprint
- `/Users/pro2kuror/Documents/Cloudbot-Vault/09-Projects/belberry-crm-enrichment/AI-AGENTS-SETUP.md` — полная карта правил для AI
- Корневой `/Users/pro2kuror/Desktop/VibeCoding/AGENTS.md` — общие правила Cloudbot (для этого модуля override'нуты выше)
