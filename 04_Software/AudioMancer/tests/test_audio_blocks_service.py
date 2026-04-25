#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_blocks_service.py
@brief Focused Audio Blocks service tests for AudioMancer.
@details Verifies direct-clone source preparation, ordered WAV generation,
         approval updates, single-block regeneration, and speaker-name
         normalization.
@author Eng. Dan Dumitru Pasare
@date 2026-04-23
@version 1.5.0
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import (
    audio_blocks_service,
    character_voices_service,
    narrator_definition_service,
    operation_runtime_service,
    project_workspace_service,
    speech_blocks_service,
)


def test_audio_blocks_service_generates_clone_prompts_and_ordered_wavs(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify a fresh Audio Blocks run creates reusable clone prompts
                and generated WAV files in speech-block order.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.3.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceGenerate")
    wait_payloads = [
        {
            "active_model": {"model_id": "Qwen3-TTS-12Hz-1.7B-Base"},
            "operation": {"status": "completed"},
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "narrator"}},
            },
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "alice"}},
            },
            "result": {},
        },
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Narrator ready."}},
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Alice ready."}},
    ]
    observed_prompt_requests: list[tuple[str, str, str]] = []
    observed_generate_requests: list[tuple[str, str, str]] = []
    audio_payloads = [b"RIFF-narrator", b"RIFF-alice"]
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"active_model": None, "operation": {"status": "idle"}},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "load_model",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "create_voice_clone_prompt",
        lambda _base_url, _api_key, sample_audio_bytes, sample_text, language, **_kwargs: (
            observed_prompt_requests.append((sample_audio_bytes.decode("utf-8"), sample_text, language)),
            {"status": "running"},
        )[1],
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "generate_voice_clone_from_prompt",
        lambda _base_url, _api_key, voice_clone_prompt, _language, text, **_kwargs: (
            observed_generate_requests.append(
                (
                    str(dict(voice_clone_prompt).get("format", "")),
                    str(dict(voice_clone_prompt).get("speaker", "")),
                    text,
                )
            ),
            {"status": "running"},
        )[1],
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: wait_payloads.pop(0),
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "download_generated_voice",
        lambda *_args, **_kwargs: audio_payloads.pop(0),
    )

    report = audio_blocks_service.start_or_continue_generation(
        project_root,
        manifest,
        _runtime_settings(),
    )

    assert report["generated_block_count"] == 2
    assert report["approved_block_count"] == 0
    clone_profiles = audio_blocks_service.load_voice_clone_profiles(project_root)
    assert [profile["voice_target_id"] for profile in clone_profiles] == ["character_alice", "narrator"]
    assert [profile["sample_text"] for profile in clone_profiles] == [
        "Character preview line.",
        "Narrator preview line.",
    ]
    assert [profile["prompt_format"] for profile in clone_profiles] == [
        "qwen_voice_clone_prompt_v1",
        "qwen_voice_clone_prompt_v1",
    ]
    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert [block["generated"] for block in audio_blocks] == [True, True]
    assert [block["approved"] for block in audio_blocks] == [False, False]
    assert observed_prompt_requests == [
        ("selected-narrator", "Narrator preview line.", "en"),
        ("alice-sample", "Character preview line.", "en"),
    ]
    assert observed_generate_requests == [
        ("qwen_voice_clone_prompt_v1", "narrator", "Narration one."),
        ("qwen_voice_clone_prompt_v1", "alice", "Hello there."),
    ]
    first_audio_path = project_root / str(audio_blocks[0]["audio_relative_path"])
    second_audio_path = project_root / str(audio_blocks[1]["audio_relative_path"])
    assert first_audio_path.name == "0001_000001_narrator.wav"
    assert second_audio_path.name == "0001_000002_alice.wav"
    assert first_audio_path.read_bytes() == b"RIFF-narrator"
    assert second_audio_path.read_bytes() == b"RIFF-alice"


