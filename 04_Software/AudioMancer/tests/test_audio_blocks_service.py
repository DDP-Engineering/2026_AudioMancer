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
"""

# IMPORTS

import io
import json
import wave

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
    observed_manifest_progress: list[tuple[int, int, str]] = []
    audio_payloads = [_wav_bytes("narrator"), _wav_bytes("alice")]
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
        progress_callback=lambda *_args: observed_manifest_progress.append(
            (
                int(
                    project_workspace_service.load_manifest(project_root)["operations"]["audio_blocks"][
                        "progress_current"
                    ]
                ),
                int(
                    project_workspace_service.load_manifest(project_root)["operations"]["audio_blocks"][
                        "progress_total"
                    ]
                ),
                str(project_workspace_service.load_manifest(project_root)["operations"]["audio_blocks"]["status"]),
            )
        ),
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
    assert [audio_blocks_service.is_generated(block) for block in audio_blocks] == [True, True]
    assert [audio_blocks_service.is_approved(block) for block in audio_blocks] == [False, False]
    assert [audio_blocks_service.audio_can_play(block) for block in audio_blocks] == [True, True]
    assert all(block["generated"] is True for block in audio_blocks)
    assert observed_prompt_requests == [
        ("selected-narrator", "Narrator preview line.", "en"),
        ("alice-sample", "Character preview line.", "en"),
    ]
    assert observed_generate_requests == [
        ("qwen_voice_clone_prompt_v1", "narrator", "Narration one."),
        ("qwen_voice_clone_prompt_v1", "alice", "Hello there."),
    ]
    assert (1, 2, "running") in observed_manifest_progress
    assert observed_manifest_progress[-1] == (2, 2, "in_progress")
    first_audio_path = project_root / str(audio_blocks[0]["audio_relative_path"])
    second_audio_path = project_root / str(audio_blocks[1]["audio_relative_path"])
    assert first_audio_path.name == "0001-000001.wav"
    assert second_audio_path.name == "0001-000002.wav"
    assert first_audio_path.read_bytes() == _wav_bytes("narrator")
    assert second_audio_path.read_bytes() == _wav_bytes("alice")


def test_audio_blocks_service_same_narrator_mode_uses_narrator_prompt_for_characters(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify same-narrator mode does not require character samples for Audio Blocks generation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceSameNarrator")
    narrator_definition_service.save_tts_plan(
        project_root,
        {"voice_assignment_mode": "same_narrator"},
        _runtime_settings()["discovered_models"],
    )
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
    audio_payloads = [_wav_bytes("narrator"), _wav_bytes("character-with-narrator")]
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


def test_audio_blocks_service_requires_selected_narrator_sample_metadata(tmp_path) -> None:
    """
    @brief      Verify Audio Blocks requires current selected narrator sample metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksCurrentNarratorMetadata")
    document = narrator_definition_service.load_narrator_voice_document(project_root)
    selected_profile_id = document["selected_profile_id"]
    selected_profile = next(profile for profile in document["profiles"] if profile["profile_id"] == selected_profile_id)
    selected_profile["sample"] = None
    narrator_definition_service.write_narrator_voice_document(project_root, document)

    with pytest.raises(ValueError, match="selected narrator sample"):
        audio_blocks_service._resolve_generation_context(  # noqa: SLF001
            project_root,
            manifest,
            _runtime_settings(),
        )


