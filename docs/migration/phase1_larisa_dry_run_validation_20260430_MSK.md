# Phase 1 Larisa dry-run validation — 2026-04-30 МСК

## Status

Phase 1 выполнен как dry-run validation.

Не выполнялись:

- deploy;
- restart;
- изменение runtime pointers;
- изменение env;
- изменение cron;
- изменение systemd;
- изменение Docker;
- изменение файлов на сервере.

## Baseline

- Local repo: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- Branch: `dev`
- HEAD: `715225b`
- Runtime rollback target from Phase 0: `/opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326`
- Current live pointer from Phase 0: `/opt/cloudbot-runtime/larisa/current`

## Validation checks

| Check | Result |
| --- | --- |
| `import apps.larisa_ivanovna` | OK |
| `import agents.larisa_ivanovna` | OK |
| `import apps.larisa_ivanovna.agent` | OK |
| `python3 -m unittest tests.integration.test_larisa_agent` | OK, 27 tests |
| `python3 -m unittest discover -s tests/unit` | OK, 18 tests |
| `python3 -m unittest discover -s tests/integration` | OK, 100 tests |
| `python3 checks/smoke_test.py` | OK |
| `python3 checks/sales_morning_dispatch_smoke.py` | OK |

## Compatibility confirmation

Confirmed locally:

- canonical Larisa path `apps/larisa_ivanovna` imports successfully;
- compatibility path `agents/larisa_ivanovna` imports successfully;
- shared smoke does not show regression from Larisa app-path migration;
- Sales smoke still passes, so Larisa validation did not break the Sales compatibility layer.

## Not confirmed in Phase 1

Not executed in this phase:

- live Telegram delivery;
- live `/opt/cloudbot-runtime/larisa/current` switch;
- live cron execution;
- live Bitrix/Todo/weather/search API calls through production env;
- rollback execution.

Reason: Phase 1 is dry-run validation only.

## Gate conclusion

Larisa dry-run validation passed.

The project is ready to prepare a Larisa cutover approval package.

The project is not yet approved for live Larisa cutover until owner confirms:

- exact release creation method;
- no env/token/chat route changes;
- rollback command;
- post-cutover smoke checklist execution window.
