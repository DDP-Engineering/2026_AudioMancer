#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_translation_ui_controller.py
@brief AI Translation UI controller tests for AudioMancer.
@details Verifies the translation controller dispatches workflow actions and
         persists reset behavior through the main window shell.
@author Eng. Dan Dumitru Pasare
@date 2026-04-22
@version 0.5.1
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import ai_translation_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_ai_translation_ui_controller_start_request_uses_modal_runner(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate ai translation ui controller start request uses modal runner.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, manifest = _create_project(tmp_path, "TranslationControllerProject")
    window = _build_window(qtbot, project_root)

    def fake_start_translation(
        _project_root,
        _manifest,
        profile,
        target_language,
        progress_callback=None,
        cancel_requested=None,
        additional_translation_instructions=None,
    ):
        _ = progress_callback
        _ = cancel_requested
        return {
            "target_language": target_language,
            "translation_profile_id_last_used": profile["id"],
            "translation_stage_status": "translated",
            "translated_chunk_count": 1,
            "approved_chunk_count": 0,
            "total_chunk_count": 1,
            "updated_at": "2026-04-07T12:02:00+00:00",
            "warnings": [],
            "additional_translation_instructions": additional_translation_instructions,
        }

    monkeypatch.setattr(
        ai_translation_ui_controller.ai_translation_service,
        "start_or_continue_translation",
        fake_start_translation,
    )
    monkeypatch.setattr(
        ai_translation_ui_controller,
        "prompt_ai_translation_instructions",
        lambda _window, _language: "Keep dialogue register formal.",
    )
    start_calls = []
    monkeypatch.setattr(
        ai_translation_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )

    ai_translation_ui_controller.handle_start_translation_requested(window, "profile-1")

    assert len(start_calls) == 1
    result = start_calls[0]["worker_callable"](
        project_root,
        dict(manifest),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )
    assert result["translation_stage_status"] == "translated"
    assert result["additional_translation_instructions"] == "Keep dialogue register formal."


def test_ai_translation_ui_controller_reset_clears_translation_state(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Validate ai translation ui controller reset clears translation state.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "TranslationResetControllerProject")
    (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.NARRATOR_PROFILE_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.CHARACTER_PROFILE_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text("[]\n", encoding="utf-8")
    window = _build_window(qtbot, project_root)
    assert window._current_manifest is not None
    window._current_manifest["narrator_profile_name"] = "Warm Narrator"
    window._current_manifest["narrator_language"] = "fr"
    window._current_manifest["operations"]["narrator_definition"]["status"] = "completed"
    window._current_manifest["operations"]["character_discovery"]["status"] = "completed"
    window._current_manifest["operations"]["speech_blocks"]["status"] = "completed"
    monkeypatch.setattr(
        ai_translation_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: ai_translation_ui_controller.QMessageBox.StandardButton.Yes,
    )

    ai_translation_ui_controller.handle_reset_translation_requested(window)

    assert window._current_manifest is not None
    assert window._current_manifest["operations"]["translation"]["status"] == "not_started"
    assert window._current_manifest["operations"]["narrator_definition"]["status"] == "completed"
    assert window._current_manifest["operations"]["character_discovery"]["status"] == "not_started"
    assert window._current_manifest["operations"]["speech_blocks"]["status"] == "not_started"
    assert not (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).exists()
    assert (project_root / config.NARRATOR_PROFILE_FILE_NAME).is_file()
    assert not (project_root / config.CHARACTER_PROFILE_FILE_NAME).exists()
    assert not (project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).exists()
    assert window._current_manifest["narrator_profile_name"] == "Warm Narrator"
    assert window._current_manifest["narrator_language"] == "fr"


def test_sync_manifest_after_translation_advances_only_after_full_approval(qtbot, tmp_path) -> None:
    """
    @brief      Verify translation manifest stage advances to character discovery only after every chunk is approved.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.3.0
    """
    project_root, _manifest = _create_project(tmp_path, "TranslationApprovalControllerProject")
    translation_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    translation_root.mkdir(parents=True, exist_ok=True)
    (translation_root / config.TRANSLATION_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "status": "completed",
                "progress_current": 1,
                "progress_total": 1,
                "mode": "ai_assisted",
                "started_at": "2026-04-22T12:00:00+00:00",
                "completed_at": "2026-04-22T12:05:00+00:00",
                "updated_at": "2026-04-22T12:05:00+00:00",
                "warning_count": 0,
                "metadata": {"log_relative_path": "log_ai_translation_20260422.log"},
                "resume_checkpoint": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    window = _build_window(qtbot, project_root)

    ai_translation_ui_controller._sync_manifest_after_translation(
        window,
        {
            "translation_stage_status": "translated",
            "translated_chunk_count": 1,
            "approved_chunk_count": 0,
            "total_chunk_count": 1,
        },
    )
    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "translation_ready"
    assert set(window._current_manifest["operations"]["translation"]) == {
        "status",
        "progress_current",
        "progress_total",
        "mode",
        "warning_count",
    }

    ai_translation_ui_controller._sync_manifest_after_translation(
        window,
        {
            "translation_stage_status": "approved",
            "translated_chunk_count": 1,
            "approved_chunk_count": 1,
            "total_chunk_count": 1,
        },
    )
    assert window._current_manifest["current_stage"] == "character_discovery_ready"


def test_sync_manifest_after_translation_resets_downstream_when_approval_is_lost(qtbot, tmp_path) -> None:
    """
    @brief      Verify unapproved translation state clears downstream artifacts and manifest metadata.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    project_root, _manifest = _create_project(tmp_path, "TranslationDownstreamResetProject")
    (project_root / config.TRANSLATION_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "status": "translated",
                "progress_current": 1,
                "progress_total": 1,
                "mode": "ai_assisted",
                "started_at": "2026-04-26T12:00:00+00:00",
                "completed_at": None,
                "updated_at": "2026-04-26T12:05:00+00:00",
                "warning_count": 0,
                "metadata": {"log_relative_path": "log_ai_translation_20260426.log"},
                "resume_checkpoint": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / config.CHARACTER_PROFILE_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.NARRATOR_PROFILE_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text("[]\n", encoding="utf-8")
    window = _build_window(qtbot, project_root)
    assert window._current_manifest is not None
    window._current_manifest["narrator_profile_name"] = "Warm Narrator"
    window._current_manifest["narrator_language"] = "fr"
    window._current_manifest["operations"]["narrator_definition"]["status"] = "completed"
    window._current_manifest["operations"]["character_discovery"]["status"] = "completed"
    window._current_manifest["operations"]["speech_blocks"]["status"] = "completed"

    ai_translation_ui_controller._sync_manifest_after_translation(
        window,
        {
            "translation_stage_status": "translated",
            "translated_chunk_count": 1,
            "approved_chunk_count": 0,
            "total_chunk_count": 1,
        },
    )

    assert window._current_manifest["current_stage"] == "translation_ready"
    assert window._current_manifest["operations"]["narrator_definition"]["status"] == "completed"
    assert window._current_manifest["operations"]["character_discovery"]["status"] == "not_started"
    assert window._current_manifest["operations"]["speech_blocks"]["status"] == "not_started"
    assert (project_root / config.NARRATOR_PROFILE_FILE_NAME).is_file()
    assert not (project_root / config.CHARACTER_PROFILE_FILE_NAME).exists()
    assert not (project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).exists()
    assert window._current_manifest["narrator_profile_name"] == "Warm Narrator"
    assert window._current_manifest["narrator_language"] == "fr"


def _create_project(tmp_path, name: str):
    """
    @brief      Provide the create project test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-07T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [config.CHUNK_ARTIFACT_FILE_NAME]
    manifest["target_language"] = "ro"
    manifest["selected_voice_language"] = "ro"
    manifest["project_options_locked"] = True
    project_workspace_service.save_manifest(manifest, project_root)
    chunk_root = project_root
    chunk_root.mkdir(parents=True, exist_ok=True)
    (chunk_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": None,
                    "text": "Original one",
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
    return project_root, manifest


def _build_window(qtbot, project_root):
    """
    @brief      Provide the build window test helper.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-02
    @version    0.1.0
    """
    settings_payload = {
        "language": "en",
        "ui_text_scale": "normal",
        "play_completion_beep": False,
        "llm_profiles": [
            {
                "id": "profile-1",
                "label": "Translation Profile",
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
    }
    window = MainWindow(settings_payload=settings_payload)
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    return window


# END OF FILE