def test_audio_blocks_service_clone_prompt_matching_uses_sample_language_for_romanian_output(tmp_path) -> None:
    """
    @brief      Verify Romanian output can reuse English reference-sample clone prompts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceRomanianCloneReuse")
    character_voices_service.save_selected_voice_language(project_root, "ro")
    generation_context = audio_blocks_service._resolve_generation_context(  # noqa: SLF001
        project_root,
        manifest,
        _runtime_settings(),
    )
    voice_target = next(
        target for target in generation_context["voice_targets"] if target["voice_target_id"] == "character_alice"
    )
    matching_profile = {
        "voice_target_id": "character_alice",
        "display_name": "Alice",
        "source_sample_relative_path": voice_target["sample_relative_path"],
        "source_sample_fingerprint": voice_target["sample_fingerprint"],
        "source_model_id": "qwen-designer",
        "voice_language": "en",
        "sample_text": "Character preview line.",
        "voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "alice"},
        "prompt_format": "qwen_voice_clone_prompt_v1",
        "generated_at": "2026-04-25T12:00:00+00:00",
        "clone_model_id": generation_context["clone_model_id"],
    }
    wrong_language_profile = {**matching_profile, "voice_language": "fr"}

    assert audio_blocks_service._clone_profile_matches(  # noqa: SLF001
        matching_profile,
        voice_target,
        generation_context,
    )
    assert not audio_blocks_service._clone_profile_matches(  # noqa: SLF001
        wrong_language_profile,
        voice_target,
        generation_context,
    )


def test_audio_blocks_service_clone_prompt_creation_uses_reference_sample_language(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify clone-prompt requests use sample language, not selected output language.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceRomanianCloneCreate")
    character_voices_service.save_selected_voice_language(project_root, "ro")
    generation_context = audio_blocks_service._resolve_generation_context(  # noqa: SLF001
        project_root,
        manifest,
        _runtime_settings(),
    )
    voice_target = next(
        target for target in generation_context["voice_targets"] if target["voice_target_id"] == "character_alice"
    )
    observed_prompt_languages: list[str] = []
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "create_voice_clone_prompt",
        lambda _base_url, _api_key, _sample_audio_bytes, _sample_text, language, **_kwargs: (
            observed_prompt_languages.append(language),
            {"status": "running"},
        )[1],
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "alice"}},
            },
            "result": {},
        },
    )

    clone_profiles, prompt_reused = audio_blocks_service._prepare_clone_profile(  # noqa: SLF001
        generation_context,
        voice_target,
        [],
        _runtime_settings(),
    )

    assert not prompt_reused
    assert observed_prompt_languages == ["en"]
    assert clone_profiles[0]["voice_language"] == "en"


def test_audio_blocks_service_generates_only_approved_speech_blocks(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Audio Blocks generation skips Speech Blocks that are not approved yet.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceApprovedOnly")
    speech_blocks_payload = _read_speech_blocks_fixture_blocks(project_root)
    speech_blocks_payload[1]["approved"] = False
    speech_blocks_payload[1]["approved_at"] = None
    _write_speech_blocks_fixture_document(project_root, speech_blocks_payload)

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
    audio_payloads = [_wav_bytes("narrator")]
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
    assert [audio_blocks_service.is_generated(block) for block in audio_blocks] == [True, False]
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
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceMetadataOnly")
    speech_blocks_payload = _read_speech_blocks_fixture_blocks(project_root)
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
            "approved": False,
            "approved_at": None,
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
    _write_speech_blocks_fixture_document(project_root, speech_blocks_payload)
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
    audio_payloads = [_wav_bytes("narrator"), _wav_bytes("alice")]
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
    assert audio_blocks_service.is_generated(audio_blocks[2]) is True
    assert audio_blocks_service.is_approved(audio_blocks[2]) is True
    assert audio_blocks[2]["audio_relative_path"] is None
    assert audio_blocks[3]["content_kind"] == speech_blocks_service.CONTENT_KIND_INDICATION
    assert audio_blocks[3]["metadata_only"] is True
    assert audio_blocks[3]["audio_relative_path"] is None


def test_audio_blocks_service_preserves_existing_audio_when_block_fingerprint_changes(tmp_path) -> None:
    """
    @brief      Verify existing generated WAV files are not regenerated only because a block fingerprint changed.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksBlockFingerprint")
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    generation_context = audio_blocks_service._resolve_generation_context(  # noqa: SLF001
        project_root,
        manifest,
        _runtime_settings(),
    )
    existing_block = audio_blocks_service._initialize_audio_blocks(speech_blocks)[0]  # noqa: SLF001
    audio_path = audio_blocks_service._audio_artifact_path(  # noqa: SLF001
        project_root,
        str(existing_block["speech_block_id"]),
    )
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(_wav_bytes("stale"))
    existing_block.update(
        {
            "audio_relative_path": audio_path.relative_to(project_root).as_posix(),
            "generated": True,
            "approved": True,
            "audio_can_play": True,
            "generation_fingerprint": "stale-fingerprint",
        }
    )

    merged_blocks = audio_blocks_service._merge_existing_audio_blocks(  # noqa: SLF001
        speech_blocks,
        [existing_block],
        generation_context=generation_context,
        project_root=project_root,
    )

    assert audio_blocks_service.is_generated(merged_blocks[0]) is True
    assert audio_blocks_service.is_approved(merged_blocks[0]) is True
    assert audio_blocks_service.audio_can_play(merged_blocks[0]) is True
    assert merged_blocks[0]["generation_fingerprint"] != "stale-fingerprint"
    assert audio_path.exists()
    assert audio_path.read_bytes() == _wav_bytes("stale")


def test_audio_blocks_service_rejects_invalid_generated_wav_bytes() -> None:
    """
    @brief      Verify downloaded generation payloads must be readable non-empty WAV files.
    @return     None.
    @exception  None
    """
    with pytest.raises(RuntimeError, match="invalid WAV audio"):
        audio_blocks_service._validate_wav_bytes(b"not-a-wav")  # noqa: SLF001


def test_audio_blocks_generation_checkpoints_a_split_block_without_error(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify generating an over-budget block persists its per-part checkpoint and completes.
    @details    Regression guard: the split checkpoint callback is only reached when a block does
                not fit the loaded model budget, so a broken call there survived every test that
                generated short blocks.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksSplitCheckpointRun")
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    long_narration = " ".join(f"Sentence number {index} of the long narration block." for index in range(1, 21))
    speech_blocks[0]["text"] = long_narration
    _write_speech_blocks_fixture_document(project_root, speech_blocks)

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
    active_model = {
        "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
        "status": "ready",
        "supported_generation_modes": ["clone"],
        "default_model_parameters": {"max_new_tokens": 512},
    }
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: {
            "active_model": dict(active_model),
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "narrator"}},
            },
            "result": {"available": True, "summary": "ready"},
        },
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "download_generated_voice",
        lambda *_args, **_kwargs: _wav_bytes("part"),
    )

    report = audio_blocks_service.start_or_continue_generation(project_root, manifest, _runtime_settings())

    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    split_block = next(block for block in audio_blocks if str(block["speech_block_id"]) == "0001-000001")
    assert int(split_block["split_part_count"]) > 1, "the long block must actually exercise the split path"
    assert split_block["generated"] is True
    assert report["generated_block_count"] == len(audio_blocks)


