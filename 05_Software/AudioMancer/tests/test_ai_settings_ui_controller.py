#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_settings_ui_controller.py
@brief Focused persistence and connection coverage for the AI Settings controller.
@details Verifies dialog persistence and normalized probe feedback paths.
"""

# IMPORTS

from types import SimpleNamespace
from unittest.mock import Mock

from audiomancer.ui.controllers import ai_settings_ui_controller


class _ReadFailureResponse:
    """@brief Minimal response that fails specifically while reading its body."""

    def __enter__(self):
        """@brief Return this response from the context manager."""
        return self

    def __exit__(self, exception_type, exception, traceback) -> bool:
        """@brief Leave the response context without suppressing exceptions."""
        return False

    def read(self) -> bytes:
        """
        @brief      Simulate a transport reset while reading the response body.
        @return     Never returns.
        @exception  ConnectionResetError Always raised.
        """
        raise ConnectionResetError("backend reset")


def test_apply_ai_settings_persists_reloads_and_refreshes_window(monkeypatch) -> None:
    """
    @brief      Verify Apply persists and reloads settings, refreshes the current page, and leaves the dialog open.
    @details    REQ-FUNC-d335d502.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    merged_settings = {"ui": {"language": "en"}, "ai_profiles": [{"id": "local"}]}
    persisted_settings = {**merged_settings, "persisted": True}
    page = SimpleNamespace(build_settings=Mock(return_value=merged_settings))
    window = SimpleNamespace(
        _ai_settings_page=page,
        _ai_settings_dialog=SimpleNamespace(close=Mock()),
        _settings_payload={"previous": True},
        _current_project_root="project-root",
        _current_manifest={"project_name": "Demo"},
        refresh_current_page_state=Mock(),
    )
    save_settings = Mock()
    show_message = Mock()
    monkeypatch.setattr(ai_settings_ui_controller.settings_service, "save_settings", save_settings)
    monkeypatch.setattr(ai_settings_ui_controller.settings_service, "load_settings", lambda: persisted_settings)
    monkeypatch.setattr(ai_settings_ui_controller.misc_ui_controller, "show_message", show_message)

    ai_settings_ui_controller.apply_ai_settings_from_dialog(window)

    save_settings.assert_called_once_with(merged_settings)
    assert window._settings_payload == persisted_settings
    window.refresh_current_page_state.assert_called_once_with()
    window._ai_settings_dialog.close.assert_not_called()
    show_message.assert_called_once()


def test_apply_ai_settings_refreshes_only_the_current_page(monkeypatch) -> None:
    """
    @brief      Verify applying AI Settings refreshes only the current page, not the project summary or export scan.
    @details    REQ-NFR-dfe9ab8a.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    page = SimpleNamespace(build_settings=Mock(return_value={"ai_profiles": []}))
    window = SimpleNamespace(
        _ai_settings_page=page,
        _ai_settings_dialog=SimpleNamespace(close=Mock()),
        _settings_payload={"previous": True},
        _current_project_root="project-root",
        _current_manifest={"project_name": "Demo"},
        refresh_current_page_state=Mock(),
        show_project_state=Mock(),
    )
    monkeypatch.setattr(ai_settings_ui_controller.settings_service, "save_settings", Mock())
    monkeypatch.setattr(ai_settings_ui_controller.settings_service, "load_settings", lambda: {"persisted": True})
    monkeypatch.setattr(ai_settings_ui_controller.misc_ui_controller, "show_message", Mock())

    ai_settings_ui_controller.apply_ai_settings_from_dialog(window)

    window.refresh_current_page_state.assert_called_once_with()
    window.show_project_state.assert_not_called()


def test_connect_ai_profile_displays_failure_popup_for_read_transport_error(monkeypatch) -> None:
    """
    @brief      Verify read-phase transport failure reaches the normal controller warning path.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    profile_payload = {
        "backend_kind": "openai_compatible",
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key": "secret",
        "model_name": "model-a",
    }
    page = SimpleNamespace(
        build_current_profile_payload=Mock(return_value=profile_payload),
        apply_probe_result=Mock(),
    )
    window = SimpleNamespace(
        _ai_settings_page=page,
        _ai_settings_dialog=object(),
        _settings_payload={"language": "en"},
    )
    warning = Mock()
    information = Mock()
    monkeypatch.setattr(
        ai_settings_ui_controller.ai_backend_service.request,
        "urlopen",
        lambda http_request, timeout: _ReadFailureResponse(),
    )
    monkeypatch.setattr(ai_settings_ui_controller.QMessageBox, "warning", warning)
    monkeypatch.setattr(ai_settings_ui_controller.QMessageBox, "information", information)

    ai_settings_ui_controller.connect_ai_profile_from_dialog(window)

    applied_result = page.apply_probe_result.call_args.args[0]
    assert applied_result["success"] is False
    warning.assert_called_once()
    information.assert_not_called()


# END OF FILE
