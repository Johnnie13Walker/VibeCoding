# 1. Wave 2 include manifest

Дата gate package: 2026-04-23, МСК.

Статус: **Wave 2 not approved**. Этот include manifest описывает только то, что **может** войти в Wave 2 после owner approval. Он не является разрешением на перенос файлов.

Owner decision recorded on 2026-04-23 МСК:

- baseline evidence accepted: `opencloud_pre_wave2_freeze_audit.md`, `opencloud_wave0_wave1_baseline.md`, `opencloud_target_reorg_plan.md`, `opencloud_owner_decision_package.md`
- code source of truth confirmed: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- `/Users/pro2kuror/Desktop/Cloudbot` confirmed as wrapper/symlink only
- docs/control-plane confirmed: `/Users/pro2kuror/Desktop/architect`
- Wave 2 remains not approved
- dirty production/shared-core/infra/config changes are excluded from Wave 2
- finance, iOS, Larisa content/search, Sales/Lev hardening, shared search, HAPP/VPN/subscription cleanup and CI additions are separate tracks
- runtime pointers, env, cron, systemd, docker, deploy scripts and server-only integrations remain no-touch until separate review

Wave 2 scope должен быть только structural migration scope. Feature work, runtime behavior, deploy scripts, live env/cron/systemd/docker и server pointers не входят.

| path / zone | why in scope | preconditions | blocked by | validation needed | owner approval needed |
|---|---|---|---|---|---|
| `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` repo boundary | canonical source of truth для application source | owner подтверждает canonical path; dirty-state disposition complete | dirty repo `70 M`, `36 D`, `46 ??`; path confusion with `/Users/pro2kuror/Desktop/Cloudbot/engineer` | `git status --short`, branch/HEAD baseline, no unexpected scope additions | yes |
| `/Users/pro2kuror/Desktop/architect` docs/control-plane boundary | docs/control-plane source remains external to runtime code | owner принимает docs/control-plane as separate source of truth | docs may contain stale runtime/path statements | docs reference checklist only, no runtime edits | yes |
| `agents/larisa_ivanovna` structural app boundary only | candidate app boundary for Larisa in target `apps/larisa_ivanovna` model | Larisa production changes reviewed or explicitly excluded; smoke checklist defined | dirty feature changes and env fallback coupling | Larisa smoke checklist must be defined before any structural move | yes |
| `agents/lev_petrovich` structural app boundary only | candidate app boundary for Lev in target `apps/lev_petrovich` model | compatibility decision with `agents/sales_agent` fixed | `agents/lev_petrovich` depends on `agents/sales_agent`; not directly dirty but coupled | Lev/Sales smoke checklist must be defined | yes |
| `agents/sales_agent` compatibility boundary only | compatibility layer may need to remain addressable during target app split | owner decides `sales_agent` remains temporary compatibility layer | dirty sales feature/runtime changes; report contract untracked | tests for Lev/Sales import compatibility defined, not necessarily executed in this gate | yes |
| `cloudbot` package as shared boundary only | target `shared/` extraction depends on existing shared package map | shared-core functional changes excluded from Wave 2; compatibility import strategy approved | dirty router/providers/skills/workflows | import compatibility checklist; no functional rewrite | yes |
| `cloudbot/orchestrator` structural classification only | orchestrator is target shared/runtime boundary | router/search feature changes excluded or accepted outside Wave 2 | dirty `router.py`, `orchestrator.py`, untracked `search_state.py` | import map and no-behavior-change rule | yes |
| `cloudbot/providers` structural classification only | providers belong to target shared/providers boundary | provider functional changes reviewed separately | Bitrix/search provider changes dirty; server state paths hardcoded | dependency map for Bitrix/search/Wazzup/Todo/WHOOP | yes |
| `cloudbot/skills` structural classification only | skills belong to target shared/skills boundary | skill functional changes excluded | dirty Bitrix sales and web search changes | import compatibility checklist | yes |
| `cloudbot/workflows` structural classification only | workflows need target placement rules | workflow feature changes excluded | Larisa/search/finance workflow changes | workflow classification table | yes |
| `configs` classification only | target `config/` scheme needs source classification | live env/cron changes excluded; examples only after review | `configs/schedules.cron` hardcodes `/Users/pro2kuror/Desktop/Cloudbot/engineer` | absolute path review and config contract decision | yes |
| `tests` classification only | tests define validation surface for structural migration | owner decides which tests are gate tests | tests currently lock old import paths and include dirty/untracked new tests | Larisa and Lev/Sales smoke checklist defined | yes |
| `docs/architecture/*` as reference evidence | architecture docs provide system map and runtime map | accepted as evidence, not as final runtime contract | stale/contradictory runtime/path statements | mark stale sections before relying on them | yes |
| target folders concept `apps/`, `shared/`, `config/`, `infra/`, `docs/`, `archive/`, `tests/` | approved target model from reorg plan | exact include/exclude scope frozen | no owner approval yet; dirty repo not dispositioned | owner signs one-page approval | yes |