def test_audio_blocks_service_split_resume_rejects_invalid_part_checkpoint(tmp_path) -> None:
    """
    @brief      Verify split resume ignores corrupt or mismatched persisted part checkpoints.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksSplitCheckpoint")
    audio_block = audio_blocks_service._initialize_audio_blocks(  # noqa: SLF001
        speech_blocks_service.load_speech_blocks(project_root)
    )[0]
    split_plan = {"parts": ["Part one.", "Part two."], "strategy": "sentence"}
    part_path = audio_blocks_service._audio_part_artifact_path(  # noqa: SLF001
        project_root,
        str(audio_block["speech_block_id"]),
        0,
    )
    part_path.parent.mkdir(parents=True, exist_ok=True)
    part_path.write_bytes(b"not-a-wav")
    audio_block["generated_part_relative_paths"] = [part_path.relative_to(project_root).as_posix()]
    audio_block["split_plan_fingerprint"] = audio_blocks_service._split_plan_fingerprint(split_plan)  # noqa: SLF001

    assert (
        audio_blocks_service._existing_part_paths(  # noqa: SLF001
            project_root,
            audio_block,
            split_plan,
            force_restart=False,
        )
        == []
    )


@pytest.mark.parametrize("path_kind", ["parent_traversal", "absolute", "unc_like"])
def test_audio_blocks_service_split_resume_rejects_escaping_part_checkpoint(tmp_path, path_kind: str) -> None:
    """
    @brief      Verify split resume refuses persisted part paths outside the project root.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  path_kind Escaping path form under test.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksEscapingSplitCheckpoint")
    outside_path = tmp_path / "outside_part.wav"
    outside_path.write_bytes(_wav_bytes("outside-part"))
    audio_block = audio_blocks_service._initialize_audio_blocks(  # noqa: SLF001
        speech_blocks_service.load_speech_blocks(project_root)
    )[0]
    split_plan = {"parts": ["Part one.", "Part two."], "strategy": "sentence"}
    audio_block["generated_part_relative_paths"] = [
        _escaping_artifact_path(path_kind, "outside_part.wav", outside_path)
    ]
    audio_block["split_plan_fingerprint"] = audio_blocks_service._split_plan_fingerprint(split_plan)  # noqa: SLF001

    assert (
        audio_blocks_service._existing_part_paths(  # noqa: SLF001
            project_root,
            audio_block,
            split_plan,
            force_restart=False,
        )
        == []
    )
    assert outside_path.is_file()


def test_audio_blocks_service_deletes_only_project_relative_artifacts(tmp_path) -> None:
    """
    @brief      Verify stale persisted artifact paths cannot delete files outside the project root.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksEscapingDelete")
    outside_audio_path = tmp_path / "outside.wav"
    outside_metadata_path = tmp_path / "outside.json"
    outside_part_path = tmp_path / "outside_part.wav"
    outside_audio_path.write_bytes(_wav_bytes("outside-audio"))
    outside_metadata_path.write_text("{}\n", encoding="utf-8")
    outside_part_path.write_bytes(_wav_bytes("outside-part"))
    audio_block = {
        "audio_relative_path": "../outside.wav",
        "metadata_relative_path": str(outside_metadata_path.resolve()),
        "generated_part_relative_paths": ["//server/share/outside_part.wav"],
    }

    audio_blocks_service._delete_audio_block_artifacts(project_root, audio_block)  # noqa: SLF001

    assert outside_audio_path.is_file()
    assert outside_metadata_path.is_file()
    assert outside_part_path.is_file()


def _escaping_artifact_path(path_kind: str, traversal_file_name: str, absolute_path) -> str:
    """
    @brief      Build one escaping persisted artifact path for traversal tests.
    @param[in]  path_kind Escaping path form under test.
    @param[in]  traversal_file_name Sibling file name used by parent traversal and UNC-like cases.
    @param[in]  absolute_path Absolute path used by the drive-qualified case.
    @return     Escaping path string.
    @exception  AssertionError Raised when the test path kind is unknown.
    """
    if path_kind == "parent_traversal":
        return f"../{traversal_file_name}"
    if path_kind == "absolute":
        return str(absolute_path.resolve())
    if path_kind == "unc_like":
        return f"//server/share/{traversal_file_name}"
    raise AssertionError(f"Unknown path kind: {path_kind}")


def test_audio_blocks_service_reset_empty_generated_subfolders_are_not_persisted_data(tmp_path) -> None:
    """
    @brief      Verify reset leaves Audio Blocks reset-state detection disabled with empty generated folders.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksResetEmptyFolders")
    parts_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "parts"
    parts_root.mkdir(parents=True)
    (parts_root / "old_part.wav").write_bytes(_wav_bytes("old-part"))

    assert audio_blocks_service.has_persisted_audio_blocks(project_root) is True

    audio_blocks_service.reset_audio_blocks(project_root)

    assert parts_root.is_dir()
    assert audio_blocks_service.has_persisted_audio_blocks(project_root) is False


