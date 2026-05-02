# Folder consolidation status — 2026-05-01 МСК

## Goal

Reduce the split between:

- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- `/Users/pro2kuror/Desktop/architect`
- `/Users/pro2kuror/Desktop/Cloudbot`

without deleting data or changing production runtime.

## Current canonical layout

| Purpose | Canonical path |
| --- | --- |
| Code/runtime/tests/migration docs | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` |
| Consolidated control-plane docs | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane` |
| Consolidated control-plane scripts/tools | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/tools/control-plane` |
| Navigation wrapper | `/Users/pro2kuror/Desktop/Cloudbot` |
| Legacy workspace pending cleanup | `/Users/pro2kuror/Desktop/architect` |

## Completed in engineer

### Batch 1 — docs/control-plane

Committed as:

`645b3dc docs: consolidate architect control plane`

Copied 39 files into:

`docs/control-plane/`

Included:

- root `AGENTS.md`
- root `README.md`
- root `baseline_*.md`
- root `opencloud_*.md`
- module README files:
  - `devops/README.md`
  - `orchestrator/README.md`
  - `providers/README.md`
  - `skills/README.md`
  - `telegram/README.md`
  - `workflows/README.md`
- `docs/PLAN.md`
- `docs/STATUS.md`
- `docs/architecture/*.md`
- `docs/checklists/*.md`
- `docs/prompts/*.md`
- `docs/workflows/*.md`

### Batch 2 — tools/control-plane

Committed as:

`c108610 tools: consolidate architect control plane scripts`

Copied 24 files into:

`tools/control-plane/`

Included:

- `architect/scripts/*.py`
- `architect/scripts/*.mjs`
- `architect/scripts/*.sh`
- `architect/tools/*.mjs`

Scripts are quarantined and not wired into runtime.

### Batch 3 — report artifacts

Copied report artifacts into:

`docs/control-plane/architect/artifacts/`

Included:

- root `specification.txt`;
- root-level business report docs from `architect/docs`;
- generated `.docx` report exports from `architect/output/doc`;
- selected `.xlsx` field-audit workbooks from `architect/docs/architecture` and `architect/outputs`.

Excluded:

- temporary Office lock files such as `~$*.xlsx`;
- zero-byte TSV exports;
- `tmp/`;
- local browser/tool output;
- local app folders.

### Batch 4 — legacy architect cleanup

Completed on `2026-05-02 МСК`.

Legacy source-of-truth files were removed from:

`/Users/pro2kuror/Desktop/architect`

The workspace now acts as a pointer-stub. Its `README.md` directs users to the canonical locations:

- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane`
- `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`
- `/Users/pro2kuror/Desktop/Cloudbot`

Ignored local/generated artifacts remain outside git and are not part of the canonical source tree.

## Not moved or deleted

The following remain in `/Users/pro2kuror/Desktop/architect`:

- `.xlsx`
- `.docx`
- `.png`
- `.pdf`
- `.html`
- `.json`
- `.tsv`
- `.zip`
- `.DS_Store`
- `~$*.xlsx`
- `output/`
- `outputs/`
- `tmp/`
- `.playwright-mcp/`
- `.publish-belberry/`
- `.netlify/`
- local app/project folders that are not Cloudbot source-of-truth

Reason:

- generated artifacts and binary reports need owner classification;
- some files may be local tool output;
- some files may belong to separate projects, not Cloudbot;
- deletion is intentionally deferred.

Note: many useful `.xlsx`, `.docx`, `.html` and `.json` report artifacts have now been copied into the canonical repo. The list above refers to ignored local leftovers that still need archive/delete decisions outside the source tree.

## Runtime safety

This consolidation did not change:

- `/opt/cloudbot-runtime`
- `/opt/openclaw`
- env files
- cron
- systemd
- Docker
- Telegram routing
- production wrappers

## Next concrete actions

1. Review `docs/control-plane/architect` and promote durable docs into cleaner paths.
2. Review `tools/control-plane/architect-scripts` and classify every script:
   - maintained workflow;
   - one-off audit tool;
   - archive;
   - delete later from legacy workspace.
3. Archive or delete ignored binary/generated leftovers after explicit approval.
4. Keep `/Users/pro2kuror/Desktop/architect` as a pointer-stub until the wrapper strategy is finalized.

## Current verdict

The important text docs, report artifacts and control-plane scripts have been consolidated into the canonical engineer repo.

The remaining work is cleanup/classification of ignored generated and binary artifacts, not runtime migration.
