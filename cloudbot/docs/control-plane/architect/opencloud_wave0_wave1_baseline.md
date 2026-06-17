# OpenCloud / Cloudbot Wave 0-1 baseline

Дата: 2026-04-23 МСК  
Режим: baseline freeze + classification only.  
Изменения runtime не выполнялись: код, env, cron, systemd, docker, symlink, runtime pointers, deploy и git commits не менялись.

Созданные артефакты:

- `/Users/pro2kuror/Desktop/architect/baseline_local_workspace.md`
- `/Users/pro2kuror/Desktop/architect/baseline_server_runtime.md`
- `/Users/pro2kuror/Desktop/architect/baseline_git_state.md`
- `/Users/pro2kuror/Desktop/architect/opencloud_wave0_wave1_baseline.md`

## 1. Wave 0 summary

Wave 0 выполнен как read-only фиксация текущего состояния.

Локальная машина:

- Canonical application source: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- Docs/control-plane source: `/Users/pro2kuror/Desktop/architect`
- Cloudbot wrapper: `/Users/pro2kuror/Desktop/Cloudbot`
- `Cloudbot` подтвержден как symlink-обертка, не source of truth:
  - `/Users/pro2kuror/Desktop/Cloudbot/engineer -> /Users/pro2kuror/Desktop/OpenClo/projects/engineer`
  - `/Users/pro2kuror/Desktop/Cloudbot/architect -> /Users/pro2kuror/Desktop/architect`
  - `/Users/pro2kuror/Desktop/Cloudbot/paperclip -> /Users/pro2kuror/Desktop/tools/paperclip`

Git:

- Engineer repo branch: `codex/feature/self-healing`
- Engineer repo HEAD: `dc19495e340a5899ca3451f4f492df65a63789da`
- Engineer repo remote: `https://github.com/Johnnie13Walker/codex-base.git`
- Engineer repo status: dirty, ahead of origin by 3 commits, 106 tracked modified/deleted entries, 36 deleted paths, 46 untracked paths.
- Architect repo branch: `codex/docs-bootstrap`
- Architect repo HEAD: `bd7e1b63a457807342283bdd7c80e0164407a399`
- Architect repo remote: not configured / no remote output observed.
- Architect repo status: dirty, 10 tracked modified entries, 63 untracked paths.

Server:

- Host: `ams-1-vm-76ds`
- Baseline timestamp: `2026-04-23 11:34:36 МСК`
- Larisa runtime:
  - `/opt/cloudbot-runtime/larisa/current`
  - target: `/opt/cloudbot-runtime/larisa/releases/codex_feature_self-healing_067d326`
  - commit: `067d326c5c23e4486efbef87741012211af1adaf`
- Lev/Sales runtime:
  - `/opt/cloudbot-runtime/current`
  - target: `/opt/cloudbot-runtime/releases/codex_feature_self-healing_c329f60`
  - commit: `c329f6077b87dc332703d043dc82a41b9f131edd`
- Services:
  - `cloudbot-bitrix-app.service`: enabled, active, running
  - `docker.service`: enabled, active, running
- Containers:
  - `openclaw-openclaw-gateway-1`: healthy
  - `searxng`: up
  - `searxng-redis`: up
- Active relevant cron files confirmed:
  - `/etc/cron.d/cloudbot-larisa-daily-brief`
  - `/etc/cron.d/cloudbot-sales-reports`
  - `/etc/cron.d/openclaw-todo-digest`
  - `/etc/cron.d/openclaw-whoop-report`

## 2. Wave 0 baseline artifacts

### 2.1 `baseline_local_workspace.md`

Purpose:

- фиксирует локальные source-of-truth paths;
- подтверждает `Cloudbot` как symlink wrapper;
- фиксирует локальные legacy/external/archive зоны.

Key facts:

- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` is canonical application source.
- `/Users/pro2kuror/Desktop/architect` is docs/control-plane source.
- `/Users/pro2kuror/Desktop/Cloudbot` is not source of truth.
- `/Users/pro2kuror/Desktop/tools/paperclip` is external.

### 2.2 `baseline_git_state.md`

Purpose:

- фиксирует git branch, HEAD, remote и dirty-state без коммитов или изменений.

Key facts:

- Engineer repo dirty and ahead 3.
- Architect repo dirty and has no remote output observed.
- Wave 2 should not start until dirty state is explicitly accepted or frozen in a controlled way.

### 2.3 `baseline_server_runtime.md`

Purpose:

- фиксирует live server runtime paths, cron, services, containers, env paths and timestamps only.

Key facts:

- Лариса уже имеет scoped runtime pointer.
- Lev/Sales пока использует generic runtime pointer.
- Todo legacy contour active for sync/reminders/execution.
- WHOOP report cron active.
- Env file paths observed, values not read or printed.

## 3. Wave 1 classification table

| Path | Role | Classification | Source of truth | Migration priority | Notes |
|---|---|---|---|---|---|
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | Основной инженерный repo Cloudbot/OpenClo | prod/dev | yes | now | Canonical application source. Dirty state must be frozen before structural migration. |
| `/Users/pro2kuror/Desktop/Cloudbot` | Symlink workspace wrapper | dev | no | later | Convenience entrypoint only. Must not be treated as source of truth. |
| `/Users/pro2kuror/Desktop/architect` | Docs/control-plane repo | dev | yes | now | Source of truth for docs/control-plane; dirty with many generated/report artifacts. |
| `/Users/pro2kuror/Desktop/tools` | Tools workspace, Paperclip parent | external | no | never_migrate | External tool zone, not OpenCloud runtime. |
| `/Users/pro2kuror/Desktop/tools/paperclip` | Paperclip orchestration product | external | no | never_migrate | Keep external; may be referenced as tool only. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/commercial-director` | Old sales/knowledge contour | legacy | no | later | Archive candidate as `commercial-director-pre-lev`; do not use as current source. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop` | Standalone WHOOP sandbox | unclear | partial | investigate_first | Contains local WHOOP module; live WHOOP currently server cron/script. Need separate role decision. |
| `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions` | JS experimental OpenClaw extensions | legacy | no | later | Archive/experiments candidate; has JS orchestrator/router/workflow/provider prototypes. |
| `/Users/pro2kuror/Desktop/OpenClo/archive/restored-workspace` | Restored historical workspace | archive | no | later | Archive evidence; not active runtime. |
| `/opt/cloudbot-runtime/larisa/current` | Live Larisa runtime pointer | prod | partial | later | Runtime source, not code source. Target currently scoped to Larisa. |
| `/opt/cloudbot-runtime/current` | Live generic runtime pointer used by Lev/Sales | prod/legacy | partial | investigate_first | Currently serves Sales/Lev; target should become scoped runtime. |
| `/opt/openclaw` | OpenClaw platform runtime/env/state | prod | partial | investigate_first | External platform runtime; not agent source. Contains Bitrix app env and docker compose. |
| `/root/.openclaw/workspace/todo-integration` | Server-only Todo legacy integration | prod/legacy | partial | investigate_first | Active sync/reminders/execution; do not archive before dependency map. |
| `/etc/openclaw` | Server env directory | prod | partial | investigate_first | Runtime-only env path. Values must not enter git. |
| `/etc/cron.d/cloudbot-larisa-daily-brief` | Active Larisa cron | prod | partial | later | Live schedule: 08:00 МСК via UTC expression. Document template later; do not edit now. |
| `/etc/cron.d/cloudbot-sales-reports` | Active Sales/Lev cron | prod | partial | later | Live schedules for daily/check/followup/weekly. Do not edit now. |
| `/etc/cron.d/openclaw-todo-digest` | Active legacy Todo cron | prod/legacy | partial | investigate_first | Digest jobs disabled, but sync/reminders/execution active. |
| `/etc/cron.d/openclaw-whoop-report` | Active WHOOP report cron | prod | partial | investigate_first | WHOOP live status confirmed at cron level; app ownership unclear. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/larisa_ivanovna` | Larisa agent code | prod/dev | yes | now | Must become `apps/larisa_ivanovna`; migrate as-is first. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/lev_petrovich` | Lev role code | prod/dev | yes | now | Must become `apps/lev_petrovich`; keep current behavior. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/agents/sales_agent` | Sales compatibility layer | prod/legacy | partial | now | Do not delete. Move later under `apps/lev_petrovich/legacy_sales_agent`. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/orchestrator` | Shared routing/orchestration | prod/dev | yes | now | High blast radius. Target `shared/orchestrator`. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/cloudbot/providers` | Shared providers | prod/dev | yes | now | Target `shared/providers`; agent-specific adapters need separation later. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/infra/orchestrator` | Shell workflow/orchestration | prod/dev | yes | now | Target `infra/orchestrator`; migrate as-is first. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/configs` | Local config templates/contracts | dev/prod-contract | yes | now | Target `config/*`; split env examples and schedules. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs` | Engineering docs | dev | partial | now | Merge/classify with architect docs later. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/server_snapshots` | Server evidence snapshots | archive/dev | partial | later | Target `infra/server_snapshots`; evidence only. |

