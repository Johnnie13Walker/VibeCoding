# Phase 4 Lev/Sales dry-run validation — 2026-04-30 МСК

## Status

Phase 4 Lev/Sales dry-run validation completed locally.

Result after fixes: OK.

No production runtime pointer, env file, cron file, systemd unit, Docker runtime, Telegram route, or `/opt/openclaw` file was changed.

## Baseline

| Field | Value |
| --- | --- |
| Local repo | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` |
| Branch | `dev` |
| Baseline HEAD | `5fcf905` |
| Time | `2026-04-30 11:58 МСК` |
| Initial worktree | clean |

Current server runtime before any future cutover remains:

`/opt/cloudbot-runtime/current` -> `/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60`

This phase did not switch that pointer.

## Import validation

Command:

```bash
python3 -c "import apps.lev_petrovich; import agents.lev_petrovich; import apps.lev_petrovich.legacy_sales_agent; import agents.sales_agent; print('lev_sales_imports OK')"
```

Result: OK.

Confirmed import paths:

- `apps.lev_petrovich`;
- `agents.lev_petrovich`;
- `apps.lev_petrovich.legacy_sales_agent`;
- `agents.sales_agent`.

`agents.sales_agent` remains a compatibility layer and was not removed or retired.

## Initial dry-run findings

The first dry-run pass found two real blockers that already matched server observations from the report inventory.

### 1. Sales follow-up workflow used an invalid report type

Failed command:

```bash
bash infra/orchestrator/workflows/sales_followup.sh
```

Failure:

```text
argument --report: invalid choice: 'followup' (choose from 'focus', 'pipeline', 'risks', 'sales', 'weekly')
```

Cause:

- `infra/orchestrator/workflows/sales_followup.sh` used `REPORT_TYPE="followup"`;
- `followup` is a workflow/job name, not a supported Lev/Sales runtime report type;
- the runtime contract supports `sales`, `pipeline`, `risks`, `focus`, `weekly`.

Fix:

- changed `sales_followup.sh` to run the supported `focus` report while preserving the file/report name `sales_followup`.

### 2. Sales weekly workflow failed format validation

Failed command:

```bash
bash infra/orchestrator/workflows/sales_weekly_review.sh
```

Failure:

```text
Sales Copilot error: Ошибки доставки sales-отчетов: weekly (format_validation): Отсутствуют обязательные секции формата: 📊 Отчёт Льва Петровича по продажам
```

Cause:

- weekly formatter emitted `🗓 Еженедельный отчёт Льва Петровича`;
- the canonical report format contract requires marker `📊 Отчёт Льва Петровича по продажам`.

Fix:

- updated weekly formatter default title to match the canonical contract marker.

## Files changed

| File | Change |
| --- | --- |
| `infra/orchestrator/workflows/sales_followup.sh` | `REPORT_TYPE` changed from invalid `followup` to supported `focus` |
| `apps/lev_petrovich/legacy_sales_agent/sales_formatter.py` | weekly default title aligned with format contract |
| `tests/integration/test_sales_dispatch_contract.py` | added regression tests for follow-up and weekly workflows |

## Post-fix dry-run validation

Commands:

```bash
python3 -m unittest tests.integration.test_sales_dispatch_contract
python3 -m unittest tests.integration.test_lev_petrovich_runtime tests.integration.test_sales_dispatch_contract
python3 checks/sales_morning_dispatch_smoke.py
```

Results:

| Check | Result |
| --- | --- |
| `tests.integration.test_sales_dispatch_contract` | OK, 5 tests |
| `tests.integration.test_lev_petrovich_runtime tests.integration.test_sales_dispatch_contract` | OK, 50 tests |
| `python3 checks/sales_morning_dispatch_smoke.py` | OK |

Manual local fixture workflow dry-runs:

| Workflow | Mode | Result |
| --- | --- | --- |
| `infra/orchestrator/workflows/sales_morning_report.sh` | fixture + Telegram dry-run | OK |
| `infra/orchestrator/workflows/sales_followup.sh` | fixture + Telegram dry-run | OK |
| `infra/orchestrator/workflows/sales_weekly_review.sh` | fixture + Telegram dry-run | OK |

Bridge checks:

| Command | Result |
| --- | --- |
| `SALES_COPILOT_MOCK=1 python3 scripts/run_sales_copilot.py --report sales --json` | OK |
| `SALES_COPILOT_MOCK=1 python3 scripts/run_sales_copilot.py --report weekly --json` | OK |
| `SALES_COPILOT_MOCK=1 python3 scripts/run_sales_copilot.py --report risks --json` | OK |
| `BITRIX_CHECK_MOCK=1 python3 scripts/run_sales_copilot.py --report bitrixcheck --json` | OK |

Note:

- `scripts/run_sales_copilot.py` does not support a `--mock` CLI flag;
- mock mode is controlled by `SALES_COPILOT_MOCK=1` or `BITRIX_CHECK_MOCK=1`.

## Full regression checks

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests/unit` | OK, 18 tests |
| `python3 -m unittest discover -s tests/integration` | OK, 102 tests |
| `python3 checks/sales_morning_dispatch_smoke.py` | OK |
| `python3 checks/smoke_test.py` | OK |

`checks/smoke_test.py` also ran the bot npm smoke path successfully.

## No-touch confirmation

Not touched:

- `/opt/cloudbot-runtime/current`;
- `/opt/cloudbot-runtime/larisa/current`;
- `/opt/openclaw`;
- `/etc/openclaw/*`;
- `/etc/cron.d/*`;
- systemd;
- Docker;
- live Telegram sends for Lev/Sales;
- token/chat routing;
- `agents/sales_agent` retirement.

## Verdict

Lev/Sales local dry-run validation is now green.

Phase 5 may prepare a Lev/Sales cutover approval package, but controlled cutover is not approved by this document.

The approval package must explicitly include:

- old target: `/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60`;
- new release id;
- rollback target;
- confirmation that `agents/sales_agent` remains a compatibility layer;
- post-cutover smoke checklist for morning report, follow-up, weekly review, Bitrix pull sanity, Telegram route, logs, and report contract integrity.