def test_audio_blocks_service_removes_audio_and_clone_profiles_for_voice_target(tmp_path) -> None:
    """
    @brief      Verify voice-target invalidation deletes only matching Audio Blocks and clone prompts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksVoiceTargetInvalidation")
    _seed_generated_audio_blocks(project_root)
    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    character_block = next(block for block in audio_blocks if str(block["speaker_id"]) == "alice")
    narrator_block = next(block for block in audio_blocks if str(block["speaker_id"]) == "narrator")
    character_audio_path = project_root / str(character_block["audio_relative_path"])
    narrator_audio_path = project_root / str(narrator_block["audio_relative_path"])
    character_target_id = str(character_block["voice_target_id"])
    clone_profiles_path = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME
    )
    clone_profiles = json.loads(clone_profiles_path.read_text(encoding="utf-8"))
    clone_profiles.append(
        {
            "voice_target_id": character_target_id,
            "display_name": "Alice",
            "source_sample_relative_path": "voice_samples/alice.wav",
            "source_sample_fingerprint": "old-alice",
            "source_model_id": "qwen-designer",
            "voice_language": "en",
            "sample_text": "Alice preview line.",
            "voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "alice"},
            "prompt_format": "qwen_voice_clone_prompt_v1",
            "generated_at": "2026-04-23T12:09:00+00:00",
            "clone_model_id": "old-model",
        }
    )
    clone_profiles_path.write_text(json.dumps(clone_profiles, indent=2) + "\n", encoding="utf-8")

    report, deletion_summary = audio_blocks_service.remove_audio_blocks_for_speech_blocks(
        project_root,
        (),
        voice_target_ids=(character_target_id,),
    )

    preserved_blocks = audio_blocks_service.load_audio_blocks(project_root)
    preserved_profiles = audio_blocks_service.load_voice_clone_profiles(project_root)
    assert [block["speech_block_id"] for block in preserved_blocks] == [narrator_block["speech_block_id"]]
    assert [profile["voice_target_id"] for profile in preserved_profiles] == ["narrator"]
    assert report is not None
    assert report["generated_block_count"] == 1
    assert deletion_summary.deleted_count >= 1
    assert not character_audio_path.exists()
    assert narrator_audio_path.exists()


def test_audio_blocks_service_preserves_invalidated_voice_target_rows(tmp_path) -> None:
    """
    @brief      Verify voice-target invalidation can clear generated audio while preserving affected rows.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksVoiceTargetRowPreservation")
    _seed_generated_audio_blocks(project_root)
    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    character_block = next(block for block in audio_blocks if str(block["speaker_id"]) == "alice")
    narrator_block = next(block for block in audio_blocks if str(block["speaker_id"]) == "narrator")
    character_audio_path = project_root / str(character_block["audio_relative_path"])
    narrator_audio_path = project_root / str(narrator_block["audio_relative_path"])
    character_target_id = str(character_block["voice_target_id"])
    clone_profiles_path = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME
    )
    clone_profiles = json.loads(clone_profiles_path.read_text(encoding="utf-8"))
    clone_profiles.append(
        {
            "voice_target_id": character_target_id,
            "display_name": "Alice",
            "source_sample_relative_path": "voice_samples/alice.wav",
            "source_sample_fingerprint": "old-alice",
            "source_model_id": "qwen-designer",
            "voice_language": "en",
            "sample_text": "Alice preview line.",
            "voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "alice"},
            "prompt_format": "qwen_voice_clone_prompt_v1",
            "generated_at": "2026-04-23T12:09:00+00:00",
            "clone_model_id": "old-model",
        }
    )
    clone_profiles_path.write_text(json.dumps(clone_profiles, indent=2) + "\n", encoding="utf-8")

    report, deletion_summary = audio_blocks_service.remove_audio_blocks_for_speech_blocks(
        project_root,
        (),
        voice_target_ids=(character_target_id,),
        preserve_invalidated_blocks=True,
    )

    updated_blocks = audio_blocks_service.load_audio_blocks(project_root)
    preserved_profiles = audio_blocks_service.load_voice_clone_profiles(project_root)
    updated_character_block = next(block for block in updated_blocks if str(block["speaker_id"]) == "alice")
    updated_narrator_block = next(block for block in updated_blocks if str(block["speaker_id"]) == "narrator")
    assert [block["speech_block_id"] for block in updated_blocks] == [
        narrator_block["speech_block_id"],
        character_block["speech_block_id"],
    ]
    assert audio_blocks_service.is_generated(updated_character_block) is False
    assert audio_blocks_service.is_approved(updated_character_block) is False
    assert updated_character_block["audio_relative_path"] is None
    assert updated_character_block["audio_can_play"] is False
    assert updated_character_block["generation_fingerprint"] is None
    assert updated_character_block["split_plan_fingerprint"] is None
    assert updated_narrator_block["audio_relative_path"] == narrator_block["audio_relative_path"]
    assert updated_narrator_block["audio_can_play"] is True
    assert [profile["voice_target_id"] for profile in preserved_profiles] == ["narrator"]
    assert report is not None
    assert report["generated_block_count"] == 1
    assert deletion_summary.deleted_count >= 1
    assert not character_audio_path.exists()
    assert narrator_audio_path.exists()


def test_audio_blocks_service_regenerates_invalidated_voice_target_row_with_stale_state(
    monkeypatch,
    tmp_path,
) -> None:
    """
    @brief      Verify selected regeneration allows a preserved invalidated row after voice sample changes.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksInvalidatedVoiceTargetRegenerate")
    _seed_generated_audio_blocks(project_root)
    _update_audio_blocks_document(project_root, input_fingerprint="stale-before-character-sample-change")

    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    character_block = next(block for block in audio_blocks if str(block["speaker_id"]) == "alice")
    character_target_id = str(character_block["voice_target_id"])
    audio_blocks_service.remove_audio_blocks_for_speech_blocks(
        project_root,
        (),
        voice_target_ids=(character_target_id,),
        preserve_invalidated_blocks=True,
    )

    wait_payloads = [
        {
            "active_model": {"model_id": "Qwen3-TTS-12Hz-1.7B-Base"},
            "operation": {"status": "completed"},
            "result": {},
        },
        {
            "operation": {
                "status": "completed",
                "result": {"voice_clone_prompt": {"format": "qwen_voice_clone_prompt_v1", "speaker": "alice"}},
            },
            "result": {},
        },
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Alice regenerated."}},
    ]
    observed_generate_requests: list[str] = []
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
        lambda *_args, **_kwargs: _wav_bytes("alice-regenerated"),
    )

    report = audio_blocks_service.regenerate_audio_block(
        project_root,
        manifest,
        str(character_block["speech_block_id"]),
        _runtime_settings(),
    )

    regenerated_blocks = audio_blocks_service.load_audio_blocks(project_root)
    regenerated_character_block = next(block for block in regenerated_blocks if str(block["speaker_id"]) == "alice")
    regenerated_narrator_block = next(block for block in regenerated_blocks if str(block["speaker_id"]) == "narrator")
    assert report["generated_block_count"] == 2
    assert observed_generate_requests == ["Hello there."]
    assert audio_blocks_service.is_generated(regenerated_character_block) is True
    assert audio_blocks_service.is_approved(regenerated_character_block) is False
    assert (project_root / str(regenerated_character_block["audio_relative_path"])).read_bytes() == _wav_bytes(
        "alice-regenerated"
    )
    assert audio_blocks_service.is_generated(regenerated_narrator_block) is True


def test_audio_blocks_service_detects_persisted_audio_for_exact_speech_block(tmp_path) -> None:
    """
    @brief      Verify exact Speech Block audio detection does not match sibling blocks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksExactSpeechBlockDetection")
    _seed_generated_audio_blocks(project_root)

    assert audio_blocks_service.has_persisted_audio_for_speech_block(project_root, "0001-000001")
    assert audio_blocks_service.has_persisted_audio_for_speech_block(project_root, "0001-000002")
    assert not audio_blocks_service.has_persisted_audio_for_speech_block(project_root, "9999-999999")


