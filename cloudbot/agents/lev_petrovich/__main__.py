"""Compatibility entrypoint for python -m agents.lev_petrovich."""

from apps.lev_petrovich.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
