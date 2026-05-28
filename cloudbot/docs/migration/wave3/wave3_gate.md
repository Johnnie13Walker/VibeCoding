# 1. Candidate moves

Date: 2026-04-27 MSK.

This is a Wave 3 gate document, not Wave 3 migration. It identifies the safest first real structural move without executing it.

Confirmed context:

- canonical code source: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- wrapper only: `/Users/pro2kuror/Desktop/Cloudbot`
- docs/control-plane: `/Users/pro2kuror/Desktop/architect`
- Wave 2 structural preparation completed
- `agents/sales_agent` remains temporary compatibility layer
- runtime remains no-touch

| candidate_id | description | exact paths involved | touches code? | touches runtime? | touches imports? | rollback complexity | blast radius | risk level | why this is safe or unsafe |
|---|---|---|---|---|---|---|---|---|---|
| W3-CAND-01 | Add source-of-truth and compatibility marker docs | `docs/migration/wave3/source_of_truth_markers.md`; optionally root-level marker later only with approval | no | no | no | trivial: remove one doc | docs only | low | safest because it only records already-approved facts; unsafe only if placed in production paths outside docs |
| W3-CAND-02 | Add ADR records for Wave 2 decisions | `docs/migration/wave3/decisions/*.md` | no | no | no | trivial | docs only | low | safe because it preserves decisions; not a structural move of code |
| W3-CAND-03 | Add target folder skeleton documentation only | `docs/migration/wave3/target_skeleton_manifest.md` | no | no | no | trivial | docs only | low | safe if it is a manifest only; unsafe if it creates production target folders prematurely |
| W3-CAND-04 | Create empty target folder skeleton with README files | `apps/`, `shared/`, `config/`, `infra/`, `archive/`, `tests/` with README only | no production code | no | no | low to medium | repo structure visible to tooling | medium | reversible, but may confuse tools and developers because empty folders can look canonical before imports exist |
| W3-CAND-05 | Add compatibility marker README near current code | `agents/sales_agent/README.md`, `agents/lev_petrovich/README.md`, `agents/larisa_ivanovna/README.md` | docs only but inside code dirs | no | no | low | near production packages | medium | useful, but touches app package directories and can be confused with code change; should happen after docs-only marker move |
| W3-CAND-06 | Add archive boundary markers | `archive/README.md`, `control_plane_snapshots/README.md` or docs-only archive policy | no | no | no | low | archive/evidence only | medium | safe if docs-only; unsafe if it changes deleted snapshot disposition or moves files |
| W3-CAND-07 | Move existing docs into `docs/migration/wave3/` | existing docs under `docs/architecture/*` or other docs | no code | no | no | medium | docs links can break | medium/high | not first move because even docs relocation can break references and audit continuity |

# 2. Ranking

## Rank 1: W3-CAND-01 — Source-of-truth and compatibility marker docs

Safest first. It creates a single docs-only marker file that records approved facts and blocks accidental misuse of `/Users/pro2kuror/Desktop/Cloudbot` and `agents/sales_agent`.

## Rank 2: W3-CAND-02 — ADR records for Wave 2 decisions

Also safe, but slightly broader because multiple decision files can create review noise. Best after the marker document exists.

## Rank 3: W3-CAND-03 — Target skeleton manifest only

Safe if it stays documentation-only. It prepares the later skeleton without creating folders that tooling may misinterpret.

## Rank 4: W3-CAND-06 — Archive boundary markers

Useful, but should wait until deleted snapshot disposition is explicit. Otherwise it can look like archive policy was already decided.

## Rank 5: W3-CAND-05 — Compatibility README near current code

Still docs-only, but it touches production package directories. That is too close to runtime code for the first move.

## Rank 6: W3-CAND-04 — Empty target folder skeleton

Reversible but not ideal first. Empty `apps/` or `shared/` folders can be mistaken for active package roots and can confuse future imports/tooling.

## Rank 7: W3-CAND-07 — Move existing docs

Most dangerous candidate in this gate. It is not code, but it can break internal references and audit traceability. Not first.

Order rationale: start with one documentation marker that changes no package paths, then add ADRs/manifests, then only later consider markers near code or empty skeletons.

# 3. Recommended first move

Recommended first real Wave 3 move: **Source-of-truth and compatibility marker document**.

This is not code migration. It is a single docs-only structural marker that makes later moves safer.

## Exact scope

Create:

```text
docs/migration/wave3/source_of_truth_markers.md
```

## Exact files/folders

Involved:

- `docs/migration/wave3/source_of_truth_markers.md`
- no other files

## What will be created

One Markdown file containing:

