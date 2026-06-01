import re
import shutil
import subprocess
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def read_script(name: str) -> str:
    return (SCRIPTS / name).read_text()


def test_run_daily_has_flock_and_tz():
    text = read_script("run_daily.sh")

    assert "flock" in text
    assert "TZ" in text
    assert "Europe/Moscow" in text
    assert "SCC_LOCK_PATH" in text
    assert "daily_runner.py" in text


def test_backup_has_pgdump_and_rotation():
    text = read_script("backup_postgres.sh")

    assert "pg_dump" in text
    assert re.search(r"find.+-mtime.+-delete", text, re.S)


def test_crontab_schedule():
    text = read_script("crontab.scc")

    assert "TZ=Europe/Moscow" in text
    assert "0 9 * * 1-5" in text
    assert "run_daily.sh" in text
    assert "backup_postgres.sh" in text


def test_no_hardcoded_secrets():
    pattern = re.compile(r"sk-ant|password=|[0-9]{6,}:[A-Za-z0-9_-]{30}")

    for name in ("run_daily.sh", "backup_postgres.sh"):
        assert not pattern.search(read_script(name))


def test_shell_syntax_is_valid():
    if not shutil.which("bash"):
        return

    for name in ("run_daily.sh", "backup_postgres.sh"):
        subprocess.run(["bash", "-n", str(SCRIPTS / name)], check=True)
