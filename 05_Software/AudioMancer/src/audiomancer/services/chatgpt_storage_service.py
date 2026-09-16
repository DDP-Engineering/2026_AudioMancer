#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chatgpt_storage_service.py
@brief Protect renewable account credentials outside portable application data.
@details Windows uses DPAPI and atomic replacement; other platforms require an
         explicitly supported native keyring. Memory-only storage is opt-in.
"""

# IMPORTS

from contextlib import contextmanager
import copy
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

from audiomancer.services.operation_runtime_service import OperationCancelledError

# CONSTANTS

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_MAX_STORE_BYTES = 256 * 1024


# PUBLIC API


def check_cancel(cancel=None):
    """@brief Raise before continuing a cancelled account operation."""
    if callable(cancel) and cancel():
        raise OperationCancelledError("ChatGPT operation cancelled.")


def account_store_path() -> Path:
    """@brief Resolve per-user credential storage independently of portable settings."""
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "AudioMancer" / "Auth" / "chatgpt.bin"


class MemoryStore:
    """@brief Explicit session-only store with the same serialized envelope contract."""

    def __init__(self):
        """@brief Initialize empty process-local state."""
        self._mutex = threading.RLock()
        self._payload = None

    @contextmanager
    def lock(self, cancel=None):
        """@brief Acquire an interruptible thread lock around a complete transaction."""
        check_cancel(cancel)
        while not self._mutex.acquire(timeout=0.05):
            check_cancel(cancel)
        try:
            check_cancel(cancel)
            yield
        finally:
            self._mutex.release()

    def read(self):
        """@brief Return an isolated copy of the current envelope."""
        return copy.deepcopy(self._payload)

    def write(self, envelope):
        """@brief Replace session state without writing any credentials to disk."""
        self._payload = copy.deepcopy(envelope)


class ProtectedStore(MemoryStore):
    """@brief Serialize processes and protect the entire versioned account envelope."""

    def __init__(self, path: Path | None = None):
        """@brief Select an OS-owned location and a shared in-process mutex."""
        super().__init__()
        self.path = Path(path) if path is not None else account_store_path()
        with _LOCKS_GUARD:
            self._mutex = _LOCKS.setdefault(str(self.path.resolve()).casefold(), threading.RLock())

    @contextmanager
    def lock(self, cancel=None):
        """@brief Hold a cancellable OS lock across read, refresh and durable write."""
        with super().lock(cancel):
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            lock_path = self.path.with_suffix(".lock")
            with lock_path.open("a+b") as handle:
                if handle.seek(0, os.SEEK_END) == 0:
                    handle.write(b"\0")
                    handle.flush()
                deadline = time.monotonic() + 30
                while True:
                    check_cancel(cancel)
                    try:
                        if sys.platform == "win32":
                            import msvcrt

                            handle.seek(0)
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl

                            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("ChatGPT account is busy in another process. Retry shortly.") from None
                        time.sleep(0.05)
                try:
                    yield
                finally:
                    if sys.platform == "win32":
                        import msvcrt

                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle, fcntl.LOCK_UN)

    def read(self):
        """@brief Load protected state, rejecting unreadable or oversized envelopes."""
        try:
            if sys.platform == "win32":
                if not self.path.exists():
                    return None
                if self.path.stat().st_size > _MAX_STORE_BYTES:
                    raise ValueError
                raw = _dpapi(self.path.read_bytes(), protect=False).decode("utf-8")
            else:
                raw = _native_keyring().get_password("AudioMancer.ChatGPT", "default")
                if raw is None:
                    return None
            if len(raw) > _MAX_STORE_BYTES:
                raise ValueError
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError
            return payload
        except Exception:
            raise RuntimeError(
                "ChatGPT protected storage is unavailable or unreadable. Reconnect or use session-only."
            ) from None

    def write(self, envelope):
        """@brief Atomically protect state; never downgrade to a plaintext credential file."""
        try:
            raw = json.dumps(envelope, separators=(",", ":"))
            if len(raw) > _MAX_STORE_BYTES:
                raise ValueError
            if sys.platform != "win32":
                _native_keyring().set_password("AudioMancer.ChatGPT", "default", raw)
                return
            encrypted = _dpapi(raw.encode("utf-8"), protect=True)
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, temporary = tempfile.mkstemp(prefix=".chatgpt-", dir=self.path.parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(encrypted)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        except Exception:
            raise RuntimeError(
                "Could not save ChatGPT credentials in protected storage. Sign-in was not saved."
            ) from None


# LOCAL HELPERS


def _native_keyring():
    """@brief Select only native encrypted backends, rejecting plaintext and chained fallbacks."""
    import keyring

    backend = keyring.get_keyring()
    name = type(backend).__module__
    if name not in {"keyring.backends.macOS", "keyring.backends.SecretService", "keyring.backends.kwallet"}:
        raise RuntimeError("A native credential store is required.")
    return backend


def _dpapi(value: bytes, *, protect: bool) -> bytes:
    """@brief Encrypt/decrypt bytes for the current Windows user without displaying OS prompts."""
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        """@brief Native DATA_BLOB with pointer-size-correct fields."""

        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError("Windows credential protection failed.")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


# END OF FILE
