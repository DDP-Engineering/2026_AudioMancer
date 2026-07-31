#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# Commercial use requires a separate commercial license.
# See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# -----------------------------------------------------------------------------
"""
@file persistence.py
@brief Cross-platform atomic file replacement and cooperative process locking.
@details Provides the small stdlib-only persistence contract shared by AEGIS
         graph, journal, requirement, and integration state writers.
"""

# IMPORTS

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import errno
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, BinaryIO, Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl

# CONSTANTS

DEFAULT_LOCK_TIMEOUT = 15.0
LOCK_POLL_INTERVAL = 0.05
LOCK_ROOT = Path(".agentic") / ".workspace" / "locks"

# DATA MODELS / TYPEDEFINITIONS


class PersistenceError(ValueError):
    """
    @brief Base class for actionable AEGIS persistence failures.
    """


class LockTimeoutError(PersistenceError):
    """
    @brief Report a bounded wait that could not acquire a live OS file lock.
    """

    code = "PERSISTENCE-LOCK-TIMEOUT"

    def __init__(self, path: Path, timeout: float) -> None:
        """
        @brief Initialize one actionable lock-timeout result.
        @param[in] path Persistent lock-file path.
        @param[in] timeout Maximum wait in seconds.
        """
        self.path = path
        self.timeout = timeout
        super().__init__(
            f"{self.code}: timed out after {timeout:.1f}s waiting for {path}. "
            "Another AEGIS process still holds the OS lock. Retry after that "
            "process finishes; do not delete the lock file to bypass a live owner."
        )


@dataclass
class _HeldLock:
    """
    @brief Track one outer OS lock and its same-thread nesting depth.
    """

    handle: BinaryIO
    depth: int


class FileLock:
    """
    @brief Coordinate threads and processes through one persistent lock file.
    @details The lock file is intentionally retained. Process termination
             releases the operating-system lock, so an unlocked stale file is
             acquired normally and is never deleted based on uncertain owner
             metadata.
    """

    def __init__(
        self,
        path: Path,
        *,
        timeout: float = DEFAULT_LOCK_TIMEOUT,
    ) -> None:
        """
        @brief Configure one bounded, reentrant lock acquisition.
        @param[in] path Lock-file path.
        @param[in] timeout Maximum wait in seconds.
        """
        self.path = path.resolve()
        self.timeout = timeout
        self.reentrant = False
        self._acquired = False
        self._thread_lock: threading.RLock | None = None

    def __enter__(self) -> "FileLock":
        """
        @brief Acquire the configured lock and return this lock object.
        """
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        """
        @brief Release one acquisition depth.
        """
        self.release()

    def acquire(self) -> None:
        """
        @brief Acquire a process-local mutex and operating-system file lock.
        @exception LockTimeoutError If the bounded wait expires.
        @exception PersistenceError If the operating-system lock fails.
        """
        if self._acquired:
            return
        deadline = time.monotonic() + self.timeout
        thread_lock = _thread_lock_for(self.path)
        remaining = max(0.0, deadline - time.monotonic())
        if not thread_lock.acquire(timeout=remaining):
            raise LockTimeoutError(self.path, self.timeout)
        self._thread_lock = thread_lock

        held = _held_locks()
        key = str(self.path)
        existing = held.get(key)
        if existing is not None:
            existing.depth += 1
            self.reentrant = True
            self._acquired = True
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b", buffering=0)
        try:
            _ensure_lock_byte(handle)
            while True:
                try:
                    _acquire_os_lock(handle)
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise LockTimeoutError(self.path, self.timeout) from None
                    time.sleep(min(LOCK_POLL_INTERVAL, remaining))
                except OSError as exc:
                    if _lock_is_busy(exc):
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise LockTimeoutError(
                                self.path, self.timeout
                            ) from None
                        time.sleep(min(LOCK_POLL_INTERVAL, remaining))
                        continue
                    raise PersistenceError(
                        f"cannot acquire AEGIS lock {self.path}: {exc}"
                    ) from exc
        except BaseException:
            handle.close()
            thread_lock.release()
            self._thread_lock = None
            raise
        held[key] = _HeldLock(handle=handle, depth=1)
        self._acquired = True

    def release(self) -> None:
        """
        @brief Release one nesting depth and the outer OS lock when appropriate.
        """
        if not self._acquired:
            return
        held = _held_locks()
        key = str(self.path)
        state = held[key]
        state.depth -= 1
        if state.depth == 0:
            try:
                _release_os_lock(state.handle)
            finally:
                state.handle.close()
                del held[key]
        self._acquired = False
        if self._thread_lock is not None:
            self._thread_lock.release()
            self._thread_lock = None


# PUBLIC API


