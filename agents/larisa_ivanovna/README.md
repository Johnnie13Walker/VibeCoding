# agents/larisa_ivanovna

## Current status

This directory is now a compatibility shim.

Canonical implementation lives in:

`apps/larisa_ivanovna`

Do not add new production logic here.

## Mandatory rules

Do NOT:

- delete this compatibility layer yet
- move runtime pointers to a new path without separate approval
- change Telegram routing here
- change env, token, or chat routing here
- treat this shim as archive

Existing imports through `agents.larisa_ivanovna` must keep working until all runtime and tests are migrated.

## Retirement rule

Retirement of this shim is a separate approved track after:

- runtime points to canonical app path;
- Larisa smoke checklist is green;
- rollback path is documented;
- server deploy has been validated separately.
