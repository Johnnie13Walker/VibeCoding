# Config / Env / Cron Review — 2026-04-29 МСК

## Scope

Reviewed remaining dirty config/env/cron files:

- `.env.integrations.example`
- `configs/schedule_contract.env`
- `configs/schedules.cron`
- `configs/README.md`
- `infra/remote-ops.env.example`

This review does not approve live env, live cron, systemd, docker, deploy, or runtime pointer changes.

## Secret Scan Result

No concrete secret values were found in the reviewed files.

Observed sensitive keys are placeholders or examples:

- `WHOOP_CLIENT_SECRET=`
- `WHOOP_REFRESH_TOKEN=`
- `GOOGLE_SERVICE_ACCOUNT_JSON=`
- `WAZZUP_API_KEY=`
- `GH_TOKEN=`

## File Decisions

| path | state | decision | rationale |
|---|---:|---|---|
| `.env.integrations.example` | modified | accept later as example-only | Adds empty placeholders for WHOOP, search, Google/finance and Wazzup forward URL. No secret values found. Must remain example-only. |
| `configs/README.md` | untracked | accept as marker | Explicitly says `configs/` is not live env and not approved migration. Safe docs marker. |
| `infra/remote-ops.env.example` | untracked | accept later after SSH-helper review | Contains placeholder host/key settings for remote ops. Safe as example, but tied to `ops/ssh_happ.sh` naming and remote ops contract. |
| `configs/schedule_contract.env` | modified | review required before acceptance | Changes Larisa schedule contract from `09:00` to `08:00`, adds UTC expressions and delivery modes. Schedule behavior must be owner-approved separately. |
| `configs/schedules.cron` | modified | do not accept now | Contains absolute path `/Users/pro2kuror/Desktop/Cloudbot/engineer`, while canonical source is `/Users/pro2kuror/Desktop/OpenClo/projects/engineer`; also adds `larisa_content_topics`, which belongs to a separate Larisa feature track. |

## Key Risks

### `configs/schedules.cron`

Risk level: high for acceptance.

Reasons:

- references non-canonical local path `/Users/pro2kuror/Desktop/Cloudbot/engineer`;
- adds `larisa_content_topics` at `19:30 МСК`;
- that workflow is part of Larisa content/search feature track, not accepted as current runtime;
- cron files are schedule-sensitive and must not be committed as current truth without owner approval.

### `configs/schedule_contract.env`

Risk level: medium.

Reasons:

- changes Larisa daily schedule from `09:00 МСК` to `08:00 МСК`;
- introduces UTC cron expressions;
- introduces delivery mode flags;
- may be valid, but should be accepted as a schedule-contract decision, not incidental config cleanup.

### `infra/remote-ops.env.example`

Risk level: medium-low.

Reasons:

- no secret values;
- useful as example;
- but it depends on the still-named `ops/ssh_happ.sh`, which is currently a general SSH helper despite the legacy name.

## Recommended Handling

### Commit now

Do not commit config/env/cron changes in the current step.

Only this review document should be committed.

### Next config action

Split config work into three follow-up decisions:

1. `env-example-acceptance`
   - accept `.env.integrations.example`;
   - optionally accept `configs/README.md`;
   - verify no secrets before commit.

2. `remote-ops-example-acceptance`
   - accept `infra/remote-ops.env.example`;
   - decide whether to rename `ops/ssh_happ.sh` later to a neutral `ops/ssh_remote.sh`;
   - do not rename in the same step.

3. `schedule-contract-decision`
   - decide whether Larisa daily brief should be `08:00 МСК` or `09:00 МСК`;
   - decide whether `larisa_content_topics` is approved for local cron;
   - decide canonical local path in cron templates;
   - only then accept or rewrite `configs/schedules.cron`.

## Owner Questions Before Acceptance

1. Should Larisa daily brief target be `08:00 МСК` or `09:00 МСК`?
2. Is `larisa_content_topics` at `19:30 МСК` approved, or should it wait for Larisa feature review?
3. Should local cron examples use `/Users/pro2kuror/Desktop/OpenClo/projects/engineer` as canonical path?
4. Should `infra/remote-ops.env.example` be accepted now as example-only?
5. Should `ops/ssh_happ.sh` be renamed later, or kept as compatibility helper for now?

## Status

Config/env/cron reviewed.

No config/env/cron file is approved for commit yet.
