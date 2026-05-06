#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_blocks_state_service.py
@brief Focused Audio Blocks state-service tests for AudioMancer.
@details Verifies persisted Audio Blocks state rendering, resumable progress
         notes, and ready-for-assembly summaries.
@author Eng. Dan Dumitru Pasare
@date 2026-04-23
@version 0.5.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import (
    audio_blocks_state_service,
    character_voices_service,
    operation_runtime_service,
    project_workspace_service,
    speech_blocks_service,
    tts_budget_service,
)


def test_build_audio_blocks_state_surfaces_progress_current_block_and_full_source_text(tmp_path) -> None:
    """
    @brief      Verify Audio Blocks page state exposes reconstructed source text, current block details, and progress.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.3.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksStateRunning")
    audio_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    audio_root.mkdir(parents=True, exist_ok=True)
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
                    "generated_at": "2026-04-23T12:01:00+00:00",
                    "split_audio_seconds_budget": 10.0,
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
                "updated_at": "2026-04-23T12:01:00+00:00",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (audio_root / config.AUDIO_BLOCKS_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
                "status": "running",
                "input_paths": [
                    f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.SPEECH_BLOCKS_OUTPUT_FILE_NAME}"
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
                "updated_at": "2026-04-23T12:01:00+00:00",
                "warning_count": 0,
                "metadata": {
                    "voice_language": "en",
                    "input_fingerprint": "stable",
                    "speech_block_count": 2,
                    "generated_block_count": 1,
                    "approved_block_count": 0,
                    "clone_profile_count": 2,
                    "prompt_count": 2,
                    "reused_prompt_count": 1,
                    "regenerated_prompt_count": 1,
                    "current_phase": "prepare_prompts",
                    "current_block_id": "0002-000001",
                },
                "resume_checkpoint": {"next_profile_index": 2, "next_speech_block_index": 1},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    state = audio_blocks_state_service.build_audio_blocks_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
    )

    assert state["full_source_text"] == 'Narration one.\n\n"Alice spoke."'
    assert state["current_block_id"] == "0002-000001"
    assert state["current_block_speaker"] == "Alice"
    assert state["current_block_text"] == "Hello there."
    assert state["progress_current"] == 1
    assert state["progress_total"] == 2
    assert state["progress_percent"] == 50
    assert state["current_phase"] == "prepare_prompts"
    assert state["prompt_count"] == 2
    assert state["reused_prompt_count"] == 1
    assert state["regenerated_prompt_count"] == 1
    assert state["stage_status"] == "running"
    assert state["selected_text_character_limit"] == (
        int(tts_budget_service.resolve_cached_tts_budget([])["safe_word_count"]) * 6
    )
    assert state["speech_blocks"][0]["generated"] is True
    assert state["speech_blocks"][1]["is_current"] is True
    assert any("Audio generation is in progress at 1/2." in note for note in state["notes"])
    assert any("Preparing reusable voice prompts." in note for note in state["notes"])
    assert any("Reusable prompts: 2 | reused: 1 | created now: 1" in line for line in state["status_lines"])


def test_build_audio_blocks_notes_cover_resume_and_ready_for_assembly_states() -> None:
    """
    @brief      Verify Audio Blocks notes describe resumable failed runs and fully approved completion.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    speech_blocks = [
        {"speech_block_id": "0001-000001", "speaker_display_name": "Narrator", "text": "Narration one."},
        {"speech_block_id": "0002-000001", "speaker_display_name": "Alice", "text": "Hello there."},
    ]
    failed_notes = audio_blocks_state_service.build_audio_blocks_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        speech_blocks=speech_blocks,
        audio_blocks=[
            {"speech_block_id": "0001-000001", "generated": True, "approved": False},
            {"speech_block_id": "0002-000001", "generated": False, "approved": False},
        ],
        report={
            "audio_blocks_stage_status": "in_progress",
            "generated_block_count": 1,
            "approved_block_count": 0,
            "total_block_count": 2,
        },
        operation_state={"status": "failed", "progress_current": 1, "progress_total": 2},
        language="en",
    )
    completed_notes = audio_blocks_state_service.build_audio_blocks_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        speech_blocks=speech_blocks,
        audio_blocks=[
            {"speech_block_id": "0001-000001", "generated": True, "approved": True},
            {"speech_block_id": "0002-000001", "generated": True, "approved": True},
        ],
        report={
            "audio_blocks_stage_status": "completed",
            "generated_block_count": 2,
            "approved_block_count": 2,
            "total_block_count": 2,
        },
        operation_state={"status": "completed", "progress_current": 2, "progress_total": 2},
        language="en",
    )

    assert any("was not finalized" in note for note in failed_notes)
    assert any("ready for Audio Assembly" in note for note in completed_notes)


