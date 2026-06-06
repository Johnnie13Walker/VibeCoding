import pytest

from src.lock import AlreadyRunning, single_instance


def test_second_instance_blocked(tmp_path):
    lock_path = str(tmp_path / "runner.lock")

    with single_instance(lock_path):
        with pytest.raises(AlreadyRunning):
            with single_instance(lock_path):
                pass


def test_lock_released_after_context(tmp_path):
    lock_path = str(tmp_path / "runner.lock")

    with single_instance(lock_path):
        pass

    with single_instance(lock_path):
        pass


def test_lock_released_on_exception(tmp_path):
    lock_path = str(tmp_path / "runner.lock")

    with pytest.raises(RuntimeError):
        with single_instance(lock_path):
            raise RuntimeError("boom")

    with single_instance(lock_path):
        pass


def test_inherited_shell_lock_fd_is_accepted(tmp_path, monkeypatch):
    lock_path = tmp_path / "runner.lock"
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        monkeypatch.setenv("SCC_LOCK_FD", str(lock_file.fileno()))
        with single_instance(str(lock_path)):
            pass
