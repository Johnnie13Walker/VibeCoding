"""Obsidian vault provider.

Референсный шаблон. Целевой путь в runtime:
``cloudbot/providers/obsidian_provider.py``.

Контракт: ``shared/docs/integrations/obsidian_vault.md``.
"""

from __future__ import annotations

import fcntl
import os
import re
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Europe/Moscow"
LOCK_FILENAME = ".cloudbot.lock"
SEARCH_SNIPPET_RADIUS = 80


@dataclass(frozen=True)
class ObsidianConfig:
    vault_path: Path
    git_remote: str | None
    sync_enabled: bool
    default_inbox: str
    daily_dir: str
    timezone: str
    git_author_name: str
    git_author_email: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "ObsidianConfig":
        env = env or os.environ
        vault_path = env.get("OBSIDIAN_VAULT_PATH")
        if not vault_path:
            raise RuntimeError("OBSIDIAN_VAULT_PATH не задан")
        return cls(
            vault_path=Path(vault_path).resolve(),
            git_remote=env.get("OBSIDIAN_GIT_REMOTE") or None,
            sync_enabled=_as_bool(env.get("OBSIDIAN_SYNC_ENABLED"), default=True),
            default_inbox=env.get("OBSIDIAN_DEFAULT_INBOX", "Inbox"),
            daily_dir=env.get("OBSIDIAN_DAILY_DIR", "Daily"),
            timezone=env.get("OBSIDIAN_TIMEZONE", DEFAULT_TIMEZONE),
            git_author_name=env.get("OBSIDIAN_GIT_AUTHOR_NAME", "Cloudbot"),
            git_author_email=env.get("OBSIDIAN_GIT_AUTHOR_EMAIL", "cloudbot@example.local"),
        )


@dataclass(frozen=True)
class SearchHit:
    path: str
    score: int
    snippet: str


class ObsidianError(RuntimeError):
    """Ошибка работы с vault."""


class ObsidianProvider:
    BASE_DIRS = ("Inbox", "Daily", "Projects", "Tasks", "Meetings", "Health", "Cloudbot", "Templates")

    def __init__(self, config: ObsidianConfig) -> None:
        self.config = config

    # --- vault lifecycle -------------------------------------------------

    def ensure_vault(self) -> None:
        vault = self.config.vault_path
        if not vault.exists():
            raise ObsidianError(f"Vault не найден: {vault}")
        if not (vault / ".git").exists():
            raise ObsidianError(f"{vault} не является git-репозиторием")
        for sub in self.BASE_DIRS:
            (vault / sub).mkdir(parents=True, exist_ok=True)

    # --- git-sync --------------------------------------------------------

    def sync_pull(self) -> None:
        if not self.config.sync_enabled:
            return
        with self._lock():
            self._git("pull", "--rebase", "--autostash")

    def sync_push(self, message: str) -> None:
        if not self.config.sync_enabled:
            return
        with self._lock():
            self._git("add", ".")
            status = self._git("status", "--porcelain", capture=True).strip()
            if not status:
                return
            env = {
                "GIT_AUTHOR_NAME": self.config.git_author_name,
                "GIT_AUTHOR_EMAIL": self.config.git_author_email,
                "GIT_COMMITTER_NAME": self.config.git_author_name,
                "GIT_COMMITTER_EMAIL": self.config.git_author_email,
            }
            self._git("commit", "-m", message, env=env)
            self._git("push")

    # --- notes -----------------------------------------------------------

    def write_note(self, relative_path: str, content: str) -> Path:
        target = self._safe_join(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_normalize(content), encoding="utf-8")
        return target

    def append_note(self, relative_path: str, content: str) -> Path:
        target = self._safe_join(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        joined = existing.rstrip() + "\n\n" + _normalize(content) if existing else _normalize(content)
        target.write_text(joined.rstrip() + "\n", encoding="utf-8")
        return target

    def read_note(self, relative_path: str) -> str:
        target = self._safe_join(relative_path)
        if not target.exists():
            raise ObsidianError(f"Заметка не найдена: {relative_path}")
        return target.read_text(encoding="utf-8")

    def search_notes(self, query: str, limit: int = 10) -> list[SearchHit]:
        query = query.strip()
        if not query:
            return []
        needle = query.lower()
        hits: list[SearchHit] = []
        for path in self._iter_markdown():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            score = 0
            lower = text.lower()
            score += lower.count(needle) * 2
            if needle in path.name.lower():
                score += 5
            if score == 0:
                continue
            snippet = _make_snippet(text, lower, needle)
            rel = path.relative_to(self.config.vault_path).as_posix()
            hits.append(SearchHit(path=rel, score=score, snippet=snippet))
        hits.sort(key=lambda hit: (-hit.score, hit.path))
        return hits[:limit]

    # --- helpers ---------------------------------------------------------

    def now_local(self) -> datetime:
        return datetime.now(ZoneInfo(self.config.timezone))

    def daily_relative_path(self, when: datetime | None = None) -> str:
        moment = when or self.now_local()
        return f"{self.config.daily_dir}/{moment.strftime('%Y-%m-%d')}.md"

    def _iter_markdown(self) -> Iterable[Path]:
        for path in self.config.vault_path.rglob("*.md"):
            rel = path.relative_to(self.config.vault_path).as_posix()
            if rel.startswith(".obsidian/") or rel.startswith(".trash/") or rel.startswith(".git/"):
                continue
            yield path

    def _safe_join(self, relative_path: str) -> Path:
        if not relative_path or relative_path.strip() in {"", "."}:
            raise ObsidianError("Пустой путь к заметке")
        cleaned = relative_path.replace("\\", "/").lstrip("/")
        if ".." in Path(cleaned).parts:
            raise ObsidianError("Запрещён путь с '..'")
        target = (self.config.vault_path / cleaned).resolve()
        try:
            target.relative_to(self.config.vault_path)
        except ValueError as exc:
            raise ObsidianError(f"Путь вне vault: {relative_path}") from exc
        if not target.suffix:
            target = target.with_suffix(".md")
        if target.suffix.lower() != ".md":
            raise ObsidianError("Разрешены только .md заметки")
        return target

    def _git(
        self,
        *args: str,
        capture: bool = False,
        env: dict[str, str] | None = None,
    ) -> str:
        cmd = ["git", "-C", str(self.config.vault_path), *args]
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            env=merged_env,
        )
        if result.returncode != 0:
            raise ObsidianError(
                f"git {' '.join(args)} завершился с кодом {result.returncode}: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return result.stdout if capture else ""

    @contextmanager
    def _lock(self) -> Iterator[None]:
        lock_path = self.config.vault_path / LOCK_FILENAME
        lock_path.touch(exist_ok=True)
        with lock_path.open("r+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").rstrip() + "\n"


def _make_snippet(text: str, lower: str, needle: str) -> str:
    idx = lower.find(needle)
    if idx == -1:
        return text[:SEARCH_SNIPPET_RADIUS].strip()
    start = max(0, idx - SEARCH_SNIPPET_RADIUS)
    end = min(len(text), idx + len(needle) + SEARCH_SNIPPET_RADIUS)
    snippet = text[start:end].strip()
    snippet = re.sub(r"\s+", " ", snippet)
    if start > 0:
        snippet = "… " + snippet
    if end < len(text):
        snippet = snippet + " …"
    return snippet
