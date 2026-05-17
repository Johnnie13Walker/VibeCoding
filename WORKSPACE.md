# WORKSPACE — Belberry CRM enrichment

> **AI agent context anchor.** Прочитай этот файл первым делом в новой сессии — он даёт canonical paths, env, и точки входа, чтобы не терять путь после context compression.

## Canonical paths

| Имя | Путь (canonical short) |
|-----|------------------------|
| Worktree root | `~/work-crm-enrich/` (symlink на `/Users/pro2kuror/Desktop/VibeCoding/belberry/bitrix24/.worktrees/Обогащение данных CRM`) |
| Модуль | `~/work-crm-enrich/belberry/bitrix24/crm_company_enrich/` |
| venv | `~/work-crm-enrich/belberry/bitrix24/crm_company_enrich/.venv/` |
| OAuth state Bitrix | `/Users/pro2kuror/Desktop/VibeCoding/shared/config/bitrix24-state/install.latest.json` |
| OAuth sync script | `/Users/pro2kuror/Desktop/VibeCoding/shared/scripts/bitrix-sync-state.sh` |
| Service account (Sheets) | `/Users/pro2kuror/.config/vibecoding/assistant/secrets/finance-director-sheets-903611b799c3.json` |
| Logs (production) | `~/work-crm-enrich/belberry/bitrix24/logs/` |
| Batch state JSON | `~/work-crm-enrich/belberry/bitrix24/logs/enrich_from_sheet_inplace_state.json` |
| tmp dir для batch | `/tmp/enrich_inplace/` |

**ВСЕГДА** используй `~/work-crm-enrich/...` пути в командах, не оригинальный длинный с кириллицей.

## Standard cd + pytest

```bash
cd ~/work-crm-enrich/belberry/bitrix24/crm_company_enrich
.venv/bin/python -m pytest -q
```

## Production system

- **Bitrix portal:** belberrycrm.bitrix24.ru
- **Sheet ID:** `13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4`
- **Главный таб задачи:** `Телемаркетинг без реквизитов` (gid=1318170868, 1207 строк)
- **OAuth Bitrix expires ~8h** — перед длинным batch обязательно `bash /Users/pro2kuror/Desktop/VibeCoding/shared/scripts/bitrix-sync-state.sh`

## Главный CLI subcommand

```bash
cd ~/work-crm-enrich/belberry/bitrix24/crm_company_enrich
.venv/bin/python -m crm_company_enrich.cli enrich-from-sheet-inplace \
  --sheet-id 13L0gqwkNzrWacYeI5TzkOxZuRuXn5bBCtfxx-uzHH_4 \
  --tab 'Телемаркетинг без реквизитов' \
  --skip-bp --live --max-duration-min 360
```

- По умолчанию dry-run; `--live` — реальный write в Bitrix + Sheets.
- Resume-safe (пропускает строки с заполненным col K status).
- `--cron` — kill switch вне окна 00:00-08:00 MSK.

## Output column layout таба

```
A  Сделка (название, hyperlink на Bitrix-сделку)
E  Компания в сделке (или 'Сделка без привязки к компании')
F  ИНН (исходно пусто)
H  Причина / результат (для людей)
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

Цвета строк: `ENRICHED/PARTIAL` → светло-зелёный, `FAILED/REJECTED/EXCEPTION` → красный, `SKIPPED/UNKNOWN` → жёлтый.

## Связанные memory (Claude)

- `project-belberry-2026-05-17-session` — sprint история
- `project-belberry-company-enrich` — общая архитектура enrich
- `feedback-codex-executes-live` — кто запускает prod writes
- `feedback-claude-local-code-when-codex-confuses` — pattern локальной работы Claude
- `reference-bitrix24-access` — OAuth flow и доступы

## Правила работы для агентов

1. **Спросить путь — нет, есть.** Canonical path — `~/work-crm-enrich/`. Не делай `find /Users -name 'X.py'`.
2. **Спросить какой Sheet — нет, есть.** ID и tab выше.
3. **Спросить OAuth — нет, refresh скриптом.** Путь выше.
4. **Прежде чем `--live` на 1000+ строк** — обязательно smoke на 5 строках через `--limit 5 --live` и **открыть Bitrix UI глазами**, что компания/сделка реально обогащены.
5. **Bug found на проде → kill batch немедленно** через `kill $(cat /tmp/enrich_inplace/full_batch.pid)`, fix локально, push hotfix, очистить мусор, потом продолжать.