def test_build_audio_blocks_state_does_not_resolve_missing_chunks(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify pre-chunking Audio Blocks state avoids noisy source-resolution errors.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("AudioBlocksNoChunks", tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-26T12:00:00+00:00",
        "size_bytes": 11,
    }
    project_workspace_service.save_manifest(manifest, project_root)

    def fail_resolve(*_args, **_kwargs):
        """
        @brief      Provide the fail resolve test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        raise AssertionError("resolve_source_chunks should not be called before chunking output exists")

    monkeypatch.setattr(audio_blocks_state_service.speech_blocks_service, "resolve_source_chunks", fail_resolve)

    state = audio_blocks_state_service.build_audio_blocks_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
    )

    assert state["full_source_text"] == ""
    assert state["can_start_or_continue"] is False
    assert any("Generate Speech Blocks before starting Audio Blocks." in note for note in state["notes"])


def test_build_audio_blocks_state_does_not_resolve_unapproved_translation(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Audio Blocks page refresh avoids noisy source-resolution errors before translation approval.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksUnapprovedTranslation")
    character_voices_service.save_selected_voice_language(project_root, "ro")
    (project_root / config.TRANSLATION_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "target_language": "ro",
                "total_chunk_count": 2,
                "approved_chunk_count": 1,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    def fail_resolve(*_args, **_kwargs):
        """
        @brief      Provide the fail resolve test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        raise AssertionError("resolve_source_chunks should not be called before translated chunks are approved")

    monkeypatch.setattr(audio_blocks_state_service.speech_blocks_service, "resolve_source_chunks", fail_resolve)

    state = audio_blocks_state_service.build_audio_blocks_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
    )

    assert "Narration one." in state["full_source_text"]
    assert state["can_start_or_continue"] is True


def test_build_audio_blocks_state_starts_when_any_speech_block_is_approved(tmp_path) -> None:
    """
    @brief      Verify Audio Blocks generation is enabled when at least one Speech Block is approved.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.2.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksRequiresSpeechApproval")
    speech_blocks_path = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME
    )
    speech_blocks = json.loads(speech_blocks_path.read_text(encoding="utf-8"))
    speech_blocks[1]["approved"] = False
    speech_blocks[1]["approved_at"] = None
    speech_blocks_path.write_text(json.dumps(speech_blocks, indent=2) + "\n", encoding="utf-8")

    state = audio_blocks_state_service.build_audio_blocks_state(project_root, manifest, "en")

    assert state["can_start_or_continue"] is True


def test_build_audio_blocks_state_keeps_reset_disabled_for_default_metadata(tmp_path) -> None:
    """
    @brief      Verify first-access default Audio Blocks metadata does not enable reset generation.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksDefaultMetadataNoReset")
    operation_runtime_service.ensure_default_operation_state(project_root, "audio_blocks")

    state = audio_blocks_state_service.build_audio_blocks_state(project_root, manifest, "en")

    assert state["stage_status"] == "not_started"
    assert state["prompt_count"] == 0
    assert state["reused_prompt_count"] == 0
    assert state["regenerated_prompt_count"] == 0
    assert state["can_reset"] is False


def _create_audio_blocks_project(tmp_path, name: str):
    """
    @brief      Create one project fixture with chunking and Speech Blocks artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  name Project display name.
    @return     Tuple containing project root and loaded manifest payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
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
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root, project_workspace_service.load_manifest(project_root)


# END OF FILE
