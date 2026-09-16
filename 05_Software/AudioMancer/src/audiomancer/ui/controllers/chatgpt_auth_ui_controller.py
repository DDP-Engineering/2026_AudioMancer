#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chatgpt_auth_ui_controller.py
@brief Run account operations independently of project workflow modal workers.
@details Qt receiver slots own widget updates. Profile snapshots and cancellation
         guards discard stale results, and shutdown retains unfinished threads.
"""

# IMPORTS

from threading import Event

from PySide6.QtCore import QObject, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from audiomancer import config
from audiomancer.services import (
    chatgpt_auth_service,
    chatgpt_catalog_service,
    chatgpt_credential_service,
    chatgpt_model_service,
    ui_state_service,
)
from audiomancer.services.operation_runtime_service import OperationCancelledError

# PUBLIC API


class AccountWorker(QThread):
    """@brief Own one cancellable account job without accessing Qt widgets."""

    progress = Signal(object)

    def __init__(self, action, profile, session_only):
        """@brief Capture immutable job inputs and a cancellation event."""
        super().__init__()
        self.action, self.profile, self.session_only = action, dict(profile), session_only
        self.cancel = Event()
        self.outcome = None

    def run(self):
        """@brief Perform blocking service work on the worker thread and retain only a safe outcome."""
        try:
            if self.action in {"browser", "device"}:
                chatgpt_credential_service.select_session_only(self.session_only)
                result = chatgpt_auth_service.sign_in(
                    self.action, progress=self.progress.emit, cancel=self.cancel.is_set
                )
            elif self.action == "verify":
                result = chatgpt_model_service.verify_profile(self.profile, cancel=self.cancel.is_set)
            else:
                manager = chatgpt_credential_service.get_manager()
                if self.action == "disconnect":
                    manager.disconnect(self.cancel.is_set)
                result = manager.status(self.cancel.is_set)
            if self.action != "verify":
                if result.get("connected"):
                    result["catalog"] = chatgpt_catalog_service.list_models(
                        cancel=self.cancel.is_set, force=self.action in {"browser", "device", "refresh"}
                    )
                else:
                    result["catalog"] = {"source": "builtin", "models": chatgpt_catalog_service.builtin_models()}
            self.outcome = ("success", result)
        except OperationCancelledError:
            self.outcome = ("cancelled", None)
        except RuntimeError as error:
            self.outcome = ("error", str(error))
        except Exception:
            self.outcome = ("error", "ChatGPT account operation failed. Retry or use session-only sign-in.")


class ChatGPTAuthUiController(QObject):
    """@brief Coordinate account buttons, non-modal feedback and worker lifetime."""

    def __init__(self, page, dialog, parent=None):
        """@brief Attach account controls and cancellation to the static settings dialog."""
        super().__init__(parent if parent is not None else dialog)
        self.page, self.dialog = page, dialog
        self._worker = None
        self._pending_disconnect = False
        self._closing = False
        page._chatgpt_browser_button.clicked.connect(lambda: self.start("browser"))
        page._chatgpt_device_button.clicked.connect(lambda: self.start("device"))
        page._chatgpt_disconnect_button.clicked.connect(self.disconnect)
        page._chatgpt_cancel_button.clicked.connect(self.cancel)
        page._chatgpt_refresh_button.clicked.connect(lambda: self.start("refresh"))
        page._profile_list.currentRowChanged.connect(self.cancel)
        page._backend_combo.currentTextChanged.connect(self.cancel)
        page._model_combo.currentTextChanged.connect(self.cancel)
        page._reasoning_mode_combo.currentIndexChanged.connect(self.cancel)
        dialog.finished.connect(self.cancel)

    @property
    def busy(self):
        """@brief Report whether a worker remains owned, including queued finalization."""
        return self._worker is not None

    def _text(self, key):
        """@brief Resolve account feedback in the settings page's current language."""
        return ui_state_service.translate("ai_settings." + key, self.page._current_language)

    def start(self, action="status"):
        """@brief Capture profile identity before dispatch; never launch overlapping account jobs."""
        if self.busy or self._closing:
            return
        profile = self.page.build_current_profile_payload() or {}
        if (action in {"browser", "device", "verify", "refresh"}
                and profile.get("backend_kind") != config.CHATGPT_BACKEND_KIND):
            return
        worker = AccountWorker(action, profile, self.page._chatgpt_session_only.isChecked())
        self._worker = worker
        worker.progress.connect(self._progress)
        worker.finished.connect(self._finished)
        self.page.set_subscription_busy(True)
        self.page.set_subscription_status(self._text("chatgpt_working"), visible=action != "status")
        worker.start()

    @Slot()
    def disconnect(self):
        """@brief Cancel pending work before serializing a logout tombstone."""
        if self.busy:
            self._pending_disconnect = True
            self.cancel()
        else:
            self.start("disconnect")

    def cancel(self, *_args):
        """@brief Request cancellation and suppress queued progress or successful stale results."""
        if self._worker is not None:
            self._worker.cancel.set()

    @Slot(object)
    def _progress(self, notice):
        """@brief Open the official authorization page on the UI thread and show a transient device code."""
        worker = self._worker
        if worker is None or worker.cancel.is_set() or self._closing:
            return
        url = QUrl(str(notice.get("url", "")))
        if url.scheme() != "https" or url.host() != "auth.openai.com":
            return
        opened = QDesktopServices.openUrl(url)
        text = self._text("chatgpt_browser_wait")
        if notice.get("kind") == "device":
            text = self._text("chatgpt_device_code").format(code=notice.get("code", ""))
            text += "\nhttps://auth.openai.com/codex/device"
        elif not opened:
            text = self._text("chatgpt_browser_failed")
        self.page.set_subscription_status(text)

    @Slot()
    def _finished(self):
        """@brief Apply results only to the unchanged selected profile, then release the stopped thread."""
        worker = self._worker
        if worker is None:
            return
        self._worker = None
        self.page.set_subscription_busy(False)
        kind, result = worker.outcome or ("cancelled", None)
        if worker.cancel.is_set() or self._closing:
            self.page.set_subscription_status(self._text("chatgpt_cancelled"), visible=False)
        elif kind == "error":
            self.page.set_subscription_status(result)
        elif kind == "success":
            if worker.action == "verify":
                current = self.page.build_current_profile_payload() or {}
                identity_fields = ("id", "backend_kind", "model_name", "reasoning_effort")
                if all(current.get(key) == worker.profile.get(key) for key in identity_fields):
                    self.page.apply_probe_result(result)
                    key = (
                        "chatgpt_verified_schema"
                        if result.get("supports_structured_output")
                        else "chatgpt_verified_text"
                    )
                    self.page.set_subscription_status(
                        self._text(key) if result.get("success") else result.get("message", ""),
                        visible=not result.get("success", False),
                    )
            else:
                if "catalog" in result:
                    self.page.apply_subscription_catalog(result["catalog"])
                connected = result.get("connected", False)
                text = self._text("chatgpt_connected" if connected else "chatgpt_signed_out")
                if connected:
                    text += " " + str(result.get("label", ""))
                if result.get("storage_warning"):
                    text += "\n" + self._text("chatgpt_storage_warning")
                self.page.set_subscription_status(text, visible=bool(result.get("storage_warning")))
                self.page._chatgpt_session_only.setChecked(bool(result.get("session_only", False)))
                if worker.action == "disconnect":
                    for profile in self.page._profiles:
                        if profile.get("backend_kind") == config.CHATGPT_BACKEND_KIND:
                            profile.update(supports_structured_output=False, discovery_succeeded=False)
                    self.page._supports_structured_checkbox.setChecked(False)
        worker.deleteLater()
        if self._pending_disconnect and not self._closing:
            self._pending_disconnect = False
            self.start("disconnect")

    def shutdown(self, timeout_ms=2000):
        """@brief Cancel and wait within the close budget; a live worker keeps the window alive."""
        self._closing = True
        self.cancel()
        worker = self._worker
        if worker is not None and not worker.wait(timeout_ms):
            self._closing = False
            return False
        if worker is not None:
            self._finished()
        return True


# END OF FILE