- canonical code source marker: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- wrapper marker: `/Users/pro2kuror/Desktop/Cloudbot` is wrapper/symlink only
- docs/control-plane marker: `/Users/pro2kuror/Desktop/architect`
- `agents/sales_agent` compatibility marker
- no-touch runtime marker for `/opt/cloudbot-runtime/larisa/current`, `/opt/cloudbot-runtime/current`, `/opt/openclaw`, `/etc/openclaw`
- exclusion marker for finance/iOS/HAPP/VPN/subscription/server-only integrations

## What will NOT be changed

- no code
- no imports
- no runtime
- no env
- no cron
- no systemd
- no docker
- no runtime pointers
- no deploy/rollback/verify scripts
- no `agents/*` moves
- no `cloudbot/*` moves
- no target folder skeleton
- no server paths

## Why this should be first

This move locks the governing facts before any structural folder creation. It is the smallest move that reduces future ambiguity:

- prevents work through the `Cloudbot` wrapper
- prevents accidental retirement of `agents/sales_agent`
- prevents runtime/server paths from entering structural work
- creates a single rollback point

## What must be checked before execution

- `git status --short` understood and current dirty state acknowledged
- `docs/migration/wave3/` exists or can be created
- no existing `source_of_truth_markers.md` would be overwritten
- owner still agrees Wave 3 first move is docs-only
- no target folder skeleton is created in the same change
- no production package directories are touched

## Rollback simplicity

Trivial. Rollback is removing one new Markdown file before commit. No code or runtime rollback needed.

# 4. Anti-scope (what must NOT be touched)

The first Wave 3 move must not touch:

- `agents/larisa_ivanovna`
- `agents/lev_petrovich`
- `agents/sales_agent`
- `cloudbot/orchestrator`
- `cloudbot/providers`
- `cloudbot/skills`
- `cloudbot/workflows`
- `cloudbot/bot/telegram`
- `scripts/run_sales_copilot.py`
- `configs`
- `infra/orchestrator`
- deploy/rollback/verify scripts
- runtime pointers
- live env
- cron
- systemd
- docker
- `/opt/*`
- `/etc/*`
- `/root/*`
- `/home/ops/*`
- finance contour
- `ios/FormaNutrition`
- HAPP/VPN cleanup
- subscription cleanup
- server-only integrations

Also prohibited:

- moving `agents/*`
- rewriting imports
- creating `apps/` or `shared/` package roots
- changing business logic
- changing shared-core behavior
- running deploy or restart
- adding tests that require live env/server/secrets

# 5. Ready checklist before execution

| check_id | requirement | status | notes |
|---|---|---|---|
| W3-GATE-01 | canonical source confirmed | pass | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` |
| W3-GATE-02 | `Cloudbot` wrapper status confirmed | pass | `/Users/pro2kuror/Desktop/Cloudbot` is wrapper/symlink only |
| W3-GATE-03 | docs/control-plane confirmed | pass | `/Users/pro2kuror/Desktop/architect` |
| W3-GATE-04 | Wave 2 docs exist | pass | `docs/migration/wave2/*` exists |
| W3-GATE-05 | `agents/sales_agent` compatibility status confirmed | pass | temporary compatibility layer |
| W3-GATE-06 | runtime no-touch confirmed | pass | no `/opt`, `/etc`, `/root`, `/home/ops` mutation |
| W3-GATE-07 | dirty git state understood | pass | existing dirty state remains; first move must be isolated to one new doc |
| W3-GATE-08 | no hidden dependencies in first move | pass | docs-only marker has no imports/runtime dependency |
| W3-GATE-09 | rollback obvious | pass | remove one new Markdown file before commit |
| W3-GATE-10 | no shared-core touch | pass | no `cloudbot/*` changes |
| W3-GATE-11 | no target folder skeleton in first move | pass | recommended move is one doc only |
| W3-GATE-12 | owner approval for executing first move | not confirmed | this document is gate planning only |

# 6. Final verdict

After analysis, the first real Wave 3 move should be:

**Source-of-truth and compatibility marker document**

Exact proposed file:

```text
docs/migration/wave3/source_of_truth_markers.md
```

Why:

- minimal
- reversible
- docs-only
- no runtime effect
- no import effect
- no server access
- no shared-core touch
- protects `agents/sales_agent` compatibility rule before any folder skeleton or code-adjacent README appears

Wave 3 should not be delayed if the owner accepts this first move exactly as scoped. Any broader first move should be delayed.

# 7. What to send back to ChatGPT

```text
Wave 3 Gate completed.

Recommended first move:
Create docs/migration/wave3/source_of_truth_markers.md only.

Do not move code.
Do not create apps/shared skeleton yet.
Do not touch agents/*, cloudbot/*, configs, infra, scripts/run_sales_copilot.py, runtime, env, cron, systemd, docker, deploy scripts, or server paths.

Reason:
This is the smallest reversible docs-only marker that locks source-of-truth and compatibility rules before any structural move.

Gate file:
/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/migration/wave3/wave3_gate.md
```