def test_audio_blocks_service_same_narrator_mode_uses_narrator_prompt_for_characters(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify same-narrator mode does not require character samples for Audio Blocks generation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceSameNarrator")
    narrator_definition_service.save_tts_plan(
        project_root,
        {"voice_assignment_mode": "same_narrator"},
        _runtime_settings()["discovered_models"],
    )
    narrator_definition_service.selected_narrator_sample_paths(project_root)[1].unlink()
    character_voices_service.delete_target_sample(project_root, "character_alice")
    manifest = project_workspace_service.load_manifest(project_root)
    wait_payloads = [
        {
            "active_model": {"model_id": "Qwen3-TTS-12Hz-1.7B-Base"},
            "operation": {"status": "completed"},
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "narrator"}},
            },
            "result": {},
        },
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Narrator block ready."}},
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Character block ready."}},
    ]
    observed_prompt_requests: list[tuple[str, str, str]] = []
    observed_generate_requests: list[tuple[str, str, str]] = []
    audio_payloads = [b"RIFF-narrator", b"RIFF-character-with-narrator"]
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"active_model": None, "operation": {"status": "idle"}},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "load_model",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "create_voice_clone_prompt",
        lambda _base_url, _api_key, sample_audio_bytes, sample_text, language, **_kwargs: (
            observed_prompt_requests.append((sample_audio_bytes.decode("utf-8"), sample_text, language)),
            {"status": "running"},
        )[1],
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "generate_voice_clone_from_prompt",
        lambda _base_url, _api_key, voice_clone_prompt, _language, text, **_kwargs: (
            observed_generate_requests.append(
                (
                    str(dict(voice_clone_prompt).get("format", "")),
                    str(dict(voice_clone_prompt).get("speaker", "")),
                    text,
                )
            ),
            {"status": "running"},
        )[1],
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: wait_payloads.pop(0),
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "download_generated_voice",
        lambda *_args, **_kwargs: audio_payloads.pop(0),
    )

    report = audio_blocks_service.start_or_continue_generation(project_root, manifest, _runtime_settings())

    assert report["generated_block_count"] == 2
    clone_profiles = audio_blocks_service.load_voice_clone_profiles(project_root)
    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert [profile["voice_target_id"] for profile in clone_profiles] == ["narrator"]
    assert observed_prompt_requests == [("selected-narrator", "Narrator preview line.", "en")]
    assert observed_generate_requests == [
        ("qwen_voice_clone_prompt_v1", "narrator", "Narration one."),
        ("qwen_voice_clone_prompt_v1", "narrator", "Hello there."),
    ]
    assert [block["voice_target_id"] for block in audio_blocks] == ["narrator", "narrator"]
    assert [block["voice_source_kind"] for block in audio_blocks] == ["narrator_sample", "narrator_sample"]


