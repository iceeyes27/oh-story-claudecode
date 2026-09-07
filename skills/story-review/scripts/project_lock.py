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


# 追踪/ 下的运行时文件：不是追踪内容，遍历快照或做投影校验时必须排除。
# 必须排除的原因是跨平台锁语义不同：Windows 的 msvcrt.locking 是**强制**字节范围
# 锁，持锁期间另一个句柄读锁文件会抛 PermissionError [Errno 13]；POSIX 的
# fcntl.flock 是**劝告**锁，照样读得通。所以「在锁内遍历 追踪/ 读全部文件」这类
# 代码在 macOS/Linux 上静默通过、在 Windows 上必炸。
# `.tracking-commit.lock` 是上游遗留名，本 fork 的 tracking_commit.project_write_lock
# 已改为委派给本模块，只有旧项目目录里可能还留着它。
TRACKING_RUNTIME_FILES = frozenset({Path(".tracking-commit.lock"), Path(".story-write.lock")})


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
    pending = unfinished_adoptions(project) + unfinished_revisions(project)
    if pending:
        names = ", ".join(path.name for path in pending)
        raise ProjectLockError(f"unfinished candidate adoption requires recover: {names}")


def unfinished_revisions(project: Path) -> list[Path]:
    history = project.resolve() / "候选" / "_历史"
    pending = []
    for path in sorted(history.glob("修订事务-*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pending.append(path)
            continue
        if document.get("phase") not in {"done", "aborted"}:
            pending.append(path)
    return pending
