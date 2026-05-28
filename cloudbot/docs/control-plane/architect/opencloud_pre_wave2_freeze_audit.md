# 1. Executive summary

Дата фиксации: 2026-04-23, МСК.

Область аудита:

- canonical engineer repo: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- docs/control-plane: `/Users/pro2kuror/Desktop/architect`
- режим: read-only анализ, без изменений runtime, кода, env, cron, systemd, docker, symlink и runtime pointers

Итог: **not ready for Wave 2**.

Причина неготовности: engineer repo находится в сильно dirty-состоянии, и это состояние затрагивает не только документацию, но и production-critical зоны:

- `agents/larisa_ivanovna`
- `agents/sales_agent`
- `agents/lev_petrovich` через shared imports и runtime tests
- `cloudbot/orchestrator`
- `cloudbot/providers`
- `cloudbot/skills`
- `cloudbot/workflows`
- `infra/orchestrator`
- `configs`
- `scripts/run_sales_copilot.py`
- runtime/deploy verification scripts

Фактическая git-картина:

- branch: `codex/feature/self-healing`
- HEAD: `dc19495e340a5899ca3451f4f492df65a63789da`
- tracked diff: `106 files changed, 4801 insertions(+), 3951 deletions(-)`
- status count: `70 M`, `36 D`, `46 ??`
- top dirty zones: `agents`, `infra`, `cloudbot`, `control_plane_snapshots`, `scripts`, `checks`, `tests`, `docs`, `ops`, `configs`

Главный риск: если начать Wave 2 сейчас, миграция структуры смешается с уже существующими незакоммиченными изменениями в боевых агентах, shared-core и deploy-инфраструктуре. После этого будет сложно отделить архитектурную реорганизацию от функциональных изменений и безопасно откатиться.

Отдельный риск: absolute paths и hidden coupling подтверждены. Есть hardcoded локальный путь `/Users/pro2kuror/Desktop/Cloudbot/engineer`, серверные runtime/config paths `/opt/*`, `/etc/*`, `/root/*`, `/home/node/*`, `/home/ops/*`, а также fallback на общий `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` в нескольких agent/runtime слоях.

Рекомендация: перед Wave 2 нужен явный freeze/acceptance текущего dirty-state. Без него Wave 2 запускать нельзя.

# 2. Dirty repo map

## 2.1 Git baseline

