#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_cleanup_ui_controller.py
@brief Controller tests for the single Cleanup command.
@details Verifies threaded-runner argument ownership and optional AI profile
         forwarding from the Cleanup page controller.
@author Eng. Dan Dumitru Pasare
@date 2026-07-27
@version 0.1.0
"""

# IMPORTS

from types import SimpleNamespace

from audiomancer.ui.controllers import text_cleanup_ui_controller

# PUBLIC API


def test_extraction_controller_leaves_project_arguments_for_threaded_runner(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify the shared runner supplies Extraction project arguments.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-27
    @version    0.1.0
    """
    captured: dict[str, object] = {}
    window = SimpleNamespace(
        _current_project_root=tmp_path,
        _current_manifest={"source_document": {"original_name": "story.txt"}},
        _settings_payload={"language": "en"},
    )
    monkeypatch.setattr(text_cleanup_ui_controller, "_completed_extraction_available", lambda _root: False)

    def _start(_window, operation_kind, _name, _message, worker, _success, _failure):
        """
        @brief      Capture the Extraction operation and worker callable.
        @param[in]  _window Window test double unused by this helper.
        @param[in]  operation_kind Operation identifier under test.
        @param[in]  _name Operation name unused by this helper.
        @param[in]  _message Progress message unused by this helper.
        @param[in]  worker Worker callable under test.
        @param[in]  _success Success callback unused by this helper.
        @param[in]  _failure Failure callback unused by this helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-27
        @version    0.1.0
        """
        captured["kind"] = operation_kind
        captured["worker"] = worker

    monkeypatch.setattr(text_cleanup_ui_controller, "start_operation", _start)

    text_cleanup_ui_controller.handle_extract_text_requested(window)

    assert captured == {
        "kind": "extraction",
        "worker": text_cleanup_ui_controller.text_extraction_service.extract_text,
    }


def test_cleanup_controller_passes_optional_selected_profile(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Cleanup forwards the optional selected AI profile.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-27
    @version    0.1.0
    """
    captured: dict[str, object] = {}
    window = SimpleNamespace(
        _current_project_root=tmp_path,
        _current_manifest={"source_document": {"original_name": "story.txt"}},
        _settings_payload={
            "language": "en",
            "llm_profiles": [
                {
                    "id": "local",
                    "enabled": True,
                    "model_name": "Qwen3.6-27B",
                    "context_window": 32768,
                    "supports_structured_output": True,
                }
            ],
        },
    )
    monkeypatch.setattr(text_cleanup_ui_controller, "_completed_extraction_available", lambda _root: True)
    monkeypatch.setattr(
        text_cleanup_ui_controller.text_cleanup_service,
        "load_cleanup_document",
        lambda _root: None,
    )

    def _start(_window, operation_kind, _name, _message, worker, _success, _failure):
        """
        @brief      Capture the Cleanup operation and partially bound worker.
        @param[in]  _window Window test double unused by this helper.
        @param[in]  operation_kind Operation identifier under test.
        @param[in]  _name Operation name unused by this helper.
        @param[in]  _message Progress message unused by this helper.
        @param[in]  worker Partially bound Cleanup worker under test.
        @param[in]  _success Success callback unused by this helper.
        @param[in]  _failure Failure callback unused by this helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-27
        @version    0.1.0
        """
        captured["kind"] = operation_kind
        captured["worker"] = worker

    monkeypatch.setattr(text_cleanup_ui_controller, "start_operation", _start)
    text_cleanup_ui_controller.handle_cleanup_requested(window, "local")

    assert captured["kind"] == "cleanup"
    assert captured["worker"].func is text_cleanup_ui_controller.text_cleanup_service.clean_text
    assert captured["worker"].keywords["ai_profile_payload"]["model_name"] == "Qwen3.6-27B"


# END OF FILE
