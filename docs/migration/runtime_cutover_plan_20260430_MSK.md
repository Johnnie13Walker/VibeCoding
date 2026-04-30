# Runtime cutover plan — 2026-04-30 МСК

## Status

This is a plan only.

No server runtime pointer, env, cron, systemd, Docker, deploy script, or live service was changed by this document.

## Code baseline

- Branch: `dev`
- Commit: `6b5e9ce`
- Commit title: `fix: close codex review feedback`

## Local gate passed

- `python3 -m unittest discover -s tests/unit` — OK, 18 tests
- `python3 -m unittest discover -s tests/integration` — OK, 100 tests
- `python3 checks/smoke_test.py` — OK
- `python3 checks/sales_morning_dispatch_smoke.py` — OK
- `bash -n infra/orchestrator/run_workflow.sh infra/orchestrator/workflows/*.sh` — OK
- `npm test` in `bot` — OK
- GitHub `Sales Contract Checks` on `dev` — OK

## Current local source layout

| Contour | Canonical source path | Compatibility path |
| --- | --- | --- |
| Larisa Ivanovna | `apps/larisa_ivanovna` | `agents/larisa_ivanovna` |
| Lev Petrovich | `apps/lev_petrovich` | `agents/lev_petrovich` |
| Sales legacy layer | `apps/lev_petrovich/legacy_sales_agent` | `agents/sales_agent` |
| Finansist | `apps/finansist` | `agents/finansist` |

## Runtime no-touch until cutover approval

- `/opt/cloudbot-runtime/larisa/current`
- `/opt/cloudbot-runtime/current`
- `/opt/openclaw`
- `/etc/openclaw`
- `/etc/cron.d/*`
- `/etc/systemd/*`
- Docker runtime
- live env files
- deploy/rollback/verify scripts

## Phase 0 — read-only server confirmation

Goal: confirm current production state without changing it.

Read-only checks:

- resolve `/opt/cloudbot-runtime/larisa/current`
- resolve `/opt/cloudbot-runtime/current`
- list relevant cron files
- list relevant systemd services
- list relevant Docker containers
- check latest Larisa reports/log timestamps
- check latest Sales reports/log timestamps
- confirm runtime currently still works with compatibility paths

Exit criteria:

- no live changes made;
- current runtime paths known;
- rollback target known;
- latest report/log timestamps captured.

## Phase 1 — Larisa dry-run release validation

Goal: validate Larisa release from `dev` without switching live runtime pointer unless the deploy script forces it.

Preconditions:

- commit `6b5e9ce` is available on the deploy host;
- Larisa smoke checklist is ready;
- rollback target for `/opt/cloudbot-runtime/larisa/current` is recorded.

Checks:

- package/import check for `apps.larisa_ivanovna`
- compatibility import check for `agents.larisa_ivanovna`
- `python3 -m agents.larisa_ivanovna --command get_day_brief` remains valid if used by runtime
- no env/token/chat routing changes

Do not proceed if:

- deploy script cannot run in dry-run/inspect mode;
- rollback target is unknown;
- live token/chat routing cannot be confirmed.

## Phase 2 — Larisa production cutover

Goal: switch only Larisa after successful dry-run.

Post-cutover smoke:

- Telegram delivery alive
- daily brief delivery
- morning brief timing validation
- calendar access
- tasks access
- weather/news/search response
- command routing
- formatter output sanity
- logs generation
- reports freshness
- no fallback to wrong shared bot token/chat route

Rollback trigger:

- Telegram delivery fails;
- daily brief fails;
- wrong bot/chat route detected;
- import/runtime failure in Larisa command path.

## Phase 3 — Lev/Sales dry-run release validation

Goal: validate Lev/Sales release without changing live runtime pointer unless explicitly approved.

Preconditions:

- Sales smoke checklist is ready;
- `agents/sales_agent` compatibility layer remains present;
- rollback target for `/opt/cloudbot-runtime/current` is recorded.

Checks:

- package/import check for `apps.lev_petrovich`
- compatibility import check for `agents.lev_petrovich`
- package/import check for `apps.lev_petrovich.legacy_sales_agent`
- compatibility import check for `agents.sales_agent`
- `scripts/run_sales_copilot.py` still works against compatibility path
- Sales report contract tests pass

Do not proceed if:

- report contract changes are detected;
- Sales Telegram token/chat route is ambiguous;
- Bitrix fixture/local smoke fails.

## Phase 4 — Lev/Sales production cutover

Goal: switch only Lev/Sales after successful dry-run and after Larisa has remained stable.

Post-cutover smoke:

- morning sales report delivery
- report contract integrity
- Telegram delivery
- Bitrix data pull sanity
- follow-up generation
- postponed deals block
- overdue tasks block
- weekly review readiness
- logs freshness
- formatting sanity
- compatibility with `agents/sales_agent`
- runtime bridge awareness for `scripts/run_sales_copilot.py`

Rollback trigger:

- morning report missing;
- report contract broken;
- Bitrix pull broken;
- wrong Telegram route;
- `agents/sales_agent` compatibility failure.

## Phase 5 — observation window

Duration: at least 24 hours after both cutovers.

Observe:

- scheduled Larisa reports;
- scheduled Sales reports;
- cron freshness;
- logs for import errors;
- Telegram delivery;
- Bitrix/Todo/WHOOP/Search degradation.

## Phase 6 — legacy cleanup decision

Only after observation window is green:

- decide which `agents/*` shims remain;
- decide whether runtime entrypoints can use `apps/*`;
- decide whether `agents/sales_agent` can start retirement track;
- decide whether Finance should be enabled in production runtime.

## Explicit non-goals

- no merge to `main` before runtime smoke;
- no deletion of compatibility shims during cutover;
- no env/token/chat routing changes mixed with code path cutover;
- no simultaneous Larisa and Lev/Sales cutover;
- no Finance production enablement unless separately approved.