def test_audio_blocks_service_removes_audio_for_exact_speech_block_only(tmp_path) -> None:
    """
    @brief      Verify Speech Block invalidation deletes only the matching Audio Block artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksExactSpeechBlockInvalidation")
    _seed_generated_audio_blocks(project_root)
    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    first_block = audio_blocks[0]
    second_block = audio_blocks[1]
    first_audio_path = project_root / str(first_block["audio_relative_path"])
    second_audio_path = project_root / str(second_block["audio_relative_path"])

    report, deletion_summary = audio_blocks_service.remove_audio_blocks_for_speech_blocks(
        project_root,
        (str(first_block["speech_block_id"]),),
    )

    preserved_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert [block["speech_block_id"] for block in preserved_blocks] == [second_block["speech_block_id"]]
    assert report is not None
    assert report["generated_block_count"] == 1
    assert deletion_summary.deleted_count >= 1
    assert not first_audio_path.exists()
    assert second_audio_path.exists()


def test_audio_blocks_service_approve_and_regenerate_selected_block(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify approving and re-generating one Audio Blocks entry updates only the targeted record.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceApprove")
    _seed_generated_audio_blocks(project_root)

    report = audio_blocks_service.approve_audio_block(project_root, "0001-000001")
    assert report["approved_block_count"] == 1
    updated_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert audio_blocks_service.is_approved(updated_blocks[0]) is True
    assert audio_blocks_service.is_approved(updated_blocks[1]) is False
    approved_audio_path = project_root / str(updated_blocks[0]["audio_relative_path"])
    approved_audio_bytes = approved_audio_path.read_bytes()

    unapprove_report = audio_blocks_service.unapprove_audio_block(project_root, "0001-000001")
    unapproved_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert unapprove_report["approved_block_count"] == 0
    assert audio_blocks_service.is_approved(unapproved_blocks[0]) is False
    assert unapproved_blocks[0]["approved"] is False
    assert approved_audio_path.read_bytes() == approved_audio_bytes

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
    generated_audio = [_wav_bytes("regenerated")]
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
    assert audio_blocks_service.is_approved(regenerated_blocks[0]) is False
    assert (project_root / str(regenerated_blocks[0]["audio_relative_path"])).read_bytes() == _wav_bytes("regenerated")


def test_audio_blocks_service_reconcile_after_resplit_deletes_changed_chunk_and_keeps_later_audio(tmp_path) -> None:
    """
    @brief      Verify Speech Block re-split reconciliation deletes changed-chunk audio and keeps later artifacts.
    @details    Generated audio is named from `speech_block_id`, so a surviving
                block keeps its file without any rename pass.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceResplitReconcile")
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
    )
    audio_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    generated_root = audio_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    generated_root.mkdir(parents=True, exist_ok=True)
    changed_audio_path = generated_root / "0001-000001.wav"
    later_audio_path = generated_root / "0002-000001.wav"
    changed_audio_path.write_bytes(_wav_bytes("old-changed"))
    later_audio_path.write_bytes(_wav_bytes("later"))
    audio_blocks_service.write_audio_blocks_document(
        project_root,
        {
            "status": "completed",
            "voice_language": "en",
            "input_fingerprint": "resplit-fixture",
            "checkpoint": None,
            "blocks": [
                {
                    "speech_block_id": "0001-000001",
                    "voice_target_id": "narrator",
                    "generated": True,
                    "approved": True,
                    "audio_can_play": True,
                    "audio_duration_seconds": None,
                    "generation_fingerprint": None,
                },
                {
                    "speech_block_id": "0002-000001",
                    "voice_target_id": "character_alice",
                    "generated": True,
                    "approved": True,
                    "audio_can_play": True,
                    "audio_duration_seconds": None,
                    "generation_fingerprint": None,
                },
            ],
        },
    )

    report = audio_blocks_service.reset_audio_for_speech_chunk(project_root, "chunk-0001")

    audio_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert report["generated_block_count"] == 1
    assert audio_blocks[0]["speech_block_id"] == "0001-000001"
    assert audio_blocks_service.is_generated(audio_blocks[0]) is False
    assert audio_blocks[1]["speech_block_id"] == "0002-000001"
    assert audio_blocks[1]["sequence_index"] == 1
    assert audio_blocks_service.is_generated(audio_blocks[1]) is True
    assert not changed_audio_path.exists()
    assert later_audio_path.read_bytes() == _wav_bytes("later")
    assert audio_blocks[1]["audio_relative_path"] == later_audio_path.relative_to(project_root).as_posix()


def test_audio_blocks_service_normalize_speaker_name_handles_diacritics() -> None:
    """
    @brief      Verify speaker-name normalization strips punctuation and diacritics into stable ASCII tokens.
    @return     None.
    @exception  None
    """
    assert audio_blocks_service.normalize_speaker_name(" Maria-Elena ÃˆËœtefan!? ") == "maria_elena_stefan"


