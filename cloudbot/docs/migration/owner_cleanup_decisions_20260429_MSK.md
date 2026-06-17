# Owner Cleanup Decisions — 2026-04-29 МСК

## Confirmed Decisions

The owner approved cleanup of these obsolete contours:

- old HAPP/VPN deployment workflow;
- old subscription service;
- old iOS `FormaNutrition` contour;
- old control-plane snapshot `control_plane_snapshots/architect_workspace_20260325_MSK`.

## Cleanup Scope

Approved cleanup includes:

- `checks/morning_health_report.sh`
- `checks/vpn_smoke_happ.sh`
- `checks/vpn_verify.sh`
- `infra/happ-vpn.env.example`
- `infra/orchestrator/workflows/audit.sh`
- `infra/orchestrator/workflows/deploy.sh`
- `infra/orchestrator/workflows/rollback.sh`
- `infra/orchestrator/workflows/verify.sh`
- `infra/templates/sing-box.service`
- `ops/architecture_happ_vpn.md`
- `ops/runbook_happ_vpn.md`
- `services/subscription/`
- `services/vpn/`
- `control_plane_snapshots/architect_workspace_20260325_MSK/`
- `ios/FormaNutrition/`

## Explicitly Kept

`ops/ssh_happ.sh` is not removed in this cleanup.

Reason:

- despite the name, current repo references use it as a general remote SSH helper;
- it is referenced by `infra/orchestrator/lib.sh`, `checks/check_access.sh`, and `Makefile`;
- removing it now would be a remote-ops behavior change, not cleanup-only.

It requires a separate rename/replacement plan later.

## Separate Tracks

The owner confirmed these tracks must stay separate from cleanup:

- finance contour review;
- Larisa content/search feature review;
- Sales / Lev runtime review;
- config/env/cron review;
- CI workflow review;
- docs/control-plane review.

## Runtime Safety

This cleanup is local repo cleanup only.

It does not change:

- server files;
- `/opt/*`;
- `/etc/*`;
- `/root/*`;
- live env;
- cron;
- systemd;
- docker;
- runtime pointers.

## Status

Cleanup decisions recorded.
