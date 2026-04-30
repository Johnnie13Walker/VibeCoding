# Wave 2 No-Touch Policy

Date: 2026-04-27 MSK.

Wave 2 is documentation-only structural preparation. The following zones are no-touch unless a later owner approval explicitly opens a separate track.

| zone | why no-touch | what approval needed later |
|---|---|---|
| `/opt/*` | live server/runtime area | explicit server/runtime wave approval |
| `/etc/*` | live server config, cron, env, system integration | explicit server config approval |
| `/root/*` | server workspace/secrets/runtime state | explicit server-only dependency map and approval |
| `/home/ops/*` | live reports/logs/runtime support paths | explicit runtime/log migration approval |
| live env files | can change token, provider, and chat behavior | env separation plan and smoke checks |
| live cron files | can change report timing and delivery | schedule change approval and rollback plan |
| systemd services | can affect running services | service change approval |
| docker containers | can affect OpenClaw/search/gateway runtime | docker/server ops approval |
| runtime pointers | can switch production release | runtime cutover approval |
| deploy scripts | can change release behavior | deploy-track approval |
| rollback scripts | can remove recovery path | rollback-track approval |
| verify scripts | can change validation meaning | verification-track approval |
| `infra/orchestrator/workflows/deploy.sh` deleted state | unresolved operational disposition | deleted-files disposition |
| `infra/orchestrator/workflows/rollback.sh` deleted state | unresolved rollback disposition | deleted-files disposition |
| `infra/orchestrator/workflows/verify.sh` deleted state | unresolved verification disposition | deleted-files disposition |
| production feature logic | can change user-visible behavior | feature-track approval |
| Larisa business logic | production assistant behavior | Larisa feature/runtime approval |
| Lev/Sales business logic | production report behavior | Sales/Lev feature/runtime approval |
| shared-core functional behavior | can break multiple agents | shared-core review and test plan |
| `agents/sales_agent` retirement | active compatibility layer | dedicated compatibility retirement track |
| finance contour | separate track | finance owner approval |
| `ios/FormaNutrition` | separate product/contour | iOS/product owner approval |
| HAPP/VPN cleanup | legacy cleanup outside Wave 2 | legacy cleanup approval |
| subscription cleanup | legacy cleanup outside Wave 2 | legacy cleanup approval |
| server-only integrations | dependency map incomplete | server-only dependency map approval |

If a required action touches any no-touch zone, it is not Wave 2.
