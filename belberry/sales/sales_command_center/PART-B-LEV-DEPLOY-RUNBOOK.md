# RUNBOOK — закрепление «Опер»-модели легаси-Льва (Часть B) деплоем из `feat/global-sales-dashboard`

> Цель: запечь коммит **4ada773** («Опер» = реальные рабочие минуты) в источник снапшота
> cloudbot, чтобы живой ручной патч на проде перестал быть временным.
> Подготовлено 2026-06-05. Cloudbot-live write — выполняет пользователь / по явному «сделай сам».

## ⚠️ Почему источник = feat, а НЕ main (разведка 05.06)

- main и feat **разошлись 20.05** (merge-base `3e0ad7b`): feat +179 коммитов, main +23 коммита (PR #34–#57).
- **В `main` НЕТ `cloudbot/` вообще** — миграция cloudbot (28.05) и весь GSD легли только на feat.
  Поэтому деплоить Льва из main НЕЛЬЗЯ (нечего собирать). Единственный носитель `cloudbot/`+4ada773 — **feat/global-sales-dashboard**.
- merge feat→main = 1631 файл в один squash + 6 конфликтов (add/add в crm_deal_merge) → отдельная задача гигиены веток, к Части B отношения не имеет.

## TL;DR контекст (проверено в разведке 05.06)

- Деплой-механизм: [`cloudbot/infra/orchestrator/workflows/sales_agent_deploy.sh`](infra/orchestrator/workflows/sales_agent_deploy.sh) собирает снапшот через `git -C cloudbot archive $RELEASE_COMMIT <runtime_files> | tar` на прод-бокс TimeWeb, кладёт в `/opt/cloudbot-runtime/releases/<RELEASE_ID>`, флипает symlink `current`.
- `RELEASE_BRANCH/RELEASE_COMMIT = git HEAD` репо VibeCoding (через `git -C cloudbot/`). С feat HEAD `8e0cc22` получится `RELEASE_ID = feat_global-sales-dashboard_8e0cc22`. Живой релиз сейчас `dev_3b160ba` (собран до миграции 28.05, ветка `dev` больше не существует).
- Пути в снапшоте корректны (`apps/…` без префикса `cloudbot/`) — проверено `git archive` эмпирически. **Код пайплайна править НЕ нужно.**
- Живой пропатченный `sales_formatter.py` ≡ версии из 4ada773 (diff = только комментарии) → деплой не меняет поведение, лишь делает патч постоянным.
- Авто-деплоя на проде НЕТ → до запуска этого runbook патч держится сам.

## ⚠️ Главный риск и как его снять

Деплой **перезаписывает** `/etc/openclaw/sales_agent.env`, `/etc/cron.d/cloudbot-sales-reports`,
скрипты `/usr/local/bin/cloudbot-sales-*.sh` и флипает `current` для **всего** рантайма (Лариса+Лев).
Если запустить с неполными `SALES_*`, env/cron регенерятся дефолтами → регресс доставки.

**Снятие:** перед деплоем снять текущие живые значения `SALES_*` с прод-бокса и скормить их
деплою — тогда регенерация env/cron = no-op (тот же контент), меняется только код-снапшот.

## Env-контракт деплоя (точный)

Обязательные (`require_env`, иначе падёт на старте):

| Переменная | Значение для cloudbot-бокса |
|---|---|
| `PRIMARY_HOST` | `72.56.83.251` |
| `SSH_USER` | `root` |
| `SSH_KEY_PATH` | `/Users/pro2kuror/.ssh/temp_migration_key` |
| `SSH_PORT` | `22` |
| `SALES_TELEGRAM_CHAT_ID` | из живого `/etc/openclaw/sales_agent.env` |

Желательные (иначе env регенерится дефолтами — снять с живого файла):
`SALES_WEEKLY_TELEGRAM_CHAT_ID`, `SALES_TELEGRAM_OWNER_ID`, `SALES_TELEGRAM_DM_CHAT_ID`,
`SALES_ALERT_TELEGRAM_CHAT_ID`, `SALES_TELEGRAM_BOT_TOKEN_FILE`, `SALES_LOG_FILE`,
`SALES_DAILY_HISTORY_FILE`, `SALES_DEPARTMENT_IDS`, `SALES_DEPARTMENT_NAMES`,
`SALES_EXCLUDED_USER_IDS`, `SALES_EXCLUDED_USER_NAMES`, `SALES_EXCLUDED_USER_MARKERS`.

Cron-расписания (дефолты в скрипте — сверить с живым `/etc/cron.d/cloudbot-sales-reports`):
`SALES_DAILY_CRON_EXPR_UTC` (def `30 6 * * 1-5`), `SALES_CHECK_CRON_EXPR_UTC` (`40 6 * * 1-5`),
`SALES_FOLLOWUP_CRON_EXPR_UTC` (`0 14 * * *`), `SALES_WEEKLY_CRON_EXPR_UTC` (`30 15 * * 5`).

## Шаги

### 0. Предпосылка — быть на feat с 4ada773 (merge в main НЕ нужен)
```bash
cd /Users/pro2kuror/Desktop/VibeCoding
git checkout feat/global-sales-dashboard
git fetch origin && git pull --ff-only origin feat/global-sales-dashboard   # HEAD должен быть 8e0cc22+
# проверить, что Опер-правка на месте:
git show HEAD:cloudbot/apps/lev_petrovich/legacy_sales_agent/sales_formatter.py | grep -n "реальных рабочих минут"
```

### 1. Снять живой env с прод-бокса (резерв + источник значений)
```bash
ssh cloudbot-ssh-proxy 'cp -a /etc/openclaw/sales_agent.env /etc/openclaw/sales_agent.env.bak-$(date +%Y%m%d-%H%M%S-MSK)'
# скопировать значения SALES_* себе в локальный gitignored файл деплоя:
mkdir -p ~/.config/vibecoding/cloudbot
scp -i ~/.ssh/temp_migration_key root@72.56.83.251:/etc/openclaw/sales_agent.env ~/.config/vibecoding/cloudbot/sales_agent.live.env
```

### 2. Собрать деплой-env на маке (gitignored, вне репо)
```bash
cat > ~/.config/vibecoding/cloudbot/deploy.env <<'EOF'
export PRIMARY_HOST=72.56.83.251
export SSH_USER=root
export SSH_KEY_PATH=/Users/pro2kuror/.ssh/temp_migration_key
export SSH_PORT=22
EOF
# добавить живые SALES_* (export каждую строку из live-файла):
sed 's/^/export /' ~/.config/vibecoding/cloudbot/sales_agent.live.env >> ~/.config/vibecoding/cloudbot/deploy.env
```

### 3. DRY-проверка (ВНИМАНИЕ — НЕ полный dry-run)
`DRY_RUN=1` пропускает только tar-sync кода; промоушн/symlink не гардятся, но `compileall`
упадёт на отсутствии кода в staging → деплой прервётся ДО флипа symlink (т.е. безопасно «на отказ»).
Используй DRY_RUN лишь чтобы проверить, что require_env проходит и lock берётся:
```bash
cd /Users/pro2kuror/Desktop/VibeCoding
git checkout feat/global-sales-dashboard && git pull --ff-only origin feat/global-sales-dashboard
set -a; . ~/.config/vibecoding/cloudbot/deploy.env; set +a
DRY_RUN=1 bash cloudbot/infra/orchestrator/workflows/sales_agent_deploy.sh
```

### 4. Боевой деплой из `feat/global-sales-dashboard`
```bash
cd /Users/pro2kuror/Desktop/VibeCoding
git checkout feat/global-sales-dashboard
git status --porcelain   # untracked CODEX-*.md / runbook не мешают (git archive берёт только закоммиченное HEAD)
set -a; . ~/.config/vibecoding/cloudbot/deploy.env; set +a
bash cloudbot/infra/orchestrator/workflows/sales_agent_deploy.sh 2>&1 | tee /tmp/lev_deploy_$(date +%s).log
# создаст релиз feat_global-sales-dashboard_8e0cc22, current → него
```

### 5. Верификация
```bash
# а) релиз и symlink:
ssh cloudbot-ssh-proxy 'readlink /opt/cloudbot-runtime/current; cat /opt/cloudbot-runtime/current/RELEASE_COMMIT'
# б) Опер-модель в живом релизе:
ssh cloudbot-ssh-proxy 'grep -n "реальных рабочих минут" /opt/cloudbot-runtime/current/apps/lev_petrovich/legacy_sales_agent/sales_formatter.py'
# в) env/cron не регрессировали (diff с бэкапом из шага 1 — ожидаем пусто):
ssh cloudbot-ssh-proxy 'diff /etc/openclaw/sales_agent.env.bak-* /etc/openclaw/sales_agent.env'
# г) штатный verify:
set -a; . ~/.config/vibecoding/cloudbot/deploy.env; set +a
bash cloudbot/infra/orchestrator/workflows/sales_agent_verify.sh
# д) smoke «Опер» (Исаева-кейс ≈ 5.7) — прогнать формирование отчёта Льва вручную (как раньше) и сверить балл.
```

### 6. Откат (если что)
```bash
# вернуть symlink на прежний релиз:
ssh cloudbot-ssh-proxy 'ln -sfn /opt/cloudbot-runtime/releases/dev_3b160ba /opt/cloudbot-runtime/current'
# вернуть env при регрессе:
ssh cloudbot-ssh-proxy 'cp -a /etc/openclaw/sales_agent.env.bak-<stamp> /etc/openclaw/sales_agent.env'
```

## После закрепления
- Удалить из памяти/STATUS пометку «патч временный»; зафиксировать `feat/global-sales-dashboard` как текущую ветку-источник деплоя Льва (cloudbot живёт только там).
- Бэкап ручного патча на проде (`…bak-20260605-084236-MSK`) можно оставить как есть.
- Отдельно (не для Части B): гигиена веток — main и feat разошлись, cloudbot/ и GSD есть только в feat; решить консолидацию (подтянуть 23 PR main→feat и/или узкий merge cloudbot/→main).
- Ключи (Hetzner/OpenAI/root/SSH) — отдельная ротация (бэклог #4).
