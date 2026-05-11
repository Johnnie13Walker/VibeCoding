from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence


EXIT_USAGE = 3

STAGES = (
    "discover",
    "inventory",
    "classify",
    "transfer",
    "merge",
    "verify",
    "rollback",
    "status",
    "migrate-pilot",
    "reclassify-failed",
    "export-manual",
    "pause",
    "resume",
)

LIMIT_REQUIRED_STAGES = {"inventory", "classify", "transfer", "merge"}

STAGE_MODULES = {
    "migrate-pilot": "migrate_pilot",
    "reclassify-failed": "reclassify_failed",
    "export-manual": "export_manual",
}


class MergeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dry-run", action="store_true", help="Показать план без write-операций.")
    common.add_argument("--limit", type=int, help="Ограничить количество групп для обработки.")
    common.add_argument("--portal", help="Override портала Bitrix24 для диагностики.")
    common.add_argument("--sheet", help="Override Google Sheet ID.")
    common.add_argument("--verbose", action="store_true", help="Подробный вывод.")

    parser = MergeArgumentParser(
        prog="crm-company-merge",
        description="Workflow service for safe Bitrix24 company duplicate merge.",
        parents=[common],
    )

    subparsers = parser.add_subparsers(dest="stage", metavar="stage")
    for stage in STAGES:
        subparsers.add_parser(stage, help=f"Запустить стадию {stage}.", parents=[common])

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.stage:
        parser.print_help()
        return 0

    if args.stage in LIMIT_REQUIRED_STAGES and args.limit is None:
        print(f"Ошибка: для стадии '{args.stage}' обязателен флаг --limit N", file=sys.stderr)
        return EXIT_USAGE

    module_name = STAGE_MODULES.get(args.stage, args.stage.replace("-", "_"))
    module = importlib.import_module(f"crm_company_merge.stages.{module_name}")
    module.run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
