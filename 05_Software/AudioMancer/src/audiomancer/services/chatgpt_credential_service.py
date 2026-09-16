#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chatgpt_credential_service.py
@brief Own the subscription account lifecycle and renewable credentials.
@details Transactions serialize rotation and logout across processes. Generation
         checks prevent late login, capability writes and requests from reviving logout.
"""

# IMPORTS

import copy
from dataclasses import asdict, dataclass, field
import math
import time
import uuid

from audiomancer.services.chatgpt_storage_service import MemoryStore, ProtectedStore, check_cancel
from audiomancer.services.logging_service import get_component_logger
from audiomancer.services.operation_runtime_service import OperationCancelledError

# DATA MODELS


@dataclass(frozen=True)
class Credential:
    """@brief Immutable credentials whose representation never exposes bearer material."""

    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: float = field(repr=False)
    account_id: str = field(repr=False)
    label: str = "ChatGPT account"
    residency: str = field(default="", repr=False)


# PUBLIC API


class CredentialManager:
    """@brief Manage a single OS-user account, independent of any saved profile."""

    def __init__(self, store=None, refresh=None, clock=time.time):
        """@brief Inject storage, rotation and clock seams for deterministic lifecycle tests."""
        self.store = store if store is not None else ProtectedStore()
        self.refresh = refresh
        self.clock = clock
        self.retired = False
        self.storage_warning = False

    def _read(self):
        """@brief Validate the envelope before interpreting sensitive fields."""
        if self.retired:
            raise RuntimeError("ChatGPT account storage mode changed. Retry with the current account.")
        try:
            payload = self.store.read()
            if payload is None:
                return {"version": 1, "generation": "initial", "credential": None, "verified": {}}
            if (
                payload.get("version") != 1
                or not isinstance(payload.get("generation"), str)
                or not isinstance(payload.get("verified"), dict)
            ):
                raise ValueError
            return payload
        except Exception:
            raise RuntimeError(
                "ChatGPT protected account data is unavailable. Reconnect or select session-only."
            ) from None

    def _write(self, payload):
        """@brief Convert all storage failures to a diagnostic that cannot contain secrets."""
        try:
            self.store.write(payload)
        except Exception:
            raise RuntimeError("Could not save ChatGPT account data in protected storage.") from None

    def begin_login(self, cancel=None):
        """@brief Capture the generation to which a pending login may commit."""
        with self.store.lock(cancel):
            return self._read()["generation"]

    def finish_login(self, expected, credential: Credential, cancel=None):
        """@brief Commit a new account only if no intervening login/logout has changed it."""
        _validate_credential(credential)
        with self.store.lock(cancel):
            current = self._read()
            _check_generation(current, expected)
            generation = uuid.uuid4().hex
            check_cancel(cancel)
            self._write({"version": 1, "generation": generation, "credential": asdict(credential), "verified": {}})
            return generation

    def disconnect(self, cancel=None):
        """@brief Replace credentials with a durable tombstone, including when old data is corrupt."""
        with self.store.lock(cancel):
            self._write({"version": 1, "generation": uuid.uuid4().hex, "credential": None, "verified": {}})

    def status(self, cancel=None):
        """@brief Expose only account label, connection state and persistence mode to the UI."""
        with self.store.lock(cancel):
            payload = self._read()
            credential = payload["credential"]
            return {
                "connected": credential is not None,
                "label": str(credential.get("label", "ChatGPT account")) if credential else "",
                "session_only": type(self.store) is MemoryStore,
                "storage_warning": self.storage_warning,
            }

    def acquire(self, cancel=None, *, expected=None, rejected_token=None):
        """@brief Return a renewable credential, rotating once under the cross-process lock.
        @param[in] expected Optional pinned login generation for an ongoing operation.
        @param[in] rejected_token Token rejected with HTTP 401; another worker may already have refreshed it.
        @return Generation and credential snapshot; no mutable credential escapes the store.
        """
        with self.store.lock(cancel):
            payload = self._read()
            if expected is not None:
                _check_generation(payload, expected)
            if payload["credential"] is None:
                raise RuntimeError("Sign in to ChatGPT in AI Settings first.")
            try:
                credential = Credential(**payload["credential"])
                _validate_credential(credential)
            except Exception:
                raise RuntimeError("ChatGPT credentials are invalid. Disconnect and sign in again.") from None
            needs_refresh = credential.expires_at <= self.clock() + 300
            needs_refresh |= rejected_token is not None and credential.access_token == rejected_token
            if needs_refresh:
                refresh = self.refresh
                if refresh is None:
                    from audiomancer.services.chatgpt_auth_service import refresh_credential

                    refresh = refresh_credential
                try:
                    renewed = refresh(credential, cancel)
                    _validate_credential(renewed)
                    if renewed.account_id != credential.account_id:
                        raise RuntimeError("The refreshed ChatGPT account changed. Sign in again.")
                except OperationCancelledError:
                    raise
                except Exception as error:
                    if getattr(error, "reauthenticate", False):
                        payload.update(credential=None, verified={}, generation=uuid.uuid4().hex)
                        self._write(payload)
                    raise RuntimeError("ChatGPT credentials could not be refreshed. Retry or sign in again.") from None
                check_cancel(cancel)
                payload["credential"] = asdict(renewed)
                self._write(payload)
                credential = renewed
            return payload["generation"], credential

    def assert_current(self, generation, cancel=None):
        """@brief Prevent an in-flight completion from being accepted after disconnect."""
        with self.store.lock(cancel):
            _check_generation(self._read(), generation)

    def mark_verified(self, generation, model, schema, cancel=None):
        """@brief Record tested model capabilities only for the current authenticated generation."""
        with self.store.lock(cancel):
            payload = self._read()
            _check_generation(payload, generation)
            payload["verified"][model] = {"text": True, "schema": bool(schema)}
            self._write(payload)

    def is_verified(self, generation, model, *, schema=False, cancel=None):
        """@brief Read protected evidence; editable profile checkboxes cannot grant capabilities."""
        with self.store.lock(cancel):
            payload = self._read()
            _check_generation(payload, generation)
            return bool(payload["verified"].get(model, {}).get("schema" if schema else "text", False))

    def read_catalog(self, generation, cancel=None):
        """@brief Read isolated model metadata only for the pinned account connection."""
        with self.store.lock(cancel):
            payload = self._read()
            _check_generation(payload, generation)
            return copy.deepcopy(payload.get("catalog"))

    def write_catalog(self, generation, catalog, cancel=None):
        """@brief Store normalized catalog metadata without allowing late refreshes to revive logout."""
        with self.store.lock(cancel):
            payload = self._read()
            _check_generation(payload, generation)
            check_cancel(cancel)
            previous = payload.get("catalog")
            timestamp = previous.get("fetched_at", 0) if isinstance(previous, dict) else 0
            if type(timestamp) not in (int, float) or not 0 < timestamp < 1e12:
                timestamp = 0
            if timestamp <= catalog["fetched_at"]:
                payload["catalog"] = copy.deepcopy(catalog)
                self._write(payload)


_MANAGER = CredentialManager()


def get_manager():
    """@brief Return the application-owned credential manager without exposing its state."""
    return _MANAGER


def select_session_only(enabled: bool):
    """@brief Explicitly select persistence before login; remove the previous connection first."""
    global _MANAGER
    get_component_logger("chatgpt_account").debug("Selecting ChatGPT credential persistence mode")
    if (type(_MANAGER.store) is MemoryStore) == enabled:
        return
    previous = _MANAGER
    warning = False
    try:
        previous.disconnect()
    except RuntimeError:
        if not enabled:
            raise
        # This explicit choice permits memory-only use when the OS store is absent.
        # Report that any older protected connection could not be removed.
        warning = True
    replacement = CredentialManager(MemoryStore() if enabled else ProtectedStore())
    if not enabled:
        # Do not revive an older protected login when returning from memory mode.
        replacement.disconnect()
    previous.retired = True
    replacement.storage_warning = warning
    _MANAGER = replacement


# LOCAL HELPERS


def _validate_credential(credential):
    """@brief Reject malformed secrets and non-finite expiry before persistence or use."""
    if (
        not isinstance(credential, Credential)
        or not isinstance(credential.expires_at, (int, float))
        or not math.isfinite(credential.expires_at)
        or credential.expires_at <= 0
    ):
        raise RuntimeError("Invalid ChatGPT credential response.")
    for value in (credential.access_token, credential.refresh_token, credential.account_id):
        if not isinstance(value, str) or not value or len(value) > 64000 or any(c in value for c in "\r\n\0"):
            raise RuntimeError("Invalid ChatGPT credential response.")


def _check_generation(payload, expected):
    """@brief Reject stale asynchronous results using a safe, action-oriented message."""
    if payload["generation"] != expected:
        raise RuntimeError("ChatGPT account changed during this operation. Retry with the current account.")


# END OF FILE
