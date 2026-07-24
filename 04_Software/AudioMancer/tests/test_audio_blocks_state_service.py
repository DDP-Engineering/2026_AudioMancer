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
@version 0.6.1
"""

# IMPORTS

import json
from pathlib import Path
import wave

from audiomancer import config
from audiomancer.services import (
    audio_blocks_service,
    audio_blocks_state_service,
    character_voices_service,
    operation_runtime_service,
    project_workspace_service,
    speech_blocks_service,
    tts_budget_service,
)
from chunking_test_support import build_chunking_document


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
                    f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME}"
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
    assert audio_blocks_service.is_generated(state["speech_blocks"][0]) is True
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


def test_build_audio_blocks_state_measures_generated_audio_duration(tmp_path) -> None:
    """
    @brief      Verify Audio Blocks page state displays measured WAV durations for generated blocks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksDuration")
    audio_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    audio_root.mkdir(parents=True, exist_ok=True)
    audio_path = audio_root / "0001_000001_narrator.wav"
    _write_wav(audio_path, frame_count=12_000)
    _write_json(
        project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME,
        [
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "speaker_id": "narrator",
                "speaker_display_name": "Narrator",
                "normalized_speaker_name": "narrator",
                "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                "text": "Narration one.",
                "audio_relative_path": f"{config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME}/0001_000001_narrator.wav",
                "generated": True,
                "approved": False,
            }
        ],
    )

    state = audio_blocks_state_service.build_audio_blocks_state(project_root, manifest, "en")

    assert state["speech_blocks"][0]["audio_file_name"] == "0001_000001_narrator.wav"
    assert state["speech_blocks"][0]["audio_duration_seconds"] is None
    assert state["speech_blocks"][0]["can_play"] is True


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
    (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        json.dumps(
            {
                "target_language": "ro",
                "status": "review_pending",
                "token_usage": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "usage_available": False,
                },
                "budget_metadata": {},
                "additional_translation_instructions": "",
                "chunks": [
                    {"chunk_id": "chunk-0001", "translated_text": "Unu", "approved": True},
                    {"chunk_id": "chunk-0002", "translated_text": "Doi", "approved": False},
                ],
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
    speech_blocks = _read_speech_blocks_fixture_blocks(project_root)
    speech_blocks[1]["approved"] = False
    speech_blocks[1]["approved_at"] = None
    _write_speech_blocks_fixture_document(project_root, speech_blocks)

    state = audio_blocks_state_service.build_audio_blocks_state(project_root, manifest, "en")

    assert state["can_start_or_continue"] is True


def test_build_audio_blocks_state_disables_start_after_completed_generation(tmp_path) -> None:
    """
    @brief      Verify completed Audio Blocks generation leaves only reset and approval/review actions enabled.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksCompletedStartDisabled")
    audio_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    audio_root.mkdir(parents=True, exist_ok=True)
    (audio_root / "0001_000001_narrator.wav").write_bytes(b"RIFF-1")
    (audio_root / "0002_000001_alice.wav").write_bytes(b"RIFF-2")
    _write_json(
        project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME,
        [
            {
                "speech_block_id": "0001-000001",
                "audio_relative_path": f"{config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME}/0001_000001_narrator.wav",
                "generated": True,
                "approved": True,
            },
            {
                "speech_block_id": "0002-000001",
                "audio_relative_path": f"{config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME}/0002_000001_alice.wav",
                "generated": True,
                "approved": True,
            },
        ],
    )
    _write_json(
        project_root / config.AUDIO_BLOCKS_REPORT_FILE_NAME,
        {
            "audio_blocks_stage_status": "completed",
            "generated_block_count": 2,
            "approved_block_count": 2,
            "total_block_count": 2,
        },
    )
    _write_json(
        project_root / config.AUDIO_BLOCKS_STATE_FILE_NAME,
        {
            "status": "completed",
            "progress_current": 2,
            "progress_total": 2,
        },
    )

    state = audio_blocks_state_service.build_audio_blocks_state(project_root, manifest, "en")

    assert state["stage_status"] == "completed"
    assert state["can_start_or_continue"] is False
    assert state["can_reset"] is True


def test_build_audio_blocks_state_reenables_start_when_completed_report_has_missing_current_block(tmp_path) -> None:
    """
    @brief      Verify completed reports do not hide newly inserted approved Speech Blocks without audio.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksCompletedWithMissing")
    speech_blocks = _read_speech_blocks_fixture_blocks(project_root)
    speech_blocks.append(
        {
            "speech_block_id": "0002-000002",
            "sequence_index": 2,
            "chunk_id": "chunk-0002",
            "source_language": "en",
            "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            "text": "Inserted narration.",
            "approved": True,
            "approved_at": "2026-05-08T12:00:00+00:00",
            "warning_flags": [],
        }
    )
    _write_speech_blocks_fixture_document(project_root, speech_blocks)
    _write_json(
        project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME,
        [
            {"speech_block_id": "0001-000001", "generated": True, "approved": True},
            {"speech_block_id": "0002-000001", "generated": True, "approved": True},
        ],
    )
    _write_json(
        project_root / config.AUDIO_BLOCKS_REPORT_FILE_NAME,
        {
            "audio_blocks_stage_status": "completed",
            "generated_block_count": 2,
            "approved_block_count": 2,
            "total_block_count": 2,
        },
    )

    state = audio_blocks_state_service.build_audio_blocks_state(project_root, manifest, "en")

    assert state["stage_status"] == "completed"
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


def test_merge_audio_block_state_uses_persisted_playability_without_file_checks(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Audio Blocks display rows do not stat generated audio paths during state merge.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """

    def fail_is_file(_path) -> bool:
        """
        @brief      Fail if state merging probes one row on disk.
        @param[in]  _path Ignored filesystem path.
        @return     No return; always raises.
        @exception  AssertionError Always raised when called.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-10
        @version    0.1.0
        """
        raise AssertionError("Path.is_file should not be called for persisted audio block flags")

    monkeypatch.setattr(Path, "is_file", fail_is_file)

    merged_blocks = audio_blocks_state_service._merge_audio_block_state(  # noqa: SLF001
        tmp_path,
        [
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                "speaker_display_name": "Narrator",
                "text": "Narration.",
            }
        ],
        [
            {
                "speech_block_id": "0001-000001",
                "generated": True,
                "approved": False,
                "audio_relative_path": "artifacts/audio_blocks/0001_000001_narrator.wav",
                "audio_duration_seconds": 1.25,
                "audio_can_play": True,
            }
        ],
        None,
    )

    assert merged_blocks[0]["can_play"] is True
    assert merged_blocks[0]["audio_file_name"] == "0001_000001_narrator.wav"


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
    return project_root, project_workspace_service.load_manifest(project_root)


def _write_json(path, payload: object) -> None:
    """
    @brief      Write one JSON fixture payload.
    @param[in]  path Target file path.
    @param[in]  payload JSON-serializable payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_wav(path: Path, frame_count: int) -> None:
    """
    @brief      Write one small mono PCM WAV test file.
    @param[in]  path Destination WAV path.
    @param[in]  frame_count Number of silent frames to write.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24_000)
        wav_file.writeframes(b"\x00\x00" * frame_count)



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
