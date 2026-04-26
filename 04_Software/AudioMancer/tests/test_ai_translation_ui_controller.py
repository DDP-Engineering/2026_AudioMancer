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
@version 0.3.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import project_workspace_service
from audiomancer.ui.controllers import ai_translation_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_ai_translation_ui_controller_start_request_uses_modal_runner(monkeypatch, qtbot, tmp_path) -> None:
    project_root, manifest = _create_project(tmp_path, "TranslationControllerProject")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        ai_translation_ui_controller.ai_translation_service,
        "start_or_continue_translation",
        lambda _project_root, _manifest, profile, target_language, progress_callback=None, cancel_requested=None: {
            "target_language": target_language,
            "translation_profile_id_last_used": profile["id"],
            "translation_stage_status": "completed",
            "translated_chunk_count": 1,
            "approved_chunk_count": 0,
            "total_chunk_count": 1,
            "updated_at": "2026-04-07T12:02:00+00:00",
            "warnings": [],
        },
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
    assert result["translation_stage_status"] == "completed"


def test_ai_translation_ui_controller_reset_clears_translation_state(monkeypatch, qtbot, tmp_path) -> None:
    project_root, _manifest = _create_project(tmp_path, "TranslationResetControllerProject")
    translation_root = project_root / "30_translation"
    translation_root.mkdir(parents=True, exist_ok=True)
    (translation_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text("[]\n", encoding="utf-8")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        ai_translation_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: ai_translation_ui_controller.QMessageBox.StandardButton.Yes,
    )

    ai_translation_ui_controller.handle_reset_translation_requested(window)

    assert window._current_manifest is not None
    assert window._current_manifest["operations"]["translation"]["status"] == "not_started"
    translated_payload = json.loads((project_root / config.TRANSLATED_CHUNKS_FILE_NAME).read_text(encoding="utf-8"))
    assert translated_payload[0]["translated_text"] == ""


def test_sync_manifest_after_translation_advances_only_after_full_approval(qtbot, tmp_path) -> None:
    """
    @brief      Verify translation manifest stage advances to character discovery only after every chunk is approved.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    project_root, _manifest = _create_project(tmp_path, "TranslationApprovalControllerProject")
    translation_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    translation_root.mkdir(parents=True, exist_ok=True)
    (translation_root / config.TRANSLATION_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
                "status": "completed",
                "output_paths": [f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.TRANSLATED_CHUNKS_FILE_NAME}"],
                "artifact_paths": [
                    f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.TRANSLATION_REPORT_FILE_NAME}"
                ],
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
            "translation_stage_status": "completed",
            "translated_chunk_count": 1,
            "approved_chunk_count": 0,
            "total_chunk_count": 1,
        },
    )
    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "translation_ready"

    ai_translation_ui_controller._sync_manifest_after_translation(
        window,
        {
            "translation_stage_status": "completed",
            "translated_chunk_count": 1,
            "approved_chunk_count": 1,
            "total_chunk_count": 1,
        },
    )
    assert window._current_manifest["current_stage"] == "character_discovery_ready"


def _create_project(tmp_path, name: str):
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