def test_audio_blocks_service_resume_continues_from_saved_checkpoint(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Audio Blocks resumes from the persisted checkpoint instead of regenerating finished work.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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
    audio_payloads = [_wav_bytes("narrator"), _wav_bytes("alice"), _wav_bytes("alice")]
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
    assert [audio_blocks_service.is_generated(block) for block in persisted_blocks] == [True, False]
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
    assert [audio_blocks_service.is_generated(block) for block in resumed_blocks] == [True, True]
    assert [block["audio_relative_path"] for block in resumed_blocks] == [
        "audio_blocks/0001-000001.wav",
        "audio_blocks/0001-000002.wav",
    ]


def test_audio_blocks_service_continuation_skips_later_existing_audio_after_insert(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify continuation generates only missing Audio Blocks and does not regenerate later existing WAVs.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceContinueMissingOnly")
    _seed_generated_audio_blocks(project_root)
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    speech_blocks[1]["sequence_index"] = 3
    speech_blocks.insert(
        1,
        {
            "speech_block_id": "0001-000003",
            "sequence_index": 2,
            "chunk_id": "chunk-0001",
            "source_language": "en",
            "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            "text": "Inserted narration.",
            "approved": True,
            "approved_at": "2026-05-08T12:00:00+00:00",
            "warning_flags": [],
        },
    )
    _write_speech_blocks_fixture_document(project_root, speech_blocks)
    original_blocks = audio_blocks_service.load_audio_blocks(project_root)
    original_audio_by_id = {
        str(block["speech_block_id"]): (project_root / str(block["audio_relative_path"])).read_bytes()
        for block in original_blocks
    }
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
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Inserted ready."}},
    ]
    observed_generate_requests: list[str] = []
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
        lambda *_args, **_kwargs: _wav_bytes("inserted"),
    )

    report = audio_blocks_service.start_or_continue_generation(project_root, manifest, _runtime_settings())

    updated_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert report["generated_block_count"] == 3
    assert observed_generate_requests == ["Inserted narration."]
    assert (project_root / str(updated_blocks[0]["audio_relative_path"])).read_bytes() == original_audio_by_id[
        "0001-000001"
    ]
    assert (project_root / str(updated_blocks[2]["audio_relative_path"])).read_bytes() == original_audio_by_id[
        "0001-000002"
    ]


def test_audio_blocks_service_input_fingerprint_mismatch_starts_fresh_run(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify stale Audio Blocks input fingerprints start a fresh run under the new schema.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceFingerprint")
    _seed_generated_audio_blocks(project_root)
    _update_audio_blocks_document(project_root, input_fingerprint="stale-fingerprint")
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
        lambda *_args, **_kwargs: _wav_bytes("fresh"),
    )

    report = audio_blocks_service.start_or_continue_generation(
        project_root,
        manifest,
        _runtime_settings(),
    )

    assert report["generated_block_count"] == 2
    refreshed_document = audio_blocks_service.load_audio_blocks_document(project_root)
    assert refreshed_document["input_fingerprint"] != "stale-fingerprint"


