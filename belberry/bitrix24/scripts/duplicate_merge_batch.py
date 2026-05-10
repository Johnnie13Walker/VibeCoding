#!/usr/bin/env python3
"""CLI для read-only duplicate merge dry-run batch."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from belberry.bitrix24.config.loader import load_config
from belberry.bitrix24.orchestration.batch_engine import BatchEngineDeps, run_dry_run_batch
from belberry.bitrix24.providers.bitrix_oauth import BitrixOAuth, urllib_transport as bitrix_transport
from belberry.bitrix24.providers.bitrix_reconciler import ReconcileSettings
from belberry.bitrix24.providers.google_sheets import GoogleSheetsClient
from belberry.bitrix24.providers.logging import sanitize


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dry-run", "apply"], required=True)
    parser.add_argument("--group-domain", default=None)
    parser.add_argument("--max-groups", type=int, default=1)
    parser.add_argument("--run-id")
    parser.add_argument("--confirm-apply")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "apply":
        raise SystemExit("apply not implemented in R3, use dry-run")

    config = load_config()
    oauth = BitrixOAuth.from_env(transport=bitrix_transport)
    sheets = GoogleSheetsClient.from_env()
    deps = BatchEngineDeps(
        config=config,
        sheets=sheets,
        oauth=oauth,
        reconciler_settings=ReconcileSettings(portal_base_url=config.portal_base_url),
        now_utc=lambda: datetime.now(timezone.utc),
    )
    result = run_dry_run_batch(deps=deps, group_domain=args.group_domain, max_groups=args.max_groups)
    summary = {
        "run_id": result.run_id,
        "mode": result.mode,
        "packages": [
            {
                "run_id": package.manifest.run_id,
                "domain": package.artifact.domain,
                "target_id": package.artifact.target_id,
                "deal_ids": list(package.artifact.deal_ids),
                "artifact": str(package.artifact_path),
                "manifest": str(package.manifest_path),
                "risk_status": str(package.artifact.risk.get("status") or ""),
                "policy_status": str(package.artifact.policy_plan.get("status") or ""),
            }
            for package in result.packages
        ],
        "skipped_groups": list(result.skipped_groups),
        "errors": list(result.errors),
    }
    print(json.dumps(sanitize(summary), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
