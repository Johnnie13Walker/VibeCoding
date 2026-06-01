import contextlib
import fcntl
import os
from collections.abc import Iterator

DEFAULT_LOCK_PATH = "/tmp/scc-daily-runner.lock"


class AlreadyRunning(RuntimeError):
    pass


@contextlib.contextmanager
def single_instance(lock_path: str | None = None) -> Iterator[None]:
    path = lock_path or os.environ.get("SCC_LOCK_PATH") or DEFAULT_LOCK_PATH
    lock_file = open(path, "w", encoding="utf-8")

    try:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            lock_file.close()
            raise AlreadyRunning(f"daily runner is already running: {path}") from exc

        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(f"{os.getpid()}\n")
        lock_file.flush()
        yield
    finally:
        if not lock_file.closed:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
            lock_file.close()