| item | value |
|---|---|
| repo | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` |
| branch | `codex/feature/self-healing` |
| HEAD | `dc19495e340a5899ca3451f4f492df65a63789da` |
| tracked diff stat | `106 files changed, 4801 insertions(+), 3951 deletions(-)` |
| modified tracked | `70` |
| deleted tracked | `36` |
| untracked | `46` |
| Wave 2 status | blocked |

## 2.2 Dirty top-level counts

| top-level zone | count | interpretation |
|---|---:|---|
| `agents` | 25 | production-critical agent code and new finance agent files |
| `infra` | 24 | deploy/runtime/server orchestration; high migration risk |
| `cloudbot` | 24 | shared-core orchestrator/providers/skills/workflows |
| `control_plane_snapshots` | 22 | deleted historical docs snapshot; likely archive cleanup, but not accepted |
| `scripts` | 15 | runtime helpers, sales bridge, finance scripts |
| `checks` | 9 | verification scripts; deleted VPN checks and modified smoke checks |
| `tests` | 8 | tests lock current module paths and runtime assumptions |
| `docs` | 7 | docs-only but includes canonical path statements |
| `ops` | 6 | runbooks and external data/source contract docs/scripts |
| `services` | 3 | deleted subscription/VPN legacy files |
| `configs` | 3 | env examples and cron schedule contracts |
| `ios` | 1 | untracked iOS app subtree; not Cloudbot core until confirmed |
| `.github` | 1 | untracked workflow |
| root files | 5 | `.env.integrations.example`, `.gitignore`, `AGENTS.md`, `Makefile` |

## 2.3 Modified files by category

| category | files / zones | assessment | Wave 2 handling |
|---|---|---|---|
| production-critical | `agents/larisa_ivanovna/agent.py`, `config.py`, providers, workflows, formatters | likely intentional but not accepted; directly affects Larisa | review-required, block-wave2 |
| production-critical | `agents/sales_agent/pipeline_analyzer.py`, `risk_detector.py`, `sales_agent.py`, `sales_formatter.py` | likely intentional but not accepted; directly affects Lev/Sales reports | review-required, block-wave2 |
| production-critical | `cloudbot/bot/telegram/commands.py`, `cloudbot/workflows/larisa_runtime.py` | likely intentional; affects Telegram routing and Larisa runtime bridge | review-required, block-wave2 |
| shared-core | `cloudbot/orchestrator/orchestrator.py`, `cloudbot/orchestrator/router.py` | likely intentional; shared routing can break multiple contours | review-required, block-wave2 |
| shared-core | `cloudbot/providers/bitrix/*`, `cloudbot/providers/search_provider.py`, `cloudbot/skills/bitrix_sales_data.py`, `cloudbot/skills/web_search.py` | likely intentional; providers/tools shared by multiple agents | review-required, block-wave2 |
| deploy/infra | `infra/orchestrator/run_workflow.sh`, `infra/orchestrator/workflows/*`, `scripts/run_sales_copilot.py`, `scripts/larisa_finalize.sh`, `scripts/verify_integrations.sh` | likely intentional mixed with risky runtime scripts | review-required, block-wave2 |
| deploy/infra | `configs/app_config.env.example`, `configs/schedule_contract.env`, `configs/schedules.cron`, `.env.integrations.example` | likely intentional; contains env/cron contracts and hardcoded paths | review-required, block-wave2 |
| tests-only | `tests/test_bitrix_app_auth.py`, `tests/test_bitrix_sales_adapter.py`, `tests/test_larisa_agent.py`, `tests/test_lev_petrovich_runtime.py` | likely intentional; locks import/runtime behavior | review-required before moving modules |
| docs-only | `docs/architecture/*`, `docs/larisa_execution_checklist_MSK.md`, `docs/message_for_larisa_MSK.md`, `docs/sales_copilot.md` | likely intentional; safe as documentation only, but contains stale path references | freeze-ready only after manual acceptance |
| legacy/unknown | deleted VPN/HAPP/subscription files under `infra`, `ops`, `services` | likely stale cleanup, but deletion is not accepted | investigate first |
| temp/noise | deleted `.DS_Store` inside `control_plane_snapshots` | likely generated artifact | cleanup candidate, not Wave 2 input |

## 2.4 Deleted tracked files

| path group | files | assessment | decision before Wave 2 |
|---|---|---|---|
| `checks` VPN/health checks | `checks/morning_health_report.sh`, `checks/vpn_smoke_happ.sh`, `checks/vpn_verify.sh` | likely stale or superseded, not confirmed | review-required |
| `control_plane_snapshots/architect_workspace_20260325_MSK` | 22 deleted files | likely archive cleanup, but deletion changes historical evidence | investigate first |
| HAPP/VPN infra | `infra/happ-vpn.env.example`, `infra/templates/sing-box.service`, `ops/architecture_happ_vpn.md`, `ops/runbook_happ_vpn.md`, `services/vpn/sing-box.server-template.json` | likely legacy cleanup | keep out of Wave 2 until accepted |
| deploy workflow scripts | `infra/orchestrator/workflows/audit.sh`, `deploy.sh`, `rollback.sh`, `verify.sh` | dangerous deletion because names are operational | block-wave2 until owner accepts |
| subscription service | `services/subscription/README.md`, `services/subscription/deploy_subscription.sh` | unclear legacy | investigate first |

## 2.5 Untracked files

| path group | files / examples | assessment | decision before Wave 2 |
|---|---|---|---|
| `.github` | `.github/workflows/sales-contract-checks.yml` | likely intentional CI addition | review-required |
| finance agent | `agents/finansist/*`, `cloudbot/workflows/finance_*.py`, `scripts/finansist_*.mjs`, `tests/test_finansist_agent.py` | new feature contour, not part of approved Larisa/Lev split | exclude from Wave 2 unless separately accepted |
| Larisa content/search | `agents/larisa_ivanovna/commands/get_content_*`, `get_web_search.py`, `workflows/content_topics.py`, `workflows/search.py`, `cloudbot/workflows/larisa_content_*`, `larisa_search.py`, `tests/test_larisa_search.py` | likely intentional product extension | review-required, block-wave2 for Larisa moves |
| sales contract | `agents/sales_agent/report_contract.py`, `tests/test_sales_dispatch_contract.py`, `checks/sales_morning_dispatch_smoke.py` | likely intentional runtime contract | review-required |
| shared search state | `cloudbot/orchestrator/search_state.py`, `tests/test_search_provider.py` | shared-core addition | review-required |
| infra env | `infra/remote-ops.env.example` | deploy/infra contract | review-required |
| iOS app | `ios/FormaNutrition/*` | separate product/app contour, relation to OpenCloud not confirmed | investigate first / exclude from Wave 2 |

## 2.6 Required zones explicitly requested

| zone | dirty state | category | assessment |
|---|---|---|---|
| `agents/larisa_ivanovna` | modified and untracked | production-critical | block-wave2 until accepted |
| `agents/lev_petrovich` | not directly dirty in status, but imported by changed sales scripts/tests | production-critical via dependency | review-required |
| `agents/sales_agent` | modified and untracked | production-critical / compatibility layer | block-wave2 until accepted |
| `cloudbot/orchestrator` | modified and untracked | shared-core | block-wave2 |
| `cloudbot/providers` | modified | shared-core | block-wave2 |
| `cloudbot/skills` | modified | shared-core | block-wave2 |
| `infra/orchestrator` | modified, deleted, untracked | deploy/infra | block-wave2 |
| `configs` | modified | deploy/infra | block-wave2 |
| `docs` | modified | docs-only with path drift | review-required |
| `tests` | modified and untracked | tests-only but path-locking | review-required |

# 3. Freeze proposal

## 3.1 Что нужно зафиксировать как baseline

Зафиксировать как baseline нужно не архитектурное решение, а точную фактическую точку перед Wave 2:

- branch: `codex/feature/self-healing`
- HEAD: `dc19495e340a5899ca3451f4f492df65a63789da`
- полный `git status --short`
- полный `git diff --stat`
- список modified/deleted/untracked
- список production-critical dirty zones
- список hidden coupling и absolute paths из этого файла
- подтверждение, что `/Users/pro2kuror/Desktop/Cloudbot` остаётся symlink-wrapper, а source of truth для кода остаётся `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- подтверждение, что `/Users/pro2kuror/Desktop/architect` остаётся docs/control-plane

## 3.2 Freeze-ready

Эти зоны можно принять как baseline только после явного подтверждения владельца, без технического изменения файлов:

| zone | why freeze-ready | caveat |
|---|---|---|
| `docs/architecture/*` | документация и архитектурные карты, не runtime | содержит старые и новые canonical path утверждения; проверить на противоречия |
| `docs/sales_copilot.md` | документация sales behavior | зависит от ещё не принятого sales runtime contract |
| `ops/external_data_sources_MSK.md` | операционная документация | не является runtime |
| `ops/owner_operating_contract_MSK.md` | contract docs | содержит `Cloudbot/engineer` как compatibility path |
| `control_plane_snapshots/*` deletion | похоже на archive cleanup | нельзя принимать без решения, что snapshot больше не нужен как evidence |

## 3.3 Review-required

Без ручного review нельзя принимать:

- все изменения в `agents/larisa_ivanovna`
- все изменения в `agents/sales_agent`
- изменения, влияющие на `agents/lev_petrovich` через `scripts/run_sales_copilot.py`, `cloudbot/devops/sales_dispatch_health.py`, tests
- `cloudbot/orchestrator/*`
- `cloudbot/providers/*`
- `cloudbot/skills/*`
- `cloudbot/workflows/*`
- `infra/orchestrator/*`
- `configs/*`
- `scripts/run_sales_copilot.py`
- `scripts/larisa_finalize.sh`
- `.env.integrations.example`
- `.github/workflows/sales-contract-checks.yml`
- all tests under `tests/*`

## 3.4 Block-wave2

Эти зоны должны быть исключены из Wave 2 до отдельного решения:

- dirty production code in `agents/larisa_ivanovna`
- dirty production/compatibility code in `agents/sales_agent`
- shared router and orchestrator changes in `cloudbot/orchestrator`
- shared provider/tool changes in `cloudbot/providers` and `cloudbot/skills`
- deploy scripts in `infra/orchestrator/workflows`
- runtime verification/rollback/deploy scripts
- `configs/schedules.cron` because it hardcodes `/Users/pro2kuror/Desktop/Cloudbot/engineer`
- `scripts/larisa_finalize.sh` because it hardcodes `/Users/pro2kuror/Desktop/Cloudbot/engineer`
- finance contour `agents/finansist`, finance workflows, finance scripts until separately accepted
- iOS contour `ios/FormaNutrition` until classified as external or in-scope
- deleted `deploy.sh`, `rollback.sh`, `verify.sh` workflow files until owner confirms they are obsolete

# 4. Absolute paths register

## 4.1 Summary

Absolute path scan found four classes of paths:

- local-machine paths: `/Users/pro2kuror/...`
- server-runtime paths: `/opt/cloudbot-runtime/*`, `/opt/openclaw/*`
- server-config paths: `/etc/openclaw/*`, `/etc/cron.d/*`, `/root/.openclaw/*`, `/home/node/.openclaw/*`
- server-log/report paths: `/var/log/*`, `/home/ops/*`

Shebangs like `#!/usr/bin/env bash` and `#!/usr/bin/env python3` were seen but are treated as normal script metadata, not migration blockers.

## 4.2 Runtime-sensitive and migration-sensitive paths

| file | line/context | path found | category | risk | blocks Wave 2 |
|---|---|---|---|---|---|
| `configs/schedules.cron` | lines 5, 7, 9 | `/Users/pro2kuror/Desktop/Cloudbot/engineer` | local-machine path | migration-sensitive | yes |
| `scripts/larisa_finalize.sh` | line 7 | `/Users/pro2kuror/Desktop/Cloudbot/engineer` | local-machine path | migration-sensitive | yes |
| `docs/larisa_execution_checklist_MSK.md` | line 5 | `/Users/pro2kuror/Desktop/Cloudbot/engineer` | local-machine path | harmless documentation, but stale canonical pointer | maybe |
| `docs/message_for_larisa_MSK.md` | lines 4, 17 | `/Users/pro2kuror/Desktop/Cloudbot/engineer` | local-machine path | harmless documentation, but stale canonical pointer | maybe |
| `ops/runbook_openclaw_security_profile_MSK.md` | line 28 | `/Users/pro2kuror/Desktop/Cloudbot/engineer` | local-machine path | harmless documentation, but stale canonical pointer | maybe |
| `ops/owner_operating_contract_MSK.md` | line 30 | `/Users/pro2kuror/Desktop/Cloudbot/architect`, `/Users/pro2kuror/Desktop/Cloudbot/engineer` | local-machine path | migration-sensitive compatibility statement | maybe |
| `docs/architecture/system_map.md` | lines 7, 13 | `/Users/pro2kuror/Desktop/Cloudbot/engineer`, `/Users/pro2kuror/Desktop/Cloudbot/architect` | local-machine path | migration-sensitive docs contract | maybe |
| `docs/architecture/system_map.md` | lines 14-22, 27-29, 185-186 | `/Users/pro2kuror/Desktop/OpenClo/projects/commercial-director`, `/Users/pro2kuror/Desktop/OpenClo/projects/whoop`, `/Users/pro2kuror/Desktop/OpenClo/archive/restored-workspace`, `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions` | local-machine path | harmless documentation / classification evidence | no |
| `ios/FormaNutrition/README_IOS.md` | lines 17, 43, 45 | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/ios/FormaNutrition/...` | local-machine path | migration-sensitive if iOS included | maybe |
| `scripts/run_sales_copilot.py` | lines 29-31 | `/opt/openclaw/.env`, `/opt/openclaw/state/bitrix_app`, `/root/.openclaw/telegram/commercial-director.bot_token` | server runtime/config path | runtime-sensitive | yes |
| `.env.integrations.example` | lines 16, 38 | `/opt/openclaw/state/bitrix_app`, `/root/.openclaw/telegram/commercial-director.bot_token` | server runtime/config path | migration-sensitive example contract | maybe |
| `configs/integrations.env.example` | lines 12, 27 | `/opt/openclaw/state/bitrix_app`, `/root/.openclaw/telegram/commercial-director.bot_token` | server runtime/config path | migration-sensitive example contract | maybe |
| `cloudbot/devops/system_health.py` | multiple lines around 347-511 | `/root/.openclaw/openclaw.json`, `/opt/openclaw/.env`, `/etc/openclaw/whoop.env`, `/opt/openclaw/state/bitrix_app`, `/root/.openclaw/workspace/todo-integration/.env.runtime`, `/etc/openclaw/todo.env` | server runtime/config path | runtime-sensitive | yes |
| `cloudbot/providers/bitrix/bitrix_app_auth.py` | line 252 | `/opt/openclaw/state/bitrix_app` | server runtime path | runtime-sensitive | yes |
| `cloudbot/providers/wazzup_provider.py` | lines 89, 95 | `/opt/openclaw/state/bitrix_app` | server runtime path | runtime-sensitive | yes |
| `agents/larisa_ivanovna/providers/tasks_provider.py` | lines 21-24 | `/home/node/.openclaw/todo-integration-data`, `/root/.openclaw/todo-integration-data`, `/root/.openclaw/workspace/todo-integration/data`, `/opt/openclaw/state/todo` | server runtime/data path | runtime-sensitive | yes |
| `agents/lev_petrovich/telegram_route.py` | line 11 | `/root/.openclaw/telegram/commercial-director.bot_token` | server secret-file path | runtime-sensitive | yes |
| `infra/orchestrator/lib.sh` | lines 61, 69-72 | `/root/.openclaw/workspace/todo-integration/.env.runtime`, `/etc/openclaw/todo.env`, `/home/node/.openclaw/todo-integration-data` | server runtime/config path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/larisa_agent_deploy.sh` | lines 11-14, 101-107, 143-157 | `/home/ops/cloudbot-larisa-agent`, `/usr/local/bin/cloudbot-larisa-daily-brief.sh`, `/etc/cron.d/cloudbot-larisa-daily-brief`, `/opt/cloudbot-runtime/larisa`, `/etc/openclaw/larisa.env`, `/opt/openclaw/.env`, `/etc/openclaw/whoop.env` | server runtime/deploy path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/sales_agent_deploy.sh` | multiple lines | `/home/ops/cloudbot-sales-agent`, `/usr/local/bin/cloudbot-sales-*.sh`, `/etc/cron.d/cloudbot-sales-reports`, `/etc/openclaw/sales_agent.env`, `/opt/cloudbot-runtime`, `/root/.openclaw/telegram/commercial-director.bot_token`, `/opt/openclaw/.env`, `/opt/openclaw/state/bitrix_app` | server runtime/deploy path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/cloudbot_runtime_verify.sh` | lines 10-12 and remote script body | `/opt/cloudbot-runtime/larisa`, `/opt/cloudbot-runtime/current`, `/usr/local/bin/cloudbot-larisa-daily-brief.sh`, `/etc/cron.d/cloudbot-larisa-daily-brief`, `/etc/cron.d/cloudbot-news-digest`, `/etc/openclaw/news_agent.env`, `/home/ops/cloudbot-larisa-agent`, `/home/ops/cloudbot-news-agent` | server runtime/legacy path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/cloudbot_runtime_rollback.sh` | lines 9, 73, 137 | `/opt/cloudbot-runtime/larisa` | server runtime path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/cloudbot_runtime_unlock.sh` | line 9 | `/opt/cloudbot-runtime/larisa/.deploy.lock` | server runtime lock path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/todo_digest_schedule.sh` | cron path | `/etc/cron.d/openclaw-todo-digest` | server config path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/todo-digest-repair.sh` | lines 11-15, 52, 246, 377, 407, 447 | `/root/.openclaw/workspace/todo-integration`, `/etc/cron.d/openclaw-todo-digest`, `/var/log/openclaw-todo-morning.log`, `/root/.openclaw/openclaw.json`, `/home/node/.openclaw/openclaw.json`, `/etc/openclaw`, `/opt/openclaw/.env`, `/opt/openclaw/docker-compose.yml`, `/opt/openclaw/dist`, `/root/openclaw-dist-backup.*.tgz` | server runtime/config/log path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/todo-digest-remediate.apply.remote.sh` | multiple lines | `/root/.openclaw/workspace/todo-integration`, `/etc/cron.d/openclaw-todo-digest`, `/root/.openclaw/openclaw.json`, `/home/node/.openclaw/workspace/todo-integration`, `/var/log/openclaw-todo-morning.log` | server runtime/config/log path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/todo-digest-remediate.smoke.remote.sh` | lines 5-8 | `/home/node/.openclaw/workspace/todo-integration`, `/root/.openclaw/workspace/todo-integration`, `/var/log/openclaw-todo-morning.log` | server runtime/log path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/whoop_report_repair.sh` | lines 19-20, 60-68 | `/etc/openclaw/whoop.env`, `/usr/local/bin/send_whoop_report.py` | server config/runner path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/whoop_morning_report_check.sh` | context | `/etc/openclaw/whoop.env`, `/usr/local/bin/send_whoop_report.py` | server config/runner path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/openclaw_gateway_repair.sh` | lines 11, 16, 18, 429-518, 774 | `/opt/openclaw`, `/opt/openclaw/.env`, `/root/.openclaw/openclaw.json`, `/home/node/.openclaw/openclaw.json`, `/home/ops/.openclaw/openclaw.json` | server runtime/config path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/openclaw_update.sh` | lines 9, 122, 153 | `/opt/openclaw`, `/root/.openclaw/openclaw.json` | server runtime/config path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/openclaw_update_permissions.sh` | lines 11, 30, 110 | `/etc/sudoers.d/openclaw-update-helper`, `/opt/openclaw`, optional `/usr/local/bin/openclaw` | server privileged/config path | runtime-sensitive | yes |
| `infra/orchestrator/workflows/excel_opiu_reconcile.sh` | line 8 | `/Users/pro2kuror/Downloads/Копия ДДС_2026.xlsx` | local-machine path | cleanup candidate / external input | maybe |
| `infra/openclaw-security-profile.env.example` | lines 1, 21 | `/opt/openclaw/.env.security_profile`, `/var/backups/openclaw`, `/opt/openclaw/backups`, `/root/.openclaw/backups` | server config/backup path | migration-sensitive example | maybe |
| `tests/test_system_health.py` | lines 109, 128, 147, 161, 181, 188 | `/opt/openclaw/state/bitrix_app/handler.latest.json`, `/home/node/.openclaw/todo-integration-data`, `/root/.openclaw/workspace/todo-integration/src/agenda/providers/googleCalendar.mjs` | test fixture path | migration-sensitive path lock | maybe |
| `server_snapshots/live_ams_1_vm_76ds_20260325/*` | many | `/opt/openclaw/*`, `/etc/cron.d/*`, `/root/.openclaw/*`, `/home/node/.openclaw/*`, `/var/log/*`, `/usr/local/bin/*` | snapshot evidence | harmless documentation unless copied into active code | no |

## 4.3 Path count hot spots

| file | approximate hit count | interpretation |
|---|---:|---|
| `docs/architecture/system_map.md` | 29 | architecture evidence and canonical path docs |
| `infra/orchestrator/workflows/sales_agent_deploy.sh` | 24 | live deploy script; runtime-sensitive |
| `docs/architecture/runtime_map.md` | 16 | runtime docs, migration-sensitive |
| `infra/orchestrator/workflows/larisa_agent_deploy.sh` | 13 | live deploy script; runtime-sensitive |
| `docs/architecture/larisa_live_contour_audit_20260325_MSK.md` | 12 | audit evidence with old/new runtime statements |
| `infra/orchestrator/workflows/todo-digest-repair.sh` | 9 | server-only repair script; runtime-sensitive |
| `infra/orchestrator/workflows/cloudbot_runtime_verify.sh` | 9 | runtime verification; runtime-sensitive |
| `cloudbot/devops/system_health.py` | 7 | hardcoded server health paths; runtime-sensitive |
| `infra/orchestrator/workflows/sales_agent_verify.sh` | 6 | generic runtime current coupling |

# 5. Hidden coupling register

| coupling_id | area | evidence | impact | Wave 2 status |
|---|---|---|---|---|
| HC-001 | old local canonical path | `configs/schedules.cron`, `scripts/larisa_finalize.sh`, docs use `/Users/pro2kuror/Desktop/Cloudbot/engineer` | moving source layout can leave cron/scripts pointing at wrapper path | block until compatibility decision |
| HC-002 | Cloudbot symlink assumption | docs and scripts still use `/Users/pro2kuror/Desktop/Cloudbot/engineer` while source of truth is `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | Wave 2 could accidentally reorganize wrapper instead of canonical repo | block until marker/ADR accepted |
| HC-003 | shared env fallback for Larisa | `agents/larisa_ivanovna/config.py` accepts `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`; `larisa_agent_deploy.sh` exports generic token/chat into Larisa-specific vars | one shared Telegram env can bind Larisa to wrong bot/chat | block env separation |
| HC-004 | shared env fallback for Sales/Lev | `scripts/run_sales_copilot.py` falls back to `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`; `sales_weekly_review.sh`, `sales_followup.sh`, `sales_dispatch_health.py` also use shared fallbacks | Lev/Sales contour can be affected by common env intended for another agent | block env separation |
| HC-005 | generic runtime current | `sales_agent_deploy.sh` uses `/opt/cloudbot-runtime/current`; `cloudbot_runtime_verify.sh` checks both Larisa scoped and generic current | generic current remains live for sales; cannot be deleted or repointed during layout migration | block runtime changes |
| HC-006 | Larisa scoped runtime | `larisa_agent_deploy.sh`, `cloudbot_runtime_rollback.sh`, `cloudbot_runtime_unlock.sh` use `/opt/cloudbot-runtime/larisa/*` | must preserve during Wave 2; no runtime pointer switch without smoke checks | block runtime changes |
| HC-007 | agents/sales_agent compatibility layer | `agents/lev_petrovich/agent.py` imports from `agents.sales_agent.sales_agent`; `agents/sales_agent/sales_agent.py` imports `agents.lev_petrovich.telegram_route` | Lev and Sales are mutually coupled; moving one without alias can break both | block app split until compatibility plan |
| HC-008 | shared cloudbot imports | tests and runtime import `cloudbot.orchestrator`, `cloudbot.providers`, `cloudbot.skills`, `cloudbot.workflows` directly | app split requires package import plan before moving directories | block shared extraction |
| HC-009 | Larisa runtime bridge imports agent package | `cloudbot/workflows/larisa_runtime.py` imports `agents.larisa_ivanovna.*` | moving Larisa into `apps/larisa` requires compatibility module or import migration | block app layout |
| HC-010 | finance contour added into shared router/workflows | untracked `agents/finansist`, `cloudbot/workflows/finance_*`, tests import finance agent | finance may be new app, external tool, or experiment; not classified | exclude from Wave 2 |
| HC-011 | todo server-only contour | `infra/orchestrator/lib.sh`, `todo-digest-repair.sh`, server snapshots reference `/root/.openclaw/workspace/todo-integration` and container `/home/node/.openclaw/workspace/todo-integration` | server-only integration may break if treated as normal repo module | investigate first |
| HC-012 | Bitrix app state path | `scripts/run_sales_copilot.py`, `cloudbot/devops/system_health.py`, providers, env examples use `/opt/openclaw/state/bitrix_app` | provider state is server runtime data, not source code | keep external/runtime-only |
| HC-013 | docs contain old and new runtime claims | `docs/architecture/larisa_live_contour_audit_20260325_MSK.md` says active cron pointed to `/opt/cloudbot-runtime/current`, but later notes scoped `/opt/cloudbot-runtime/larisa/current` | can mislead cutover decisions | review docs before Wave 2 |
| HC-014 | tests lock old import paths | `tests/test_larisa_agent.py`, `tests/test_lev_petrovich_runtime.py`, `tests/test_finansist_agent.py`, `tests/test_sales_dispatch_contract.py` import old packages | moving files without compatibility aliases breaks tests | block app layout |
| HC-015 | server snapshots include stale live wrappers | `server_snapshots/.../usr/local/bin/cloudbot-larisa-daily-brief.sh` contains `cd '/opt/cloudbot-runtime/current'` | snapshot evidence can be mistaken for current live state | classify as archive/evidence only |

# 6. Wave 2 readiness verdict

Verdict: **not ready**.

Wave 2 was supposed to start apps layout work. That is currently unsafe because:

1. Dirty repo contains production-critical changes, not just docs.
2. Dirty repo contains deploy/runtime scripts that affect server behavior.
3. There are untracked new contours (`agents/finansist`, `ios/FormaNutrition`) with unclear scope.
4. There are deleted tracked deploy/rollback/verify scripts that must not silently disappear during reorg.
5. Absolute local paths still point to `/Users/pro2kuror/Desktop/Cloudbot/engineer`, while accepted source of truth is `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`.
6. Env fallbacks still allow generic `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` to affect agent identity.
7. Lev/Sales compatibility is still coupled through imports between `agents/lev_petrovich` and `agents/sales_agent`.
8. Tests lock current import paths and will fail or become misleading if apps layout begins without compatibility plan.

Condition for readiness: Wave 2 can start only after freeze acceptance is explicit and all block-wave2 zones are either accepted, committed by owner process, or excluded from Wave 2 scope with written decision.

# 7. Minimal actions required before Wave 2

Ничего из списка ниже не выполнено в этом аудите. Это только минимальные действия, которые нужно согласовать и выполнить отдельно.

1. Owner acceptance of dirty baseline:
   - принять или отклонить текущий dirty-state на branch `codex/feature/self-healing`
   - отдельно решить судьбу `70 M`, `36 D`, `46 ??`

2. Review production-critical changes:
   - `agents/larisa_ivanovna`
   - `agents/sales_agent`
   - `cloudbot/orchestrator`
   - `cloudbot/providers`
   - `cloudbot/skills`
   - `cloudbot/workflows`
   - `scripts/run_sales_copilot.py`

3. Review deploy/infra changes:
   - `infra/orchestrator/workflows/*`
   - `configs/*`
   - `.env.integrations.example`
   - `.github/workflows/sales-contract-checks.yml`

4. Decide deleted files:
   - deleted `deploy.sh`, `rollback.sh`, `verify.sh`
   - deleted VPN/HAPP files
   - deleted subscription files
   - deleted `control_plane_snapshots/architect_workspace_20260325_MSK/*`

5. Classify new contours:
   - `agents/finansist`
   - finance workflows and scripts
   - `ios/FormaNutrition`

6. Accept compatibility contract before moving files:
   - `agents/sales_agent` remains compatibility layer until Lev migration is complete
   - `cloudbot/*` remains import-compatible during apps/shared extraction
   - `Cloudbot` symlink-wrapper must not become source of truth

7. Create pre-Wave 2 no-change decisions:
   - no runtime pointer changes
   - no env fallback changes
   - no cron edits
   - no deploy scripts edits
   - no systemd/docker changes

8. Produce Wave 2 entry checklist:
   - exact scope of folders to reorganize
   - exact folders excluded
   - test commands for both Larisa and Lev/Sales
   - rollback plan for source-only layout change

# 8. What to send back to ChatGPT

Перед следующим этапом отправить:

```text
Pre-Wave 2 freeze audit complete.

Verdict: not ready for Wave 2.

Engineer repo:
- path: /Users/pro2kuror/Desktop/OpenClo/projects/engineer
- branch: codex/feature/self-healing
- HEAD: dc19495e340a5899ca3451f4f492df65a63789da
- diff: 106 files changed, 4801 insertions(+), 3951 deletions(-)
- status: 70 modified, 36 deleted, 46 untracked

Main blockers:
1. Dirty production-critical code in agents/larisa_ivanovna, agents/sales_agent, cloudbot/orchestrator, cloudbot/providers, cloudbot/skills, cloudbot/workflows.
2. Dirty deploy/runtime code in infra/orchestrator, configs, scripts/run_sales_copilot.py.
3. Hardcoded local paths still reference /Users/pro2kuror/Desktop/Cloudbot/engineer.
4. Runtime-sensitive server paths are embedded in deploy scripts and health/providers.
5. Shared TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID fallback still couples agent identity.
6. Lev/Sales compatibility layer still couples agents/lev_petrovich and agents/sales_agent.
7. New unclear contours: agents/finansist and ios/FormaNutrition.

Required before Wave 2:
- explicit owner acceptance/rejection of current dirty-state
- manual review of production-critical and deploy/infra changes
- decision on deleted tracked scripts and snapshots
- classification of finance and iOS contours
- written compatibility contract for old imports and Cloudbot symlink wrapper

Full report file:
/Users/pro2kuror/Desktop/architect/opencloud_pre_wave2_freeze_audit.md
```
