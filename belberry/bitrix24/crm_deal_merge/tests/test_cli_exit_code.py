from __future__ import annotations

import argparse

from crm_deal_merge import cli
from crm_deal_merge.stages import transfer


def test_cmd_transfer_returns_zero_when_no_failed(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_sync_before_write", lambda: None)
    monkeypatch.setattr(cli, "_make_clients", lambda: (object(), object()))
    monkeypatch.setattr(transfer, "run", lambda *a, **k: {"groups": 1})

    code = cli.cmd_transfer(argparse.Namespace(dry_run=False, limit=1, group=None, batch_mode=False))

    assert code == 0


def test_cmd_transfer_returns_one_when_failed(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_sync_before_write", lambda: None)
    monkeypatch.setattr(cli, "_make_clients", lambda: (object(), object()))
    monkeypatch.setattr(transfer, "run", lambda *a, **k: {"failed": 1})

    code = cli.cmd_transfer(argparse.Namespace(dry_run=False, limit=1, group=None, batch_mode=False))

    assert code == 1
