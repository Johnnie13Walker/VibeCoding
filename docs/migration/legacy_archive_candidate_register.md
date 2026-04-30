# Legacy / Archive Candidate Register

Дата фиксации: 2026-04-28 МСК.

Статус: register only. Этот документ не архивирует, не удаляет и не перемещает файлы.

## 1. Confirmed candidates

| Path | Current classification | Decision |
| --- | --- | --- |
| `control_plane_snapshots` | possible snapshot/archive | investigate before archive |
| `server_snapshots` | server snapshot evidence | keep, do not archive automatically |
| `server_snapshots/live_ams_1_vm_76ds_20260325` | live server snapshot | keep as audit evidence |
| `apps/lev_petrovich/legacy_sales_agent` | target placeholder only | do not use as active path |
| `archive/README.md` | archive boundary marker | marker only |
| `scripts/context_snapshot.sh` | snapshot helper | investigate before moving |
| `checks/larisa_remote_todo_snapshot.sh` | check/snapshot helper | investigate before moving |

## 2. Explicit non-archive

Do not classify as archive:

```text
agents/sales_agent
agents/lev_petrovich
agents/larisa_ivanovna
cloudbot/*
configs/schedule_contract.env
configs/schedules.cron
```

## 3. Rules

Before anything moves to `archive/`:

1. Confirm not used by runtime.
2. Confirm not used by tests.
3. Confirm not used by docs/runbooks.
4. Confirm no server dependency.
5. Get owner disposition.

## 4. Verdict

```text
archive candidates registered
no archive move approved
```