## 4. Proposed source-of-truth markers

No files were created in these locations. This is a proposal only.

| Location | Proposed file name | Purpose | Short content outline |
|---|---|---|---|
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | `SOURCE_OF_TRUTH.md` | Mark canonical application source | Repo role, active branches, what belongs here, what does not, link to migration plan. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` | `MIGRATION_BASELINE.md` | Freeze Wave 0 facts in app repo later | Branch/HEAD, dirty warning, source map, server runtime pointers. |
| `/Users/pro2kuror/Desktop/architect` | `CONTROL_PLANE.md` | Mark docs/control-plane source | Docs role, status files, audits, decisions, not runtime code. |
| `/Users/pro2kuror/Desktop/architect/docs` | `DOCS_CLASSIFICATION.md` | Classify docs zones | Architecture, runbooks, audits, generated reports, status, prompts. |
| future `archive/` root | `ARCHIVE_README.md` | Prevent accidental runtime use | Archive rules, no active code, how to restore/read historical material. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/commercial-director` | `LEGACY_NOT_SOURCE_OF_TRUTH.md` | Mark old sales contour | Superseded by `agents/lev_petrovich`; do not use for new features. |
| `/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions` | `EXPERIMENTAL_NOT_RUNTIME.md` | Mark incubator/experiment | JS prototypes, no prod source-of-truth, migration needs explicit decision. |
| `/Users/pro2kuror/Desktop/OpenClo/projects/whoop` | `WHOOP_STATUS_INVESTIGATE.md` | Mark unclear WHOOP ownership | Local sandbox vs server cron; list checks needed before migration. |
| `/Users/pro2kuror/Desktop/tools/paperclip` | `EXTERNAL_TOOL.md` | Mark Paperclip external | External orchestration product, not OpenCloud runtime. |
| `/Users/pro2kuror/Desktop/Cloudbot` | `WRAPPER_NOT_SOURCE_OF_TRUTH.md` | Mark symlink wrapper | Symlink map, canonical paths, warning against direct source assumptions. |
| server runtime docs later | `SERVER_RUNTIME_BASELINE.md` | Document current live runtime | Larisa pointer, Sales pointer, OpenClaw, Todo legacy, cron, env paths only. |

## 5. Proposed decision records

No ADR files were written. These are drafts only.

### ADR 1. Cloudbot is not source of truth

Status: proposed

Context:

- `/Users/pro2kuror/Desktop/Cloudbot` exists and looks like a workspace.
- It contains symlinks to real source locations.

Decision:

