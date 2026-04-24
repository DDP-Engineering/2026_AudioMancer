#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_blocks_upstream_invalidation.py
@brief Upstream Audio Blocks invalidation regression tests for AudioMancer.
@details Verifies narrator-side upstream changes clear persisted Audio Blocks
         progress only after confirmation.
@author Eng. Dan Dumitru Pasare
@date 2026-04-23
@version 0.1.0
"""

# IMPORTS

import json

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import narrator_definition_service, project_workspace_service
from audiomancer.ui.controllers import narator_voice_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_selected_narrator_change_invalidates_persisted_audio_blocks_after_confirmation(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify selecting a different narrator sample clears persisted Audio Blocks after confirmation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying valid baseline settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    project_root = _create_project(tmp_path, "AudioBlocksNarratorInvalidation")
    custom_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Warm Narrator",
        "English",
        "Prompt text.",
        "Preview text.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        custom_profile,
        "Preview text.",
        {
            "generation_mode": "definition",
            "source_model_id": "qwen-designer",
            "language": "en",
        },
        "Custom narrator ready.",
        b"RIFF-custom",
    )
    _seed_audio_blocks_artifacts(project_root)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    monkeypatch.setattr(
        narator_voice_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        narator_voice_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args, **kwargs: None,
    )

    narator_voice_ui_controller.handle_select_profile_requested(window, custom_profile["profile_id"])

    updated_manifest = project_workspace_service.load_manifest(project_root)
    assert updated_manifest["current_stage"] == "narrator_definition_ready"
    assert updated_manifest["operations"]["audio_blocks"]["status"] == "not_started"
    assert not (project_root / config.AUDIO_BLOCKS_FOLDER_NAME / "artifact.txt").exists()


def _create_project(tmp_path, name: str):
    """
    @brief      Create one project fixture past the Audio Blocks stage.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  name Project display name.
    @return     Project root folder.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-23T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "audio_assembly_ready"
    manifest["narrator_profile_name"] = "Vivian"
    manifest["narrator_language"] = "English"
    manifest["operations"]["audio_blocks"]["status"] = "completed"
    manifest["operations"]["audio_assembly"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    default_profile = narrator_definition_service.load_profiles(project_root)[0]
    narrator_definition_service.store_profile_sample(
        project_root,
        default_profile,
        "Preview text.",
        {
            "generation_mode": "custom_voice",
            "source_model_id": "qwen-custom",
            "language": "en",
        },
        "Default narrator ready.",
        b"RIFF-default",
    )
    narrator_definition_service.select_narrator_profile(project_root, default_profile["profile_id"], "en")
    narrator_definition_service.copy_selected_narrator_sample(project_root, default_profile["profile_id"])
    return project_root


def _seed_audio_blocks_artifacts(project_root) -> None:
    """
    @brief      Write persisted Audio Blocks artifacts that upstream changes can invalidate.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    audio_root = project_root / config.AUDIO_BLOCKS_FOLDER_NAME
    audio_root.mkdir(parents=True, exist_ok=True)
    (audio_root / "artifact.txt").write_text("stale", encoding="utf-8")
    (audio_root / config.AUDIO_BLOCKS_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "voice_language": "en",
                "audio_blocks_stage_status": "completed",
                "generated_block_count": 1,
                "approved_block_count": 1,
                "total_block_count": 1,
                "warning_count": 0,
                "warnings": [],
                "updated_at": "2026-04-23T12:10:00+00:00",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (audio_root / config.OPERATION_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.AUDIO_BLOCKS_FOLDER_NAME,
                "status": "completed",
                "input_paths": [],
                "output_paths": [],
                "artifact_paths": [f"{config.AUDIO_BLOCKS_FOLDER_NAME}/{config.AUDIO_BLOCKS_REPORT_FILE_NAME}"],
                "progress_current": 1,
                "progress_total": 1,
                "mode": "tts_generation",
                "started_at": "2026-04-23T12:00:00+00:00",
                "completed_at": "2026-04-23T12:10:00+00:00",
                "updated_at": "2026-04-23T12:10:00+00:00",
                "warning_count": 0,
                "metadata": {"input_fingerprint": "stable"},
                "resume_checkpoint": {"next_profile_index": 1, "next_speech_block_index": 1},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# END OF FILE
