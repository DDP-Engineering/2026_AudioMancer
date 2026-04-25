#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_blocks_main_window.py
@brief Main-window Audio Blocks integration tests for AudioMancer.
@details Verifies the real Audio Blocks page is loaded and refreshed from
         persisted `80_audio_blocks` artifacts.
@author Eng. Dan Dumitru Pasare
@date 2026-04-23
@version 0.2.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import character_voices_service, project_workspace_service, speech_blocks_service
from audiomancer.ui.main_window import MainWindow
from audiomancer.ui.pages.audio_blocks_page import AudioBlocksPage


def test_main_window_loads_audio_blocks_state_into_real_page(qtbot, tmp_path, default_settings_payload) -> None:
    """
    @brief      Verify the main window refreshes the real Audio Blocks page from persisted workflow artifacts.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying valid baseline settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    project_root = _create_project(tmp_path, "AudioBlocksWindowProject")
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    assert isinstance(window._audio_blocks_page, AudioBlocksPage)
    assert window._audio_blocks_page._speech_block_list.count() == 2
    assert window._audio_blocks_page._source_text_edit.toPlainText() == 'Narration one.\n\n"Alice spoke."'
    assert window._audio_blocks_page._speaker_label.text() == "Speaker: Narrator"
    assert window._audio_blocks_page._progress_bar.value() == 50
    assert "Generated audio: 1/2" in window._audio_blocks_page._status_edit.toPlainText()


def _create_project(tmp_path, name: str):
    """
    @brief      Create one project fixture with persisted Audio Blocks progress.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  name Project display name.
    @return     Tuple containing project root and loaded manifest payload.
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
    manifest["original_language"] = "en"
    manifest["current_stage"] = "speech_blocks_ready"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    manifest["operations"]["speech_blocks"]["status"] = "completed"
    manifest["operations"]["audio_blocks"]["status"] = "running"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": None,
                    "text": "Narration one.",
                    "source_start_line": 1,
                    "source_end_line": 1,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                },
                {
                    "chunk_id": "chunk-0002",
                    "sequence_index": 2,
                    "chapter_label": None,
                    "text": '"Alice spoke."',
                    "source_start_line": 2,
                    "source_end_line": 2,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "speech_block_id": "0001-000001",
                    "sequence_index": 1,
                    "chunk_id": "chunk-0001",
                    "chunk_sequence_index": 1,
                    "source_language": "en",
                    "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
                    "speaker_id": "narrator",
                    "speaker_display_name": "Narrator",
                    "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                    "text": "Narration one.",
                    "warning_flags": [],
                },
                {
                    "speech_block_id": "0002-000002",
                    "sequence_index": 2,
                    "chunk_id": "chunk-0002",
                    "chunk_sequence_index": 2,
                    "source_language": "en",
                    "speaker_kind": speech_blocks_service.SPEAKER_KIND_CHARACTER,
                    "speaker_id": "alice",
                    "speaker_display_name": "Alice",
                    "content_kind": speech_blocks_service.CONTENT_KIND_DIALOGUE,
                    "text": "Hello there.",
                    "warning_flags": [],
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    audio_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    (audio_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "speech_block_id": "0001-000001",
                    "sequence_index": 1,
                    "chunk_id": "chunk-0001",
                    "speaker_id": "narrator",
                    "speaker_display_name": "Narrator",
                    "normalized_speaker_name": "narrator",
                    "text": "Narration one.",
                    "voice_target_id": "narrator",
                    "voice_source_kind": "narrator_sample",
                    "audio_relative_path": "80_audio_blocks/generated_audio/000001_narrator.wav",
                    "metadata_relative_path": "80_audio_blocks/generated_audio/000001_narrator.json",
                    "generated": True,
                    "approved": False,
                    "approved_at": None,
                    "generated_at": "2026-04-23T12:09:00+00:00",
                    "runtime_result_summary": "Narrator ready.",
                    "warning_flags": [],
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (audio_root / config.AUDIO_BLOCKS_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "voice_language": "en",
                "audio_blocks_stage_status": "in_progress",
                "generated_block_count": 1,
                "approved_block_count": 0,
                "total_block_count": 2,
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
                "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
                "status": "running",
                "input_paths": [
                    f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.AUDIO_BLOCKS_INPUT_SPEECH_BLOCKS_FILE_NAME}"
                ],
                "output_paths": [
                    f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.AUDIO_BLOCKS_OUTPUT_FILE_NAME}"
                ],
                "artifact_paths": [
                    f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.AUDIO_BLOCKS_REPORT_FILE_NAME}"
                ],
                "progress_current": 1,
                "progress_total": 2,
                "mode": "tts_generation",
                "started_at": "2026-04-23T12:00:00+00:00",
                "completed_at": None,
                "updated_at": "2026-04-23T12:10:00+00:00",
                "warning_count": 0,
                "metadata": {
                    "voice_language": "en",
                    "input_fingerprint": "stable",
                    "speech_block_count": 2,
                    "generated_block_count": 1,
                    "approved_block_count": 0,
                    "clone_profile_count": 1,
                    "current_phase": "generate_blocks",
                    "current_block_id": "0001-000001",
                },
                "resume_checkpoint": {"next_profile_index": 1, "next_speech_block_index": 1},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root


# END OF FILE
