# Shared Core Import Map

Дата фиксации: 2026-04-28 МСК.

Статус: read-only import map. Этот документ не меняет `cloudbot/*`, imports или runtime behavior.

## 1. Current shared-core path

```text
cloudbot/
```

Target placeholders exist:

```text
shared/orchestrator
shared/providers
shared/skills
shared/devops
shared/formatting
shared/logging
shared/time
```

No shared-core code has moved.

## 2. Confirmed internal dependencies

| Area | Confirmed dependencies |
| --- | --- |
| `cloudbot/orchestrator` | imports `cloudbot.orchestrator.context`, `cloudbot.orchestrator.router`, `cloudbot.orchestrator.search_state` |
| `cloudbot/workflows/larisa_*` | import `cloudbot.workflows.larisa_runtime` |
| `cloudbot/workflows/finance_*` | import `cloudbot.workflows.finance_runtime` and `apps.finansist` canonical, `agents.finansist` compatibility shim |
| `cloudbot/skills/*` | several use `cloudbot.compat.node_bridge`; `web_search` uses `cloudbot.providers.search_provider` |
| `cloudbot/providers/bitrix/*` | imports `cloudbot.providers.bitrix_provider` and app auth |
| `cloudbot/devops/*` | used by workflows and tests |

## 3. Tests locking current paths

Current tests import:

```text
cloudbot.providers.search_provider
cloudbot.providers.bitrix.bitrix_app_auth
cloudbot.providers.bitrix.bitrix_sales_adapter
cloudbot.devops.system_health
cloudbot.devops.sales_dispatch_health
cloudbot.orchestrator.router
cloudbot.workflows.larisa_runtime
```

## 4. Migration risk

Shared-core move is high risk because:

- `cloudbot.*` is a broad import surface;
- it is shared by Larisa, Sales/Lev, finance, health checks and tests;
- several workflows are excluded contours;
- moving one module may require many compatibility shims.

## 5. Blocked changes

Blocked:

- moving `cloudbot/orchestrator`;
- moving `cloudbot/providers`;
- moving `cloudbot/skills`;
- moving `cloudbot/workflows`;
- rewriting `cloudbot.*` imports;
- changing node bridge behavior;
- changing shared provider behavior.

## 6. Verdict

```text
shared-core move blocked
import map completed
next safe step: provider boundary map
```
