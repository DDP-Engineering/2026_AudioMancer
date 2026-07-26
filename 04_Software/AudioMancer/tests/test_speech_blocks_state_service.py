#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
@version 0.5.2
"""

# IMPORTS

import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    audio_blocks_service,
    character_voices_service,
    project_workspace_service,
    speech_blocks_service,
    speech_blocks_state_service,
    tts_budget_service,
)
from chunking_test_support import build_chunking_document


def test_build_speech_blocks_profile_state_prefers_default_enabled_profile() -> None:
    """
    @brief      Verify Speech Blocks profile state prefers the configured default enabled profile.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
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
    speech_blocks_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
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
    speech_blocks_service.write_speech_blocks_document(
        project_root,
        {
            "status": "review_pending",
            "source": {"kind": "original", "language": "en", "fingerprint": "state-fingerprint"},
            "ai_profile_id": "profile-1",
            "instructions": "",
            "scene_ambience": {"enabled": False},
            "response_contract": "direct_blocks",
            "token_usage": {
                "input_tokens": 30,
                "output_tokens": 10,
                "total_tokens": 40,
                "usage_available": True,
            },
            "budget_metadata": {},
            "checkpoint": {
                "next_chunk_index": 1,
                "run_token": "2026-04-21T12:00:00+00:00",
                "log_relative_path": "log_ai_speech_blocks_20260421T120000Z.log",
                "source_snapshot_fingerprint": "state-fingerprint",
                "source_language": "en",
                "ai_profile_id": "profile-1",
                "additional_speech_block_instructions_fingerprint": "",
                "speech_blocks_response_contract": "direct_blocks",
            },
            "failure": None,
            "blocks": [
                {
                    "speech_block_id": "0001-000001",
                    "sequence_index": 1,
                    "chunk_id": "chunk-0001",
                    "source_language": "en",
                    "speaker_kind": "narrator",
                    "speaker_id": "narrator",
                    "speaker_display_name": "Narrator",
                    "content_kind": "narration",
                    "text": "Narration.",
                    "warning_flags": [],
                }
            ],
        },
    )
    (speech_blocks_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME).mkdir(parents=True, exist_ok=True)
    (speech_blocks_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "0001-000001.wav").write_bytes(b"RIFF")
    audio_blocks_service.write_audio_blocks_document(
        project_root,
        {
            "status": "in_progress",
            "voice_language": "en",
            "input_fingerprint": "speech-state-fixture",
            "checkpoint": None,
            "blocks": [
                {
                    "speech_block_id": "0001-000001",
                    "voice_target_id": "narrator",
                    "generated": True,
                    "approved": False,
                    "audio_can_play": True,
                    "audio_duration_seconds": None,
                    "generation_fingerprint": None,
                }
            ],
        },
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
    assert state["stage_status"] == speech_blocks_service.SPEECH_BLOCKS_STAGE_IN_PROGRESS
    assert state["processed_chunk_count"] == 1
    assert state["total_chunk_count"] == 2
    assert state["speech_blocks"][0]["speech_block_id"] == "0001-000001"
    assert state["speech_blocks"][0]["audio_generated"] is True
    assert state["speech_blocks"][0]["audio_can_play"] is True
    assert state["speech_blocks"][0]["audio_metadata_only"] is False
    assert state["selected_text_character_limit"] == (
        int(tts_budget_service.resolve_cached_tts_budget([])["safe_word_count"]) * 6
    )
    assert any("Generated 1 speech blocks from 1/2 chunks." in note for note in state["notes"])
    assert any("Input tokens: 30 | Output tokens: 10 | Total: 40" in note for note in state["notes"])


def test_build_speech_blocks_state_allows_scene_ambience_selected_audio_generation(tmp_path) -> None:
    """
    @brief      Verify Scene Ambience blocks remain eligible for selected audio generation.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-20
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksSceneAmbienceState")
    character_voices_service.save_selected_voice_language(project_root, "en")
    speech_blocks_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    speech_blocks_root.mkdir(parents=True, exist_ok=True)
    (speech_blocks_root / "input_source_chunks.json").write_text(
        json.dumps(
            [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "A quiet room."}],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    speech_blocks_service.write_speech_blocks_document(
        project_root,
        {
            "status": "review_pending",
            "source": {"kind": "original", "language": "en", "fingerprint": "scene-fingerprint"},
            "ai_profile_id": "profile-1",
            "instructions": "",
            "scene_ambience": {"enabled": True},
            "response_contract": "direct_blocks",
            "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "usage_available": False},
            "budget_metadata": {},
            "checkpoint": None,
            "failure": None,
            "blocks": [
                {
                    "speech_block_id": "0001-000001",
                    "sequence_index": 1,
                    "chunk_id": "chunk-0001",
                    "source_language": "en",
                    "speaker_kind": speech_blocks_service.SPEAKER_KIND_OPERATION,
                    "speaker_id": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
                    "speaker_display_name": "Scene Ambience",
                    "content_kind": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
                    "text": "Quiet room tone with sparse interface clicks.",
                    "sound_prompt": "Quiet room tone with sparse interface clicks.",
                    "negative_prompt": "continuous beep, speech",
                    "duration_seconds": 8,
                    "ambience_position": "opener",
                    "approved": True,
                    "warning_flags": [],
                }
            ],
        },
    )
    audio_root = speech_blocks_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    audio_root.mkdir(parents=True, exist_ok=True)
    (audio_root / "0001-000001.wav").write_bytes(b"RIFF")
    audio_blocks_service.write_audio_blocks_document(
        project_root,
        {
            "status": "in_progress",
            "voice_language": "en",
            "input_fingerprint": "speech-state-ambience-fixture",
            "checkpoint": None,
            "blocks": [
                {
                    "speech_block_id": "0001-000001",
                    "voice_target_id": "narrator",
                    "generated": True,
                    "approved": False,
                    "audio_can_play": True,
                    "audio_duration_seconds": None,
                    "generation_fingerprint": None,
                }
            ],
        },
    )

    state = speech_blocks_state_service.build_speech_blocks_state(
        project_root,
        manifest,
        "en",
        {
            "llm_profiles": [{"id": "profile-1", "label": "Speech Blocks Profile", "enabled": True}],
            "default_speech_blocks_profile_id": "profile-1",
        },
    )

    assert state["speech_blocks"][0]["audio_metadata_only"] is False
    assert state["speech_blocks"][0]["audio_can_play"] is True


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


def test_build_speech_blocks_state_does_not_resolve_missing_chunks(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify normal pre-chunking page state avoids noisy source-resolution errors.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("SpeechBlocksNoChunks", tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-26T12:00:00+00:00",
        "size_bytes": 12,
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

    monkeypatch.setattr(speech_blocks_state_service.speech_blocks_service, "resolve_source_chunks", fail_resolve)

    state = speech_blocks_state_service.build_speech_blocks_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
        {"llm_profiles": [{"id": "profile-1", "label": "Speech Blocks Profile", "enabled": True}]},
    )

    assert state["source_chunks"] == []
    assert state["total_chunk_count"] == 0
    assert any("Run text chunking" in note for note in state["notes"])


def test_build_speech_blocks_state_does_not_resolve_unapproved_translation(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify normal page refresh avoids noisy source-resolution errors before translation approval.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksUnapprovedTranslation")
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

    monkeypatch.setattr(speech_blocks_state_service.speech_blocks_service, "resolve_source_chunks", fail_resolve)

    state = speech_blocks_state_service.build_speech_blocks_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
        {"llm_profiles": [{"id": "profile-1", "label": "Speech Blocks Profile", "enabled": True}]},
    )

    assert state["source_chunks"] == []
    assert state["total_chunk_count"] == 0
    assert any("approve translation" in note for note in state["notes"])


def test_build_speech_blocks_state_filters_speaker_catalog_for_same_narrator(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify same-narrator projects expose only narrator in the Speech Blocks speaker selector.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksSameNarratorSpeakers")
    manifest["voice_assignment_mode"] = "same_narrator"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    monkeypatch.setattr(
        speech_blocks_state_service.speech_blocks_service,
        "speaker_catalog_entries",
        lambda _project_root: [
            {"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"},
            {"speaker_id": "alice", "display_name": "Alice", "speaker_kind": "character"},
        ],
    )

    state = speech_blocks_state_service.build_speech_blocks_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
        {"llm_profiles": [{"id": "profile-1", "label": "Speech Blocks Profile", "enabled": True}]},
    )

    assert state["voice_assignment_mode"] == "same_narrator"
    assert state["speaker_catalog"] == [
        {"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}
    ]


def test_merge_audio_preview_state_uses_persisted_playability_without_file_checks(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Speech Blocks preview state does not stat every generated audio row.
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
        @brief      Fail if state building falls back to per-row file probes.
        @param[in]  _path Ignored filesystem path.
        @return     No return; always raises.
        @exception  AssertionError Always raised when called.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-06-10
        @version    0.1.0
        """
        raise AssertionError("Path.is_file should not be called for persisted audio preview flags")

    monkeypatch.setattr(Path, "is_file", fail_is_file)
    monkeypatch.setattr(
        audio_blocks_service,
        "load_audio_blocks",
        lambda _project_root: [
            {
                "speech_block_id": "0001-000001",
                "generated": True,
                "approved": False,
                "audio_relative_path": "artifacts/audio_blocks/0001_000001_narrator.wav",
                "audio_can_play": True,
            }
        ],
    )

    merged_blocks = speech_blocks_state_service._merge_audio_preview_state(  # noqa: SLF001
        tmp_path,
        [
            {
                "speech_block_id": "0001-000001",
                "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            }
        ],
    )

    assert merged_blocks[0]["audio_can_play"] is True


def _create_chunked_project(tmp_path, name: str):
    """
    @brief      Create one project fixture with chunking output for state-service tests.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  name Project display name.
    @return     Tuple containing project root and loaded manifest payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
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
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            build_chunking_document(
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
                ]
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root, project_workspace_service.load_manifest(project_root)


# END OF FILE
