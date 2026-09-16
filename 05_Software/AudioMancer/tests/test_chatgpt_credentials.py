#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_chatgpt_credentials.py
@brief Protected account lifecycle and renewable credential concurrency.
@details Exercises isolated protocol, lifecycle and workflow fixtures without live credentials.
"""

# IMPORTS

from concurrent.futures import ThreadPoolExecutor
import importlib
import importlib.util
import json
import subprocess
import sys
import threading
import time

import pytest


def services():
    """@brief Load protected storage and account lifecycle boundaries."""
    name = "audiomancer.services.chatgpt_credential_service"
    assert importlib.util.find_spec(name) is not None, "Protected subscription account lifecycle is missing"
    return importlib.import_module(name), importlib.import_module("audiomancer.services.chatgpt_storage_service")


def credential(module, expires=10000):
    """@brief Build a synthetic immutable credential."""
    return module.Credential("sentinel-access", "sentinel-refresh", expires, "account-one", "Account")


def test_disconnect_rejects_late_login_and_capability_write():
    """@brief Verify disconnect rejects late login and capability write."""
    service, storage = services()
    manager = service.CredentialManager(storage.MemoryStore())
    pending = manager.begin_login()
    manager.disconnect()
    with pytest.raises(RuntimeError, match="changed"):
        manager.finish_login(pending, credential(service))
    generation = manager.finish_login(manager.begin_login(), credential(service))
    manager.disconnect()
    with pytest.raises(RuntimeError, match="changed"):
        manager.mark_verified(generation, "gpt-5.4", True)
    assert not manager.status()["connected"]


def test_concurrent_refresh_rotates_once_and_preserves_verified_models():
    """@brief Verify concurrent refresh rotates once and preserves verified models."""
    service, storage = services()
    calls = []

    def refresh(old, cancel):
        """@brief Simulate bounded credential rotation."""
        calls.append(old.refresh_token)
        time.sleep(0.05)
        return service.Credential("new-access", "new-refresh", 10000, "account-one", "Account")

    manager = service.CredentialManager(storage.MemoryStore(), refresh=refresh, clock=lambda: 100)
    generation = manager.finish_login(manager.begin_login(), credential(service, expires=101))
    manager.mark_verified(generation, "gpt-5.4", True)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: manager.acquire(), range(4)))
    assert calls == ["sentinel-refresh"]
    assert all(result[1].access_token == "new-access" for result in results)
    assert manager.is_verified(generation, "gpt-5.4", schema=True)
    assert "sentinel" not in str(manager.status())
    assert "new-access" not in repr(results[0][1])


def test_store_write_failure_never_reports_connected():
    """@brief Verify store write failure never reports connected."""
    service, storage = services()

    class BrokenStore(storage.MemoryStore):
        """@brief Provide the BrokenStore test fixture."""

        def write(self, envelope):
            """@brief Simulate a protected-store write failure."""
            raise OSError("sentinel-storage-secret")

    manager = service.CredentialManager(BrokenStore())
    with pytest.raises(RuntimeError) as error:
        manager.finish_login(manager.begin_login(), credential(service))
    assert "sentinel" not in str(error.value)
    assert not manager.status()["connected"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native protection")
def test_windows_dpapi_restart_and_tombstone(tmp_path):
    """@brief Verify windows dpapi restart and tombstone."""
    service, storage = services()
    path = tmp_path / "account.bin"
    first = service.CredentialManager(storage.ProtectedStore(path))
    first.finish_login(first.begin_login(), credential(service, expires=time.time() + 10000))
    assert b"sentinel" not in path.read_bytes()
    second = service.CredentialManager(storage.ProtectedStore(path))
    assert second.acquire()[1].account_id == "account-one"
    second.disconnect()
    assert not first.status()["connected"]
    assert "sentinel" not in json.dumps(first.status())


def test_cancelled_lock_acquisition_does_not_wait_for_owner():
    """@brief Verify cancelled lock acquisition does not wait for owner."""
    service, storage = services()
    from audiomancer.services.operation_runtime_service import OperationCancelledError

    store = storage.MemoryStore()
    entered, release = threading.Event(), threading.Event()

    def hold():
        """@brief Hold a competing store lock until the fixture releases it."""
        with store.lock():
            entered.set()
            release.wait(2)

    thread = threading.Thread(target=hold)
    thread.start()
    assert entered.wait(1)
    try:
        with pytest.raises(OperationCancelledError), store.lock(lambda: True):
            pytest.fail("Cancelled lock entered")
    finally:
        release.set()
        thread.join()


def test_explicit_session_mode_works_when_native_store_is_unavailable(monkeypatch):
    """@brief Verify explicit session mode works when native store is unavailable."""
    service, storage = services()

    class UnavailableStore(storage.MemoryStore):
        """@brief Provide the UnavailableStore test fixture."""

        def read(self):
            """@brief Simulate unavailable native credential storage."""
            raise RuntimeError("No native keyring")

        def write(self, payload):
            """@brief Simulate a protected-store write failure."""
            raise RuntimeError("No native keyring")

    monkeypatch.setattr(service, "_MANAGER", service.CredentialManager(UnavailableStore()))
    service.select_session_only(True)
    assert service.get_manager().status()["session_only"]
    assert not service.get_manager().status()["connected"]


def test_invalid_refresh_revokes_and_failed_rotation_write_cannot_succeed():
    """@brief Verify invalid refresh revokes and failed rotation write cannot succeed."""
    service, storage = services()
    from audiomancer.services.chatgpt_http_service import ProviderError

    def invalid(old, cancel):
        """@brief Simulate revocation at the refresh endpoint."""
        raise ProviderError("invalid_grant")

    store = storage.MemoryStore()
    manager = service.CredentialManager(store, refresh=invalid, clock=lambda: 100)
    manager.finish_login(manager.begin_login(), credential(service, expires=101))
    with pytest.raises(RuntimeError, match="refreshed"):
        manager.acquire()
    assert not manager.status()["connected"]

    manager.refresh = lambda old, cancel: credential(service)
    manager.finish_login(manager.begin_login(), credential(service, expires=101))
    store.write = lambda payload: (_ for _ in ()).throw(OSError("sentinel"))
    with pytest.raises(RuntimeError, match="protected storage"):
        manager.acquire()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows cross-process DPAPI storage")
def test_two_processes_serialize_refresh_rotation(tmp_path):
    """@brief Separate processes share one durable refresh rotation and its replacement token."""
    service, storage = services()
    path, rotations = tmp_path / "account.bin", tmp_path / "rotations.txt"
    parent = service.CredentialManager(storage.ProtectedStore(path))
    parent.finish_login(parent.begin_login(), credential(service, expires=time.time() - 1))
    script = """
