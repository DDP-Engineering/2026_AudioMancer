#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_chatgpt_ui.py
@brief Account UI workers preserve thread affinity, profile ownership and shutdown.
@details Exercises isolated protocol, lifecycle and workflow fixtures without live credentials.
"""

# IMPORTS

import importlib
import time

from PySide6.QtWidgets import QDialog

from audiomancer.services import chatgpt_model_service, settings_service
from audiomancer.ui.pages.ai_settings_page import AiSettingsPage


def page_with_profiles(qtbot):
    """@brief Create independent subscription and local editor profiles."""
    dialog = QDialog()
    qtbot.addWidget(dialog)
    page = AiSettingsPage(dialog)
    settings = settings_service.build_default_settings()
    settings["llm_profiles"] = [
        {"id": "sub", "label": "ChatGPT", "backend_kind": "chatgpt_subscription", "model_name": "gpt-5.5"},
        {"id": "local", "label": "Local", "backend_kind": "lmstudio", "model_name": "local-model"},
    ]
    page.load_settings(settings)
    return dialog, page


def test_subscription_controls_hide_api_key_and_normalize_profile(qtbot):
    """@brief Verify subscription controls hide api key and normalize profile."""
    dialog, page = page_with_profiles(qtbot)
    assert hasattr(page, "_chatgpt_browser_button"), "Subscription account controls are missing"
    assert page._api_key_edit.isHidden()
    assert page._base_url_edit.isReadOnly()
    profile = page.build_current_profile_payload()
    assert profile["base_url"] == "https://chatgpt.com/backend-api"
    assert profile["credential_ref"] == "chatgpt-default"
    for model in ("gpt-5.6-terra", "gpt-5.6-luna"):
        assert page._model_combo.findText(model) >= 0
        page._model_combo.setCurrentText(model)
        assert page.build_current_profile_payload()["model_name"] == model
    page._profile_list.setCurrentRow(1)
    assert not page._api_key_edit.isHidden()
    assert not page._base_url_edit.isReadOnly()
    assert page._chatgpt_panel.isHidden()


def test_worker_does_not_apply_probe_to_another_profile_and_shuts_down(qtbot, monkeypatch):
    """@brief Verify worker does not apply probe to another profile and shuts down."""
    dialog, page = page_with_profiles(qtbot)
    assert hasattr(page, "_chatgpt_browser_button"), "Subscription account worker UI is missing"
    controller_module = importlib.import_module("audiomancer.ui.controllers.chatgpt_auth_ui_controller")
    controller = controller_module.ChatGPTAuthUiController(page, dialog)
    calls = []

    def verify(profile, cancel=None):
        """@brief Keep model verification running until cancellation."""
        calls.append(profile["id"])
        while not cancel():
            time.sleep(0.01)
        return {
            "success": True,
            "supports_structured_output": True,
            "discovered_models": [{"id": "wrong-model", "label": "wrong-model"}],
        }

    monkeypatch.setattr(chatgpt_model_service, "verify_profile", verify)
    controller.start("verify")
    qtbot.waitUntil(lambda: bool(calls))
    page._profile_list.setCurrentRow(1)
    qtbot.waitUntil(lambda: not controller.busy)
    assert page.build_current_profile_payload()["model_name"] == "local-model"
    assert controller.shutdown(1000)


def test_dialog_close_cancels_account_worker(qtbot, monkeypatch):
    """@brief Verify dialog close cancels account worker."""
    dialog, page = page_with_profiles(qtbot)
    assert hasattr(page, "_chatgpt_browser_button"), "Subscription cancellation controls are missing"
    controller_module = importlib.import_module("audiomancer.ui.controllers.chatgpt_auth_ui_controller")
    controller = controller_module.ChatGPTAuthUiController(page, dialog)
    entered = []

    def verify(profile, cancel=None):
        """@brief Keep model verification running until cancellation."""
        entered.append(True)
        while not cancel():
            time.sleep(0.01)
        return {"success": False}

    monkeypatch.setattr(chatgpt_model_service, "verify_profile", verify)
    dialog.show()
    controller.start("verify")
    qtbot.waitUntil(lambda: bool(entered))
    dialog.reject()
    qtbot.waitUntil(lambda: not controller.busy)
    assert controller.shutdown(1000)


def test_disconnect_cancels_login_before_writing_tombstone(qtbot, monkeypatch):
    """@brief Logout waits for cancelled sign-in and clears account evidence without overlapping workers."""
    from audiomancer.services import chatgpt_auth_service, chatgpt_credential_service, chatgpt_storage_service
    from audiomancer.services.operation_runtime_service import OperationCancelledError

    dialog, page = page_with_profiles(qtbot)
    module = importlib.import_module("audiomancer.ui.controllers.chatgpt_auth_ui_controller")
    controller = module.ChatGPTAuthUiController(page, dialog)
    manager = chatgpt_credential_service.CredentialManager(chatgpt_storage_service.MemoryStore())
    generation = manager.begin_login()
    monkeypatch.setattr(chatgpt_credential_service, "_MANAGER", manager)
    monkeypatch.setattr(chatgpt_credential_service, "select_session_only", lambda enabled: None)
    entered = []

    def sign_in(method, progress=None, cancel=None):
        """@brief Keep a synthetic browser attempt pending until the controller cancels it."""
        entered.append(method)
        while not cancel():
            time.sleep(0.01)
        raise OperationCancelledError("Cancelled")

    monkeypatch.setattr(chatgpt_auth_service, "sign_in", sign_in)
    try:
        controller.start("browser")
        qtbot.waitUntil(lambda: bool(entered))
        controller.disconnect()
        qtbot.waitUntil(lambda: not controller.busy)
        assert manager.begin_login() != generation
        assert not manager.status()["connected"]
        assert not page._supports_structured_checkbox.isChecked()
    finally:
        assert controller.shutdown(1000)


def test_shutdown_keeps_blocked_worker_owned_until_it_stops(qtbot, monkeypatch):
    """@brief A non-cooperative native-store call keeps its QThread alive after the close budget expires."""
    from threading import Event

    dialog, page = page_with_profiles(qtbot)
    module = importlib.import_module("audiomancer.ui.controllers.chatgpt_auth_ui_controller")
    controller = module.ChatGPTAuthUiController(page, dialog)
    entered, release = Event(), Event()

    def verify(profile, cancel=None):
        """@brief Hold a native-call-shaped operation beyond a short shutdown budget."""
        entered.set()
        release.wait(3)
        return {"success": False}

    monkeypatch.setattr(chatgpt_model_service, "verify_profile", verify)
    try:
        controller.start("verify")
        qtbot.waitUntil(entered.is_set)
        assert not controller.shutdown(1)
        assert controller.busy and controller._worker.isRunning()
    finally:
        release.set()
        assert controller.shutdown(1000)
    assert not controller.busy


def test_catalog_refresh_preserves_model_edits_and_rebuilds_reasoning_options(qtbot):
    """@brief Live discovery adds new models without switching profiles or silently changing saved effort."""
    dialog, page = page_with_profiles(qtbot)
    assert hasattr(page, "apply_subscription_catalog"), "Catalog UI integration is missing"
    page._model_combo.setCurrentText("future-model")
    page._label_edit.setText("Unsaved name")
    page.apply_subscription_catalog({"source": "live", "models": [
        {"id": "future-model", "efforts": ["low", "high"], "default_effort": "low"},
        {"id": "another-model", "efforts": ["low"], "default_effort": "low"},
    ]})
    assert page._chatgpt_status.isHidden()
    assert "refreshed" in page._chatgpt_refresh_button.toolTip().lower()
    assert page._label_edit.text() == "Unsaved name"
    assert page._model_combo.currentText() == "future-model"
    assert page._model_combo.findText("another-model") >= 0
    page._reasoning_mode_combo.setCurrentIndex(page._reasoning_mode_combo.findData("high"))
    assert page.build_current_profile_payload()["reasoning_effort"] == "high"
    page._model_combo.setCurrentText("another-model")
    assert page._reasoning_mode_combo.currentData() == "high"
    assert "unavailable" in page._reasoning_mode_combo.currentText().lower()
    page._reasoning_mode_combo.setCurrentIndex(page._reasoning_mode_combo.findData("low"))
    page._profile_list.setCurrentRow(1)
    assert page._reasoning_mode_combo.findData("enabled") >= 0
    assert page._reasoning_mode_combo.findData("low") == -1
    page._profile_list.setCurrentRow(0)
    assert page._model_combo.currentText() == "another-model"
    assert page._reasoning_mode_combo.currentData() == "low"


def test_open_and_manual_refresh_use_account_worker_without_inference(qtbot, monkeypatch):
    """@brief Opening settings refreshes stale metadata and the button requests a forced refresh."""
    from audiomancer.services import chatgpt_catalog_service, chatgpt_credential_service
    from test_chatgpt_provider import manager

    dialog, page = page_with_profiles(qtbot)
    assert hasattr(page, "_chatgpt_refresh_button"), "Refresh models action is missing"
    account, calls = manager(), []
    monkeypatch.setattr(chatgpt_credential_service, "_MANAGER", account)

    def discover(**kwargs):
        """@brief Capture worker refresh requests and return safe metadata."""
        calls.append(kwargs.get("force", False))
        return {"source": "live", "models": [{"id": "future-model", "efforts": ["low"], "default_effort": "low"}]}

    monkeypatch.setattr(chatgpt_catalog_service, "list_models", discover)
    module = importlib.import_module("audiomancer.ui.controllers.chatgpt_auth_ui_controller")
    controller = module.ChatGPTAuthUiController(page, dialog)
    try:
        controller.start("status")
        qtbot.waitUntil(lambda: not controller.busy)
        assert page._model_combo.findText("future-model") >= 0
        page._chatgpt_refresh_button.click()
        qtbot.waitUntil(lambda: not controller.busy)
        assert calls == [False, True]
        assert page._chatgpt_status.isHidden()

        def failed_discovery(**kwargs):
            """@brief Keep actionable failures visible after removing idle status rows."""
            raise RuntimeError("Synthetic account error")

        monkeypatch.setattr(chatgpt_catalog_service, "list_models", failed_discovery)
        page._chatgpt_refresh_button.click()
        qtbot.waitUntil(lambda: not controller.busy)
        assert not page._chatgpt_status.isHidden()
        assert page._chatgpt_status.text() == "Synthetic account error"
    finally:
        assert controller.shutdown(1000)


def test_backend_round_trip_preserves_explicit_subscription_effort(qtbot):
    """@brief Temporarily choosing a legacy backend cannot silently increase subscription effort."""
    dialog, page = page_with_profiles(qtbot)
    page._reasoning_mode_combo.setCurrentIndex(page._reasoning_mode_combo.findData("low"))
    page._backend_combo.setCurrentText("lmstudio")
    assert page._reasoning_mode_combo.currentData() == "enabled"
    page.build_current_profile_payload()
    page._backend_combo.setCurrentText("chatgpt_subscription")
    assert page._reasoning_mode_combo.currentData() == "low"
    assert page.build_current_profile_payload()["reasoning_effort"] == "low"


def test_subscription_context_follows_selected_model_and_preserves_manual_edits(qtbot):
    """@brief Model selection applies its default, later edits survive refresh/reload, and local stays manual."""
    dialog, page = page_with_profiles(qtbot)
    catalog = {"source": "live", "models": [
        {"id": "gpt-5.5", "efforts": ["low"], "default_effort": "low", "context_window": 272000},
        {"id": "future-model", "efforts": ["low"], "default_effort": "low", "context_window": 1200000},
        {"id": "unknown-model", "efforts": [], "default_effort": None, "context_window": None},
    ]}
    page.apply_subscription_catalog(catalog)
    assert page._context_window_spin.value() == 272000
    page._context_window_spin.setValue(64000)
    page.apply_subscription_catalog(catalog)
    assert page._context_window_spin.value() == 64000
    page._model_combo.setCurrentText("future-model")
    assert page._context_window_spin.value() == 1200000
    assert not page.build_current_profile_payload()["user_overrode_context_window"]
    page._context_window_spin.setValue(96000)
    settings = page.build_settings({})
    page.load_settings(settings)
    assert page._context_window_spin.value() == 96000
    page._model_combo.setCurrentText("gpt-5.5")
    assert page._context_window_spin.value() == 272000
    page._model_combo.setCurrentText("unknown-model")
    assert page._context_window_spin.value() == 272000
    page._profile_list.setCurrentRow(1)
    page._context_window_spin.setValue(32768)
    page._model_combo.setCurrentText("gpt-5.5")
    page.apply_subscription_catalog(catalog)
    assert page._context_window_spin.value() == 32768


# END OF FILE
