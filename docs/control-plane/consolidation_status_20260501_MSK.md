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
- local app/project folders such as `acoola-landing/`

Reason:

- generated artifacts and binary reports need owner classification;
- some files may be local tool output;
- some files may belong to separate projects, not Cloudbot;
- deletion is intentionally deferred.

Note: many useful `.xlsx`, `.docx`, `.html` and `.json` report artifacts have now been copied into the canonical repo. The list above refers to leftovers that still need cleanup or deletion decisions in the legacy workspace.

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
3. Add or update ignore rules in `/Users/pro2kuror/Desktop/architect` for generated artifacts.
4. Archive binary/generated reports after explicit approval.
5. Only after review, replace duplicated `architect` docs with pointers or delete them from the legacy workspace.

## Current verdict

The important text docs and control-plane scripts have been consolidated into the canonical engineer repo.

The remaining work is cleanup/classification of generated and binary artifacts, not runtime migration.
