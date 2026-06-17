# Wave 2 Target Layout

Date: 2026-04-27 MSK.

This document describes the target structure only. It does not move code, rewrite imports, or change runtime behavior.

## Target Structure

```text
OpenCloud/
  apps/
    larisa_ivanovna/
    lev_petrovich/
      legacy_sales_agent/
    bot_gateway/
  shared/
    orchestrator/
    providers/
    skills/
    devops/
    formatting/
    logging/
    time/
  config/
    env/
      examples/
      schemas/
    schedules/
  infra/
    orchestrator/
    deploy/
    cron/
    systemd/
    docker/
    server_snapshots/
  docs/
    architecture/
    runbooks/
    roles/
    migration/
    decisions/
  archive/
  tests/
```

## Boundary Intent

| target zone | intent | Wave 2 action |
|---|---|---|
| `apps/larisa_ivanovna/` | future app boundary for Larisa | document only |
| `apps/lev_petrovich/` | future app boundary for Lev | document only |
| `apps/lev_petrovich/legacy_sales_agent/` | future compatibility holding area if approved later | document only |
| `apps/bot_gateway/` | future Telegram gateway boundary | document only |
| `shared/orchestrator/` | future shared orchestration boundary | document only |
| `shared/providers/` | future shared provider boundary | document only |
| `shared/skills/` | future shared tools/skills boundary | document only |
| `shared/devops/` | future shared diagnostics/health boundary | document only |
| `shared/formatting/` | future common formatting boundary | document only |
| `shared/logging/` | future common logging boundary | document only |
| `shared/time/` | future timezone/time utilities boundary | document only |
| `config/env/examples/` | future env examples boundary | document only |
| `config/env/schemas/` | future env schema boundary | document only |
| `config/schedules/` | future schedule contract boundary | document only |
| `infra/*` | future infra documentation/source boundary, not live server mutation | document only |
| `docs/*` | architecture, runbooks, roles, migration, decisions | document only |
| `archive/` | future archive boundary after explicit disposition | document only |
| `tests/` | future validation boundary | document only |

## Empty Folders

Wave 2 does not require creating target folders under production code paths. If empty folders are created later, they must contain only `README.md` or `.gitkeep` and must not change imports.

No target production folder is populated by this document.
