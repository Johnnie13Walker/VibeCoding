# Wave 2 Scope

Date: 2026-04-27 MSK.

Wave 2 is controlled structural preparation only. It prepares documentation, boundaries, compatibility rules, and migration readiness artifacts for future work. It does not authorize runtime changes, behavior changes, deploy, refactor, or file migration of production code.

## In Scope

- Document target structural boundaries for `apps/`, `shared/`, `config/`, `infra/`, `docs/`, `archive/`, and `tests/`.
- Document current-to-target mapping without moving code.
- Record compatibility rules for `agents/sales_agent`, `agents/lev_petrovich`, `agents/larisa_ivanovna`, and the `Cloudbot` wrapper.
- Record source-of-truth markers:
  - code: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
  - docs/control-plane: `/Users/pro2kuror/Desktop/architect`
  - wrapper only: `/Users/pro2kuror/Desktop/Cloudbot`
- Record no-touch policy for runtime, env, cron, systemd, docker, deploy scripts, and server-only integrations.
- Prepare readiness report for the next wave.

## Out of Scope

- Production code moves.
- Import rewrites.
- Runtime refactors.
- Deploy, restart, or server mutation.
- Live env changes.
- Cron/systemd/docker changes.
- Runtime pointer changes.
- Business logic changes for Larisa or Lev/Sales.
- Shared-core behavior changes.
- Any work on excluded contours.

## Explicitly Excluded Zones

| zone | reason |
|---|---|
| Larisa feature changes | feature work, not structural preparation |
| Sales/Lev feature/runtime changes | production behavior and runtime bridge work |
| `cloudbot/orchestrator`, providers, skills, workflows functional changes | shared-core behavior changes are not allowed in Wave 2 |
| infra runtime/deploy changes | no deploy/runtime mutation in Wave 2 |
| configs/env/cron live changes | no live config or schedule changes |
| finance contour | separate track |
| `ios/FormaNutrition` | separate product/contour |
| HAPP/VPN/subscription cleanup | separate legacy cleanup track |
| server-only integrations | no-touch until dependency map and separate approval |

## Non-Behavior Rule

Wave 2 does not allow changing system behavior. Any change that can affect Telegram delivery, Bitrix/Todo/WHOOP/search access, command routing, formatter output, report content, runtime pointers, env resolution, cron timing, deploy/rollback/verify behavior, or server-only integrations is outside Wave 2.