- Treat `/Users/pro2kuror/Desktop/Cloudbot` as a convenience wrapper only.
- Canonical application source remains `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`.
- Canonical docs/control-plane source remains `/Users/pro2kuror/Desktop/architect`.

Consequences:

- No migrations should target `Cloudbot` as physical source.
- Future cleanup may update wrapper symlinks only in a dedicated wave.

### ADR 2. Engineer repo is canonical application source

Status: proposed

Context:

- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` contains app code, tests, configs, infra workflows and source docs.
- Git remote is `https://github.com/Johnnie13Walker/codex-base.git`.

Decision:

- Treat this repo as application source of truth until a controlled migration changes that.

Consequences:

- All app restructuring must start here.
- Dirty state must be frozen before Wave 2.

### ADR 3. Architect is docs/control-plane

Status: proposed

Context:

- `/Users/pro2kuror/Desktop/architect` contains plans, status, checklists, prompts, architecture docs and audits.

Decision:

- Treat `architect` as docs/control-plane source, not runtime code source.

Consequences:

- Docs must be classified before merging into target `docs/`.
- Generated reports should be separated from durable architecture/control documents.

### ADR 4. sales_agent remains compatibility layer

Status: proposed

Context:

- `agents/lev_petrovich` is canonical role code.
- `agents/sales_agent` is still referenced by runtime/tests and report logic.

Decision:

- Keep `agents/sales_agent` as compatibility layer until Lev migration is complete.

Consequences:

- Do not delete or rewrite `sales_agent` during Wave 1-4.
- Target location later: `apps/lev_petrovich/legacy_sales_agent`.

### ADR 5. generic runtime current is legacy

Status: proposed

Context:

- `/opt/cloudbot-runtime/current` currently serves Lev/Sales.
- Larisa already uses scoped pointer `/opt/cloudbot-runtime/larisa/current`.

Decision:

- Treat generic `/opt/cloudbot-runtime/current` as legacy runtime pointer.
- Future runtime should use scoped pointer for Lev/Sales.

Consequences:

- No new agent deploy should depend on generic `current`.
- Cutover to scoped Lev runtime requires dedicated Wave 5/7 plan.

### ADR 6. shared env must not hold agent identity

Status: proposed

Context:

- Shared env currently mixes general integration keys and agent-specific Telegram identities.

Decision:

- Shared env may hold infrastructure config.
- Agent identity belongs in per-agent env.
- Generic `TELEGRAM_BOT_TOKEN` must not be fallback for Larisa or Lev identity.

Consequences:

- Need env schemas for `shared.env`, `larisa.env`, `lev_petrovich.env`.
- Compatibility aliases may exist temporarily, but must be explicit.

### ADR 7. Paperclip is external

Status: proposed

Context:

- `/Users/pro2kuror/Desktop/tools/paperclip` is a full external orchestration product.
- It has OpenClaw-related adapters/docs but is not Cloudbot runtime.

Decision:

- Treat Paperclip as external tool, not OpenCloud source tree.

Consequences:

- Do not migrate Paperclip into OpenCloud.
- References to Paperclip should be docs/tooling only.

## 6. Wave 0/1 risk register

