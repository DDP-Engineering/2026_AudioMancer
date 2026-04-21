#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_speech_blocks_state_service.py
@brief Focused Speech Blocks state-service tests for AudioMancer.
@details Verifies Speech Blocks profile selection, persisted output loading,
         and operator note rendering for resumable and warning-bearing state.
@author Eng. Dan Dumitru Pasare
@date 2026-04-21
@version 0.1.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import character_voices_service, project_workspace_service, speech_blocks_state_service


def test_build_speech_blocks_profile_state_prefers_default_enabled_profile() -> None:
    """
    @brief      Verify Speech Blocks profile state prefers the configured default enabled profile.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    profile_state = speech_blocks_state_service.build_speech_blocks_profile_state(
        {
            "llm_profiles": [
                {"id": "profile-1", "label": "Profile 1", "enabled": True},
                {"id": "profile-2", "label": "Profile 2", "enabled": True},
            ],
            "default_speech_blocks_profile_id": "profile-2",
        }
    )

    assert profile_state["entries"] == [("Profile 1", "profile-1"), ("Profile 2", "profile-2")]
    assert profile_state["selected_profile_id"] == "profile-2"


def test_build_speech_blocks_state_loads_persisted_blocks_and_summary(tmp_path) -> None:
    """
    @brief      Verify Speech Blocks page state loads persisted source chunks, output blocks, and summary notes.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksState")
    character_voices_service.save_selected_voice_language(project_root, "en")
    speech_blocks_root = project_root / config.SPEECH_BLOCKS_FOLDER_NAME
    (speech_blocks_root / "input_source_chunks.json").write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "text": 'Narration. "Hello there."',
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (speech_blocks_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "speech_block_id": "speech-block-0001",
                    "sequence_index": 1,
                    "chunk_id": "chunk-0001",
                    "chunk_sequence_index": 1,
                    "source_language": "en",
                    "speaker_kind": "narrator",
                    "speaker_id": "narrator",
                    "speaker_display_name": "Narrator",
                    "content_kind": "narration",
                    "text": "Narration.",
                    "warning_flags": [],
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (speech_blocks_root / config.SPEECH_BLOCKS_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "source_language": "en",
                "source_kind": "original",
                "ai_profile_id": "profile-1",
                "speech_blocks_stage_status": "completed",
                "processed_chunk_count": 1,
                "total_chunk_count": 1,
                "speech_block_count": 1,
                "warning_count": 0,
                "warnings": [],
                "updated_at": "2026-04-21T12:10:00+00:00",
                "token_usage": {
                    "input_tokens": 30,
                    "output_tokens": 10,
                    "total_tokens": 40,
                    "usage_available": True,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (speech_blocks_root / config.OPERATION_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.SPEECH_BLOCKS_FOLDER_NAME,
                "status": "completed",
                "input_paths": [f"{config.SPEECH_BLOCKS_FOLDER_NAME}/input_source_chunks.json"],
                "output_paths": [f"{config.SPEECH_BLOCKS_FOLDER_NAME}/{config.SPEECH_BLOCKS_OUTPUT_FILE_NAME}"],
                "artifact_paths": [f"{config.SPEECH_BLOCKS_FOLDER_NAME}/{config.SPEECH_BLOCKS_REPORT_FILE_NAME}"],
                "progress_current": 1,
                "progress_total": 1,
                "mode": "ai_assisted",
                "started_at": "2026-04-21T12:00:00+00:00",
                "completed_at": "2026-04-21T12:10:00+00:00",
                "updated_at": "2026-04-21T12:10:00+00:00",
                "warning_count": 0,
                "metadata": {"ai_profile_id": "profile-1", "source_language": "en"},
                "resume_checkpoint": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    state = speech_blocks_state_service.build_speech_blocks_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
        {
            "llm_profiles": [{"id": "profile-1", "label": "Speech Blocks Profile", "enabled": True}],
            "default_speech_blocks_profile_id": "profile-1",
        },
    )

    assert state["selected_profile_id"] == "profile-1"
    assert state["stage_status"] == "completed"
    assert state["processed_chunk_count"] == 1
    assert state["total_chunk_count"] == 2
    assert state["speech_blocks"][0]["speech_block_id"] == "speech-block-0001"
    assert any("Generated 1 speech blocks from 1/2 chunks." in note for note in state["notes"])
    assert any("Input tokens: 30 | Output tokens: 10 | Total: 40" in note for note in state["notes"])


def test_build_speech_blocks_notes_show_resume_and_warning_entries() -> None:
    """
    @brief      Verify Speech Blocks notes surface warning entries and resumable failed state.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    notes = speech_blocks_state_service.build_speech_blocks_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        source_chunks=[
            {"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Chunk one"},
            {"chunk_id": "chunk-0002", "sequence_index": 2, "text": "Chunk two"},
        ],
        report={
            "speech_blocks_stage_status": "in_progress",
            "processed_chunk_count": 1,
            "speech_block_count": 2,
            "warning_count": 1,
            "warnings": [{"chunk_id": "chunk-0002", "reason": "ambiguous speaker"}],
            "token_usage": {
                "input_tokens": 12,
                "output_tokens": 3,
                "total_tokens": 15,
                "usage_available": True,
            },
        },
        operation_state={
            "status": "failed",
            "progress_current": 1,
            "progress_total": 2,
            "metadata": {},
        },
        has_ai_profiles=True,
        language="en",
    )

    assert any("Generated 2 speech blocks from 1/2 chunks." in note for note in notes)
    assert any("chunk-0002: ambiguous speaker" in note for note in notes)
    assert any("was not finalized" in note for note in notes)


def _create_chunked_project(tmp_path, name: str):
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-21T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["original_language"] = "en"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["current_stage"] = "character_voices_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / config.CHUNKING_FOLDER_NAME / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": None,
                    "text": 'Narration. "Hello there."',
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
                    "text": 'Maria smiled. "Welcome."',
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
    return project_root, project_workspace_service.load_manifest(project_root)


# END OF FILE