def scoped_lock_path(repo_root: Path, namespace: str, identity: str) -> Path:
    """
    @brief Build a repository-local lock path without exposing identity syntax.
    @param[in] repo_root Repository root.
    @param[in] namespace Stable state category such as runs or requirements.
    @param[in] identity Run or record identity scoped within the category.
    @return Persistent worktree-local lock-file path.
    """
    digest = sha256(identity.encode("utf-8")).hexdigest()
    return repo_root / LOCK_ROOT / namespace / f"{digest}.lock"


@contextmanager
def locked(
    path: Path,
    *,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> Iterator[FileLock]:
    """
    @brief Hold one cross-process lock for the context duration.
    @param[in] path Persistent lock-file path.
    @param[in] timeout Maximum wait in seconds.
    @return Iterator yielding the acquired lock.
    @exception LockTimeoutError If the bounded wait expires.
    """
    lock = FileLock(path, timeout=timeout)
    with lock:
        yield lock


def create_temporary_bytes(path: Path, content: bytes) -> Path:
    """
    @brief Exclusively create, flush, and fsync a unique sibling temporary file.
    @param[in] path Final destination used to select the sibling directory.
    @param[in] content Complete bytes to persist.
    @return Created temporary path ready for publication.
    @exception OSError If creation or persistence fails.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def create_temporary_text(path: Path, content: str) -> Path:
    """
    @brief Persist UTF-8 text to a unique, exclusive sibling temporary file.
    @param[in] path Final destination.
    @param[in] content Complete text to persist with caller-selected newlines.
    @return Created temporary path ready for publication.
    @exception OSError If creation or persistence fails.
    """
    return create_temporary_bytes(path, content.encode("utf-8"))


def replace_temporary(temporary: Path, path: Path) -> None:
    """
    @brief Atomically publish a completed sibling temporary file.
    @param[in] temporary Completed temporary file.
    @param[in] path Final destination.
    @return None.
    @exception OSError If atomic replacement fails.
    """
    os.replace(temporary, path)
    sync_directory(path.parent)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """
    @brief Publish complete bytes atomically and clean every unpublished temp.
    @param[in] path Final destination.
    @param[in] content Complete bytes to persist.
    @return None.
    @exception OSError If persistence or replacement fails.
    """
    temporary = create_temporary_bytes(path, content)
    try:
        replace_temporary(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path: Path, content: str) -> None:
    """
    @brief Publish complete UTF-8 text through atomic sibling replacement.
    @param[in] path Final destination.
    @param[in] content Complete text to persist.
    @return None.
    @exception OSError If persistence or replacement fails.
    """
    atomic_write_bytes(path, content.encode("utf-8"))


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """
    @brief Serialize and atomically publish one normalized JSON document.
    @param[in] path Final destination.
    @param[in] data JSON-compatible mapping.
    @return None.
    @exception OSError If persistence or replacement fails.
    """
    atomic_write_text(
        path,
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def sync_directory(directory: Path) -> None:
    """
    @brief Fsync directory metadata on platforms that support directory handles.
    @param[in] directory Directory containing a newly replaced entry.
    @return None.
    @details Windows does not expose a portable stdlib directory-fsync path;
             unsupported filesystems are tolerated after file fsync and replace.
    """
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        try:
            os.fsync(descriptor)
        except OSError:
            pass
    finally:
        os.close(descriptor)


# LOCAL HELPERS

_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_STATE = threading.local()


def _thread_lock_for(path: Path) -> threading.RLock:
    """
    @brief Return the process-local reentrant mutex for one lock path.
    """
    key = str(path)
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def _held_locks() -> dict[str, _HeldLock]:
    """
    @brief Return same-thread OS lock state.
    """
    held = getattr(_THREAD_STATE, "held", None)
    if held is None:
        held = {}
        _THREAD_STATE.held = held
    return held


def _ensure_lock_byte(handle: BinaryIO) -> None:
    """
    @brief Ensure Windows can lock the first byte of a new lock file.
    """
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)


def _acquire_os_lock(handle: BinaryIO) -> None:
    """
    @brief Attempt one non-blocking platform lock acquisition.
    """
    handle.seek(0)
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_os_lock(handle: BinaryIO) -> None:
    """
    @brief Release one platform lock.
    """
    handle.seek(0)
    if os.name == "nt":
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _lock_is_busy(exc: OSError) -> bool:
    """
    @brief Identify platform error codes used for non-blocking contention.
    @details ``EACCES`` is included because Windows reports lock contention as
             a permission error; a genuine permission problem therefore spins
             until the lock timeout before surfacing. Documented trade-off.
    """
    return exc.errno in {
        errno.EAGAIN,
        errno.EACCES,
        errno.EDEADLK,
        getattr(errno, "EWOULDBLOCK", errno.EAGAIN),
    }


# END OF FILE
