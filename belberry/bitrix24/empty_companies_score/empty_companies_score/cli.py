"""Entrypoint: запустить полный pipeline (fetch → score → upload → опц. TG).

  python -m empty_companies_score [--notify] [--dry-run]
"""

import argparse
import sys
from datetime import datetime

from . import __version__
from .bitrix_client import BitrixClient
from .config import BITRIX_STATE, DATA_DIR
from .fetcher import fetch_all, resolve_user_names
from .notifier import notify_if_morning
from .scorer import score_companies, select_for_upload, summary_counts
from .uploader import tab_url, upload, upload_no_inn


def _log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="empty_companies_score")
    p.add_argument("--notify", action="store_true", help="послать TG-сводку (флаг утреннего прогона)")
    p.add_argument("--dry-run", action="store_true", help="не писать в Sheet и не слать TG")
    p.add_argument("--version", action="version", version=__version__)
    args = p.parse_args(argv)

    _log(f"empty_companies_score start (notify={args.notify}, dry={args.dry_run})")

    bx = BitrixClient(BITRIX_STATE)
    data = fetch_all(bx, DATA_DIR)

    user_ids: set[str] = set()
    for c in data["companies"]:
        for k in ("ASSIGNED_BY_ID", "CREATED_BY_ID"):
            v = c.get(k)
            if v:
                user_ids.add(str(v))
    _log(f"resolving {len(user_ids)} user names ...")
    users = resolve_user_names(bx, user_ids)

    _log("scoring ...")
    scored = score_companies(
        data["companies"], data["deals"], data["contacts"],
        data["leads"], data["requisites"], users,
    )
    filtered = select_for_upload(scored)
    snapshot = summary_counts(filtered)
    _log(f"scored: {len(scored)} total; selected for sheet: {len(filtered)}; snapshot={snapshot}")

    if args.dry_run:
        _log("dry-run: пропускаем upload и TG")
        return 0

    _log(f"uploading {len(filtered)} rows to Sheet ...")
    upload(filtered)

    no_inn_count = sum(1 for s in scored if getattr(s, "empty_inn", False))
    _log(f"uploading {no_inn_count} rows to «Компании без ИНН» ...")
    upload_no_inn(scored)

    _log("update state + maybe TG ...")
    notify_if_morning(snapshot, DATA_DIR / "state.json", tab_url(), force=args.notify)

    _log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
