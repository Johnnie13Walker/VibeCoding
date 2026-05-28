# CODEX path remediation step

Дата: 2026-05-02 09:27:45 МСК.

Статус: выполнен первый минимальный path remediation без live cutover.

## Изменено

`scripts/larisa_finalize.sh` больше не делает hardcoded переход:

```bash
cd "/Users/pro2kuror/Desktop/OpenClo/projects/engineer"
```

Вместо этого script root вычисляется от расположения самого скрипта, с возможностью явного override:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${CLOUDBOT_ENGINEER_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
cd "$REPO_ROOT"
```

Это сохраняет совместимость со старым путем и позволяет запускать скрипт через:

- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/scripts/larisa_finalize.sh`;
- `/Users/pro2kuror/Desktop/CODEX/engineer/scripts/larisa_finalize.sh`;
- future physical path with `CLOUDBOT_ENGINEER_ROOT`.

## Добавлен guard

Добавлен тест:

`tests/integration/test_workspace_path_contract.py`

Он запрещает вернуть hardcoded `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` в `scripts/larisa_finalize.sh` и проверяет наличие `CLOUDBOT_ENGINEER_ROOT`.

## Что не менялось

- `configs/schedules.cron` не изменялся, потому что cron changes требуют отдельного approval.
- Local crontab не изменялся.
- systemd, Docker, env, Telegram token/chat routing не изменялись.
- `/opt/openclaw` и `/opt/cloudbot-runtime/*` не трогались.
- `agents/sales_agent` не трогался.

## Проверки после изменения

После изменения `scripts/larisa_finalize.sh`:

```bash
bash -n scripts/larisa_finalize.sh
git diff --check
python3 -m unittest tests.integration.test_app_compatibility_contract
```

Результат: OK.

После добавления guard test:

```bash
python3 -m unittest tests.integration.test_workspace_path_contract
bash -n scripts/larisa_finalize.sh
git diff --check
python3 -m unittest tests.integration.test_app_compatibility_contract
```

Результат: OK.

## Оставшиеся path risks

Следующие path dependencies остаются сознательно без изменений:

- `configs/schedules.cron`: repo-local cron template с hardcoded old engineer root;
- `tools/control-plane/architect-scripts/scripts/*`: old `Cloudbot/engineer`, `Cloudbot/architect`, `architect` defaults;
- historical docs с упоминаниями старых source-of-truth путей.

Следующий безопасный шаг: подготовить template/guard для cron без применения live crontab.
