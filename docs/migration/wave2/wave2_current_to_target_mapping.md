# Wave 2 Current-to-Target Mapping

Date: 2026-04-27 MSK.

This mapping is a planning artifact. It does not move files.

Allowed decisions:

- `structural candidate`
- `keep compatibility`
- `keep external`
- `exclude from Wave 2`
- `archive later`
- `investigate later`
- `no-touch runtime`

| current path | target path | decision | status | notes |
|---|---|---|---|---|
| `agents/larisa_ivanovna` | `apps/larisa_ivanovna/` | structural candidate | excluded from code moves | future app boundary; feature changes excluded from Wave 2 |
| `agents/lev_petrovich` | `apps/lev_petrovich/` | structural candidate | excluded from code moves | future app boundary; must remain compatible with `agents/sales_agent` |
| `agents/sales_agent` | `apps/lev_petrovich/legacy_sales_agent/` | keep compatibility | no-touch for Wave 2 | temporary compatibility layer; do not retire or delete |
| `cloudbot/orchestrator` | `shared/orchestrator/` | structural candidate | excluded from behavior changes | document only; no import rewrites |
| `cloudbot/providers` | `shared/providers/` | structural candidate | excluded from behavior changes | providers contain server/runtime assumptions |
| `cloudbot/skills` | `shared/skills/` | structural candidate | excluded from behavior changes | shared skills stay behavior-stable |
| `cloudbot/workflows` | `shared/orchestrator/` or `apps/*/workflows/` | investigate later | excluded from Wave 2 moves | workflow ownership must be split later |
| `cloudbot/bot/telegram` | `apps/bot_gateway/` | structural candidate | excluded from code moves | Telegram gateway boundary only |
| `configs` | `config/` | structural candidate | excluded from live config changes | examples/contracts only after review; no env/cron mutation |
| `infra/orchestrator` | `infra/orchestrator/` | structural candidate | no-touch runtime | deploy/rollback/verify scripts not changed |
| `docs` | `docs/` | structural candidate | documentation only | migration docs may be added; existing docs not normalized in Wave 2 |
| `server_snapshots` | `infra/server_snapshots/` or `archive/server_snapshots/` | archive later | excluded from moves | evidence/archive disposition later |
| `/Users/pro2kuror/Desktop/architect` | `docs/control-plane` external source | keep external | active docs/control-plane | not moved into engineer in Wave 2 |
| `/Users/pro2kuror/Desktop/Cloudbot` | none | keep compatibility | wrapper only | not source of truth |
| `/Users/pro2kuror/Desktop/tools` | external tools | keep external | excluded | relation to OpenCloud not part of Wave 2 |
| `OpenClo/projects/whoop` | external or future integration docs | keep external | excluded | standalone WHOOP contour; not production code migration |
| `OpenClo/projects/commercial-director` | external knowledge/archive | keep external | excluded | historical/knowledge contour |
| `OpenClo/incubator/openclaw-extensions` | incubator | investigate later | excluded | experimental contour |
| `ios/FormaNutrition` | separate product contour | exclude from Wave 2 | excluded | not Cloudbot runtime |
| `apps/finansist` canonical, `agents/finansist` compatibility shim | future finance app if approved | exclude from Wave 2 | excluded | finance contour is separate track |
| `/opt/cloudbot-runtime/larisa/current` | runtime pointer | no-touch runtime | excluded | live server pointer; not touched |
| `/opt/cloudbot-runtime/current` | runtime pointer | no-touch runtime | excluded | live generic/sales pointer; not touched |
| `/opt/openclaw` | server-only platform/runtime | no-touch runtime | excluded | server-only integration |
| `/etc/openclaw` | live env/config | no-touch runtime | excluded | no env mutation |