import sys, time
from pathlib import Path
from audiomancer.services.chatgpt_credential_service import Credential, CredentialManager
from audiomancer.services.chatgpt_storage_service import ProtectedStore
def refresh(old, cancel):
    with Path(sys.argv[2]).open("a") as handle:
        handle.write("rotation\\n")
    time.sleep(.1)
    return Credential("new-access", "new-refresh", time.time()+3600, "account-one")
CredentialManager(ProtectedStore(Path(sys.argv[1])), refresh=refresh).acquire()
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(path), str(rotations)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        for _ in range(2)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr.decode()
        assert not stdout
    assert rotations.read_text().splitlines() == ["rotation"]
    assert parent.acquire()[1].refresh_token == "new-refresh"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native protection")
def test_corrupt_protected_store_can_be_disconnected_and_reconnected(tmp_path):
    """@brief A corrupt encrypted file fails safely and an explicit logout permits recovery."""
    service, storage = services()
    path = tmp_path / "account.bin"
    path.write_bytes(b"sentinel-corrupt-ciphertext")
    manager = service.CredentialManager(storage.ProtectedStore(path))
    with pytest.raises(RuntimeError) as error:
        manager.status()
    assert "sentinel" not in str(error.value)
    manager.disconnect()
    assert not manager.status()["connected"]
    manager.finish_login(manager.begin_login(), credential(service, expires=time.time() + 3600))
    assert manager.acquire()[1].account_id == "account-one"


def test_plaintext_keyring_is_never_selected(monkeypatch):
    """@brief Native-store selection rejects plaintext plugin backends before accessing secrets."""
    import keyring

    _, storage = services()
    backend = type("PlaintextKeyring", (), {"__module__": "keyrings.alt.file"})()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    with pytest.raises(RuntimeError, match="native credential store"):
        storage._native_keyring()


# END OF FILE
