# Runtime No-Touch Register

Дата фиксации: 2026-05-02 МСК.

Статус: no-touch register. Этот документ не меняет runtime.

## 1. Server paths

No-touch:

```text
/opt/cloudbot-runtime/larisa/current
/opt/cloudbot-runtime/current
/opt/openclaw
/etc/openclaw
/etc/cron.d/*
/etc/systemd/*
/root/*
/home/ops/*
```

## 2. Local runtime-sensitive files

No-touch:

```text
configs/schedule_contract.env
configs/schedules.cron
infra/orchestrator/workflows/deploy.sh
infra/orchestrator/workflows/rollback.sh
infra/orchestrator/workflows/verify.sh
infra/orchestrator/workflows/audit.sh
scripts/run_sales_copilot.py
```

## 3. Runtime pointers

No-touch:

```text
Larisa runtime current
Generic/Sales runtime current
OpenClaw runtime
cron runner paths
systemd service pointers
docker containers
```

## 4. Agent-specific no-touch

No-touch until separate approval:

```text
agents/sales_agent
agents/lev_petrovich
agents/larisa_ivanovna
```

Important:

- `agents/sales_agent` is an active temporary compatibility layer.
- It is not an archive and not cleanup trash.
- Do not delete, move, rename or retire it without a dedicated approval package.
- Do not remove old imports unless `tests.integration.test_app_compatibility_contract` stays green.

## 5. Why this exists

Structural migration must not accidentally become runtime migration.

Runtime changes require:

1. Runtime approval.
2. Smoke checklist.
3. Rollback plan.
4. Server dependency map.
5. Owner confirmation.

## 6. Verdict

```text
runtime no-touch remains active
production/runtime pointer changes blocked
agents/sales_agent retirement blocked
```
