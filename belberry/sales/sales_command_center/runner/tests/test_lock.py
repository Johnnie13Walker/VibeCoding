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