def test_audio_blocks_service_rejects_legacy_global_sequence_schema(tmp_path) -> None:
    """
    @brief      Verify legacy global Audio Blocks artifacts require reset/regeneration.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksLegacySchema")
    output_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME
    output_path.write_text(
        json.dumps(
            [
                {
                    "speech_block_id": "0002-000004",
                    "sequence_index": 4,
                    "chunk_sequence_index": 1,
                    "chunk_id": "chunk-0002",
                    "speaker_id": "alice",
                    "speaker_display_name": "Alice",
                    "normalized_speaker_name": "alice",
                    "text": "Legacy block.",
                    "voice_target_id": "character_alice",
                    "voice_source_kind": "character_sample",
                    "audio_relative_path": None,
                    "metadata_relative_path": None,
                    "generated": False,
                    "approved": False,
                    "approved_at": None,
                    "generated_at": None,
                    "runtime_result_summary": "",
                    "warning_flags": [],
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="legacy global-sequence schema"):
        audio_blocks_service.load_audio_blocks(project_root)


def test_audio_blocks_service_generates_only_approved_speech_blocks(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Audio Blocks generation skips Speech Blocks that are not approved yet.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceApprovedOnly")
    speech_blocks_path = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME
    )
    speech_blocks_payload = json.loads(speech_blocks_path.read_text(encoding="utf-8"))
    speech_blocks_payload[1]["approved"] = False
    speech_blocks_payload[1]["approved_at"] = None
    speech_blocks_path.write_text(json.dumps(speech_blocks_payload, indent=2) + "\n", encoding="utf-8")

    wait_payloads = [
        {
            "active_model": {"model_id": "Qwen3-TTS-12Hz-1.7B-Base"},
            "operation": {"status": "completed"},
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "narrator"}},
            },
            "result": {},
        },
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Narrator ready."}},
    ]
    observed_prompt_requests: list[tuple[str, str, str]] = []
    observed_generate_requests: list[str] = []
    audio_payloads = [b"RIFF-narrator"]
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"active_model": None, "operation": {"status": "idle"}},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "load_model",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "create_voice_clone_prompt",
        lambda _base_url, _api_key, sample_audio_bytes, sample_text, language, **_kwargs: (
            observed_prompt_requests.append((sample_audio_bytes.decode("utf-8"), sample_text, language)),
            {"status": "running"},
        )[1],
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "generate_voice_clone_from_prompt",
        lambda _base_url, _api_key, _voice_clone_prompt, _language, text, **_kwargs: (
            observed_generate_requests.append(text),
            {"status": "running"},
        )[1],
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: wait_payloads.pop(0),
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "download_generated_voice",
        lambda *_args, **_kwargs: audio_payloads.pop(0),
    )

    report = audio_blocks_service.start_or_continue_generation(project_root, manifest, _runtime_settings())

    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    operation_state = audio_blocks_service.load_operation_state(project_root)
    assert report["audio_blocks_stage_status"] == audio_blocks_service.AUDIO_BLOCKS_STAGE_IN_PROGRESS
    assert report["generated_block_count"] == 1
    assert report["total_block_count"] == 2
    assert operation_state is not None
    assert operation_state["status"] == "in_progress"
    assert [block["generated"] for block in audio_blocks] == [True, False]
    assert [block["speech_block_approved"] for block in audio_blocks] == [True, False]
    assert observed_prompt_requests == [("selected-narrator", "Narrator preview line.", "en")]
    assert observed_generate_requests == ["Narration one."]


def test_audio_blocks_service_skips_voiceweaver_for_metadata_only_blocks(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify pause, background-noise, and indication blocks skip VoiceWeaver generation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceMetadataOnly")
    speech_blocks_path = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME
    )
    speech_blocks_payload = json.loads(speech_blocks_path.read_text(encoding="utf-8"))
    speech_blocks_payload.append(
        {
            "speech_block_id": "0001-000003",
            "sequence_index": 3,
            "chunk_id": "chunk-0001",
            "source_language": "en",
            "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_PAUSE,
            "text": "Pause between sections for 1500 ms.",
            "approved": True,
            "approved_at": "2026-04-23T12:04:00+00:00",
            "warning_flags": [],
        }
    )
    speech_blocks_payload.append(
        {
            "speech_block_id": "0001-000004",
            "sequence_index": 4,
            "chunk_id": "chunk-0001",
            "source_language": "en",
            "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_INDICATION,
            "text": "[whisper]",
            "approved": True,
            "approved_at": "2026-04-23T12:05:00+00:00",
            "warning_flags": [],
        }
    )
    speech_blocks_path.write_text(json.dumps(speech_blocks_payload, indent=2) + "\n", encoding="utf-8")
    wait_payloads = [
        {
            "active_model": {"model_id": "Qwen3-TTS-12Hz-1.7B-Base"},
            "operation": {"status": "completed"},
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "narrator"}},
            },
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "alice"}},
            },
            "result": {},
        },
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Narrator ready."}},
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Alice ready."}},
    ]
    observed_generate_requests: list[str] = []
    audio_payloads = [b"RIFF-narrator", b"RIFF-alice"]
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"active_model": None, "operation": {"status": "idle"}},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "load_model",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "create_voice_clone_prompt",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "generate_voice_clone_from_prompt",
        lambda _base_url, _api_key, _voice_clone_prompt, _language, text, **_kwargs: (
            observed_generate_requests.append(text),
            {"status": "running"},
        )[1],
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: wait_payloads.pop(0),
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "download_generated_voice",
        lambda *_args, **_kwargs: audio_payloads.pop(0),
    )

    report = audio_blocks_service.start_or_continue_generation(project_root, manifest, _runtime_settings())

    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert report["total_block_count"] == 4
    assert observed_generate_requests == ["Narration one.", "Hello there."]
    assert audio_blocks[2]["speech_block_id"] == "0001-000003"
    assert audio_blocks[2]["metadata_only"] is True
    assert audio_blocks[2]["pause_duration_ms"] == 1500
    assert audio_blocks[2]["generated"] is True
    assert audio_blocks[2]["approved"] is True
    assert audio_blocks[2]["audio_relative_path"] is None
    assert audio_blocks[3]["content_kind"] == speech_blocks_service.CONTENT_KIND_INDICATION
    assert audio_blocks[3]["metadata_only"] is True
    assert audio_blocks[3]["audio_relative_path"] is None


def test_audio_blocks_service_approve_and_regenerate_selected_block(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify approving and re-generating one Audio Blocks entry updates only the targeted record.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.3.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceApprove")
    _seed_generated_audio_blocks(project_root)

    report = audio_blocks_service.approve_audio_block(project_root, "0001-000001")
    assert report["approved_block_count"] == 1
    updated_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert updated_blocks[0]["approved"] is True
    assert updated_blocks[1]["approved"] is False

    wait_payloads = [
        {
            "active_model": {"model_id": "Qwen3-TTS-12Hz-1.7B-Base"},
            "operation": {"status": "completed"},
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "narrator"}},
            },
            "result": {},
        },
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Narrator regenerated."}},
    ]
    generated_audio = [b"RIFF-regenerated"]
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"active_model": None, "operation": {"status": "idle"}},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "load_model",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "create_voice_clone_prompt",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "generate_voice_clone_from_prompt",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: wait_payloads.pop(0),
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "download_generated_voice",
        lambda *_args, **_kwargs: generated_audio.pop(0),
    )

    regen_report = audio_blocks_service.regenerate_audio_block(
        project_root,
        manifest,
        "0001-000001",
        _runtime_settings(),
    )

    regenerated_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert regen_report["generated_block_count"] == 2
    assert regenerated_blocks[0]["approved"] is False
    assert regenerated_blocks[0]["runtime_result_summary"] == "Narrator regenerated."
    assert (project_root / str(regenerated_blocks[0]["audio_relative_path"])).read_bytes() == b"RIFF-regenerated"


def test_audio_blocks_service_reconcile_after_resplit_deletes_changed_chunk_and_remaps_later_audio(tmp_path) -> None:
    """
    @brief      Verify Speech Block re-split reconciliation deletes changed-chunk audio and remaps later artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceResplitReconcile")
    speech_blocks_path = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME
    )
    speech_blocks_path.write_text(
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
                    "text": "Replacement narration.",
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
                    "warning_flags": [],
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    audio_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    generated_root = audio_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    generated_root.mkdir(parents=True, exist_ok=True)
    changed_audio_path = generated_root / "000001_narrator.wav"
    changed_metadata_path = generated_root / "000001_narrator.json"
    later_audio_path = generated_root / "0002_000001_alice.wav"
    later_metadata_path = generated_root / "0002_000001_alice.json"
    changed_audio_path.write_bytes(b"RIFF-old-changed")
    changed_metadata_path.write_text("{}\n", encoding="utf-8")
    later_audio_path.write_bytes(b"RIFF-later")
    later_metadata_path.write_text(
        json.dumps({"speech_block_id": "0002-000001", "chunk_id": "chunk-0002", "sequence_index": 1}, indent=2) + "\n",
        encoding="utf-8",
    )
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
                    "text": "Old changed narration.",
                    "voice_target_id": "narrator",
                    "voice_source_kind": "narrator_sample",
                    "audio_relative_path": changed_audio_path.relative_to(project_root).as_posix(),
                    "metadata_relative_path": changed_metadata_path.relative_to(project_root).as_posix(),
                    "generated": True,
                    "approved": True,
                    "approved_at": "2026-04-23T12:10:00+00:00",
                    "generated_at": "2026-04-23T12:09:00+00:00",
                    "runtime_result_summary": "Old changed ready.",
                    "warning_flags": [],
                },
                {
                    "speech_block_id": "0002-000001",
                    "sequence_index": 1,
                    "chunk_id": "chunk-0002",
                    "speaker_id": "alice",
                    "speaker_display_name": "Alice",
                    "normalized_speaker_name": "alice",
                    "text": "Hello there.",
                    "voice_target_id": "character_alice",
                    "voice_source_kind": "character_sample",
                    "audio_relative_path": later_audio_path.relative_to(project_root).as_posix(),
                    "metadata_relative_path": later_metadata_path.relative_to(project_root).as_posix(),
                    "generated": True,
                    "approved": True,
                    "approved_at": "2026-04-23T12:10:00+00:00",
                    "generated_at": "2026-04-23T12:09:00+00:00",
                    "runtime_result_summary": "Later ready.",
                    "warning_flags": [],
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report = audio_blocks_service.reconcile_after_speech_blocks_resplit(project_root, "chunk-0001")

    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    remapped_audio_path = generated_root / "0002_000001_alice.wav"
    remapped_metadata_path = generated_root / "0002_000001_alice.json"
    assert report["generated_block_count"] == 1
    assert audio_blocks[0]["speech_block_id"] == "0001-000001"
    assert audio_blocks[0]["generated"] is False
    assert audio_blocks[1]["speech_block_id"] == "0002-000001"
    assert audio_blocks[1]["sequence_index"] == 1
    assert audio_blocks[1]["generated"] is True
    assert not changed_audio_path.exists()
    assert later_audio_path.exists()
    assert remapped_audio_path.read_bytes() == b"RIFF-later"
    assert json.loads(remapped_metadata_path.read_text(encoding="utf-8"))["speech_block_id"] == "0002-000001"


def test_audio_blocks_service_normalize_speaker_name_handles_diacritics() -> None:
    """
    @brief      Verify speaker-name normalization strips punctuation and diacritics into stable ASCII tokens.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    assert audio_blocks_service.normalize_speaker_name(" Maria-Elena ÃˆËœtefan!? ") == "maria_elena_stefan"


def test_audio_blocks_service_resume_continues_from_saved_checkpoint(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Audio Blocks resumes from the persisted checkpoint instead of regenerating finished work.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.3.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceResume")
    wait_payloads = [
        {
            "active_model": {"model_id": "Qwen3-TTS-12Hz-1.7B-Base"},
            "operation": {"status": "completed"},
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "narrator"}},
            },
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "alice"}},
            },
            "result": {},
        },
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Narrator ready."}},
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Alice ready."}},
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Alice ready."}},
    ]
    observed_generate_requests: list[tuple[str, str, str]] = []
    audio_payloads = [b"RIFF-narrator", b"RIFF-alice", b"RIFF-alice"]
    read_status_calls = {"count": 0}
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: (
            read_status_calls.__setitem__("count", int(read_status_calls["count"]) + 1),
            (
                {"active_model": None, "operation": {"status": "idle"}}
                if int(read_status_calls["count"]) == 1
                else {
                    "active_model": {
                        "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
                        "effective_model_parameters": {"max_new_tokens": 512},
                    },
                    "operation": {"status": "idle"},
                }
            ),
        )[1],
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "load_model",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "create_voice_clone_prompt",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "generate_voice_clone_from_prompt",
        lambda _base_url, _api_key, voice_clone_prompt, _language, text, **_kwargs: (
            observed_generate_requests.append(
                (
                    str(dict(voice_clone_prompt).get("format", "")),
                    str(dict(voice_clone_prompt).get("speaker", "")),
                    text,
                )
            ),
            {"status": "running"},
        )[1],
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: wait_payloads.pop(0),
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "download_generated_voice",
        lambda *_args, **_kwargs: audio_payloads.pop(0),
    )

    try:
        audio_blocks_service.start_or_continue_generation(
            project_root,
            manifest,
            _runtime_settings(),
            cancel_requested=lambda: len(observed_generate_requests) >= 1,
        )
    except operation_runtime_service.OperationCancelledError:
        pass
    else:
        raise AssertionError("Expected the first Audio Blocks run to stop through cooperative cancellation.")

    persisted_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert [block["generated"] for block in persisted_blocks] == [True, False]
    assert observed_generate_requests == [("qwen_voice_clone_prompt_v1", "narrator", "Narration one.")]

    report = audio_blocks_service.start_or_continue_generation(
        project_root,
        manifest,
        _runtime_settings(),
    )

    resumed_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert report["generated_block_count"] == 2
    assert observed_generate_requests == [
        ("qwen_voice_clone_prompt_v1", "narrator", "Narration one."),
        ("qwen_voice_clone_prompt_v1", "alice", "Hello there."),
    ]
    assert [block["generated"] for block in resumed_blocks] == [True, True]
    assert resumed_blocks[0]["runtime_result_summary"] == "Narrator ready."
    assert resumed_blocks[1]["runtime_result_summary"] == "Alice ready."


def test_audio_blocks_service_input_fingerprint_mismatch_starts_fresh_run(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify stale Audio Blocks input fingerprints start a fresh run under the new schema.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceFingerprint")
    _seed_generated_audio_blocks(project_root)
    state_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_STATE_FILE_NAME
    operation_state = json.loads(state_path.read_text(encoding="utf-8"))
    operation_state["metadata"]["input_fingerprint"] = "stale-fingerprint"
    state_path.write_text(json.dumps(operation_state, indent=2) + "\n", encoding="utf-8")
    wait_payloads = [
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "narrator"}},
            },
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "alice"}},
            },
            "result": {},
        },
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Narrator fresh."}},
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Alice fresh."}},
    ]
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {
            "active_model": {
                "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
                "effective_model_parameters": {"max_new_tokens": 512},
            },
            "operation": {"status": "idle"},
        },
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "load_model",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "create_voice_clone_prompt",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "generate_voice_clone_from_prompt",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: wait_payloads.pop(0),
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "download_generated_voice",
        lambda *_args, **_kwargs: b"RIFF-fresh",
    )

    report = audio_blocks_service.start_or_continue_generation(
        project_root,
        manifest,
        _runtime_settings(),
    )

    assert report["generated_block_count"] == 2
    refreshed_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert refreshed_state["metadata"]["input_fingerprint"] != "stale-fingerprint"


def test_audio_blocks_service_prefers_qwen_1_7b_base_model(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Audio Blocks prefers the 1.7B Qwen base model when multiple healthy base models exist.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServicePreferredModel")
    observed_loaded_models: list[str] = []
    wait_payloads = [
        {
            "active_model": {"model_id": "Qwen3-TTS-12Hz-1.7B-Base"},
            "operation": {"status": "completed"},
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "narrator"}},
            },
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "alice"}},
            },
            "result": {},
        },
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Narrator ready."}},
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Alice ready."}},
    ]
    audio_payloads = [b"RIFF-narrator", b"RIFF-alice"]
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"active_model": None, "operation": {"status": "idle"}},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "load_model",
        lambda _base_url, _api_key, model_id, **_kwargs: (
            observed_loaded_models.append(model_id),
            {"status": "running"},
        )[1],
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "create_voice_clone_prompt",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "generate_voice_clone_from_prompt",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: wait_payloads.pop(0),
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "download_generated_voice",
        lambda *_args, **_kwargs: audio_payloads.pop(0),
    )

    audio_blocks_service.start_or_continue_generation(
        project_root,
        manifest,
        _runtime_settings(),
    )

    assert observed_loaded_models == ["Qwen3-TTS-12Hz-1.7B-Base"]


def test_audio_blocks_service_approve_all_marks_only_generated_blocks(tmp_path) -> None:
    """
    @brief      Verify Approve All only approves generated audio blocks and leaves missing audio untouched.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceApproveAll")
    _seed_generated_audio_blocks(project_root)
    output_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME
    persisted_blocks = json.loads(output_path.read_text(encoding="utf-8"))
    persisted_blocks[1]["generated"] = False
    persisted_blocks[1]["audio_relative_path"] = None
    persisted_blocks[1]["metadata_relative_path"] = None
    persisted_blocks[1]["generated_at"] = None
    persisted_blocks[1]["runtime_result_summary"] = ""
    output_path.write_text(json.dumps(persisted_blocks, indent=2) + "\n", encoding="utf-8")

    report = audio_blocks_service.approve_all_audio_blocks(project_root)

    updated_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert report["approved_block_count"] == 1
    assert updated_blocks[0]["approved"] is True
    assert updated_blocks[1]["approved"] is False


def test_audio_blocks_split_planner_prefers_sentences_then_word_groups() -> None:
    """
    @brief      Verify long Audio Blocks text is split on natural boundaries before word groups.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    sentence_plan = audio_blocks_service._plan_audio_block_splits(  # noqa: SLF001
        "One two. Three four. Five six.",
        {"split_audio_seconds_budget": 1.0},
    )
    word_plan = audio_blocks_service._plan_audio_block_splits(  # noqa: SLF001
        "One two three four five six.",
        {"split_audio_seconds_budget": 1.0},
    )

    assert sentence_plan["strategy"] == "sentence"
    assert sentence_plan["parts"] == ["One two.", "Three four.", "Five six."]
    assert word_plan["strategy"] == "word_group"
    assert " ".join(word_plan["parts"]) == "One two three four five six."


def test_audio_blocks_part_artifact_paths_include_chunk_order(tmp_path) -> None:
    """
    @brief      Verify split-part artifact names include chunk order and local sequence.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    first_chunk_part = audio_blocks_service._audio_part_artifact_path(  # noqa: SLF001
        tmp_path,
        {
            "chunk_id": "chunk-0001",
            "sequence_index": 1,
            "normalized_speaker_name": "narrator",
        },
        0,
    )
    second_chunk_part = audio_blocks_service._audio_part_artifact_path(  # noqa: SLF001
        tmp_path,
        {
            "chunk_id": "chunk-0002",
            "sequence_index": 1,
            "normalized_speaker_name": "narrator",
        },
        0,
    )

    assert first_chunk_part.name == "0001_000001_narrator_part001.wav"
    assert second_chunk_part.name == "0002_000001_narrator_part001.wav"
    assert first_chunk_part != second_chunk_part


def test_audio_blocks_model_budget_prefers_runtime_effective_parameters() -> None:
    """
    @brief      Verify runtime effective `max_new_tokens` is preferred over model defaults.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    budget = audio_blocks_service._resolve_model_budget(  # noqa: SLF001
        {
            "active_model": {
                "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
                "effective_model_parameters": {"max_new_tokens": 128},
            }
        },
        {
            "default_model_parameters": {"max_new_tokens": 512},
            "generation_parameter_ranges": {"max_new_tokens": {"default": 256}},
        },
    )

    assert budget["model_token_budget"] == 128
    assert budget["model_budget_source"] == "runtime_effective"


def _create_audio_blocks_project(tmp_path, name: str):
    """
    @brief      Create one project fixture with approved Speech Blocks and voice samples.
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
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    speech_blocks_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    speech_blocks_root.mkdir(parents=True, exist_ok=True)
    speech_blocks_payload = [
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
            "speech_block_id": "0001-000002",
            "sequence_index": 2,
            "chunk_id": "chunk-0001",
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
    ]
    (speech_blocks_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(speech_blocks_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    narrator_profile = narrator_definition_service.load_profiles(project_root)[0]
    narrator_definition_service.store_profile_sample(
        project_root,
        narrator_profile,
        "Narrator preview line.",
        {
            "generation_mode": "custom_voice",
            "source_model_id": "qwen-custom",
            "language": "en",
        },
        "Narrator sample ready.",
        b"selected-narrator",
    )
    narrator_definition_service.copy_selected_narrator_sample(project_root, narrator_profile["profile_id"])
    (project_root / config.NARRATOR_SELECTION_FILE_NAME).write_text(
        json.dumps(
            {
                "selected_profile_id": narrator_profile["profile_id"],
                "selected_language": "en",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    alice_target = {
        "target_id": "character_alice",
        "target_kind": character_voices_service.TARGET_KIND_CHARACTER,
        "display_name": "Alice",
        "prompt_text": "Alice voice prompt.",
        "preview_text": "Character preview line.",
    }
    character_voices_service.save_voice_targets(project_root, [alice_target])
    character_voices_service.store_target_sample(
        project_root,
        alice_target,
        "en",
        "Character preview line.",
        {
            "generation_mode": "voice_designer",
            "source_model_id": "qwen-designer",
        },
        "Character sample ready.",
        b"alice-sample",
    )
    return project_root, project_workspace_service.load_manifest(project_root)


def _seed_generated_audio_blocks(project_root) -> None:
    """
    @brief      Write generated Audio Blocks output, report, profiles, and operation state.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    audio_root = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    )
    audio_root.mkdir(parents=True, exist_ok=True)
    audio_blocks_payload = []
    for speech_block in speech_blocks:
        sequence_index = int(speech_block["sequence_index"])
        speaker_name = audio_blocks_service.normalize_speaker_name(str(speech_block["speaker_display_name"]))
        stem = str(speech_block["speech_block_id"]).replace("-", "_")
        audio_path = audio_root / f"{stem}_{speaker_name}.wav"
        metadata_path = audio_root / f"{stem}_{speaker_name}.json"
        audio_path.write_bytes(f"RIFF-{sequence_index}".encode())
        metadata_path.write_text("{}\n", encoding="utf-8")
        audio_blocks_payload.append(
            {
                "speech_block_id": speech_block["speech_block_id"],
                "sequence_index": sequence_index,
                "chunk_id": speech_block["chunk_id"],
                "speaker_id": speech_block["speaker_id"],
                "speaker_display_name": speech_block["speaker_display_name"],
                "normalized_speaker_name": speaker_name,
                "text": speech_block["text"],
                "voice_target_id": (
                    "narrator"
                    if speech_block["speaker_id"] == "narrator"
                    else character_voices_service.character_target_id(speech_block["speaker_id"])
                ),
                "voice_source_kind": (
                    "narrator_sample" if speech_block["speaker_id"] == "narrator" else "character_sample"
                ),
                "audio_relative_path": audio_path.relative_to(project_root).as_posix(),
                "metadata_relative_path": metadata_path.relative_to(project_root).as_posix(),
                "speech_block_approved": bool(speech_block.get("approved", False)),
                "generated": True,
                "approved": False,
                "approved_at": None,
                "generated_at": "2026-04-23T12:10:00+00:00",
                "runtime_result_summary": "Generated.",
                "warning_flags": [],
            }
        )
    audio_root.parent.mkdir(parents=True, exist_ok=True)
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(audio_blocks_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME
    ).write_text(
        json.dumps(
            [
                {
                    "voice_target_id": "narrator",
                    "display_name": "Narrator",
                    "source_sample_relative_path": str(
                        narrator_definition_service.selected_narrator_sample_paths(project_root)[0]
                        .relative_to(project_root)
                        .as_posix()
                    ),
                    "source_sample_fingerprint": "old-narrator",
                    "source_model_id": "qwen-custom",
                    "voice_language": "en",
                    "sample_text": "Narrator preview line.",
                    "voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "narrator"},
                    "prompt_format": "qwen_voice_clone_prompt_v1",
                    "generated_at": "2026-04-23T12:09:00+00:00",
                    "clone_model_id": "old-model",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report_payload = {
        "voice_language": "en",
        "audio_blocks_stage_status": "in_progress",
        "generated_block_count": 2,
        "approved_block_count": 0,
        "total_block_count": 2,
        "warning_count": 0,
        "warnings": [],
        "updated_at": "2026-04-23T12:10:00+00:00",
    }
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_REPORT_FILE_NAME).write_text(
        json.dumps(report_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    operation_state = {
        "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        "status": "completed",
        "input_paths": [f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.SPEECH_BLOCKS_OUTPUT_FILE_NAME}"],
        "output_paths": [f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.AUDIO_BLOCKS_OUTPUT_FILE_NAME}"],
        "artifact_paths": [f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.AUDIO_BLOCKS_REPORT_FILE_NAME}"],
        "progress_current": 2,
        "progress_total": 2,
        "mode": "tts_generation",
        "started_at": "2026-04-23T12:00:00+00:00",
        "completed_at": "2026-04-23T12:10:00+00:00",
        "updated_at": "2026-04-23T12:10:00+00:00",
        "warning_count": 0,
        "metadata": {
            "voice_language": "en",
            "input_fingerprint": "",
            "speech_block_count": 2,
            "generated_block_count": 2,
            "approved_block_count": 0,
            "clone_profile_count": 1,
            "prompt_count": 1,
            "reused_prompt_count": 0,
            "regenerated_prompt_count": 1,
            "current_phase": "generate_blocks",
            "current_block_id": None,
        },
        "resume_checkpoint": {"next_profile_index": 0, "next_speech_block_index": 2},
    }
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_STATE_FILE_NAME).write_text(
        json.dumps(operation_state, indent=2) + "\n",
        encoding="utf-8",
    )


def _runtime_settings() -> dict[str, object]:
    """
    @brief      Build minimal runtime settings with healthy clone-capable Qwen models.
    @return     Runtime settings payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    return {
        "base_url": "http://127.0.0.1:8059",
        "runtime_api_key": "",
        "timeout_seconds": 60,
        "discovered_models": [
            {
                "model_id": "Qwen3-TTS-12Hz-0.6B-Base",
                "backend_name": "qwen3-tts-base",
                "status": "healthy",
                "supported_generation_modes": ["clone"],
                "supported_presets": [],
                "default_model_parameters": {"max_new_tokens": 512},
            },
            {
                "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
                "backend_name": "qwen3-tts-base",
                "status": "healthy",
                "supported_generation_modes": ["clone"],
                "supported_presets": [],
                "default_model_parameters": {"max_new_tokens": 512},
            },
        ],
    }


# END OF FILE
