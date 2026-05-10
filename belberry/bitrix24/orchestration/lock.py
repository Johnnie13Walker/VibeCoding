"""Process lock для защиты apply, OAuth refresh и ledger race."""

from __future__ import annotations

import json
import os
import socket
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Mapping
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


class LockBusy(RuntimeError):
    """Lock занят живым holder-ом."""


class LockStale(RuntimeError):
    """Lock stale и может быть перехвачен."""


@dataclass(frozen=True)
class LockHolder:
    pid: int
    hostname: str
    started_at_msk: str
    ttl_sec: int

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def _now_msk(now_msk: datetime | None = None) -> datetime:
    current = now_msk or datetime.now(MOSCOW_TZ)
    return current.replace(tzinfo=MOSCOW_TZ) if current.tzinfo is None else current.astimezone(MOSCOW_TZ)


def _parse_started_at(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("started_at_msk is required")
    parsed = datetime.fromisoformat(raw)
    return parsed.replace(tzinfo=MOSCOW_TZ) if parsed.tzinfo is None else parsed.astimezone(MOSCOW_TZ)


def _holder_from_payload(payload: Mapping[str, Any]) -> LockHolder:
    return LockHolder(
        pid=int(payload["pid"]),
        hostname=str(payload["hostname"]),
        started_at_msk=str(payload["started_at_msk"]),
        ttl_sec=int(payload["ttl_sec"]),
    )


def _write_lock_exclusive(lock_path: Path, holder: LockHolder) -> None:
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(holder.to_json(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        finally:
            raise
    os.chmod(path, 0o600)


def _is_stale(holder: LockHolder, *, now_msk: datetime) -> bool:
    started_at = _parse_started_at(holder.started_at_msk)
    return started_at + timedelta(seconds=holder.ttl_sec) <= _now_msk(now_msk)


def inspect_lock(lock_path: Path) -> LockHolder | None:
    """Read-only lock check для healthcheck CLI."""
    path = Path(lock_path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    try:
        return _holder_from_payload(payload)
    except (KeyError, TypeError, ValueError):
        return None


def _new_holder(*, ttl_sec: int, now_msk: datetime | None = None) -> LockHolder:
    if int(ttl_sec) <= 0:
        raise ValueError("ttl_sec must be positive")
    started_at = _now_msk(now_msk).isoformat(timespec="seconds")
    return LockHolder(
        pid=os.getpid(),
        hostname=socket.gethostname(),
        started_at_msk=started_at,
        ttl_sec=int(ttl_sec),
    )


def acquire_lock(
    lock_path: Path,
    *,
    ttl_sec: int = 1800,
    now_msk: datetime | None = None,
) -> LockHolder:
    """Атомарно создает lock-файл или перехватывает stale lock."""
    path = Path(lock_path)
    holder = _new_holder(ttl_sec=ttl_sec, now_msk=now_msk)
    try:
        _write_lock_exclusive(path, holder)
        return holder
    except FileExistsError:
        current = inspect_lock(path)
        current_is_stale = True
        if current is not None:
            try:
                current_is_stale = _is_stale(current, now_msk=_now_msk(now_msk))
            except ValueError:
                current_is_stale = True
        if current is not None and not current_is_stale:
            raise LockBusy(
                f"lock busy: pid={current.pid} host={current.hostname} started={current.started_at_msk}"
            ) from None

        if current is not None:
            stale_message = f"stale lock: pid={current.pid} host={current.hostname} started={current.started_at_msk}"
        else:
            stale_message = "stale lock: unreadable lock file"

        try:
            path.unlink()
        except FileNotFoundError:
            pass
        try:
            _write_lock_exclusive(path, holder)
        except FileExistsError as error:
            raise LockBusy(stale_message) from error
        return holder


def release_lock(lock_path: Path, holder: LockHolder) -> None:
    """Удаляет lock только если PID+hostname+started_at совпадают."""
    path = Path(lock_path)
    current = inspect_lock(path)
    if current is None:
        return
    if (
        current.pid == holder.pid
        and current.hostname == holder.hostname
        and current.started_at_msk == holder.started_at_msk
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            return


@contextmanager
def process_lock(lock_path: Path, **kwargs: Any) -> Iterator[LockHolder]:
    """try/finally wrapper для process lock."""
    holder = acquire_lock(lock_path, **kwargs)
    try:
        yield holder
    finally:
        release_lock(lock_path, holder)
