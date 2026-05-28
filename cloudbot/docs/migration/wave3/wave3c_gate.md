# Wave 3C Gate

Date: 2026-04-28 MSK.

This is gate planning for the first code-adjacent marker. It is not the marker execution step.

No production code is moved. No imports are changed. No runtime, env, cron, systemd, docker, deploy, rollback, verify, or server-only path is touched.

## 1. Context

Completed:

- Wave 2 structural preparation.
- Wave 3A source-of-truth marker.
- Wave 3B target folder skeleton.

Confirmed:

- canonical code source: `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- wrapper only: `/Users/pro2kuror/Desktop/Cloudbot`
- docs/control-plane: `/Users/pro2kuror/Desktop/architect`
- `agents/sales_agent` is a temporary compatibility layer
- runtime is no-touch

## 2. Candidate Code-Adjacent Markers

| candidate_id | proposed future marker | exact path | touches code? | touches runtime? | touches imports? | rollback complexity | blast radius | risk level | notes |
|---|---|---|---|---|---|---|---|---|---|
| W3C-CAND-01 | sales compatibility marker README | `agents/sales_agent/README.md` | no, docs only | no | no | trivial | near production package | medium | strongest safety value because it prevents accidental retirement of the active compatibility layer |
| W3C-CAND-02 | Lev app boundary marker README | `agents/lev_petrovich/README.md` | no, docs only | no | no | trivial | near production package | medium | useful but depends on `agents/sales_agent` compatibility being explicit first |
| W3C-CAND-03 | Larisa app boundary marker README | `agents/larisa_ivanovna/README.md` | no, docs only | no | no | trivial | near production package | medium | useful, but Larisa has dirty feature work; marker must avoid feature acceptance language |
| W3C-CAND-04 | shared-core active path marker | `cloudbot/README.md` | no, docs only | no | no | trivial | near shared-core root | medium/high | useful but broader blast radius; can be misread as shared-core reorganization approval |
| W3C-CAND-05 | orchestrator active path marker | `cloudbot/orchestrator/README.md` | no, docs only | no | no | trivial | near shared-core routing | high | too close to shared-core behavior; should wait |
| W3C-CAND-06 | config active path marker | `configs/README.md` | no, docs only | no | no | trivial | near config contracts | high | configs/env/cron are excluded; marker could be misread as config migration start |
| W3C-CAND-07 | infra active path marker | `infra/README.md` | no, docs only | no | no | low | near deploy/runtime area | high | infra already active; avoid until deploy/rollback/verify disposition is resolved |

## 3. Ranking

1. `W3C-CAND-01` - `agents/sales_agent/README.md`
2. `W3C-CAND-02` - `agents/lev_petrovich/README.md`
3. `W3C-CAND-03` - `agents/larisa_ivanovna/README.md`
4. `W3C-CAND-04` - `cloudbot/README.md`
5. `W3C-CAND-05` - `cloudbot/orchestrator/README.md`
6. `W3C-CAND-06` - `configs/README.md`
7. `W3C-CAND-07` - `infra/README.md`

Reasoning:

- The safest first code-adjacent marker is the one that prevents the most dangerous misunderstanding with the smallest scope.
- `agents/sales_agent` is explicitly a temporary compatibility layer and must not be retired, moved, or deleted.
- Marking `agents/sales_agent` first reduces risk for any future Lev/Sales boundary work.
- `cloudbot/*`, `configs`, and `infra` are broader and closer to shared-core/runtime/deploy assumptions, so they should wait.

## 4. Recommended First Code-Adjacent Marker

Recommended next move after this gate:

```text
agents/sales_agent/README.md
```

Purpose:

- Mark `agents/sales_agent` as the current temporary compatibility layer.
- State clearly that it is not legacy for deletion.
- State clearly that it must not be moved or retired in Wave 3.
- State clearly that Lev/Sales runtime must remain compatible with it.

Allowed content only:

- compatibility status
- no-retirement rule
- no-move rule
- owner approval requirement
- future retirement must be separate approved track

Must not include:

- business logic notes
- implementation details
- import changes
- code examples that imply new entrypoints
- migration instructions that move files
- runtime/deploy/env references beyond no-touch policy

## 5. Anti-Scope

The future first code-adjacent marker must not touch:

- `agents/sales_agent/*.py`
- `agents/lev_petrovich`
- `agents/larisa_ivanovna`
- `cloudbot/*`
- `configs`
- `infra`
- `scripts/run_sales_copilot.py`
- deploy/rollback/verify scripts
- tests
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
- HAPP/VPN
- subscription cleanup
- server-only integrations

Also prohibited:

- moving files
- creating Python package files
- adding `__init__.py`
- changing imports
- copying production code
- adding runtime scripts
- adding env examples
- running live checks

## 6. Ready Checklist Before Executing Marker

| check_id | requirement | status | evidence |
|---|---|---|---|
| W3C-GATE-01 | Wave 3A marker exists | pass | `docs/migration/wave3/source_of_truth_markers.md` |
| W3C-GATE-02 | Wave 3B skeleton report exists | pass | `docs/migration/wave3/wave3b_skeleton_report.md` |
| W3C-GATE-03 | `agents/sales_agent` compatibility rule confirmed | pass | Wave 3A marker and Wave 2 compatibility docs |
| W3C-GATE-04 | first marker scope is one README only | pass | proposed path: `agents/sales_agent/README.md` |
| W3C-GATE-05 | no code/import/runtime touch required | pass | README-only future move |
| W3C-GATE-06 | owner approval for executing README marker | not confirmed | this file is gate planning only |

## 7. Final Verdict

Wave 3C gate completed.

The next safe move should be:

```text
agents/sales_agent/README.md
```

This should be executed only after explicit owner approval and only as a single README marker. It must not include code changes, import changes, runtime changes, or retirement/move of `agents/sales_agent`.

## 8. What to Send Back to ChatGPT

```text
Wave 3C gate completed.

Recommended next move:
Create agents/sales_agent/README.md only.

Purpose:
Mark agents/sales_agent as temporary compatibility layer.

Do not move or retire agents/sales_agent.
Do not touch code/imports/runtime/env/cron/systemd/docker/deploy/server paths.

Gate file:
/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/migration/wave3/wave3c_gate.md
```
