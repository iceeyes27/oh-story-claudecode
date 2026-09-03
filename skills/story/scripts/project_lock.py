#!/usr/bin/env python3
"""Cross-platform project lock shared by candidate and tracking commands."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO


class ProjectLockError(RuntimeError):
    """The project is busy or has an unfinished adoption transaction."""


def lock_path(project: Path) -> Path:
    return project.resolve() / "追踪" / ".story-write.lock"


def _lock(handle: TextIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise ProjectLockError("another story-write operation holds the project lock") from exc
    else:
        import fcntl

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ProjectLockError("another story-write operation holds the project lock") from exc


def _unlock(handle: TextIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def project_lock(project: Path) -> Iterator[None]:
    path = lock_path(project)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = path.open("a+b")
    except OSError as exc:
        raise ProjectLockError("unable to acquire the project lock") from exc
    with raw:
        raw.seek(0)
        try:
            if raw.read(1) == b"":
                raw.seek(0)
                raw.write(b"0")
                raw.flush()
            handle = raw  # msvcrt/fcntl only require fileno/seek.
            _lock(handle)  # type: ignore[arg-type]
        except ProjectLockError:
            raise
        except OSError as exc:
            raise ProjectLockError("unable to acquire the project lock") from exc
        try:
            yield
        finally:
            _unlock(handle)  # type: ignore[arg-type]


def unfinished_adoptions(project: Path) -> list[Path]:
    history = project.resolve() / "候选" / "_历史"
    if not history.is_dir():
        return []
    pending: list[Path] = []
    for path in sorted(history.glob("采用事务-*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pending.append(path)
            continue
        if document.get("phase") != "done":
            pending.append(path)
    return pending


def assert_no_unfinished_adoption(project: Path) -> None:
    pending = unfinished_adoptions(project)
    if pending:
        names = ", ".join(path.name for path in pending)
        raise ProjectLockError(f"unfinished candidate adoption requires recover: {names}")
