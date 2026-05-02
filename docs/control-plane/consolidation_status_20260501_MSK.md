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

### Batch 5 — ignored artifact cleanup

Completed on `2026-05-02 МСК`.

Removed ignored/generated leftovers from the legacy workspace:

- `.DS_Store`
- `.netlify/`
- `.playwright-mcp/`
- `.publish-belberry/`
- `.serena/`
- `output/`
- `outputs/`
- `tmp/`
- local SEO dashboard PDF/PNG render artifacts

The legacy workspace now contains only:

- `.git/`
- `.gitignore`
- `README.md`

### Batch 6 — wrapper symlink cleanup

Completed on `2026-05-02 МСК`.

Removed legacy symlink from:

`/Users/pro2kuror/Desktop/Cloudbot/architect`

Updated wrapper files:

- `/Users/pro2kuror/Desktop/Cloudbot/README.md`
- `/Users/pro2kuror/Desktop/Cloudbot/bin/verify_workspace.sh`

The wrapper now exposes only active navigation targets:

- `engineer`
- `paperclip`

## Not moved or deleted

No source-of-truth files remain in `/Users/pro2kuror/Desktop/architect`.

Useful `.xlsx`, `.docx`, `.html` and `.json` report artifacts were copied into the canonical repo before cleanup.

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
3. Keep or archive `/Users/pro2kuror/Desktop/architect` as a separate local stub decision outside the Cloudbot wrapper.

## Current verdict

The important text docs, report artifacts and control-plane scripts have been consolidated into the canonical engineer repo.

The folder consolidation work is complete for Cloudbot source-of-truth and wrapper navigation. Any remaining decision about `/Users/pro2kuror/Desktop/architect` is local archive housekeeping, not runtime migration.