# 2. Wave 2 exclude manifest

These zones are **not** in Wave 2. They must not silently enter structural migration.

| path / zone | why excluded | when it can be revisited | separate track name |
|---|---|---|---|
| `agents/larisa_ivanovna` feature changes | dirty production feature work: content/search, workflows, formatters, providers, env behavior | after manual Larisa feature review and smoke checklist | Larisa Feature Track |
| `agents/larisa_ivanovna/commands/get_content_post.py`, `get_content_topics.py`, `get_web_search.py` | untracked feature files, not structural migration | after owner accepts Larisa content/search feature | Larisa Content/Search |
| `agents/larisa_ivanovna/workflows/content_topics.py`, `workflows/search.py`, `schemas/content.py`, `timezone.py` | new behavior and schemas | after feature review | Larisa Content/Search |
| `cloudbot/workflows/larisa_content_post.py`, `larisa_content_topics.py`, `larisa_search.py` | runtime bridge for feature work | after Larisa feature accepted | Larisa Runtime Bridge |
| `infra/orchestrator/workflows/larisa_content_topics.sh` | runtime script, can affect execution | after infra/runtime review | Larisa Runtime Ops |
| `agents/sales_agent/*` feature/runtime changes | dirty Lev/Sales production behavior and formatter/report logic | after Sales/Lev review | Sales/Lev Feature Track |
| `agents/sales_agent/report_contract.py` | untracked contract addition; useful but not structural | after owner accepts sales contract hardening | Sales Contract Track |
| `scripts/run_sales_copilot.py` | runtime bridge using server env/state/token-file paths | after Sales/Lev runtime review | Sales Runtime Bridge |
| `cloudbot/devops/sales_dispatch_health.py` | health/alert behavior, shared with Sales/Lev | after monitoring contract review | Sales Monitoring Track |
| `agents/lev_petrovich` behavior | coupled to `agents/sales_agent`; not to be changed in Wave 2 | after compatibility decision and tests | Lev Compatibility Track |
| `cloudbot/orchestrator/orchestrator.py`, `router.py`, `search_state.py` functional changes | shared-core functional changes affect multiple agents | after shared-core review | Shared Core Feature Track |
| `cloudbot/providers/bitrix/*`, `cloudbot/providers/search_provider.py` | provider changes and server path assumptions | after provider dependency map | Provider Track |
| `cloudbot/skills/bitrix_sales_data.py`, `cloudbot/skills/web_search.py` | shared tool behavior | after tool/provider acceptance | Skills Track |
| `cloudbot/workflows/finance_*.py`, `cashflow_analysis.py`, `pnl_analysis.py`, etc. | finance contour, not approved for Wave 2 | after finance scope decision | Finance Contour |
| `agents/finansist/*` | new finance agent contour | after separate product/agent approval | Finance Contour |
| `scripts/finansist_*.mjs`, `checks/finansist_google_smoke.mjs`, `tests/test_finansist_agent.py` | finance tooling and tests | after finance review | Finance Tooling |
| `ios/FormaNutrition/*` | iOS app/product contour, not Cloudbot runtime | after owner classifies as separate repo/product or in-scope product | iOS FormaNutrition Track |
| `infra/orchestrator/*` runtime/deploy changes | deploy/repair/verify scripts can affect server | after infra review; not in structural Wave 2 | Infra Runtime Track |
| `infra/orchestrator/workflows/deploy.sh`, `rollback.sh`, `verify.sh`, `audit.sh` deleted state | deleted tracked operational scripts require explicit disposition | after deleted files disposition | Deleted Ops Scripts |
| `configs/*`, `.env.integrations.example` behavior changes | env/cron contract changes, hardcoded local paths | after config/env contract approval | Config Contract Track |
| live env files `/etc/openclaw/*`, `/opt/openclaw/.env`, `/root/.openclaw/*` | server-only live config/secrets path | after server dependency map; never as structural source move | Server Env Track |
| live cron `/etc/cron.d/*` | production schedules | after separate cron plan and approval | Server Cron Track |
| runtime pointers `/opt/cloudbot-runtime/larisa/current`, `/opt/cloudbot-runtime/current` | live server runtime pointers | only in runtime separation wave, not Wave 2 | Runtime Pointer Track |
| systemd/docker services `cloudbot-bitrix-app.service`, `docker.service`, containers | live server operations | after separate server-only dependency map | Server Ops Track |
| `control_plane_snapshots/architect_workspace_20260325_MSK/*` deleted files | historical evidence deletion not dispositioned | after archive/evidence decision | Archive Disposition Track |
| HAPP/VPN files: `infra/happ-vpn.env.example`, `infra/templates/sing-box.service`, `ops/*happ_vpn*`, `services/vpn/*` | likely legacy cleanup, not structural migration | after owner confirms HAPP/VPN retired | HAPP/VPN Legacy Cleanup |
| `services/subscription/*` deleted files | unclear legacy service | after owner confirms obsolete or external | Subscription Legacy Track |
| server-only integrations `/opt/openclaw`, `/root/.openclaw/workspace/todo-integration`, `/etc/openclaw`, `/usr/local/bin/send_whoop_report.py` | not same repo, live/server-only runtime | after dependency map | Server-only Integration Map |
| generated/temp noise such as deleted `.DS_Store` in snapshot | cleanup candidate, not migration scope | after archive decision | Cleanup Track |

