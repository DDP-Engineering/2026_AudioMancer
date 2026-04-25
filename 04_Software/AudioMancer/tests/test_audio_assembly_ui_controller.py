#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_assembly_ui_controller.py
@brief Audio Assembly UI controller tests for AudioMancer.
@details Verifies confirmation, settings persistence, threaded dispatch, and
         reset synchronization for the Audio Assembly controller.
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.1.0
"""

# IMPORTS

from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import audio_assembly_ui_controller


def test_audio_assembly_ui_controller_persists_settings_and_starts_threaded_operation(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Generate Audio confirms, persists settings, and dispatches a threaded operation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    window = _controller_window(tmp_path)
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        audio_assembly_ui_controller.operation_runner_controller,
        "start_threaded_operation",
        lambda _window, operation_kind, operation_name, initial_message, worker_callable, **kwargs: observed.update(
            {
                "operation_kind": operation_kind,
                "operation_name": operation_name,
                "initial_message": initial_message,
                "worker_callable": worker_callable,
                "set_busy": kwargs["set_busy"],
            }
        ),
    )

    audio_assembly_ui_controller.handle_generate_requested(
        window,
        {
            "output_mode": "time_limit",
            "max_duration_minutes": 45,
            "output_format": "wav",
            "inter_block_silence_ms": 300,
            "inter_chunk_silence_ms": 900,
        },
    )

    manifest = project_workspace_service.load_manifest(window._current_project_root)
    assert observed["operation_kind"] == "audio_assembly"
    assert manifest["audio_assembly_settings"]["output_mode"] == "time_limit"
    assert manifest["audio_assembly_settings"]["max_duration_minutes"] == 45


def test_audio_assembly_ui_controller_reset_clears_artifacts_and_manifest_summary(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Reset Audio Assembly clears artifacts and refreshes the manifest summary.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    window = _controller_window(tmp_path)
    (window._current_project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME).mkdir()
    (window._current_project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME / "audiobook.wav").write_bytes(b"RIFF")
    (window._current_project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME).write_text("{}\n", encoding="utf-8")
    (window._current_project_root / config.AUDIO_ASSEMBLY_STATE_FILE_NAME).write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    audio_assembly_ui_controller.handle_reset_requested(window)

    manifest = project_workspace_service.load_manifest(window._current_project_root)
    assert not (window._current_project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME / "audiobook.wav").exists()
    assert manifest["operations"]["audio_assembly"]["status"] == "not_started"


def _controller_window(tmp_path):
    """
    @brief      Build a minimal main-window test double for controller tests.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     Controller-compatible window namespace.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("AudioAssemblyController", tmp_path)
    return SimpleNamespace(
        _active_operation_kind=None,
        _current_project_root=project_root,
        _current_manifest=manifest,
        _settings_payload={"language": "en"},
        _audio_assembly_page=SimpleNamespace(set_busy=lambda _is_busy: None, set_playback_active=lambda _active: None),
        _audio_assembly_audio_player=SimpleNamespace(
            stop=lambda: None,
            setSource=lambda _source: None,
            play=lambda: None,
        ),
        _audio_assembly_playback_output_key=None,
        show_project_state=lambda project_root, manifest: _set_project_state,
    )


def _set_project_state(project_root, manifest) -> None:
    """
    @brief      Accept project-state refresh calls from controller test doubles.
    @param[in]  project_root Active project root.
    @param[in]  manifest Active manifest payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _ = project_root
    _ = manifest


# END OF FILE