| risk_id | description | impact | likelihood | mitigation | blocker_for_next_wave |
|---|---|---:|---:|---|---|
| W01-R001 | Engineer repo is heavily dirty: modified, deleted and untracked files in production-critical areas. | high | high | Freeze status, review diff ownership, avoid Wave 2 until dirty state is accepted or split into intentional branches. | yes |
| W01-R002 | Architect repo is dirty and contains generated/reporting artifacts mixed with durable docs. | medium | high | Classify docs before merging into target `docs/`; separate generated outputs. | no |
| W01-R003 | Server drift between baseline and future migration. | high | medium | Re-run read-only server baseline immediately before Wave 5/Wave 7. | yes for runtime waves |
| W01-R004 | Proxy/SSH ambiguity: `cloudbot-ssh-proxy` may fail while direct SSH works. | medium | medium | Document official read-only access path; avoid assuming proxy alias health. | no |
| W01-R005 | Hidden absolute paths to `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` and `/Users/pro2kuror/Desktop/architect`. | high | high | Run path reference scan before physical moves; replace only in controlled wave. | yes |
| W01-R006 | WHOOP live ownership unclear: local sandbox exists and server cron exists. | medium | medium | Investigate WHOOP separately before migration; classify local sandbox vs server app. | no |
| W01-R007 | News live status unclear in current Wave 0 data. | medium | medium | Add news-specific live audit before moving news code/env. | no |
| W01-R008 | Todo legacy contour remains active for sync/reminders/execution. | high | high | Keep `/root/.openclaw/workspace/todo-integration` untouched until dependency map exists. | yes for todo migration |
| W01-R009 | Accidental confusion between `Cloudbot` wrapper and `engineer` repo. | high | high | Add future marker `WRAPPER_NOT_SOURCE_OF_TRUTH.md`; use absolute canonical paths in plans. | no |
| W01-R010 | Generic `/opt/cloudbot-runtime/current` is still live for Sales/Lev and can be mistaken for shared safe pointer. | high | high | Treat as legacy; require explicit runtime scope in future deploy design. | yes for runtime waves |
| W01-R011 | Shared env contains or implies agent identity fallback. | high | medium | Draft env contract; prohibit generic Telegram fallback in target design. | yes for env wave |
| W01-R012 | Old `.bak` cron files on server may confuse operators. | medium | medium | Document active cron list; do not cleanup until Wave 8. | no |

## 7. Ready / not ready for Wave 2

Status: **not ready for Wave 2 implementation**.

Ready:

- Wave 0 baseline exists.
- Wave 1 classification exists.
- Source-of-truth candidates are identified.
- Server runtime baseline is confirmed.

Not ready:

- Engineer repo dirty state is too large to start structural moves safely.
- Hidden absolute path scan has not been completed as a migration gate.
- WHOOP/news/todo ownership still has `investigate_first` items.
- No source-of-truth marker files have been approved or added.
- No ADRs have been approved or added.

Minimum gates before Wave 2:

1. Accept or freeze current dirty state of `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`.
2. Approve source-of-truth marker files.
3. Approve ADRs 1-7.
4. Run absolute path reference scan.
5. Decide whether Wave 2 happens in current repo branch or a new dedicated migration branch.

## 8. What to send back to ChatGPT

```text
Wave 0/Wave 1 completed as documentation-only baseline.
No runtime, code, env, cron, systemd, docker, symlink, deploy or git commit changes were made.

Artifacts:
- /Users/pro2kuror/Desktop/architect/baseline_local_workspace.md
- /Users/pro2kuror/Desktop/architect/baseline_git_state.md
- /Users/pro2kuror/Desktop/architect/baseline_server_runtime.md
- /Users/pro2kuror/Desktop/architect/opencloud_wave0_wave1_baseline.md

Key facts:
- Application source of truth: /Users/pro2kuror/Desktop/OpenClo/projects/engineer
- Docs/control-plane source: /Users/pro2kuror/Desktop/architect
- Cloudbot is symlink wrapper, not source of truth.
- Larisa runtime: /opt/cloudbot-runtime/larisa/current -> codex_feature_self-healing_067d326
- Lev/Sales runtime: /opt/cloudbot-runtime/current -> codex_feature_self-healing_c329f60
- cloudbot-bitrix-app.service and docker.service are active.
- openclaw gateway container is healthy.
- active cron files: cloudbot-larisa-daily-brief, cloudbot-sales-reports, openclaw-todo-digest, openclaw-whoop-report.

Readiness:
- Not ready for Wave 2 implementation until dirty repo state is accepted/frozen, ADRs are approved, source-of-truth markers are approved, and absolute path scan is done.
```

