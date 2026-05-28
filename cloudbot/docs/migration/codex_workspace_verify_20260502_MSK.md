# CODEX workspace verify script

Дата: 2026-05-02 09:30:19 МСК.

Статус: добавлен read-only verifier для `/Users/pro2kuror/Desktop/CODEX`.

## Новый script

`scripts/verify_codex_workspace.sh`

Проверяет:

- что `/Users/pro2kuror/Desktop/CODEX` существует;
- что `CODEX/engineer` указывает на `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`;
- что `CODEX/control-plane` указывает на `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane`;
- что `CODEX/tools/paperclip` указывает на `/Users/pro2kuror/Desktop/tools/paperclip`;
- что `CODEX/wrappers/Cloudbot` указывает на `/Users/pro2kuror/Desktop/Cloudbot`;
- что есть local `/Users/pro2kuror/Desktop/CODEX/README.md`;
- что `CODEX/engineer` и `CODEX/tools/paperclip` доступны как git work trees.

Script не меняет filesystem и не делает cleanup.

## Override-переменные

Для future dry-run/cutover script поддерживает:

- `CODEX_ROOT`;
- `ENGINEER_TARGET`;
- `CONTROL_PLANE_TARGET`;
- `PAPERCLIP_TARGET`;
- `CLOUDBOT_TARGET`.

## Guard

`tests/integration/test_workspace_path_contract.py` теперь проверяет:

- `scripts/larisa_finalize.sh` не содержит hardcoded old engineer root;
- `scripts/verify_codex_workspace.sh` исполняемый;
- verifier содержит default CODEX root;
- verifier не содержит destructive `rm`, `rmdir`, `mv` commands.

## Проверки

После добавления script:

```bash
bash -n scripts/verify_codex_workspace.sh
scripts/verify_codex_workspace.sh
git diff --check
python3 -m unittest tests.integration.test_app_compatibility_contract
```

Результат: OK.

После добавления guard:

```bash
python3 -m unittest tests.integration.test_workspace_path_contract
bash -n scripts/verify_codex_workspace.sh
scripts/verify_codex_workspace.sh
git diff --check
python3 -m unittest tests.integration.test_app_compatibility_contract
```

Результат: OK.

## No-touch

Не менялись:

- старые Desktop-папки;
- cron/systemd/Docker/env;
- Telegram token/chat routing;
- production runtime symlinks;
- `/opt/openclaw`;
- `agents/sales_agent`.
