# Folder consolidation final report — 2026-05-02 МСК

## Verdict

Folder consolidation is complete for source-of-truth materials.

Canonical locations:

| Purpose | Path |
| --- | --- |
| Code, tests, runtime migration docs | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` |
| Control-plane docs and migrated architect materials | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/docs/control-plane` |
| Control-plane scripts/tools quarantine | `/Users/pro2kuror/Desktop/OpenClo/projects/engineer/tools/control-plane` |
| Navigation wrapper | `/Users/pro2kuror/Desktop/Cloudbot` |
| Legacy pointer-stub | `/Users/pro2kuror/Desktop/architect` |

## Completed

- Markdown control-plane docs copied from `architect` into `engineer/docs/control-plane`.
- Control-plane scripts/tools copied into `engineer/tools/control-plane`.
- Report artifacts copied into `engineer/docs/control-plane/architect/artifacts`.
- Obsolete `acoola-landing` task files removed.
- Legacy `architect` tracked source files removed and replaced with a pointer `README.md`.
- Ignored/generated leftovers in `architect` removed.
- Wrapper `Cloudbot/README.md` updated to point users at `engineer/docs/control-plane`.

## Current legacy architect state

`/Users/pro2kuror/Desktop/architect` intentionally contains only:

- `.git/`
- `.gitignore`
- `README.md`

It is no longer source of truth.

## Runtime safety

This folder cleanup did not change:

- `/opt/cloudbot-runtime`
- `/opt/openclaw`
- env files
- cron
- systemd
- Docker
- Telegram routing
- runtime pointers

## Remaining non-folder migration work

1. Confirm scheduled Sales follow-up after `dev_3b160ba` at `2026-05-02 17:10 МСК`.
2. Close Phase 9 observation docs after the scheduled proof.
3. Decide whether to keep or remove the `Cloudbot/architect` symlink.
4. Continue runtime cleanup only after scheduled observations stay green.