# 3. Wave 2 entry checklist

Status values: `pass`, `fail`, `not confirmed`.

Current gate status: **fail**. Some owner decisions are now recorded, but Wave 2 remains blocked by unresolved review/disposition/checklist items.

| check id | requirement | status | evidence | blocker |
|---|---|---|---|---|
| W2-GATE-01 | Owner accepts baseline evidence only, not execution | pass | owner accepted `opencloud_pre_wave2_freeze_audit.md`, `opencloud_wave0_wave1_baseline.md`, `opencloud_target_reorg_plan.md`, `opencloud_owner_decision_package.md` as baseline evidence | no |
| W2-GATE-02 | Included scope frozen in writing | not confirmed | include manifest exists, but owner has not approved Wave 2 include scope; owner explicitly says Wave 2 is not allowed yet | yes |
| W2-GATE-03 | Excluded scope frozen in writing | pass | owner excluded dirty production changes, shared-core changes, infra/deploy/runtime changes, configs/env/cron changes, `scripts/run_sales_copilot.py`, deleted deploy/rollback/verify files and deleted snapshots until separate decisions | no |
| W2-GATE-04 | Deleted tracked files disposition complete | fail | deleted files include `deploy.sh`, `rollback.sh`, `verify.sh`, snapshots, HAPP/VPN, subscription | yes |
| W2-GATE-05 | Dirty production changes reviewed or excluded | fail | owner excluded dirty production changes from Wave 2, but also requires manual review before Wave 2 entry | yes |
| W2-GATE-06 | Larisa smoke checklist defined | not confirmed | pre-Wave 2 audit says needed; no approved checklist recorded | yes |
| W2-GATE-07 | Lev/Sales smoke checklist defined | not confirmed | sales contract tests exist, but approved smoke checklist not confirmed | yes |
| W2-GATE-08 | Compatibility decision for `agents/sales_agent` fixed | not confirmed | owner package recommends compatibility layer; no approval recorded | yes |
| W2-GATE-09 | Compatibility decision for Cloudbot symlink wrapper fixed | pass | owner confirmed `/Users/pro2kuror/Desktop/Cloudbot` is only wrapper/symlink, not source of truth | no |
| W2-GATE-10 | Canonical local path fixed | pass | owner confirmed code source of truth: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`; docs/control-plane: `/Users/pro2kuror/Desktop/architect` | no |
| W2-GATE-11 | Rollback expectations documented | not confirmed | deleted `rollback.sh` status unresolved; no Wave 2 rollback expectation approved | yes |
| W2-GATE-12 | No hidden unrelated contours in scope | pass | owner moved finance contour, iOS contour, HAPP/VPN/subscription cleanup and CI additions to separate tracks | no |
| W2-GATE-13 | Server-only integrations excluded until dependency map | pass | owner confirmed no changes before separate review for server-only integrations | no |
| W2-GATE-14 | Env/cron live changes prohibited in Wave 2 | pass | owner confirmed no changes to runtime pointers, env, cron, systemd, docker, deploy scripts, server-only integrations until separate review | no |
| W2-GATE-15 | Shared-core functional changes excluded from Wave 2 | pass | owner excluded shared-core changes in `cloudbot/orchestrator`, providers, skills, workflows from Wave 2 | no |
| W2-GATE-16 | Tests to validate structural migration identified | not confirmed | tests exist but are dirty and path-locking | yes |
| W2-GATE-17 | Absolute path register reviewed for blockers | not confirmed | register exists in `opencloud_pre_wave2_freeze_audit.md`; owner review not recorded | yes |
| W2-GATE-18 | Final go/no-go owner decision recorded | fail | owner explicitly says Wave 2 is not allowed yet | yes |

Minimum pass criteria before Wave 2:

- W2-GATE-01 through W2-GATE-18 must be `pass`, or any remaining `not confirmed` must be explicitly waived by owner in writing.
- No item marked `fail` may remain.
- Any waiver must state why it is safe and what is excluded from Wave 2.

# 4. One-page owner approval draft

This is a manual approval draft. It does not apply changes.

```text
OWNER APPROVAL — WAVE 2 RELEASE GATE

