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
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import (
    audio_blocks_service,
    character_voices_service,
    project_workspace_service,
    speech_blocks_service,
)
from audiomancer.ui.main_window import MainWindow
from audiomancer.ui.pages.audio_blocks_page import AudioBlocksPage
from chunking_test_support import build_chunking_document


def test_main_window_loads_audio_blocks_state_into_real_page(qtbot, tmp_path, default_settings_payload) -> None:
    """
    @brief      Verify the main window refreshes the real Audio Blocks page from persisted workflow artifacts.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying valid baseline settings.
    @return     None.
    @exception  None
    """
    project_root = _create_project(tmp_path, "AudioBlocksWindowProject")
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    window.set_current_page("audio_blocks")

    assert isinstance(window._audio_blocks_page, AudioBlocksPage)
    assert window._audio_blocks_page._speech_block_list.count() == 2
    assert window._audio_blocks_page._source_text_edit.toPlainText() == 'Narration one.\n\n"Alice spoke."'
    assert window._audio_blocks_page._speaker_label.text() == "Speaker: Narrator"
    assert window._audio_blocks_page._progress_bar.value() == 50
    assert "Generated audio: 1/2" in window._audio_blocks_page.operation_status_text()


def _create_project(tmp_path, name: str):
    """
    @brief      Create one project fixture with persisted Audio Blocks progress.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  name Project display name.
    @return     Tuple containing project root and loaded manifest payload.
    @exception  None
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
            build_chunking_document(
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
                ]
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_speech_blocks_fixture_document(
        project_root,
            [
                {
                    "speech_block_id": "0001-000001",
                    "sequence_index": 1,
                    "chunk_id": "chunk-0001",
                    "source_language": "en",
                    "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
                    "speaker_id": "narrator",
                    "speaker_display_name": "Narrator",
                    "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                    "text": "Narration one.",
                    "approved": True,
                    "approved_at": "2026-04-23T12:02:00+00:00",
                    "warning_flags": [],
                },
                {
                    "speech_block_id": "0002-000001",
                    "sequence_index": 1,
                    "chunk_id": "chunk-0002",
                    "source_language": "en",
                    "speaker_kind": speech_blocks_service.SPEAKER_KIND_CHARACTER,
                    "speaker_id": "alice",
                    "speaker_display_name": "Alice",
                    "content_kind": speech_blocks_service.CONTENT_KIND_DIALOGUE,
                    "text": "Hello there.",
                    "approved": True,
                    "approved_at": "2026-04-23T12:03:00+00:00",
                    "warning_flags": [],
                },
            ],
    )
    audio_blocks_service.write_audio_blocks_document(
        project_root,
        {
            "status": "in_progress",
            "voice_language": "en",
            "input_fingerprint": "stable",
            "checkpoint": {
                "run_token": "2026-04-23T12:00:00+00:00",
                "current_phase": "generate_blocks",
                "current_block_id": None,
                "next_speech_block_index": 1,
                "next_split_part_index": 0
            },
            "blocks": [
                {
                    "speech_block_id": "0001-000001",
                    "voice_target_id": "narrator",
                    "generated": True,
                    "approved": False,
                    "audio_can_play": True,
                    "audio_duration_seconds": None,
                    "generation_fingerprint": None
                }
            ]
        },
    )
    return project_root



def _write_speech_blocks_fixture_document(project_root, blocks, *, status: str = "completed"):
    """Persist a valid single Speech Blocks document wrapping fixture blocks."""
    speech_blocks_service.write_speech_blocks_document(
        project_root,
        {
            "status": status,
            "source": {"kind": "original", "language": "en", "fingerprint": "sb-fixture-fingerprint"},
            "ai_profile_id": "profile-1",
            "instructions": "",
            "scene_ambience": {"enabled": False},
            "response_contract": "direct_blocks",
            "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "usage_available": False},
            "budget_metadata": {},
            "checkpoint": {
                "next_chunk_index": 1,
                "run_token": "2026-04-23T12:00:00+00:00",
                "log_relative_path": "log_ai_speech_blocks_20260423T120000Z.log",
                "source_snapshot_fingerprint": "sb-fixture-fingerprint",
                "source_language": "en",
                "ai_profile_id": "profile-1",
                "additional_speech_block_instructions_fingerprint": "",
                "speech_blocks_response_contract": "direct_blocks",
            },
            "failure": None,
            "blocks": list(blocks),
        },
    )


def _read_speech_blocks_fixture_blocks(project_root):
    """Return the persisted Speech Blocks document blocks for fixture mutation."""
    document = speech_blocks_service.load_speech_blocks_document(project_root)
    return document["blocks"] if document else []

# END OF FILE
