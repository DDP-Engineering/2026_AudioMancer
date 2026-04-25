#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_speech_blocks_ui_controller.py
@brief Speech Blocks UI controller tests for AudioMancer.
@details Verifies confirmation gating and explicit destructive reset behavior for
         the Speech Blocks workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-21
@version 0.3.0
"""

# IMPORTS

import json
from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import character_voices_service, project_workspace_service
from audiomancer.ui.controllers import speech_blocks_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_speech_blocks_ui_controller_requires_confirmation_before_starting(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify Speech Blocks generation stops when the operator declines the confirmation popup.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    project_root = _create_project(tmp_path, "SpeechBlocksControllerConfirm")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "resolve_source_chunks",
        lambda *_args, **_kwargs: {
            "selected_source_language": "en",
            "source_kind": "original",
            "source_chunks": [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Narration."}],
        },
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    start_calls = []
    monkeypatch.setattr(
        speech_blocks_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )

    speech_blocks_ui_controller.handle_generate_requested(window, "profile-1")

    assert start_calls == []


def test_speech_blocks_ui_controller_edit_start_does_not_refresh_page(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify starting a block edit clears warnings without reloading the Speech Blocks page.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    project_root = tmp_path / "SpeechBlocksEditStart"
    project_root.mkdir()
    update_calls = []
    window = SimpleNamespace(
        _current_project_root=project_root,
        _current_manifest={"current_stage": "character_voices_ready"},
        show_project_state=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected refresh")),
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "load_speech_blocks",
        lambda _project_root: [
            {
                "speech_block_id": "0001-000001",
                "speaker_id": "alice",
                "content_kind": "dialogue",
                "text": "Hello.",
            }
        ],
    )
    monkeypatch.setattr(
        speech_blocks_ui_controller.speech_blocks_service,
        "update_speech_block",
        lambda *args: update_calls.append(args),
    )

    speech_blocks_ui_controller.handle_edit_started(window, "0001-000001")

    assert update_calls == [(project_root, "0001-000001", "alice", "dialogue", "Hello.")]


def test_speech_blocks_ui_controller_explicit_reset_clears_speech_blocks_and_downstream(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify explicit Speech Blocks reset clears Speech Blocks and downstream folders.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    project_root = _create_project(tmp_path, "SpeechBlocksControllerRerun")
    manifest = project_workspace_service.load_manifest(project_root)
    manifest["current_stage"] = "audio_assembly_ready"
    manifest["operations"]["speech_blocks"]["status"] = "completed"
    manifest["operations"]["audio_blocks"]["status"] = "completed"
    manifest["operations"]["audio_assembly"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    for folder_name in (
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
    ):
        (project_root / folder_name / "artifact.txt").write_text("stale", encoding="utf-8")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        speech_blocks_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(speech_blocks_ui_controller.misc_ui_controller, "show_message", lambda *args, **kwargs: None)

    speech_blocks_ui_controller.handle_reset_generation_requested(window)

    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "character_voices_ready"
    assert window._current_manifest["operations"]["speech_blocks"]["status"] == "not_started"
    assert window._current_manifest["operations"]["audio_blocks"]["status"] == "not_started"
    assert window._current_manifest["operations"]["audio_assembly"]["status"] == "not_started"
    assert not (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / "artifact.txt").exists()
    assert not (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / "artifact.txt").exists()
    assert not (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / "artifact.txt").exists()


def _create_project(tmp_path, name: str):
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-21T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["original_language"] = "en"
    manifest["current_stage"] = "character_voices_ready"
    manifest["operations"]["chunking"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": None,
                    "text": "Narration.",
                    "source_start_line": 1,
                    "source_end_line": 1,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root


def _build_window(qtbot, project_root):
    window = MainWindow(settings_payload=_settings_payload())
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    return window


def _settings_payload() -> dict[str, object]:
    return {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [
            {
                "id": "profile-1",
                "label": "Speech Blocks Profile",
                "backend_kind": "lmstudio",
                "base_url": "http://127.0.0.1:1234",
                "api_key": "",
                "model_name": "qwen3-8b",
                "context_window": 4096,
                "max_output_tokens": 512,
                "request_timeout_seconds": 30,
                "temperature": 0.2,
                "supports_structured_output": False,
                "enabled": True,
            }
        ],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_translation_profile_id": None,
        "default_speech_blocks_profile_id": "profile-1",
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": None,
        "tts_runtime_base_url": "http://127.0.0.1:8059",
        "tts_runtime_api_key": "",
        "tts_runtime_probe_succeeded": False,
        "tts_runtime_probe_message": "",
        "tts_runtime_discovered_models": [],
        "tts_runtime_active_model_id": None,
        "tts_runtime_device_diagnostics": {},
        "tts_audio_preview_timeout_seconds": 60,
        "tts_audio_generation_timeout_seconds": 300,
    }


# END OF FILE