Дата: 2026-04-23 МСК

Repo:
/Users/pro2kuror/Desktop/OpenClo/projects/engineer

Docs/control-plane:
/Users/pro2kuror/Desktop/architect

Current branch:
codex/feature/self-healing

Current HEAD:
dc19495e340a5899ca3451f4f492df65a63789da

1. Что разрешено

Разрешено только подготовить structural Wave 2 после выполнения gate checklist.

Потенциальный Wave 2 scope ограничен:
- classification of app boundaries for agents/larisa_ivanovna
- classification of app boundaries for agents/lev_petrovich
- compatibility classification of agents/sales_agent
- structural classification of cloudbot as shared boundary
- structural classification of configs as config boundary
- docs/control-plane remains external
- tests are used only as validation surface, not as feature work

2. Что запрещено

Запрещено в Wave 2:
- удалять, перемещать, переименовывать без отдельного утверждения
- менять runtime pointers
- менять live env
- менять cron
- менять systemd
- менять docker
- менять deploy/rollback/verify scripts
- переписывать imports без compatibility decision
- включать feature work в structural migration
- запускать deploy или restart

3. Что исключено

Из Wave 2 исключены:
- Larisa feature changes
- Sales/Lev feature/runtime changes
- shared-core functional changes
- infra runtime/deploy changes
- env/cron live changes
- finance contour: agents/finansist, finance workflows/scripts/tests
- iOS contour: ios/FormaNutrition
- HAPP/VPN/subscription cleanup
- deleted tracked files until disposition complete
- server-only integrations until dependency map complete