def test_audio_blocks_service_prefers_qwen_1_7b_base_model(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Audio Blocks prefers the 1.7B Qwen base model when multiple healthy base models exist.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
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
    audio_payloads = [_wav_bytes("narrator"), _wav_bytes("alice")]
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
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceApproveAll")
    _seed_generated_audio_blocks(project_root)
    document = audio_blocks_service.load_audio_blocks_document(project_root)
    persisted_blocks = [dict(block) for block in document["blocks"]]
    persisted_blocks[1]["generated"] = False
    persisted_blocks[1]["audio_can_play"] = False
    _update_audio_blocks_document(project_root, blocks=persisted_blocks)

    report = audio_blocks_service.approve_all_audio_blocks(project_root)

    updated_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert report["approved_block_count"] == 1
    assert audio_blocks_service.is_approved(updated_blocks[0]) is True
    assert audio_blocks_service.is_approved(updated_blocks[1]) is False


def test_audio_blocks_service_approve_all_promotes_stale_in_progress_state(tmp_path) -> None:
    """
    @brief      Verify Approve All promotes stale in-progress state when the report becomes completed.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksServiceApproveAllStaleState")
    _seed_generated_audio_blocks(project_root)
    _update_audio_blocks_document(project_root, status="in_progress")

    report = audio_blocks_service.approve_all_audio_blocks(project_root)

    operation_state = audio_blocks_service.load_operation_state(project_root)
    manifest = project_workspace_service.load_manifest(project_root)
    assert report["audio_blocks_stage_status"] == audio_blocks_service.AUDIO_BLOCKS_STAGE_COMPLETED
    assert operation_state is not None
    assert operation_state["status"] == "completed"
    assert "completed_at" not in operation_state
    assert operation_state["metadata"]["current_block_id"] is None
    assert manifest["operations"]["audio_blocks"]["status"] == "completed"
    assert "completed_at" not in manifest["operations"]["audio_blocks"]
    assert manifest["current_stage"] == "audio_blocks_ready"


def test_audio_blocks_split_planner_prefers_sentences_then_word_groups() -> None:
    """
    @brief      Verify long Audio Blocks text is split on natural boundaries before word groups.
    @return     None.
    @exception  None
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


def test_audio_blocks_part_artifact_paths_are_keyed_by_speech_block_id(tmp_path) -> None:
    """
    @brief      Verify split-part artifact names derive from `speech_block_id` alone.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    first_chunk_part = audio_blocks_service._audio_part_artifact_path(tmp_path, "0001-000001", 0)  # noqa: SLF001
    second_chunk_part = audio_blocks_service._audio_part_artifact_path(tmp_path, "0002-000001", 0)  # noqa: SLF001

    assert first_chunk_part.name == "0001-000001_part001.wav"
    assert second_chunk_part.name == "0002-000001_part001.wav"
    assert "narrator" not in first_chunk_part.name
    assert first_chunk_part != second_chunk_part


def test_audio_blocks_model_budget_prefers_runtime_effective_parameters() -> None:
    """
    @brief      Verify runtime effective `max_new_tokens` is preferred over model defaults.
    @return     None.
    @exception  None
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


def test_audio_blocks_service_generates_scene_ambience_audio_after_spoken_blocks(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Scene Ambience Audio uses sound_prompt after spoken chunk audio generation.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksSceneAmbience")
    speech_blocks = _read_speech_blocks_fixture_blocks(project_root)
    speech_blocks.append(
        {
            "speech_block_id": "0001-000003",
            "sequence_index": 3,
            "chunk_id": "chunk-0001",
            "source_language": "en",
            "speaker_kind": speech_blocks_service.SPEAKER_KIND_OPERATION,
            "speaker_id": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
            "speaker_display_name": "Scene Ambience",
            "content_kind": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
            "text": "rain in trenches",
            "sound_prompt": "rain in trenches",
            "negative_prompt": "speech",
            "duration_seconds": 5,
            "ambience_position": "closer",
            "approved": True,
            "approved_at": "2026-04-23T12:04:00+00:00",
            "warning_flags": [],
        }
    )
    _write_speech_blocks_fixture_document(project_root, speech_blocks)
    runtime_settings = _runtime_settings()
    runtime_settings["generate_scene_ambience_audio"] = True
    runtime_settings["discovered_models"].append(
        {
            "model_id": "StableAudioOpen",
            "backend_name": "stable-audio-open",
            "status": "healthy",
            "supported_generation_modes": ["sound_prompt"],
        }
    )
    generation_order: list[str] = []
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
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Narrator ready."}},
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Alice ready."}},
        {"active_model": {"model_id": "StableAudioOpen"}, "operation": {"status": "completed"}, "result": {}},
        {"operation": {"status": "completed"}, "result": {"available": True, "summary": "Rain ready."}},
    ]
    audio_payloads = [_wav_bytes("narrator"), _wav_bytes("alice")]
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
        lambda _base_url, _api_key, model_id, **_kwargs: (
            generation_order.append(f"load:{model_id}") or {"status": "running"}
        ),
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "create_voice_clone_prompt",
        lambda *_args, **_kwargs: {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "generate_voice_clone_from_prompt",
        lambda *_args, **_kwargs: generation_order.append("tts") or {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "generate_sound_prompt",
        lambda *_args, **_kwargs: generation_order.append("sound") or {"status": "running"},
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
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "download_generated_audio",
        lambda *_args, **_kwargs: _wav_bytes("rain"),
    )

    audio_blocks_service.start_or_continue_generation(project_root, manifest, runtime_settings)

    generated_blocks = audio_blocks_service.load_audio_blocks(project_root)
    ambience_block = generated_blocks[-1]
    assert generation_order == ["tts", "tts", "load:StableAudioOpen", "sound"]
    assert ambience_block["content_kind"] == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
    assert ambience_block["audio_relative_path"]


def test_audio_blocks_service_regenerates_scene_ambience_without_tts_reset_guard(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify selected Scene Ambience regeneration bypasses stale TTS run fingerprint checks.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None.
    """
    project_root, manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksSceneAmbienceRegenerate")
    speech_blocks = _read_speech_blocks_fixture_blocks(project_root)
    speech_blocks.append(
        {
            "speech_block_id": "0001-000003",
            "sequence_index": 3,
            "chunk_id": "chunk-0001",
            "source_language": "en",
            "speaker_kind": speech_blocks_service.SPEAKER_KIND_OPERATION,
            "speaker_id": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
            "speaker_display_name": "Scene Ambience",
            "content_kind": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
            "text": "distant rain on metal trench covers",
            "sound_prompt": "distant rain on metal trench covers",
            "negative_prompt": "voice, speech",
            "duration_seconds": 6,
            "ambience_position": "scene_change",
            "approved": True,
            "approved_at": "2026-04-23T12:04:00+00:00",
            "warning_flags": [],
        }
    )
    _write_speech_blocks_fixture_document(project_root, speech_blocks)
    audio_blocks_service.write_audio_blocks_document(
        project_root,
        {
            "status": "completed",
            "voice_language": "en",
            "input_fingerprint": "stale-tts-fingerprint",
            "checkpoint": {
                "run_token": "2026-04-23T12:00:00+00:00",
                "current_phase": "generate_blocks",
                "current_block_id": None,
                "next_speech_block_index": 2,
                "next_split_part_index": 0,
            },
            "blocks": [
                {
                    "speech_block_id": speech_block_id,
                    "voice_target_id": voice_target_id,
                    "generated": True,
                    "approved": False,
                    "audio_can_play": True,
                    "audio_duration_seconds": 1.0,
                    "generation_fingerprint": None,
                }
                for speech_block_id, voice_target_id in (
                    ("0001-000001", "narrator"),
                    ("0001-000002", "character_alice"),
                )
            ],
        },
    )
    runtime_settings = _runtime_settings()
    runtime_settings["scene_ambience_guidance_scale"] = 8.5
    runtime_settings["scene_ambience_duration_seconds"] = 11
    runtime_settings["scene_ambience_num_inference_steps"] = 75
    runtime_settings["scene_ambience_seed"] = 321
    runtime_settings["discovered_models"].append(
        {
            "model_id": "StableAudioOpen",
            "backend_name": "stable-audio-open",
            "status": "healthy",
            "supported_generation_modes": ["sound_prompt"],
        }
    )
    sound_requests: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"active_model": {"model_id": "StableAudioOpen"}, "operation": {"status": "idle"}},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "load_model",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("TTS model loading was not expected")),
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "generate_sound_prompt",
        lambda *args, **kwargs: sound_requests.append((args, kwargs)) or {"status": "running"},
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        lambda *_args, **_kwargs: {
            "operation": {"status": "completed"},
            "result": {"available": True, "summary": "Scene ambience ready."},
        },
    )
    monkeypatch.setattr(
        audio_blocks_service.voiceweaver_runtime_service,
        "download_generated_audio",
        lambda *_args, **_kwargs: _wav_bytes("ambience"),
    )

    report = audio_blocks_service.regenerate_audio_block(
        project_root,
        manifest,
        "0001-000003",
        runtime_settings,
    )

    regenerated_blocks = audio_blocks_service.load_audio_blocks(project_root)
    ambience_block = regenerated_blocks[-1]
    assert report["generated_block_count"] == 1
    assert sound_requests
    assert sound_requests[0][0][2] == "distant rain on metal trench covers"
    assert sound_requests[0][1]["negative_prompt"] == "voice, speech"
    assert sound_requests[0][1]["duration_seconds"] == 11.0
    assert sound_requests[0][1]["guidance_scale"] == 8.5
    assert sound_requests[0][1]["num_inference_steps"] == 75
    assert sound_requests[0][1]["seed"] == 321
    assert ambience_block["content_kind"] == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
    assert (project_root / str(ambience_block["audio_relative_path"])).read_bytes() == _wav_bytes("ambience")


def test_audio_blocks_service_reconciles_playability_for_missing_files(tmp_path) -> None:
    """
    @brief      Verify reconciliation heals a stale playability flag whose WAV is gone.
    @details    The document contract always carries `audio_can_play`, so the
                only remaining drift is a persisted `True` for a deleted WAV.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_audio_blocks_project(tmp_path, "AudioBlocksPlayabilityReconcile")
    _seed_generated_audio_blocks(project_root)
    seeded_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert [audio_blocks_service.audio_can_play(block) for block in seeded_blocks] == [True, True]

    (project_root / str(seeded_blocks[0]["audio_relative_path"])).unlink()

    assert audio_blocks_service.reconcile_audio_playability(project_root) is True
    reconciled_blocks = audio_blocks_service.load_audio_blocks(project_root)
    assert [audio_blocks_service.audio_can_play(block) for block in reconciled_blocks] == [False, True]


def _create_audio_blocks_project(tmp_path, name: str):
    """
    @brief      Create one project fixture with approved Speech Blocks and voice samples.
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
    _write_speech_blocks_fixture_document(project_root, speech_blocks_payload)
    narrator_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Test Narrator",
        "English",
        "Narrator prompt.",
        "Narrator preview line.",
    )
    narrator_definition_service.store_profile_sample(
        project_root,
        narrator_profile,
        "Narrator preview line.",
        {
            "generation_mode": "definition",
            "source_model_id": "qwen-designer",
            "language": "en",
        },
        "Narrator sample ready.",
        b"selected-narrator",
    )
    narrator_definition_service.select_narrator_profile(project_root, narrator_profile["profile_id"], "en")
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
    @brief      Write one generated Audio Blocks document plus its clone-profile cache.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    """
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    generation_context = audio_blocks_service._resolve_generation_context(  # noqa: SLF001
        project_root,
        project_workspace_service.load_manifest(project_root),
        _runtime_settings(),
    )
    audio_root = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    )
    audio_root.mkdir(parents=True, exist_ok=True)
    document_blocks = []
    for speech_block in speech_blocks:
        speech_block_id = str(speech_block["speech_block_id"])
        audio_path = audio_root / f"{speech_block_id}.wav"
        audio_path.write_bytes(_wav_bytes(str(speech_block["sequence_index"])))
        fingerprint_block = {
            **speech_block,
            "normalized_speaker_name": audio_blocks_service.normalize_speaker_name(
                str(speech_block["speaker_display_name"])
            ),
            "voice_target_id": (
                "narrator"
                if speech_block["speaker_id"] == "narrator"
                else character_voices_service.character_target_id(speech_block["speaker_id"])
            ),
        }
        document_blocks.append(
            {
                "speech_block_id": speech_block_id,
                "voice_target_id": fingerprint_block["voice_target_id"],
                "generated": True,
                "approved": False,
                "audio_can_play": True,
                "audio_duration_seconds": 1.0,
                "generation_fingerprint": audio_blocks_service._build_audio_block_fingerprint(  # noqa: SLF001
                    fingerprint_block,
                    generation_context,
                ),
            }
        )
    audio_blocks_service.write_audio_blocks_document(
        project_root,
        {
            "status": "in_progress",
            "voice_language": "en",
            "input_fingerprint": "",
            "checkpoint": {
                "run_token": "2026-04-23T12:00:00+00:00",
                "current_phase": "generate_blocks",
                "current_block_id": None,
                "next_speech_block_index": len(document_blocks),
                "next_split_part_index": 0,
            },
            "blocks": document_blocks,
        },
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
                        narrator_definition_service.selected_narrator_sample_path(project_root)
                        .relative_to(project_root)
                        .as_posix()
                    ),
                    "source_sample_fingerprint": "old-narrator",
                    "source_model_id": "qwen-designer",
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


def _wav_bytes(label: str, frame_count: int = 240) -> bytes:
    """
    @brief      Build deterministic non-empty mono PCM WAV bytes for generation tests.
    @param[in]  label Payload label used to vary the sample byte pattern.
    @param[in]  frame_count Number of audio frames.
    @return     WAV payload bytes.
    @exception  None
    """
    sample_value = len(str(label).encode("utf-8")) % 128
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24_000)
        wav_file.writeframes(bytes([sample_value, 0]) * frame_count)
    return buffer.getvalue()


def _runtime_settings() -> dict[str, object]:
    """
    @brief      Build minimal runtime settings with healthy clone-capable Qwen models.
    @return     Runtime settings payload.
    @exception  None
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
                "default_model_parameters": {"max_new_tokens": 512},
            },
            {
                "model_id": "Qwen3-TTS-12Hz-1.7B-Base",
                "backend_name": "qwen3-tts-base",
                "status": "healthy",
                "supported_generation_modes": ["clone"],
                "default_model_parameters": {"max_new_tokens": 512},
            },
        ],
    }



def _update_audio_blocks_document(project_root, **fields):
    """Rewrite selected root fields of the persisted Audio Blocks document."""
    document = audio_blocks_service.load_audio_blocks_document(project_root)
    assert document is not None
    audio_blocks_service.write_audio_blocks_document(project_root, {**document, **fields})


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