4. Условия, при которых Wave 2 can start

Wave 2 может стартовать только если:
- owner accepts baseline evidence: done
- include manifest approved
- exclude manifest approved: done for the listed exclusions
- deleted files disposition complete
- Larisa smoke checklist approved
- Lev/Sales smoke checklist approved
- agents/sales_agent compatibility decision approved
- Cloudbot symlink wrapper compatibility decision approved: done
- canonical local path approved as /Users/pro2kuror/Desktop/OpenClo/projects/engineer: done
- rollback expectations documented
- finance and iOS explicitly excluded or moved to separate tracks: done
- server-only integrations explicitly excluded until separate review: done

5. Условия, при которых Wave 2 remains blocked

Wave 2 остаётся заблокированным, если:
- dirty production changes are not manually reviewed
- deleted deploy/rollback/verify files are unresolved
- deleted snapshots are unresolved
- Larisa or Lev/Sales smoke checklist is missing
- compatibility decision for sales_agent is missing
- include manifest is not approved for execution
- rollback expectations are not documented

Manual owner decision:
[ ] APPROVE Wave 2 gate after all checklist items pass
[ ] KEEP Wave 2 BLOCKED
[ ] REQUEST changes to include/exclude manifests
```

# 5. Final readiness verdict

Verdict: **still blocked**.

Reason:

- Owner decision was provided and recorded, but it explicitly keeps Wave 2 not approved.
- Baseline evidence is accepted.
- Code source of truth, Cloudbot wrapper role and docs/control-plane role are confirmed.
- Exclude decisions are recorded for dirty production/shared-core/infra/config changes and separate tracks.
- Include manifest is prepared, but not approved for execution.
- Entry checklist currently has `fail` and `not confirmed` items.
- Deleted tracked files disposition is incomplete.
- Dirty production changes are excluded from Wave 2, but still require manual review before entry.
- Larisa and Lev/Sales smoke checklists are not approved.
- Compatibility decision for `/Users/pro2kuror/Desktop/Cloudbot` wrapper is recorded.
- Compatibility decision for `agents/sales_agent` is still not recorded.
- Finance and iOS are recorded as separate tracks.

Possible future status after owner approval: **conditionally ready**.

To reach `conditionally ready`, owner must approve:

- include manifest
- deleted files disposition
- production-critical dirty changes manual review result
- smoke checklist requirements
- `agents/sales_agent` compatibility decision
- rollback expectations
- test/absolute-path validation expectations

This document does not move the project to `ready for Wave 2`.

# 6. What to send back to ChatGPT

```text
Wave 2 gate package prepared.

File:
/Users/pro2kuror/Desktop/architect/opencloud_wave2_gate_package.md

Final verdict:
still blocked

Owner decision recorded:
- baseline evidence accepted
- source of truth confirmed: /Users/pro2kuror/Desktop/OpenClo/projects/engineer
- Cloudbot confirmed as wrapper/symlink only
- docs/control-plane confirmed: /Users/pro2kuror/Desktop/architect
- Wave 2 remains not approved
- dirty production/shared-core/infra/config changes excluded
- finance/iOS and other feature/cleanup work moved to separate tracks

Reason:
- Wave 2 is explicitly not owner-approved.
- Include manifest is prepared but not approved for execution.
- Entry checklist contains fail/not confirmed items.
- Deleted tracked files disposition is incomplete.
- Dirty production changes are excluded from Wave 2 but still require manual review before entry.
- Larisa and Lev/Sales smoke checklists are not approved.
- Compatibility decision for sales_agent is not recorded.
- Cloudbot wrapper decision is recorded.
- Finance and iOS are separate tracks and remain excluded from Wave 2.

Wave 2 can become conditionally ready only after owner manually approves:
1. include manifest
2. deleted files disposition
3. manual review result for production-critical dirty changes
4. Larisa smoke checklist
5. Lev/Sales smoke checklist
6. sales_agent compatibility decision
7. rollback expectations
8. test validation expectations
9. absolute-path blocker review
```
