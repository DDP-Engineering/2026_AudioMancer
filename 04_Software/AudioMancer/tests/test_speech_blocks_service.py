#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_speech_blocks_service.py
@brief Focused Speech Blocks service tests for AudioMancer.
@details Verifies source-language resolution, persisted Speech Blocks
         artifacts, warning fallback behavior, dialogue-quote stripping,
         approval/edit state, selected-chunk re-splitting, resumable
         chunk-based generation, and narrator-only segmentation.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.13.12
"""

# IMPORTS

import json
from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import (
    character_discovery_service,
    character_voices_service,
    chunking_document_service,
    project_workspace_service,
    prompt_template_service,
    speech_blocks_service,
)
from chunking_test_support import build_chunking_document

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_resolve_source_chunks_uses_original_when_no_translation(tmp_path) -> None:
    """
    @brief      Verify Speech Blocks uses original chunking text when no translation exists (SPEC-SB-XLAT-PARTIAL).
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.4.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksOriginal")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    # A translated voice language is selected, but no translation exists yet; source stays original.
    character_voices_service.save_selected_voice_language(project_root, "ro")

    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)

    assert source_resolution["source_kind"] == "original"
    assert source_resolution["selected_source_language"] == "en"
    assert source_resolution["source_chunks"][0]["text"] == 'Narration. "Hello there."'


def test_resolve_source_chunks_falls_back_to_original_when_translation_partially_approved(tmp_path) -> None:
    """
    @brief      Verify partial translation approval falls back to original text (SPEC-SB-XLAT-PARTIAL).
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.3.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksTranslationApproval")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "ro")
    _write_translation_artifacts(
        project_root,
        approved_chunk_count=1,
        translated_chunks=[
            {"chunk_id": "chunk-0001", "translated_text": 'Naratiune. "Salut."'},
            {"chunk_id": "chunk-0002", "translated_text": 'Maria a zambit. "Bine ai venit."'},
        ],
    )

    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)

    assert source_resolution["source_kind"] == "original"
    assert source_resolution["selected_source_language"] == "en"
    assert source_resolution["source_chunks"][0]["text"] == 'Narration. "Hello there."'


def test_resolve_source_chunks_uses_translated_when_fully_approved(tmp_path) -> None:
    """
    @brief      Verify a complete, fully approved translation is used as the source (SPEC-SB-XLAT-SOURCE).
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.2.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksTranslated")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "ro")
    _write_translation_artifacts(
        project_root,
        approved_chunk_count=2,
        translated_chunks=[
            {"chunk_id": "chunk-0001", "translated_text": 'Naratiune. "Salut."'},
            {"chunk_id": "chunk-0002", "translated_text": 'Maria a zambit. "Bine ai venit."'},
        ],
    )

    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)

    assert source_resolution["source_kind"] == "translated"
    assert source_resolution["selected_source_language"] == "ro"
    assert source_resolution["source_chunks"][0]["text"] == 'Naratiune. "Salut."'


def test_resolve_source_chunks_uses_translated_regardless_of_selected_voice_language(tmp_path) -> None:
    """
    @brief      Verify an approved translation is used even when the original voice language is selected
                (SPEC-SB-XLAT-SOURCE, REQ-FUNC-e85a7cf0).
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-24
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksTranslatedOverridesVoice")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    # Operator selected the ORIGINAL voice language, yet the translation is complete and fully approved.
    character_voices_service.save_selected_voice_language(project_root, "en")
    _write_translation_artifacts(
        project_root,
        approved_chunk_count=2,
        translated_chunks=[
            {"chunk_id": "chunk-0001", "translated_text": 'Naratiune. "Salut."'},
            {"chunk_id": "chunk-0002", "translated_text": 'Maria a zambit. "Bine ai venit."'},
        ],
    )

    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)

    assert source_resolution["source_kind"] == "translated"
    assert source_resolution["selected_source_language"] == "ro"
    assert source_resolution["source_chunks"][0]["text"] == 'Naratiune. "Salut."'


def test_start_or_continue_generation_creates_artifacts_and_normalizes_blocks(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Speech Blocks generation persists artifacts and normalizes speaker fallback plus dialogue quotes.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksArtifacts")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    character_discovery_service.add_character_profile(project_root, "Maria")

    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    responses = [
        {
            "payload": {
                "blocks": [
                    {
                        "text": "Narration. ",
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    },
                    {
                        "text": '"Hello there."',
                        "speaker_id": "maria",
                        "content_kind": "dialogue",
                        "confidence": "high",
                        "warning_flags": [],
                    },
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
        },
        {
            "payload": {
                "blocks": [
                    {
                        "text": "Maria smiled. ",
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    },
                    {
                        "text": '"Welcome."',
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
                        "confidence": "medium",
                        "warning_flags": ["ambiguous_speaker"],
                    },
                ]
            },
            "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30, "usage_available": True},
        },
    ]
    monkeypatch.setattr(
        speech_blocks_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: responses.pop(0),
    )

    report = speech_blocks_service.start_or_continue_generation(project_root, manifest, _profile_payload())

    speech_blocks_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    assert (speech_blocks_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME).is_file()
    assert not (speech_blocks_root / "speech_blocks_report.json").exists()
    assert not (speech_blocks_root / "speech_blocks_state.json").exists()
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert [block["speech_block_id"] for block in speech_blocks] == [
        "0001-000001",
        "0001-000002",
        "0002-000001",
        "0002-000002",
    ]
    assert [block["approved"] for block in speech_blocks] == [False, False, False, False]
    assert speech_blocks[0]["text"] == "Narration."
    assert speech_blocks[0]["source_text"] == "Narration. "
    assert speech_blocks[1]["speaker_id"] == "maria"
    assert speech_blocks[1]["text"] == "Hello there."
    assert speech_blocks[1]["source_text"] == '"Hello there."'
    assert speech_blocks[2]["speaker_id"] == "narrator"
    assert speech_blocks[2]["content_kind"] == "narration"
    assert speech_blocks[2]["text"] == "Maria smiled."
    assert speech_blocks[3]["speaker_id"] == "narrator"
    assert speech_blocks[3]["content_kind"] == "dialogue"
    assert speech_blocks[3]["warning_flags"] == ["ambiguous_speaker"]
    assert speech_blocks[3]["text"] == "Welcome."
    assert report["warning_count"] == 1
    assert report["token_usage"]["total_tokens"] == 45
    assert report["approved_block_count"] == 0
    assert report["total_block_count"] == 4
    assert report["budget_metadata"]["context_window"] == 4096
    assert report["budget_metadata"]["max_output_tokens"] == 512
    state = speech_blocks_service.load_operation_state(project_root)
    assert state is not None
    assert state["metadata"]["budget_metadata"] == report["budget_metadata"]


def test_start_or_continue_generation_adds_scene_ambience_blocks(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Scene Ambience placement settings insert opener, scene-change, and closer blocks.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-20
    @version    0.2.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksSceneAmbience")
    _write_source_chunks(
        project_root,
        [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Rain falls. The shelling starts."}],
    )
    character_voices_service.save_selected_voice_language(project_root, "en")
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)

    responses = [
        {
            "payload": {
                "blocks": [
                    {
                        "text": "Rain falls. ",
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    },
                    {
                        "text": "The shelling starts.",
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    },
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
        },
        {
            "payload": {
                "scene_ambience_blocks": [
                    {
                        "ambience_position": "opener",
                        "sound_prompt": "steady rain in muddy trenches",
                        "negative_prompt": "speech",
                        "duration_seconds": 4,
                    },
                    {
                        "ambience_position": "scene_change",
                        "after_speech_block_id": "0001-000002",
                        "sound_prompt": "distant artillery begins under heavy rain",
                        "negative_prompt": "speech",
                        "duration_seconds": 6,
                    },
                    {
                        "ambience_position": "closer",
                        "sound_prompt": "rain fading into distant thunder",
                        "negative_prompt": "speech",
                        "duration_seconds": 3,
                    },
                ]
            },
            "usage": {"input_tokens": 8, "output_tokens": 4, "total_tokens": 12, "usage_available": True},
        },
    ]
    captured_requests: list[tuple[str, str]] = []

    def _fake_chat_json(_profile, system_prompt, user_prompt, **_kwargs):
        """
        @brief      Capture Speech Blocks and Scene Ambience prompts while returning fixture responses.
        @param[in]  _profile Ignored AI profile payload.
        @param[in]  system_prompt Rendered system prompt.
        @param[in]  user_prompt Rendered user prompt.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake LLM response payload.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-20
        @version    0.1.0
        """
        captured_requests.append((str(system_prompt), str(user_prompt)))
        return responses.pop(0)

    monkeypatch.setattr(speech_blocks_service.llm_provider_service, "chat_json", _fake_chat_json)

    report = speech_blocks_service.start_or_continue_generation(
        project_root,
        manifest,
        _profile_payload(),
        settings_payload={
            "scene_ambience_placement": "openers_closers_and_scene_changes",
            "scene_ambience_duration_seconds": 5,
            "scene_ambience_max_blocks_per_sequence": 6,
        },
    )

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert [block["content_kind"] for block in speech_blocks] == [
        speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
        speech_blocks_service.CONTENT_KIND_NARRATION,
        speech_blocks_service.CONTENT_KIND_NARRATION,
        speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
        speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
    ]
    assert [block.get("ambience_position") for block in speech_blocks if block["content_kind"] == "scene_ambience"] == [
        "opener",
        "scene_change",
        "closer",
    ]
    assert speech_blocks[0]["text"] == "steady rain in muddy trenches"
    assert speech_blocks[0]["sound_prompt"] == speech_blocks[0]["text"]
    assert all("ambient_sound_type" not in block for block in speech_blocks)
    assert [block["duration_seconds"] for block in speech_blocks if block["content_kind"] == "scene_ambience"] == [
        5.0,
        5.0,
        5.0,
    ]
    assert all("ambience_group_id" not in block for block in speech_blocks)
    assert report["token_usage"]["total_tokens"] == 27
    assert len(captured_requests) == 2
    ambience_system_prompt, ambience_user_prompt = captured_requests[1]
    assert "production-ready sound-design prompts" in ambience_system_prompt
    assert "concrete physical sound sources" in ambience_system_prompt
    assert "continuous beep, pure sine wave, single tone, alarm" in ambience_system_prompt
    assert "Return ordered individual sound blocks" in ambience_user_prompt
    assert "Maximum blocks per sequence: 6" in ambience_user_prompt
    assert "occasional, intermittent, sparse, irregular" in ambience_user_prompt
    assert "describe only the new or changed acoustic layer" in ambience_user_prompt


def test_scene_ambience_none_placement_disables_generation() -> None:
    """
    @brief      Verify the TTS Settings `none` placement disables Scene Ambience generation.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-22
    @version    0.1.0
    """
    settings = speech_blocks_service._resolve_scene_ambience_settings(  # noqa: SLF001
        {"scene_ambience_placement": "none"}
    )

    assert settings["enabled"] is False
    assert settings["allowed_positions"] == []


def test_scene_ambience_normalization_splits_composed_sound_prompts() -> None:
    """
    @brief      Verify composed Scene Ambience prompts become separate sound-source blocks.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-21
    @version    0.1.0
    """
    speech_blocks = speech_blocks_service._normalize_scene_ambience_response(
        {
            "scene_ambience_blocks": [
                {
                    "ambience_position": "opener",
                    "sound_prompt": (
                        "low-volume indoor room tone of a quiet office, "
                        "subtle hum of an air conditioning unit, "
                        "occasional soft electronic whirring from computer hardware"
                    ),
                    "negative_prompt": "speech",
                    "duration_seconds": 6,
                }
            ]
        },
        "chunk-0001",
        "en",
        {
            "allowed_positions": ["opener"],
            "duration_seconds": 10,
            "max_blocks_per_sequence": 6,
        },
    )

    assert [block["sound_prompt"] for block in speech_blocks] == [
        "low-volume indoor room tone of a quiet office",
        "subtle hum of an air conditioning unit",
        "occasional soft electronic whirring from computer hardware",
    ]
    assert [block["duration_seconds"] for block in speech_blocks] == [10.0, 10.0, 10.0]
    assert all(block["content_kind"] == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE for block in speech_blocks)
    assert all("ambience_group_id" not in block for block in speech_blocks)
    assert all("ambient_sound_type" not in block for block in speech_blocks)


def test_start_generation_appends_and_persists_operator_speech_block_rules(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify optional operator Speech Blocks rules are sent to AI prompts and persisted.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksExtraPrompt")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    additional_rules = "Keep stage directions as indication blocks."
    requested_prompts: list[str] = []
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Capture the rendered user prompt and return one simple Speech Blocks response.
        @param[in]  _profile Ignored AI profile payload.
        @param[in]  _system_prompt Ignored system prompt.
        @param[in]  user_prompt Rendered user prompt.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake Speech Blocks response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-13
        @version    0.1.0
        """
        requested_prompts.append(str(user_prompt))
        chunk_text = 'Narration. "Hello there."' if len(requested_prompts) == 1 else 'Maria smiled. "Welcome."'
        return {
            "payload": {
                "blocks": [
                    {
                        "text": chunk_text,
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    }
                ]
            },
            "usage": {"input_tokens": 5, "output_tokens": 4, "total_tokens": 9, "usage_available": True},
        }

    monkeypatch.setattr(speech_blocks_service.llm_provider_service, "chat_json", _fake_chat_json)

    report = speech_blocks_service.start_or_continue_generation(
        project_root,
        manifest,
        _profile_payload(),
        additional_speech_block_instructions=additional_rules,
    )

    state = speech_blocks_service.load_operation_state(project_root)
    assert len(requested_prompts) == 2
    assert all("Additional operator Speech Blocks instructions:" in prompt for prompt in requested_prompts)
    assert all(additional_rules in prompt for prompt in requested_prompts)
    assert report["additional_speech_block_instructions"] == additional_rules
    assert report["additional_speech_block_instructions_fingerprint"] == (
        speech_blocks_service._compute_prompt_fingerprint(additional_rules)  # noqa: SLF001
    )
    assert state is not None
    assert state["metadata"]["additional_speech_block_instructions"] == additional_rules
    assert (
        state["metadata"]["additional_speech_block_instructions_fingerprint"]
        == report["additional_speech_block_instructions_fingerprint"]
    )


def test_start_generation_splits_oversized_chunk_by_ai_context_budget(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify long chunks are split into multiple AI requests using the selected profile context budget.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksBudgetSplit")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    long_chunk_text = " ".join(f"Sentence {index}." for index in range(1, 700))
    _write_source_chunks(project_root, [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": long_chunk_text}])
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)

    def _fake_render_prompt(_name, variables):
        """
        @brief      Provide the fake render prompt test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        if "chunk_text" not in variables:
            return "system prompt"
        return f"Chunk id: {variables['chunk_id']}\nChunk text:\n{variables['chunk_text']}"

    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "render_prompt", _fake_render_prompt)
    requested_segments: list[str] = []

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Provide the fake chat json test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        segment_text = str(user_prompt).split("Chunk text:\n", maxsplit=1)[1]
        requested_segments.append(segment_text)
        return {
            "payload": {
                "blocks": [
                    {
                        "text": segment_text,
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    }
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
        }

    monkeypatch.setattr(speech_blocks_service.llm_provider_service, "chat_json", _fake_chat_json)
    profile_payload = {**_profile_payload(), "context_window": 2048, "max_output_tokens": 512}

    report = speech_blocks_service.start_or_continue_generation(project_root, manifest, profile_payload)

    assert len(requested_segments) > 1
    assert "".join(requested_segments) == long_chunk_text
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert [block["speech_block_id"] for block in speech_blocks] == [
        f"0001-{index:06d}" for index in range(1, len(speech_blocks) + 1)
    ]
    assert report["budget_metadata"]["text_budget_tokens"] < speech_blocks_service._estimate_text_tokens(  # noqa: SLF001
        long_chunk_text
    )


def test_speech_blocks_direct_generation_splits_large_chunk_by_output_safety_cap(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify direct Speech Blocks generation caps source segments for output safety.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-07
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksDirectOutputCap")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    long_chunk_text = " ".join(f"Sentence {index}." for index in range(1, 1400))
    _write_source_chunks(project_root, [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": long_chunk_text}])
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: (
            f"Chunk text:\n{variables['chunk_text']}" if "chunk_text" in variables else "system prompt"
        ),
    )
    requested_segments: list[str] = []

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Provide a direct-block model response for one requested segment.
        @return     Fake direct Speech Blocks response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-07
        @version    0.1.0
        """
        segment_text = str(user_prompt).split("Chunk text:\n", maxsplit=1)[1]
        requested_segments.append(segment_text)
        return {
            "payload": {
                "blocks": [
                    {
                        "text": segment_text,
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    }
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
        }

    monkeypatch.setattr(speech_blocks_service.llm_provider_service, "chat_json", _fake_chat_json)
    profile_payload = {**_profile_payload(), "context_window": 32768, "max_output_tokens": 512}

    speech_blocks_service.start_or_continue_generation(project_root, manifest, profile_payload)

    assert len(requested_segments) > 1
    assert "".join(requested_segments) == long_chunk_text
    assert all(speech_blocks_service._estimate_text_tokens(segment) <= 2000 for segment in requested_segments)  # noqa: SLF001


def test_start_generation_direct_malformed_json_falls_back_for_segment_only(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify malformed direct JSON falls back one segment and generation continues.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-07
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksDirectMalformedSegment")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    _write_source_chunks(project_root, [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "First.Second."}])
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: (
            f"Chunk text:\n{variables['chunk_text']}" if "chunk_text" in variables else "system prompt"
        ),
    )
    monkeypatch.setattr(
        speech_blocks_service,
        "_budgeted_source_chunk_segments",
        lambda _source_chunk, _budget_metadata, **_kwargs: [
            {"chunk_id": "chunk-0001", "text": "First."},
            {"chunk_id": "chunk-0001", "text": "Second."},
        ],
    )
    calls: list[str] = []

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Fail the first segment and return a direct block for the second.
        @return     Fake direct Speech Blocks response.
        @exception  ValueError Raised for the first segment.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-07
        @version    0.1.0
        """
        calls.append(str(user_prompt))
        if len(calls) == 1:
            raise ValueError("malformed json")
        segment_text = str(user_prompt).split("Chunk text:\n", maxsplit=1)[1]
        return {
            "payload": {
                "blocks": [
                    {
                        "text": segment_text,
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    }
                ]
            },
            "usage": {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6, "usage_available": True},
        }

    monkeypatch.setattr(speech_blocks_service.llm_provider_service, "chat_json", _fake_chat_json)

    speech_blocks_service.start_or_continue_generation(project_root, manifest, _profile_payload())

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert len(calls) == 2
    assert [block["source_text"] for block in speech_blocks] == ["First.", "Second."]
    assert "speech_blocks_ai_parse_failed" in speech_blocks[0]["warning_flags"]
    assert "needs_review" in speech_blocks[0]["warning_flags"]
    assert speech_blocks[1]["warning_flags"] == []


def test_speech_blocks_resume_continues_from_unfinished_direct_segment(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify direct Speech Blocks resume skips completed segments in the active chunk.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-07
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksDirectSegmentResume")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    _write_source_chunks(project_root, [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "First.Second."}])
    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)
    existing_blocks = [
        {
            "speech_block_id": "0001-000001",
            "sequence_index": 1,
            "chunk_id": "chunk-0001",
            "source_language": "en",
            "speaker_kind": "narrator",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": "narration",
            "source_text": "First.",
            "text": "First.",
            "warning_flags": [],
            "approved": False,
            "approved_at": None,
        }
    ]
    fingerprint = speech_blocks_service._build_source_fingerprint(source_resolution["source_chunks"], "en", "original")  # noqa: SLF001
    budget_metadata = speech_blocks_service._build_budget_metadata(  # noqa: SLF001
        _profile_payload(),
        "system prompt",
        "speech_blocks_user",
        "en",
        speech_blocks_service._speaker_catalog([]),  # noqa: SLF001
        config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
        speech_blocks_service._resolve_narrator_only_budget(None),  # noqa: SLF001
    )
    report = speech_blocks_service._rebuild_report(  # noqa: SLF001
        existing_blocks,
        "en",
        "original",
        "profile-1",
        1,
        0,
        [],
        {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "usage_available": True},
        budget_metadata,
    )
    operation_state = speech_blocks_service._build_operation_state(  # noqa: SLF001
        project_root,
        source_resolution["source_chunks"],
        existing_blocks,
        status="running",
        started_at="2026-07-07T06:00:00+00:00",
        completed_at=None,
        source_language="en",
        source_kind="original",
        profile_id="profile-1",
        warning_records=[],
        input_fingerprint=fingerprint,
        log_path=project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / "log_ai_transactions_resume.log",
        token_usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "usage_available": True},
        next_chunk_index=0,
        budget_metadata=budget_metadata,
    )
    operation_state["metadata"]["speech_blocks_response_contract"] = "direct_blocks"
    operation_state["resume_checkpoint"]["speech_blocks_response_contract"] = "direct_blocks"
    operation_state["resume_checkpoint"]["active_chunk_id"] = "chunk-0001"
    operation_state["resume_checkpoint"]["next_chunk_index"] = 0
    operation_state["resume_checkpoint"]["next_segment_index"] = 1
    operation_state["resume_checkpoint"]["completed_segment_count"] = 1
    speech_blocks_service._persist_state(  # noqa: SLF001
        project_root,
        source_resolution["source_chunks"],
        existing_blocks,
        report,
        operation_state,
    )
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: (
            f"Chunk text:\n{variables['chunk_text']}" if "chunk_text" in variables else "system prompt"
        ),
    )
    monkeypatch.setattr(
        speech_blocks_service,
        "_budgeted_source_chunk_segments",
        lambda _source_chunk, _budget_metadata, **_kwargs: [
            {"chunk_id": "chunk-0001", "text": "First."},
            {"chunk_id": "chunk-0001", "text": "Second."},
        ],
    )
    requested_segments: list[str] = []

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Return a direct block for the requested resumed segment.
        @return     Fake direct Speech Blocks response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-07
        @version    0.1.0
        """
        segment_text = str(user_prompt).split("Chunk text:\n", maxsplit=1)[1]
        requested_segments.append(segment_text)
        return {
            "payload": {
                "blocks": [
                    {
                        "text": segment_text,
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    }
                ]
            },
            "usage": {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6, "usage_available": True},
        }

    monkeypatch.setattr(speech_blocks_service.llm_provider_service, "chat_json", _fake_chat_json)

    speech_blocks_service.start_or_continue_generation(project_root, manifest, _profile_payload())

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert requested_segments == ["Second."]
    assert [block["source_text"] for block in speech_blocks] == ["First.", "Second."]
    assert [block["speech_block_id"] for block in speech_blocks] == ["0001-000001", "0001-000002"]


def test_start_generation_rejects_profile_with_too_little_ai_context(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Speech Blocks fails early when context and output budgets leave too little source input room.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksTinyBudget")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    profile_payload = {**_profile_payload(), "context_window": 1024, "max_output_tokens": 900}

    with pytest.raises(ValueError, match="too little room for source chunk input"):
        speech_blocks_service.start_or_continue_generation(project_root, manifest, profile_payload)


def test_speech_blocks_online_profile_uses_direct_context_fraction(monkeypatch) -> None:
    """
    @brief      Verify online Speech Blocks budgets ignore output-token budget subtraction.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    profile_payload = {
        **_profile_payload(),
        "backend_kind": config.ONLINE_AI_BACKEND_KIND,
        "context_window": 10000,
        "max_output_tokens": 9900,
    }

    budget_metadata = speech_blocks_service._build_budget_metadata(
        profile_payload,
        "system",
        "speech_blocks_user",
        "en",
        {"narrator": {"speaker_id": "narrator", "display_name": "Narrator"}},
        config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
        speech_blocks_service._resolve_narrator_only_budget(None),
    )

    assert budget_metadata["text_budget_tokens"] == 3000


def test_speech_blocks_resume_accepts_changed_profile_and_budget_metadata(tmp_path) -> None:
    """
    @brief      Verify Speech Blocks resume accepts a new profile and context-budget metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.2.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksBudgetResume")
    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)
    source_chunks = list(source_resolution["source_chunks"])
    input_fingerprint = speech_blocks_service._build_source_fingerprint(source_chunks, "en", "original")  # noqa: SLF001
    previous_budget = {
        "context_window": 4096,
        "max_output_tokens": 1024,
        "prompt_budget_tokens": 40,
        "text_budget_tokens": 2000,
        "safety_margin_tokens": 409,
    }

    restored = speech_blocks_service._restore_resume_state(  # noqa: SLF001
        project_root,
        {
            "status": "running",
            "metadata": {
                "source_snapshot_fingerprint": input_fingerprint,
                "ai_profile_id": "profile-1",
                "source_language": "en",
                "speech_blocks_response_contract": "source_span_selection",
                "warnings": [],
            },
            "resume_checkpoint": {
                "next_chunk_index": 1,
                "source_snapshot_fingerprint": input_fingerprint,
                "source_language": "en",
                "ai_profile_id": "profile-1",
                "speech_blocks_response_contract": "source_span_selection",
                "budget_metadata": previous_budget,
            },
        },
        None,
        input_fingerprint,
        "en",
        len(source_chunks),
        speech_blocks_service._compute_prompt_fingerprint(""),  # noqa: SLF001
    )

    assert restored == ([], [], 0)


def test_speech_blocks_resume_accepts_changed_scene_ambience_settings(tmp_path) -> None:
    """
    @brief      Verify Speech Blocks resume is not invalidated by Scene Ambience setting changes.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-22
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksAmbienceResume")
    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)
    source_chunks = list(source_resolution["source_chunks"])
    input_fingerprint = speech_blocks_service._build_source_fingerprint(source_chunks, "en", "original")  # noqa: SLF001
    current_scene_settings = speech_blocks_service._resolve_scene_ambience_settings(  # noqa: SLF001
        {"scene_ambience_placement": "openers_and_closers"}
    )

    restored = speech_blocks_service._restore_resume_state(  # noqa: SLF001
        project_root,
        {
            "status": "running",
            "metadata": {
                "source_snapshot_fingerprint": input_fingerprint,
                "source_language": "en",
                "speech_blocks_response_contract": "source_span_selection",
                "additional_speech_block_instructions_fingerprint": (
                    speech_blocks_service._compute_generation_rules_fingerprint("", current_scene_settings)  # noqa: SLF001
                ),
                "scene_ambience_generation": {
                    "enabled": False,
                    "placement_policy": "none",
                    "duration_seconds": 10,
                    "max_blocks_per_sequence": 6,
                    "allowed_positions": [],
                },
            },
            "resume_checkpoint": {
                "next_chunk_index": 1,
                "source_snapshot_fingerprint": input_fingerprint,
                "source_language": "en",
                "speech_blocks_response_contract": "source_span_selection",
            },
        },
        None,
        input_fingerprint,
        "en",
        len(source_chunks),
        speech_blocks_service._compute_generation_rules_fingerprint("", current_scene_settings),  # noqa: SLF001
    )

    assert restored == ([], [], 0)


def test_speech_blocks_resume_ignores_source_chunk_count_without_processed_count(tmp_path) -> None:
    """
    @brief      Verify Speech Blocks resume ignores old source-chunk-count fallback metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksNoSourceChunkFallback")
    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)

    restored_index = speech_blocks_service._restore_next_speech_blocks_chunk_index(  # noqa: SLF001
        {"status": "review_pending"},
        None,
        {"source_chunks": source_resolution["source_chunks"]},
        {},
        len(source_resolution["source_chunks"]),
    )

    assert restored_index == 0


def test_speech_blocks_resume_restarts_previous_full_cast_state(tmp_path) -> None:
    """
    @brief      Verify previous narrator-and-character partial state is treated as non-resumable.
    @details    Covers SBCON-004 and REQ-FUNC-041.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksPreviousResume")
    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)
    source_chunks = list(source_resolution["source_chunks"])
    input_fingerprint = speech_blocks_service._build_source_fingerprint(source_chunks, "en", "original")  # noqa: SLF001

    restored = speech_blocks_service._restore_resume_state(  # noqa: SLF001
        project_root,
        {
            "status": "running",
            "metadata": {
                "source_snapshot_fingerprint": input_fingerprint,
                "source_language": "en",
                "voice_assignment_mode": "narrator_and_characters",
            },
            "resume_checkpoint": {
                "next_chunk_index": 1,
                "source_snapshot_fingerprint": input_fingerprint,
                "source_language": "en",
            },
        },
        None,
        input_fingerprint,
        "en",
        len(source_chunks),
        speech_blocks_service._compute_prompt_fingerprint(""),  # noqa: SLF001
    )

    assert restored == ([], [], 0)


@pytest.mark.parametrize(
    ("response_contract", "expected_next_chunk_index"),
    [
        ("deterministic_narrator_blocks", 1),
        ("narrator_boundary_ids", 0),
    ],
)
def test_same_narrator_resume_depends_on_the_recorded_response_contract(
    tmp_path,
    response_contract: str,
    expected_next_chunk_index: int,
) -> None:
    """
    @brief      Verify only current-contract same-narrator state resumes, retired state restarts.
    @details    Covers SBCON-004 and REQ-FUNC-041. Resuming a retired narrator-boundary run
                would leave one document holding two different segmentations.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  response_contract Persisted response contract under test.
    @param[in]  expected_next_chunk_index Chunk index generation must continue from.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.2.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksSameNarratorResume")
    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)
    source_chunks = list(source_resolution["source_chunks"])
    input_fingerprint = speech_blocks_service._build_source_fingerprint(source_chunks, "en", "original")  # noqa: SLF001

    restored = speech_blocks_service._restore_resume_state(  # noqa: SLF001
        project_root,
        {
            "status": "running",
            "metadata": {
                "source_snapshot_fingerprint": input_fingerprint,
                "source_language": "en",
                "voice_assignment_mode": "same_narrator",
                "speech_blocks_response_contract": response_contract,
            },
            "resume_checkpoint": {
                "next_chunk_index": 1,
                "source_snapshot_fingerprint": input_fingerprint,
                "source_language": "en",
                "speech_blocks_response_contract": response_contract,
            },
        },
        None,
        input_fingerprint,
        "en",
        len(source_chunks),
        speech_blocks_service._compute_prompt_fingerprint(""),  # noqa: SLF001
    )

    assert restored == ([], [], expected_next_chunk_index)


def test_legacy_narrator_boundary_project_regenerates_without_error(tmp_path) -> None:
    """
    @brief      Verify a project left on the retired contract regenerates cleanly after upgrade.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksLegacyContract")
    manifest["original_language"] = "en"
    manifest["voice_assignment_mode"] = "same_narrator"
    manifest["project_options_locked"] = True
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    speech_blocks_service.start_or_continue_generation(project_root, manifest, {})

    document = speech_blocks_service.load_speech_blocks_document(project_root)
    document["response_contract"] = "narrator_boundary_ids"
    document["status"] = "running"
    speech_blocks_service.write_speech_blocks_document(project_root, document)

    report = speech_blocks_service.start_or_continue_generation(project_root, manifest, {})

    assert report["total_block_count"] > 0
    reloaded = speech_blocks_service.load_speech_blocks_document(project_root)
    assert reloaded["response_contract"] == "deterministic_narrator_blocks"


def test_insert_speech_block_appends_after_selected_block(tmp_path) -> None:
    """
    @brief      Verify manual insertion after a selected block resequences only that chunk.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.3.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksInsert")
    _seed_review_speech_blocks(project_root)

    _report, inserted_id = speech_blocks_service.insert_speech_block(project_root, "chunk-0001", "0001-000001")

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert inserted_id == "0001-000002"
    assert [block["speech_block_id"] for block in speech_blocks] == [
        "0001-000001",
        "0001-000002",
        "0002-000001",
    ]
    assert speech_blocks[0]["text"] == "Hello."
    assert speech_blocks[1]["speaker_id"] == "narrator"
    assert speech_blocks[1]["content_kind"] == speech_blocks_service.CONTENT_KIND_NARRATION
    assert speech_blocks[1]["text"] == ""
    assert speech_blocks[1]["approved"] is False
    assert speech_blocks[2]["text"] == "Later narration."


def test_insert_speech_block_into_empty_chunk_creates_unapproved_narration(tmp_path) -> None:
    """
    @brief      Verify manual insertion can recreate the first block in an empty source chunk.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksInsertEmpty")
    _seed_review_speech_blocks(project_root)
    speech_blocks_service.delete_speech_block(project_root, "0001-000001")

    _report, inserted_id = speech_blocks_service.insert_speech_block(project_root, "chunk-0001")

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    inserted_block = next(block for block in speech_blocks if str(block["speech_block_id"]) == inserted_id)
    assert inserted_id == "0001-000001"
    assert inserted_block["chunk_id"] == "chunk-0001"
    assert inserted_block["speaker_id"] == "narrator"
    assert inserted_block["content_kind"] == speech_blocks_service.CONTENT_KIND_NARRATION
    assert inserted_block["approved"] is False


def test_insert_speech_block_initializes_manual_state_without_generation(tmp_path) -> None:
    """
    @brief      Verify manual insertion can start Speech Blocks state directly from source chunks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksManualInsert")

    report, inserted_id = speech_blocks_service.insert_speech_block(project_root, "chunk-0001")

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    operation_state = speech_blocks_service.load_operation_state(project_root)
    manifest = project_workspace_service.load_manifest(project_root)
    assert inserted_id == "0001-000001"
    assert len(speech_blocks) == 1
    assert speech_blocks[0]["chunk_id"] == "chunk-0001"
    assert speech_blocks[0]["speaker_id"] == "narrator"
    assert speech_blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_NARRATION
    assert speech_blocks[0]["approved"] is False
    assert report["speech_blocks_stage_status"] == speech_blocks_service.SPEECH_BLOCKS_STAGE_IN_PROGRESS
    assert report["processed_chunk_count"] == 1
    assert report["total_chunk_count"] == 2
    assert operation_state is not None
    assert operation_state["status"] == "review_pending"
    assert "source_chunks" not in operation_state["metadata"]
    assert operation_state["metadata"]["total_chunk_count"] == 2
    assert manifest["operations"]["speech_blocks"]["status"] == "review_pending"
    assert manifest["current_stage"] == "character_voices_ready"

    delete_report = speech_blocks_service.delete_speech_block(project_root, inserted_id)
    cleared_state = speech_blocks_service.load_operation_state(project_root)
    cleared_manifest = project_workspace_service.load_manifest(project_root)

    assert delete_report["speech_blocks_stage_status"] == speech_blocks_service.SPEECH_BLOCKS_STAGE_NOT_STARTED
    assert delete_report["processed_chunk_count"] == 0
    assert delete_report["total_chunk_count"] == 2
    assert cleared_state is not None
    assert cleared_state["status"] == "not_started"
    assert cleared_manifest["operations"]["speech_blocks"]["status"] == "not_started"
    assert cleared_manifest["current_stage"] == "character_voices_ready"


def test_insert_speech_block_after_first_manual_block_appends_next_block(tmp_path) -> None:
    """
    @brief      Verify repeated manual insertion after the selected first block appends the next local block.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksManualAppend")

    _report, first_inserted_id = speech_blocks_service.insert_speech_block(project_root, "chunk-0001")
    _report, second_inserted_id = speech_blocks_service.insert_speech_block(
        project_root,
        "chunk-0001",
        first_inserted_id,
    )

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert first_inserted_id == "0001-000001"
    assert second_inserted_id == "0001-000002"
    assert [block["speech_block_id"] for block in speech_blocks] == ["0001-000001", "0001-000002"]
    assert [block["sequence_index"] for block in speech_blocks] == [1, 2]


def test_delete_speech_block_renumbers_remaining_chunk_blocks(tmp_path) -> None:
    """
    @brief      Verify manual deletion removes the selected block and resequences remaining blocks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksDelete")
    _seed_review_speech_blocks(project_root)
    _report, inserted_id = speech_blocks_service.insert_speech_block(project_root, "chunk-0001", "0001-000001")

    speech_blocks_service.delete_speech_block(project_root, inserted_id)

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert [block["speech_block_id"] for block in speech_blocks] == ["0001-000001", "0002-000001"]
    assert speech_blocks[0]["text"] == "Hello."


def test_delete_unknown_speech_block_raises(tmp_path) -> None:
    """
    @brief      Verify deleting an unknown Speech Block reports a service error.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksDeleteUnknown")
    _seed_review_speech_blocks(project_root)

    with pytest.raises(ValueError, match="not found"):
        speech_blocks_service.delete_speech_block(project_root, "9999-999999")


def test_indication_content_kind_normalizes_and_pause_duration_parses(tmp_path) -> None:
    """
    @brief      Verify indication persists as a content kind and pause duration parsing has a default.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksIndication")
    _seed_review_speech_blocks(project_root)

    speech_blocks_service.update_speech_block(
        project_root,
        "0001-000001",
        "narrator",
        "Indication",
        "[whisper]",
    )

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert speech_blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_INDICATION
    assert speech_blocks[0]["speaker_kind"] == speech_blocks_service.SPEAKER_KIND_OPERATION
    assert speech_blocks[0]["speaker_id"] == speech_blocks_service.CONTENT_KIND_INDICATION
    assert speech_blocks[0]["speaker_display_name"] == "Indication"
    assert speech_blocks_service.pause_duration_ms("pause 2500 ms") == 2500
    assert speech_blocks_service.pause_duration_ms("pause") == config.DEFAULT_SPEECH_BLOCK_PAUSE_DURATION_MS


def test_same_narrator_edit_forces_narration_but_preserves_operations(tmp_path) -> None:
    """
    @brief      Verify same-narrator manual edits keep narrator flow while preserving operation labels.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksSameNarratorEdit")
    manifest["voice_assignment_mode"] = "same_narrator"
    project_workspace_service.save_manifest(manifest, project_root)
    _seed_review_speech_blocks(project_root)

    speech_blocks_service.update_speech_block(
        project_root,
        "0001-000001",
        "unknown-character",
        speech_blocks_service.CONTENT_KIND_DIALOGUE,
        "Narrator reads everything.",
    )
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert speech_blocks[0]["speaker_kind"] == speech_blocks_service.SPEAKER_KIND_NARRATOR
    assert speech_blocks[0]["speaker_id"] == "narrator"
    assert speech_blocks[0]["speaker_display_name"] == "Narrator"
    assert speech_blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_NARRATION

    speech_blocks_service.update_speech_block(
        project_root,
        "0001-000001",
        "unknown-character",
        speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
        {
            "sound_prompt": "Wind against the shutters.",
            "negative_prompt": "speech, music",
            "duration_seconds": 3.5,
        },
    )
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert speech_blocks[0]["speaker_kind"] == speech_blocks_service.SPEAKER_KIND_OPERATION
    assert speech_blocks[0]["speaker_id"] == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
    assert speech_blocks[0]["speaker_display_name"] == "Scene Ambience"
    assert speech_blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
    assert speech_blocks[0]["sound_prompt"] == "Wind against the shutters."
    assert speech_blocks[0]["negative_prompt"] == "speech, music"
    assert speech_blocks[0]["duration_seconds"] == 3.5


def test_null_like_started_at_creates_timestamped_speech_blocks_log(tmp_path) -> None:
    """
    @brief      Verify null-like persisted timestamps do not produce `None` Speech Blocks log names.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksNullTimestamp")

    started_at = speech_blocks_service._resolve_started_at({"started_at": None})  # noqa: SLF001
    log_path = speech_blocks_service._resolve_log_path(project_root, started_at)  # noqa: SLF001

    assert started_at != "None"
    assert "None" not in log_path.name
    assert log_path.name.startswith("log_ai_speech_blocks_")


def test_review_update_replaces_null_like_started_at(tmp_path) -> None:
    """
    @brief      Verify review-only Speech Blocks saves replace null-like operation timestamps.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksReviewNullTimestamp")
    _seed_review_speech_blocks(project_root)
    document = speech_blocks_service.load_speech_blocks_document(project_root)
    document["checkpoint"]["run_token"] = "None"
    document["checkpoint"]["log_relative_path"] = "log_ai_speech_blocks_None.log"
    speech_blocks_service.write_speech_blocks_document(project_root, document)

    speech_blocks_service.approve_speech_block(project_root, "0001-000001")

    updated_state = speech_blocks_service.load_operation_state(project_root)
    assert updated_state is not None
    assert updated_state["started_at"] != "None"
    assert updated_state["completed_at"] != "null"
    assert all("None" not in str(path) for path in updated_state["artifact_paths"])


def test_approve_all_and_edit_preserve_warning_cleared_state(tmp_path) -> None:
    """
    @brief      Verify approval plus selected-block edit warning state semantics.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.1
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksApprovalEdit")
    _seed_review_speech_blocks(project_root)

    approved_report = speech_blocks_service.approve_all_speech_blocks(project_root)
    approved_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert approved_report["approved_block_count"] == 2
    assert approved_report["total_block_count"] == 2
    assert approved_report["warning_count"] == 0
    assert approved_report["speech_blocks_stage_status"] == speech_blocks_service.SPEECH_BLOCKS_STAGE_COMPLETED
    assert approved_blocks[0]["warning_flags"] == []

    edited_report = speech_blocks_service.update_speech_block(
        project_root,
        "0001-000001",
        "narrator",
        speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
        "Wind against the shutters.",
    )
    edited_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert edited_report["warning_count"] == 0
    assert edited_blocks[0]["warning_flags"] == []
    assert edited_blocks[0]["approved"] is False
    assert edited_blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
    assert edited_blocks[0]["speaker_kind"] == speech_blocks_service.SPEAKER_KIND_OPERATION
    assert edited_blocks[0]["speaker_id"] == speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE
    assert edited_blocks[0]["speaker_display_name"] == "Scene Ambience"
    assert edited_blocks[0]["text"] == "Wind against the shutters."


def test_approve_selected_speech_block_only_marks_target_block(tmp_path) -> None:
    """
    @brief      Verify selected Speech Block approval does not approve sibling blocks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.1
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksSelectedApproval")
    _seed_review_speech_blocks(project_root)

    report = speech_blocks_service.approve_speech_block(project_root, "0001-000001")
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)

    assert report["approved_block_count"] == 1
    assert report["total_block_count"] == 2
    assert report["warning_count"] == 0
    assert report["speech_blocks_stage_status"] == speech_blocks_service.SPEECH_BLOCKS_STAGE_IN_PROGRESS
    assert speech_blocks[0]["approved"] is True
    assert speech_blocks[0]["approved_at"] is not None
    assert speech_blocks[0]["warning_flags"] == []
    assert speech_blocks[1]["approved"] is False
    assert speech_blocks[1]["approved_at"] is None


def test_unapprove_selected_speech_block_only_clears_target_block(tmp_path) -> None:
    """
    @brief      Verify selected Speech Block unapproval does not clear sibling approvals.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-05
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksSelectedUnapproval")
    _seed_review_speech_blocks(project_root)
    speech_blocks_service.approve_all_speech_blocks(project_root)

    report = speech_blocks_service.unapprove_speech_block(project_root, "0002-000001")
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)

    assert report["approved_block_count"] == 1
    assert report["total_block_count"] == 2
    assert report["speech_blocks_stage_status"] == speech_blocks_service.SPEECH_BLOCKS_STAGE_IN_PROGRESS
    assert speech_blocks[0]["approved"] is True
    assert speech_blocks[0]["approved_at"] is not None
    assert speech_blocks[1]["approved"] is False
    assert speech_blocks[1]["approved_at"] is None


def test_update_character_speech_block_display_name_preserves_approval(tmp_path) -> None:
    """
    @brief      Verify character display-name refreshes do not revoke Speech Block approval.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-08
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksCharacterDisplayName")
    _seed_review_speech_blocks(project_root)
    document = speech_blocks_service.load_speech_blocks_document(project_root)
    document["blocks"][0]["speaker_kind"] = speech_blocks_service.SPEAKER_KIND_CHARACTER
    document["blocks"][0]["speaker_id"] = "alice"
    document["blocks"][0]["speaker_display_name"] = "Alice"
    document["blocks"][0]["approved"] = True
    document["blocks"][0]["approved_at"] = "2026-04-24T12:00:00+00:00"
    speech_blocks_service.write_speech_blocks_document(project_root, document)

    report, affected_ids = speech_blocks_service.update_character_speech_block_display_name(
        project_root,
        "alice",
        display_name="Alice Renamed",
    )

    updated_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert report is not None
    assert affected_ids == ("0001-000001",)
    assert updated_blocks[0]["speaker_display_name"] == "Alice Renamed"
    assert updated_blocks[0]["approved"] is True
    assert updated_blocks[0]["approved_at"] == "2026-04-24T12:00:00+00:00"
    assert updated_blocks[1]["speaker_display_name"] == "Narrator"


def test_regenerate_selected_chunk_replaces_chunk_and_renumbers_following_blocks(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify selected-chunk re-splitting replaces that chunk and rebuilds global IDs.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksResplit")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    _seed_review_speech_blocks(project_root)
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    monkeypatch.setattr(
        speech_blocks_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: {
            "payload": {
                "blocks": [
                    {
                        "text": "Narration. ",
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    },
                    {
                        "text": '"Hello there."',
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
                        "confidence": "high",
                        "warning_flags": [],
                    },
                ]
            },
            "usage": {"input_tokens": 5, "output_tokens": 4, "total_tokens": 9, "usage_available": True},
        },
    )

    report = speech_blocks_service.regenerate_chunk_speech_blocks(
        project_root,
        manifest,
        "chunk-0001",
        _profile_payload(),
    )

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert [block["speech_block_id"] for block in speech_blocks] == ["0001-000001", "0001-000002", "0002-000001"]
    assert [block["chunk_id"] for block in speech_blocks] == ["chunk-0001", "chunk-0001", "chunk-0002"]
    assert speech_blocks[0]["approved"] is False
    assert speech_blocks[0]["text"] == "Narration."
    assert speech_blocks[1]["text"] == "Hello there."
    assert speech_blocks[2]["text"] == "Later narration."
    assert report["approved_block_count"] == 0
    assert report["total_block_count"] == 3


def test_normalize_chunk_blocks_preserves_ai_dialogue_and_attribution_boundaries() -> None:
    """
    @brief      Verify AI source spans drive dialogue and attribution boundaries.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    speaker_catalog = {
        "narrator": {
            "speaker_id": "narrator",
            "speaker_kind": "narrator",
            "display_name": "Narrator",
        },
        "ottmar_drenthe": {
            "speaker_id": "ottmar_drenthe",
            "speaker_kind": "character",
            "display_name": "Ottmar Drenthe",
        },
    }
    source_chunk = {
        "chunk_id": "chunk-0001",
        "text": (
            "Ottmar Drenthe watched the screen.\n"
            '"Different how?" Drenthe snapped. "I am Drenthe."\n'
            '"Sure, absolutely," his agent said. "But I have an offer."'
        ),
    }
    response_payload = {
        "speech_blocks": [
            {
                "speaker_id": "narrator",
                "content_kind": "narration",
                "source_text": "Ottmar Drenthe watched the screen.\n",
                "text": "Ottmar Drenthe watched the screen.",
                "warning_flags": [],
            },
            {
                "speaker_id": "ottmar_drenthe",
                "content_kind": "dialogue",
                "source_text": '"Different how?"',
                "text": '"Different how?"',
                "warning_flags": [],
            },
            {
                "speaker_id": "narrator",
                "content_kind": "narration",
                "source_text": " Drenthe snapped. ",
                "text": "Drenthe snapped.",
                "warning_flags": [],
            },
            {
                "speaker_id": "ottmar_drenthe",
                "content_kind": "dialogue",
                "source_text": '"I am Drenthe."',
                "text": '"I am Drenthe."',
                "warning_flags": [],
            },
            {
                "speaker_id": "narrator",
                "content_kind": "dialogue",
                "source_text": '"Sure, absolutely,"',
                "text": '"Sure, absolutely,"',
                "warning_flags": ["ambiguous_speaker"],
            },
            {
                "speaker_id": "narrator",
                "content_kind": "narration",
                "source_text": " his agent said. ",
                "text": "his agent said.",
                "warning_flags": [],
            },
            {
                "speaker_id": "narrator",
                "content_kind": "dialogue",
                "source_text": '"But I have an offer."',
                "text": '"But I have an offer."',
                "warning_flags": ["ambiguous_speaker"],
            },
        ]
    }

    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        source_chunk,
        response_payload,
        speaker_catalog,
        "en",
    )

    assert [block["text"] for block in blocks] == [
        "Ottmar Drenthe watched the screen.",
        "Different how?",
        "Drenthe snapped.",
        "I am Drenthe.",
        "Sure, absolutely,",
        "his agent said.",
        "But I have an offer.",
    ]
    assert [block["content_kind"] for block in blocks] == [
        "narration",
        "dialogue",
        "narration",
        "dialogue",
        "dialogue",
        "narration",
        "dialogue",
    ]
    assert blocks[1]["speaker_id"] == "ottmar_drenthe"
    assert blocks[2]["speaker_id"] == "narrator"
    assert blocks[4]["speaker_id"] == "narrator"
    assert blocks[4]["warning_flags"] == ["ambiguous_speaker"]
    assert blocks[6]["speaker_id"] == "narrator"
    assert blocks[6]["warning_flags"] == ["ambiguous_speaker"]
    assert len(warnings) == 2


def test_normalize_chunk_blocks_resolves_unique_speaker_suffix_alias() -> None:
    """
    @brief      Verify a unique model speaker suffix such as `drenthe` resolves to the catalog id.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    speaker_catalog = {
        "narrator": {
            "speaker_id": "narrator",
            "speaker_kind": "narrator",
            "display_name": "Narrator",
        },
        "ottmar_drenthe": {
            "speaker_id": "ottmar_drenthe",
            "speaker_kind": "character",
            "display_name": "Ottmar Drenthe",
        },
    }

    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": '"Where is the engineer now?"'},
        {
            "speech_blocks": [
                {
                    "speaker_id": "drenthe",
                    "content_kind": "dialogue",
                    "source_text": '"Where is the engineer now?"',
                    "text": "Where is the engineer now?",
                    "warning_flags": ["ambiguous_speaker"],
                }
            ]
        },
        speaker_catalog,
        "en",
    )

    assert blocks[0]["speaker_id"] == "ottmar_drenthe"
    assert blocks[0]["speaker_display_name"] == "Ottmar Drenthe"
    assert blocks[0]["warning_flags"] == ["ambiguous_speaker"]
    assert len(warnings) == 1


def test_normalize_chunk_blocks_reconstructs_text_from_source_span_ids() -> None:
    """
    @brief      Verify span selections reconstruct exact source text and ignore model-owned rewrites.
    @details    Covers SBCON-001, SBCON-003, and REQ-FUNC-040.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    speaker_catalog = {
        "narrator": _narrator_catalog_entry(),
        "maria": {
            "speaker_id": "maria",
            "speaker_kind": "character",
            "display_name": "Maria",
        },
    }
    source_chunk = {
        "chunk_id": "chunk-0001",
        "text": 'Narration. "Hello."',
        "source_spans": [
            {
                "source_span_id": "s001",
                "start_offset": 0,
                "end_offset": 11,
                "text": "Narration. ",
            },
            {
                "source_span_id": "s002",
                "start_offset": 11,
                "end_offset": 19,
                "text": '"Hello."',
            },
        ],
    }

    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        source_chunk,
        {
            "blocks": [
                {
                    "source_span_ids": ["s001"],
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "confidence": "high",
                    "source_text": "The model rewrote this narration.",
                    "text": "The model rewrote this narration.",
                    "warnings": [],
                },
                {
                    "source_span_ids": ["s002"],
                    "speaker_id": "maria",
                    "content_kind": "dialogue",
                    "confidence": "high",
                    "source_text": "The model rewrote this dialogue.",
                    "text": "The model rewrote this dialogue.",
                    "warnings": [],
                },
            ]
        },
        speaker_catalog,
        "en",
    )

    assert [block["source_text"] for block in blocks] == ["Narration. ", '"Hello."']
    assert [block["text"] for block in blocks] == ["Narration.", "Hello."]
    assert [block["speaker_id"] for block in blocks] == ["narrator", "maria"]
    assert warnings == []


@pytest.mark.parametrize(
    ("model_block", "expected_warning_flag"),
    [
        (
            {
                "source_span_ids": ["missing-span"],
                "speaker_id": "maria",
                "content_kind": "dialogue",
                "confidence": "high",
            },
            "source_span_selection_invalid",
        ),
        (
            {
                "source_span_ids": ["s002", "s001"],
                "speaker_id": "maria",
                "content_kind": "dialogue",
                "confidence": "high",
            },
            "source_span_selection_invalid",
        ),
        (
            {
                "source_span_ids": ["s001", "s001"],
                "speaker_id": "maria",
                "content_kind": "dialogue",
                "confidence": "high",
            },
            "source_span_selection_invalid",
        ),
        (
            {
                "source_span_ids": [],
                "speaker_id": "maria",
                "content_kind": "dialogue",
                "confidence": "high",
            },
            "source_span_selection_invalid",
        ),
        (
            {
                "source_span_ids": ["s001"],
                "speaker_id": "unknown_character",
                "content_kind": "dialogue",
                "confidence": "high",
            },
            "speaker_selection_invalid",
        ),
    ],
)
def test_normalize_chunk_blocks_rejects_invalid_span_or_speaker_selection(
    model_block: dict[str, object],
    expected_warning_flag: str,
) -> None:
    """
    @brief      Verify invalid span or speaker selections do not persist unsafe character blocks.
    @details    Covers SBCON-002 and REQ-FUNC-040.
    @param[in]  model_block Model block selection under test.
    @param[in]  expected_warning_flag Warning flag expected on deterministic fallback.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    speaker_catalog = {
        "narrator": _narrator_catalog_entry(),
        "maria": {
            "speaker_id": "maria",
            "speaker_kind": "character",
            "display_name": "Maria",
        },
    }
    source_chunk = {
        "chunk_id": "chunk-0001",
        "text": 'Narration. "Hello."',
        "source_spans": [
            {
                "source_span_id": "s001",
                "start_offset": 0,
                "end_offset": 11,
                "text": "Narration. ",
            },
            {
                "source_span_id": "s002",
                "start_offset": 11,
                "end_offset": 19,
                "text": '"Hello."',
            },
        ],
    }

    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        source_chunk,
        {"blocks": [model_block]},
        speaker_catalog,
        "en",
    )

    assert len(blocks) == 1
    assert blocks[0]["speaker_id"] == "narrator"
    assert blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_NARRATION
    assert blocks[0]["source_text"] == source_chunk["text"]
    assert expected_warning_flag in blocks[0]["warning_flags"]
    assert any(expected_warning_flag in str(warning.get("reason", "")) for warning in warnings)


def test_normalize_chunk_blocks_supports_french_guillemets() -> None:
    """
    @brief      Verify French guillemet dialogue keeps exact source text and clean audio text.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    speaker_catalog = {"narrator": _narrator_catalog_entry()}

    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": "Il dit : « Bonjour. » Elle sourit."},
        {
            "speech_blocks": [
                {
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "source_text": "Il dit : ",
                    "text": "Il dit :",
                    "warning_flags": [],
                },
                {
                    "speaker_id": "narrator",
                    "content_kind": "dialogue",
                    "source_text": "« Bonjour. »",
                    "text": "« Bonjour. »",
                    "warning_flags": ["ambiguous_speaker"],
                },
                {
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "source_text": " Elle sourit.",
                    "text": "Elle sourit.",
                    "warning_flags": [],
                },
            ]
        },
        speaker_catalog,
        "fr",
    )

    assert [block["source_text"] for block in blocks] == ["Il dit : ", "« Bonjour. »", " Elle sourit."]
    assert [block["text"] for block in blocks] == ["Il dit :", "Bonjour.", "Elle sourit."]
    assert blocks[1]["content_kind"] == speech_blocks_service.CONTENT_KIND_DIALOGUE
    assert warnings == [
        {
            "chunk_id": "chunk-0001",
            "reason": "Speaker attribution was ambiguous and fell back to narrator.",
        }
    ]


def test_normalize_chunk_blocks_supports_dash_dialogue() -> None:
    """
    @brief      Verify dash-led dialogue removes only the leading dash from audio text.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    speaker_catalog = {"narrator": _narrator_catalog_entry()}

    blocks, _warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": "- Bonjour, dit-elle. - Venez ici."},
        {
            "speech_blocks": [
                {
                    "speaker_id": "narrator",
                    "content_kind": "dialogue",
                    "source_text": "- Bonjour, dit-elle.",
                    "text": "- Bonjour, dit-elle.",
                    "warning_flags": ["ambiguous_speaker"],
                },
                {
                    "speaker_id": "narrator",
                    "content_kind": "dialogue",
                    "source_text": " - Venez ici.",
                    "text": "- Venez ici.",
                    "warning_flags": ["ambiguous_speaker"],
                },
            ]
        },
        speaker_catalog,
        "fr",
    )

    assert [block["source_text"] for block in blocks] == ["- Bonjour, dit-elle.", " - Venez ici."]
    assert [block["text"] for block in blocks] == ["Bonjour, dit-elle.", "Venez ici."]
    assert [block["speech_block_id"] for block in blocks] == ["0001-000001", "0001-000002"]


def test_normalize_chunk_blocks_flags_direct_source_gaps_and_unmatched_text() -> None:
    """
    @brief      Verify direct normalization preserves source gaps and rejects unmatched model text.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    speaker_catalog = {"narrator": _narrator_catalog_entry()}

    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": "A. B. C."},
        {
            "speech_blocks": [
                {
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "source_text": "B.",
                    "text": "B.",
                    "warning_flags": [],
                },
                {
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "source_text": "A.",
                    "text": "Altered.",
                    "warning_flags": [],
                },
            ]
        },
        speaker_catalog,
        "en",
    )

    assert [block["source_text"] for block in blocks] == ["A. ", "B.", " C."]
    assert "source_gap" in blocks[0]["warning_flags"]
    assert "needs_review" in blocks[0]["warning_flags"]
    assert "source_gap" in blocks[2]["warning_flags"]
    assert any("unmatched_model_text" in str(warning["reason"]) for warning in warnings)


def test_normalize_block_text_only_strips_wrapping_dialogue_quotes() -> None:
    """
    @brief      Verify dialogue quote stripping removes only one outer quote pair for dialogue spans.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    assert (
        speech_blocks_service._normalize_block_text('"Hello there."', "dialogue")  # noqa: SLF001
        == "Hello there."
    )
    assert (
        speech_blocks_service._normalize_block_text("“Hello there.”", "dialogue")  # noqa: SLF001
        == "Hello there."
    )
    assert (
        speech_blocks_service._normalize_block_text("« Bonjour. »", "dialogue")  # noqa: SLF001
        == "Bonjour."
    )
    assert (
        speech_blocks_service._normalize_block_text("- Bonjour.", "dialogue")  # noqa: SLF001
        == "Bonjour."
    )
    assert (
        speech_blocks_service._normalize_block_text('He said "Hello there."', "dialogue")  # noqa: SLF001
        == 'He said "Hello there."'
    )
    assert (
        speech_blocks_service._normalize_block_text('"Hello there."', "narration")  # noqa: SLF001
        == '"Hello there."'
    )


def test_start_or_continue_generation_resumes_with_current_selected_profile(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Speech Blocks resume continues from the next chunk using the current selected profile.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-30
    @version    0.2.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksResume")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)
    existing_blocks = [
        {
            "speech_block_id": "0001-000001",
            "sequence_index": 1,
            "chunk_id": "chunk-0001",
            "source_language": "en",
            "speaker_kind": "narrator",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": "narration",
            "source_text": "Narration. ",
            "text": "Narration.",
            "warning_flags": [],
        }
    ]
    fingerprint = speech_blocks_service._build_source_fingerprint(source_resolution["source_chunks"], "en", "original")  # noqa: SLF001
    budget_metadata = speech_blocks_service._build_budget_metadata(  # noqa: SLF001
        _profile_payload(),
        "prompt {}",
        "speech_blocks_user",
        "en",
        speech_blocks_service._speaker_catalog([]),  # noqa: SLF001
        config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
        speech_blocks_service._resolve_narrator_only_budget(None),  # noqa: SLF001
    )
    report = speech_blocks_service._rebuild_report(  # noqa: SLF001
        existing_blocks,
        "en",
        "original",
        "profile-1",
        2,
        1,
        [],
        {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7, "usage_available": True},
        budget_metadata,
    )
    speech_blocks_service._persist_state(  # noqa: SLF001
        project_root,
        source_resolution["source_chunks"],
        existing_blocks,
        report,
        speech_blocks_service._build_operation_state_with_prompt_rules(  # noqa: SLF001
            project_root,
            source_resolution["source_chunks"],
            existing_blocks,
            status="running",
            started_at="2026-04-21T12:00:00+00:00",
            completed_at=None,
            source_language="en",
            source_kind="original",
            profile_id="profile-1",
            warning_records=[],
            input_fingerprint=fingerprint,
            log_path=project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / "log_ai_transactions_resume.log",
            token_usage={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7, "usage_available": True},
            next_chunk_index=1,
            budget_metadata=budget_metadata,
            additional_speech_block_instructions="",
            speech_blocks_response_contract="direct_blocks",
        ),
    )
    calls: list[dict[str, object]] = []

    def _fake_chat_json(profile, *_args, **_kwargs):
        """
        @brief      Provide the fake chat json test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        calls.append(dict(profile))
        return {
            "payload": {
                "blocks": [
                    {
                        "text": "Maria smiled. ",
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    },
                    {
                        "text": '"Welcome."',
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
                        "confidence": "high",
                        "warning_flags": [],
                    },
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
        }

    monkeypatch.setattr(speech_blocks_service.llm_provider_service, "chat_json", _fake_chat_json)
    selected_profile = {**_profile_payload(), "id": "profile-2", "model_name": "qwen3-14b", "temperature": 0.7}

    report = speech_blocks_service.start_or_continue_generation(project_root, manifest, selected_profile)

    assert len(calls) == 1
    assert calls[0]["id"] == "profile-2"
    assert calls[0]["model_name"] == "qwen3-14b"
    assert report["ai_profile_id"] == "profile-2"
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert len(speech_blocks) == 3
    assert speech_blocks[0]["chunk_id"] == "chunk-0001"
    assert speech_blocks[1]["chunk_id"] == "chunk-0002"
    assert speech_blocks[1]["text"] == "Maria smiled."
    assert speech_blocks[2]["text"] == "Welcome."
    assert report["processed_chunk_count"] == 2
    assert report["token_usage"]["total_tokens"] == 22


def test_start_or_continue_generation_resumes_after_partial_review_approval(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify approved partial Speech Blocks remain committed when generation continues.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksPartialReviewResume")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)
    source_chunks = list(source_resolution["source_chunks"])
    existing_blocks = [
        {
            "speech_block_id": "0001-000001",
            "sequence_index": 1,
            "chunk_id": "chunk-0001",
            "source_language": "en",
            "speaker_kind": "narrator",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": "narration",
            "source_text": "Narration.",
            "text": "Narration.",
            "warning_flags": [],
            "approved": True,
            "approved_at": "2026-05-08T18:00:00+00:00",
        }
    ]
    fingerprint = speech_blocks_service._build_source_fingerprint(source_chunks, "en", "original")  # noqa: SLF001
    token_usage = {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7, "usage_available": True}
    budget_metadata = speech_blocks_service._build_budget_metadata(  # noqa: SLF001
        _profile_payload(),
        "prompt {}",
        "speech_blocks_user",
        "en",
        speech_blocks_service._speaker_catalog([]),  # noqa: SLF001
        config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
        speech_blocks_service._resolve_narrator_only_budget(None),  # noqa: SLF001
    )
    speech_blocks_service._persist_state(  # noqa: SLF001
        project_root,
        source_chunks,
        existing_blocks,
        speech_blocks_service._rebuild_report(  # noqa: SLF001
            existing_blocks,
            "en",
            "original",
            "profile-1",
            len(source_chunks),
            1,
            [],
            token_usage,
            budget_metadata,
        ),
        speech_blocks_service._build_operation_state_with_prompt_rules(  # noqa: SLF001
            project_root,
            source_chunks,
            existing_blocks,
            status="review_pending",
            started_at="2026-05-08T17:47:40+00:00",
            completed_at="2026-05-08T18:00:00+00:00",
            source_language="en",
            source_kind="original",
            profile_id="profile-1",
            warning_records=[],
            input_fingerprint=fingerprint,
            log_path=project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / "log_ai_transactions_review.log",
            token_usage=token_usage,
            next_chunk_index=None,
            budget_metadata=budget_metadata,
            additional_speech_block_instructions="",
            speech_blocks_response_contract="direct_blocks",
        ),
    )
    requested_prompts: list[str] = []

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Return one generated block for the unfinished chunk.
        @param[in]  _profile Ignored AI profile payload.
        @param[in]  _system_prompt Ignored system prompt.
        @param[in]  user_prompt Captured user prompt.
        @param[in]  _kwargs Ignored keyword request arguments.
        @return     Fake Speech Blocks model response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-08
        @version    0.1.0
        """
        requested_prompts.append(str(user_prompt))
        return {
            "payload": {
                "blocks": [
                    {
                        "text": "Maria smiled. ",
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    },
                    {
                        "text": '"Welcome."',
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
                        "confidence": "medium",
                        "warning_flags": ["ambiguous_speaker"],
                    },
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
        }

    monkeypatch.setattr(speech_blocks_service.llm_provider_service, "chat_json", _fake_chat_json)

    report = speech_blocks_service.start_or_continue_generation(project_root, manifest, _profile_payload())

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert len(requested_prompts) == 1
    assert [block["chunk_id"] for block in speech_blocks] == ["chunk-0001", "chunk-0002", "chunk-0002"]
    assert speech_blocks[0]["approved"] is True
    assert speech_blocks[0]["text"] == "Narration."
    assert speech_blocks[1]["approved"] is False
    assert speech_blocks[1]["text"] == "Maria smiled."
    assert speech_blocks[2]["approved"] is False
    assert speech_blocks[2]["text"] == "Welcome."
    assert report["processed_chunk_count"] == 2
    assert report["approved_block_count"] == 1
    assert report["token_usage"]["total_tokens"] == 22


def test_start_generation_preserves_french_dash_and_guillemet_source_spans(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify generation can persist multiple French guillemet and dash Speech Blocks per chunk.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksFrenchGeneration")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "fr")
    _write_translation_artifacts(
        project_root,
        approved_chunk_count=2,
        target_language="fr",
        translated_chunks=[
            {"chunk_id": "chunk-0001", "translated_text": "Il dit : « Bonjour. » Elle sourit."},
            {"chunk_id": "chunk-0002", "translated_text": "- Bonjour, dit-elle. - Venez ici."},
        ],
    )
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    responses = [
        {
            "payload": {
                "blocks": [
                    {
                        "text": "Il dit : ",
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    },
                    {
                        "source_span_ids": ["s002"],
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
                        "source_text": "« Bonjour. »",
                        "text": "« Bonjour. »",
                        "warning_flags": ["ambiguous_speaker"],
                    },
                    {
                        "text": " Elle sourit.",
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    },
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
        },
        {
            "payload": {
                "blocks": [
                    {
                        "text": "- Bonjour, dit-elle.",
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
                        "confidence": "medium",
                        "warning_flags": ["ambiguous_speaker"],
                    },
                    {
                        "text": " - Venez ici.",
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
                        "confidence": "medium",
                        "warning_flags": ["ambiguous_speaker"],
                    },
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
        },
    ]
    monkeypatch.setattr(
        speech_blocks_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: responses.pop(0),
    )

    report = speech_blocks_service.start_or_continue_generation(project_root, manifest, _profile_payload())

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert [block["speech_block_id"] for block in speech_blocks] == [
        "0001-000001",
        "0001-000002",
        "0001-000003",
        "0002-000001",
        "0002-000002",
    ]
    assert {block["source_language"] for block in speech_blocks} == {"fr"}
    assert speech_blocks[1]["source_text"] == "« Bonjour. »"
    assert speech_blocks[1]["text"] == "Bonjour."
    assert speech_blocks[3]["source_text"] == "- Bonjour, dit-elle."
    assert speech_blocks[3]["text"] == "Bonjour, dit-elle."
    assert speech_blocks[4]["source_text"] == " - Venez ici."
    assert speech_blocks[4]["text"] == "Venez ici."
    assert report["total_block_count"] == 5


def test_start_generation_splits_same_narrator_without_calling_a_model(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify same-narrator projects segment deterministically and never reach a model.
    @details    Covers the deterministic narrator contract: no prompt is rendered, no provider
                request is issued, every block is narrator narration, and no tokens are spent.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.3.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksNarratorOnly")
    manifest["original_language"] = "en"
    manifest["target_language"] = "en"
    manifest["selected_voice_language"] = "en"
    manifest["voice_assignment_mode"] = "same_narrator"
    manifest["project_options_locked"] = True
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")

    def _fail_on_model_call(*_args, **_kwargs):
        """
        @brief      Fail the test if same-narrator generation contacts a model.
        @return     None.
        @exception  AssertionError Always raised.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-26
        @version    0.1.0
        """
        raise AssertionError("same-narrator generation must not call the model")

    monkeypatch.setattr(speech_blocks_service.llm_provider_service, "chat_json", _fail_on_model_call)

    report = speech_blocks_service.start_or_continue_generation(project_root, manifest, _profile_payload())

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert {block["speaker_id"] for block in speech_blocks} == {"narrator"}
    assert {block["content_kind"] for block in speech_blocks} == {speech_blocks_service.CONTENT_KIND_NARRATION}
    assert speech_blocks[0]["text"] == 'Narration. "Hello there."'
    assert report["token_usage"]["usage_available"] is False
    assert not report["token_usage"]["total_tokens"]


def test_start_generation_allows_same_narrator_without_an_ai_profile(tmp_path) -> None:
    """
    @brief      Verify deterministic segmentation runs with no AI profile when ambience is off.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksNarratorNoProfile")
    manifest["original_language"] = "en"
    manifest["voice_assignment_mode"] = "same_narrator"
    manifest["project_options_locked"] = True
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")

    report = speech_blocks_service.start_or_continue_generation(project_root, manifest, {})

    assert report["total_block_count"] > 0
    assert speech_blocks_service.load_speech_blocks(project_root)


def test_same_narrator_blocks_inherit_uncertain_cleanup_boundaries(tmp_path) -> None:
    """
    @brief      Verify a paragraph repaired across a page break marks its blocks for review.
    @details    Cleanup already decides whether a paragraph was stitched back together across a
                page break; that verdict must reach the operator instead of being discarded.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksWeakBoundary")
    manifest["original_language"] = "en"
    manifest["voice_assignment_mode"] = "same_narrator"
    manifest["project_options_locked"] = True
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    chunking_document = chunking_document_service.load_chunking_document(project_root)
    chunking_document["chunks"][0]["cleanup_boundary_confidence"] = "repaired"
    chunking_document["chunks"][0]["cleanup_joined_across_page_break"] = True
    chunking_document_service.write_chunking_document(project_root, chunking_document)

    speech_blocks_service.start_or_continue_generation(project_root, manifest, {})

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    repaired_blocks = [block for block in speech_blocks if str(block["chunk_id"]) == "chunk-0001"]
    strong_blocks = [block for block in speech_blocks if str(block["chunk_id"]) == "chunk-0002"]
    assert repaired_blocks
    assert strong_blocks
    assert all("weak_source_boundary" in block["warning_flags"] for block in repaired_blocks)
    assert all("needs_review" in block["warning_flags"] for block in repaired_blocks)
    assert all("weak_source_boundary" not in block["warning_flags"] for block in strong_blocks)


def test_same_narrator_blocks_reproduce_every_source_chunk(tmp_path) -> None:
    """
    @brief      Verify deterministic segmentation never drops or alters source chunk text.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksNarratorCoverage")
    manifest["original_language"] = "en"
    manifest["voice_assignment_mode"] = "same_narrator"
    manifest["project_options_locked"] = True
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")

    speech_blocks_service.start_or_continue_generation(project_root, manifest, {})

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    for source_chunk in speech_blocks_service.load_input_source_chunks(project_root):
        chunk_id = str(source_chunk["chunk_id"])
        rebuilt = "".join(str(block["source_text"]) for block in speech_blocks if str(block["chunk_id"]) == chunk_id)
        assert rebuilt == str(source_chunk["text"]), chunk_id


@pytest.mark.parametrize(
    ("voice_assignment_mode", "system_prompt_name", "user_prompt_name", "include_character", "expected_snippets"),
    [
        (
            "narrator_and_characters",
            "speech_blocks_system",
            "speech_blocks_user",
            True,
            (
                "Voice assignment mode: narrator_and_characters",
                '"speaker_id": "maria"',
                '"aliases": [',
                "Non-selectable attribution context:",
            ),
        ),
    ],
)
def test_speech_blocks_production_prompt_contract_matrix(
    voice_assignment_mode: str,
    system_prompt_name: str,
    user_prompt_name: str,
    include_character: bool,
    expected_snippets: tuple[str, ...],
) -> None:
    """
    @brief      Verify production Speech Blocks prompt pairs render with their runtime variable contract.
    @param[in]  voice_assignment_mode Runtime voice-assignment mode under test.
    @param[in]  system_prompt_name Production system prompt name.
    @param[in]  user_prompt_name Production user prompt name.
    @param[in]  include_character True when the matrix case includes one character speaker.
    @param[in]  expected_snippets Rendered prompt snippets expected for this prompt pair.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    speaker_catalog = {"narrator": _narrator_catalog_entry()}
    if include_character:
        speaker_catalog["maria"] = {
            "speaker_id": "maria",
            "speaker_kind": "character",
            "display_name": "Maria",
            "aliases": ["doamna Maria", "pilotul"],
        }
        source_chunk = speech_blocks_service._source_chunk_with_source_spans(  # noqa: SLF001
            {
                "chunk_id": "chunk-contract-0001",
                "text": 'Contract narration. "Hello there."',
                "previous_context": "Maria ridica mana inaintea replicii.",
                "next_context": "Pilotul ii raspunse imediat dupa aceea.",
            }
        )
    else:
        source_chunk = {"chunk_id": "chunk-contract-0001", "text": 'Contract narration. "Hello there."'}

    rendered_system_prompt = prompt_template_service.render_prompt(system_prompt_name, {})
    rendered_prompt = speech_blocks_service._chunk_user_prompt(  # noqa: SLF001
        source_chunk,
        "en",
        speaker_catalog,
        voice_assignment_mode=voice_assignment_mode,
        tts_budget={
            "model_token_budget": 9876,
            "safe_word_count": 321,
            "model_budget_source": "contract-test-cache",
        },
        prompt_name=user_prompt_name,
    )

    assert rendered_system_prompt.strip()
    assert "chunk-contract-0001" in rendered_prompt
    assert "Contract narration" in rendered_prompt
    assert "TTS maximum model token budget: 9876" in rendered_prompt
    assert "Safe approximate words per block: 321" in rendered_prompt
    assert "TTS budget source: contract-test-cache" in rendered_prompt
    if include_character:
        assert "Allowed speaker catalog:" in rendered_prompt
        assert "`blocks`" in rendered_system_prompt
        assert "`text`" in rendered_system_prompt
        assert "`unit_ids`" not in rendered_system_prompt
        assert "`source_span_ids`" not in rendered_system_prompt
        assert "`source_text`" not in rendered_system_prompt
        assert "`speech_blocks`" not in rendered_system_prompt
        assert "Do not translate" in rendered_system_prompt
        assert "Romanian" in rendered_system_prompt
        assert "Do not return text from previous or next context" in rendered_prompt
        assert "Maria ridica mana" in rendered_prompt
        assert "Pilotul ii raspunse" in rendered_prompt
        assert "previous_context" in rendered_prompt
        assert "next_context" in rendered_prompt
        assert "h001" not in rendered_prompt
    else:
        assert "Candidate split boundaries:" in rendered_prompt
    for expected_snippet in expected_snippets:
        assert expected_snippet in rendered_prompt


def test_speech_blocks_prompt_uses_direct_blocks_and_forbids_text_rewrites() -> None:
    """
    @brief      Verify the narrator-and-character prompt exposes direct source text, not unit IDs.
    @details    Covers SB-DIRECT-001 and REQ-FUNC-052.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    speaker_catalog = {
        "narrator": _narrator_catalog_entry(),
        "ana": {
            "speaker_id": "ana",
            "speaker_kind": "character",
            "display_name": "Ana",
            "aliases": ["Ana"],
        },
    }
    source_chunk = speech_blocks_service._source_chunk_with_source_spans(  # noqa: SLF001
        {
            "chunk_id": "chunk-atomic-0001",
            "text": '"Come?" Ana asked. "Soon."',
        }
    )

    rendered_system_prompt = prompt_template_service.render_prompt("speech_blocks_system", {})
    rendered_prompt = speech_blocks_service._chunk_user_prompt(  # noqa: SLF001
        source_chunk,
        "en",
        speaker_catalog,
        voice_assignment_mode="narrator_and_characters",
        tts_budget={
            "model_token_budget": 2048,
            "safe_word_count": 300,
            "model_budget_source": "test",
        },
    )

    assert "Current chunk segment text:" in rendered_prompt
    assert '"Come?" Ana asked. "Soon."' in rendered_prompt
    assert "Available atomic speech units:" not in rendered_prompt
    assert '"atomic_unit_id": "u001"' not in rendered_prompt
    assert "exact source substring" in rendered_system_prompt
    assert "`text`" in rendered_system_prompt
    assert "`unit_ids`" not in rendered_system_prompt
    assert "`source_span_ids`" not in rendered_system_prompt
    assert "`source_text`" not in rendered_system_prompt


def test_normalize_chunk_blocks_rejects_dialogue_attribution_unit_merge() -> None:
    """
    @brief      Verify validation rejects one dialogue block that merges dialogue and attribution units.
    @details    Covers SB-ATOMIC-003 and REQ-FUNC-052.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    speaker_catalog = {
        "narrator": _narrator_catalog_entry(),
        "ana": {
            "speaker_id": "ana",
            "speaker_kind": "character",
            "display_name": "Ana",
        },
    }
    source_chunk = speech_blocks_service._source_chunk_with_source_spans(  # noqa: SLF001
        {
            "chunk_id": "chunk-0001",
            "text": '"Come?" Ana asked. "Soon."',
        }
    )

    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        source_chunk,
        {
            "blocks": [
                {
                    "unit_ids": ["u001", "u002", "u003"],
                    "speaker_id": "ana",
                    "content_kind": "dialogue",
                    "confidence": "high",
                    "warning_flags": [],
                }
            ]
        },
        speaker_catalog,
        "en",
    )

    assert blocks
    assert blocks[0]["speaker_id"] == "narrator"
    assert "atomic_unit_selection_invalid" in blocks[0]["warning_flags"]
    assert any("attribution" in str(warning["reason"]).casefold() for warning in warnings)


def test_normalize_chunk_blocks_accepts_narration_with_non_spoken_quoted_words() -> None:
    """
    @brief      Verify narrator emphasis quotes do not force atomic selection fallback.
    @details    Covers SB-ATOMIC-006 and REQ-FUNC-051.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-05
    @version    0.1.0
    """
    source_text = (
        'Not "our" Emperor, Scytale noted. "Your" Emperor. Irulan is too much the Bene Gesserit to miss that slip.'
    )
    speaker_catalog = {"narrator": _narrator_catalog_entry()}
    source_chunk = speech_blocks_service._source_chunk_with_source_spans(  # noqa: SLF001
        {
            "chunk_id": "chunk-0001",
            "text": source_text,
        }
    )
    selectable_unit_ids = [
        str(unit["atomic_unit_id"])
        for unit in source_chunk["atomic_units"]
        if unit["structural_kind"] != "separator" and str(unit.get("text", "")).strip()
    ]

    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        source_chunk,
        {
            "blocks": [
                {
                    "unit_ids": selectable_unit_ids,
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "confidence": "high",
                    "warning_flags": [],
                }
            ]
        },
        speaker_catalog,
        "en",
    )

    assert len(blocks) == 1
    assert blocks[0]["speaker_id"] == "narrator"
    assert blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_NARRATION
    assert blocks[0]["source_text"] == source_text
    assert blocks[0]["text"] == source_text
    assert not blocks[0]["warning_flags"]
    assert not warnings


def test_speech_blocks_direct_prompt_does_not_expose_atomic_separator_units() -> None:
    """
    @brief      Verify direct prompts do not expose atomic separator rows.
    @details    Covers SB-DIRECT-001 and REQ-FUNC-054.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    speaker_catalog = {
        "narrator": _narrator_catalog_entry(),
        "ana": {
            "speaker_id": "ana",
            "speaker_kind": "character",
            "display_name": "Ana",
        },
    }
    source_chunk = speech_blocks_service._source_chunk_with_source_spans(  # noqa: SLF001
        {
            "chunk_id": "chunk-separator-0001",
            "text": '"A."\n"B."',
        }
    )

    rendered_system_prompt = prompt_template_service.render_prompt("speech_blocks_system", {})
    rendered_prompt = speech_blocks_service._chunk_user_prompt(  # noqa: SLF001
        source_chunk,
        "en",
        speaker_catalog,
        voice_assignment_mode="narrator_and_characters",
        tts_budget={
            "model_token_budget": 2048,
            "safe_word_count": 300,
            "model_budget_source": "test",
        },
    )

    assert '"structural_kind": "separator"' not in rendered_prompt
    assert "Available atomic speech units:" not in rendered_prompt
    assert "selectable speakable atomic unit" not in rendered_system_prompt


def test_normalize_chunk_blocks_ignores_separator_coverage_and_rejects_separator_selection() -> None:
    """
    @brief      Verify separator-only units are not required for coverage and cannot be selected.
    @details    Covers SB-ATOMIC-005 and REQ-FUNC-054.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    speaker_catalog = {
        "narrator": _narrator_catalog_entry(),
        "ana": {
            "speaker_id": "ana",
            "speaker_kind": "character",
            "display_name": "Ana",
        },
    }
    source_chunk = speech_blocks_service._source_chunk_with_source_spans(  # noqa: SLF001
        {
            "chunk_id": "chunk-separator-0002",
            "text": '"A."\n"B."',
        }
    )
    separator_unit_id = next(
        str(unit["atomic_unit_id"]) for unit in source_chunk["atomic_units"] if unit["structural_kind"] == "separator"
    )
    speakable_unit_ids = [
        str(unit["atomic_unit_id"]) for unit in source_chunk["atomic_units"] if unit["structural_kind"] != "separator"
    ]

    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        source_chunk,
        {
            "blocks": [
                {
                    "unit_ids": [speakable_unit_ids[0]],
                    "speaker_id": "ana",
                    "content_kind": "dialogue",
                    "confidence": "high",
                    "warning_flags": [],
                },
                {
                    "unit_ids": [speakable_unit_ids[1]],
                    "speaker_id": "ana",
                    "content_kind": "dialogue",
                    "confidence": "high",
                    "warning_flags": [],
                },
            ]
        },
        speaker_catalog,
        "en",
    )

    assert [block["text"] for block in blocks] == ["A.", "B."]
    assert all(str(block["text"]).strip() for block in blocks)
    assert not warnings

    fallback_blocks, fallback_warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        source_chunk,
        {
            "blocks": [
                {
                    "unit_ids": [separator_unit_id],
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "confidence": "high",
                    "warning_flags": [],
                }
            ]
        },
        speaker_catalog,
        "en",
    )

    assert fallback_blocks
    assert fallback_blocks[0]["speaker_id"] == "narrator"
    assert "atomic_unit_selection_invalid" in fallback_blocks[0]["warning_flags"]
    assert any("separator" in str(warning["reason"]).casefold() for warning in fallback_warnings)


def test_speech_blocks_direct_prompt_includes_aliases_and_attribution_hints() -> None:
    """
    @brief      Verify source-language aliases and deterministic attribution hints are available to speaker assignment.
    @details    Covers SB-DIRECT-001 and REQ-FUNC-053.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    speaker_catalog = {
        "narrator": _narrator_catalog_entry(),
        "ion": {
            "speaker_id": "ion",
            "speaker_kind": "character",
            "display_name": "Ion",
            "aliases": ["domnul Ion", "pilotul"],
            "source_language_evidence": [{"chunk_id": "chunk-0001", "text": "răspunse pilotul Ion"}],
        },
    }
    source_chunk = speech_blocks_service._source_chunk_with_source_spans(  # noqa: SLF001
        {
            "chunk_id": "chunk-atomic-0002",
            "text": "„Vii?” întrebă Ion. „Curând.”",
        }
    )

    rendered_prompt = speech_blocks_service._chunk_user_prompt(  # noqa: SLF001
        source_chunk,
        "ro",
        speaker_catalog,
        voice_assignment_mode="narrator_and_characters",
        tts_budget={
            "model_token_budget": 2048,
            "safe_word_count": 300,
            "model_budget_source": "test",
        },
    )

    assert "domnul Ion" in rendered_prompt
    assert "pilotul" in rendered_prompt
    assert "răspunse pilotul Ion" in rendered_prompt
    assert "Current chunk segment text:" in rendered_prompt
    assert '"speaker_hint_ids": [' not in rendered_prompt
    assert '"ion"' in rendered_prompt


def test_speaker_catalog_preserves_character_aliases_for_prompt() -> None:
    """
    @brief      Verify Speech Blocks prompt catalogs carry source-language aliases from character discovery.
    @details    Covers SB456-SPEC-002 and REQ-FUNC-048.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    catalog = speech_blocks_service._speaker_catalog(  # noqa: SLF001
        [
            {
                "character_id": "maria",
                "canonical_name": "Maria",
                "aliases": ["doamna Maria", "pilotul"],
                "evidence": [{"chunk_id": "chunk-0001", "text": "pilotul Maria raspunse"}],
            }
        ]
    )

    assert catalog["maria"]["aliases"] == ["doamna Maria", "pilotul"]
    assert catalog["maria"]["source_language_evidence"] == [
        {"chunk_id": "chunk-0001", "text": "pilotul Maria raspunse"}
    ]


def test_speech_blocks_adjacent_prompts_preserve_dialogue_attribution_context() -> None:
    """
    @brief      Verify upstream prompts preserve multilingual dialogue context needed by Speech Blocks.
    @details    Covers SB456-SPEC-003 and REQ-FUNC-049.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.2.0
    """
    translation_prompt = (config.APP_PROMPTS_PATH / "text_translation_system.txt").read_text(encoding="utf-8")
    chunking_prompt = (config.APP_PROMPTS_PATH / "text_chunking_system.txt").read_text(encoding="utf-8")

    assert "dialogue attribution" in translation_prompt
    assert "paragraph breaks" in translation_prompt
    assert "attribution halo" in chunking_prompt
    assert "not selectable source text" in chunking_prompt


def test_local_model_guidance_is_honest_about_ai_settings_and_lmstudio_presets() -> None:
    """
    @brief      Verify local-model docs describe supported AudioMancer settings and LM Studio-only sampler presets.
    @details    Covers SB456-SPEC-004 and REQ-PLAT-004.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    local_model_doc = (_REPO_ROOT / "05_SoftwareDocu/AudioMancer_LMStudio_Local_Model_Recommendations.md").read_text(
        encoding="utf-8"
    )
    user_guide = (_REPO_ROOT / "05_SoftwareDocu/UserGuide/index.html").read_text(encoding="utf-8")
    user_guide_ro = (_REPO_ROOT / "05_SoftwareDocu/UserGuide_ro/index.html").read_text(encoding="utf-8")
    ai_settings_source = (
        _REPO_ROOT / "04_Software/AudioMancer/src/audiomancer/ui/pages/ai_settings_page.py"
    ).read_text(encoding="utf-8")
    settings_source = (_REPO_ROOT / "04_Software/AudioMancer/src/audiomancer/services/settings_service.py").read_text(
        encoding="utf-8"
    )

    assert "qwen/qwen3.6-27b" in local_model_doc
    assert "google/gemma-4-31b" in local_model_doc
    assert "AudioMancer does not send top-p, top-k, repeat penalty, seed, or reasoning mode" in local_model_doc
    assert "configure top-p, top-k, repeat penalty, seed, and reasoning mode in LM Studio presets" in user_guide
    assert "configureaza top-p, top-k, repeat penalty, seed si reasoning mode in preseturile LM Studio" in user_guide_ro
    for unsupported_setting in ("top_k", "top_p", "repeat_penalty", "reasoning_mode"):
        assert unsupported_setting not in ai_settings_source
        assert unsupported_setting not in settings_source


def test_normalize_chunk_blocks_narrator_only_preserves_delimiters() -> None:
    """
    @brief      Verify narrator-only normalization preserves dialogue delimiters.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    source_chunk = {"chunk_id": "chunk-0001", "text": "- Bonjour. Â« Venez. Â»"}
    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        source_chunk,
        {
            "speech_blocks": [
                {
                    "speaker_id": "maria",
                    "content_kind": "dialogue",
                    "source_text": "- Bonjour. Â« Venez. Â»",
                    "text": "- Bonjour. Â« Venez. Â»",
                    "warning_flags": [],
                }
            ]
        },
        {"narrator": _narrator_catalog_entry()},
        "fr",
        voice_assignment_mode="same_narrator",
        tts_budget={"safe_word_count": 20},
    )

    assert blocks[0]["speaker_id"] == "narrator"
    assert blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_NARRATION
    assert blocks[0]["text"] == "- Bonjour. Â« Venez. Â»"
    assert blocks[0]["source_text"] == "- Bonjour. Â« Venez. Â»"
    assert "ambiguous_speaker" not in blocks[0]["warning_flags"]
    assert "tts_budget_exceeded" not in blocks[0]["warning_flags"]
    assert warnings == []


def test_budgeted_source_chunk_segments_attach_source_spans() -> None:
    """
    @brief      Verify Speech Blocks request segments carry deterministic source-span selections.
    @details    Covers SBSPAN-001, SBSPAN-003, and REQ-FUNC-042.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    source_text = 'Narration before. "Deal," the pilot said.\n\n- Vii acasa? intreba Ion.'

    source_segments = speech_blocks_service._budgeted_source_chunk_segments(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": source_text},
        {"text_budget_tokens": speech_blocks_service._estimate_text_tokens(source_text) + 10},  # noqa: SLF001
    )

    assert len(source_segments) == 1
    source_spans = source_segments[0]["source_spans"]
    assert [span["source_span_id"] for span in source_spans] == [
        f"s{index:03d}" for index in range(1, len(source_spans) + 1)
    ]
    assert "".join(str(span["text"]) for span in source_spans) == source_text
    assert {str(span["candidate_kind"]) for span in source_spans if str(span["text"]).strip()} >= {
        "mixed_candidate",
        "dialogue_candidate",
    }


def test_normalize_chunk_blocks_splits_over_budget_sentence_boundaries() -> None:
    """
    @brief      Verify over-budget AI output is split on sentence boundaries before payload persistence.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    source_text = "One two. Three four. Five six."
    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": source_text},
        {
            "speech_blocks": [
                {
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "source_text": source_text,
                    "text": source_text,
                    "warning_flags": [],
                }
            ]
        },
        {"narrator": _narrator_catalog_entry()},
        "en",
        tts_budget={"safe_word_count": 2},
    )

    assert [block["text"] for block in blocks] == ["One two.", "Three four.", "Five six."]
    assert [block["source_text"] for block in blocks] == ["One two.", "Three four.", "Five six."]
    assert [block["speaker_id"] for block in blocks] == ["narrator", "narrator", "narrator"]
    assert [block["content_kind"] for block in blocks] == ["narration", "narration", "narration"]
    assert all("tts_hard_split" not in block["warning_flags"] for block in blocks)
    assert any("split after AI output" in str(warning["reason"]) for warning in warnings)


def test_normalize_chunk_blocks_hard_splits_over_budget_without_boundaries() -> None:
    """
    @brief      Verify hard fallback splits oversized text and marks the resulting blocks for review.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    source_text = "one two three four five"
    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": source_text},
        {
            "speech_blocks": [
                {
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "source_text": source_text,
                    "text": source_text,
                    "warning_flags": [],
                }
            ]
        },
        {"narrator": _narrator_catalog_entry()},
        "en",
        tts_budget={"safe_word_count": 2},
    )

    assert [block["text"] for block in blocks] == ["one two", "three four", "five"]
    assert all("tts_hard_split" in block["warning_flags"] for block in blocks)
    assert any("split after AI output" in str(warning["reason"]) for warning in warnings)


def test_normalize_chunk_blocks_narrator_only_preserves_operation_blocks() -> None:
    """
    @brief      Verify narrator-only normalization does not coerce operation blocks into narrator rows.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    blocks, _warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": "pause 2500 ms"},
        {
            "speech_blocks": [
                {
                    "speaker_id": "narrator",
                    "content_kind": "pause",
                    "source_text": "pause 2500 ms",
                    "text": "pause 2500 ms",
                    "warning_flags": [],
                }
            ]
        },
        {"narrator": _narrator_catalog_entry()},
        "en",
        voice_assignment_mode="same_narrator",
        tts_budget={"safe_word_count": 20},
    )

    assert blocks[0]["speaker_kind"] == speech_blocks_service.SPEAKER_KIND_OPERATION
    assert blocks[0]["speaker_id"] == speech_blocks_service.CONTENT_KIND_PAUSE
    assert blocks[0]["speaker_display_name"] == "Pause"
    assert blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_PAUSE
    assert "tts_budget_exceeded" not in blocks[0]["warning_flags"]


def test_direct_blocks_align_mixed_narration_dialogue_to_source_text() -> None:
    """
    @brief      Verify direct LLM blocks preserve aligned source text for mixed narration and dialogue.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-07
    @version    0.1.0
    """
    source_text = 'Despite the plan, Paul whispered, "Stay ready." The room stilled.'

    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": source_text},
        {
            "blocks": [
                {
                    "text": "Despite the plan, Paul whispered, ",
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "confidence": "high",
                    "warning_flags": [],
                },
                {
                    "text": '"Stay ready."',
                    "speaker_id": "paul",
                    "content_kind": "dialogue",
                    "confidence": "high",
                    "warning_flags": [],
                },
                {
                    "text": " The room stilled.",
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "confidence": "high",
                    "warning_flags": [],
                },
            ]
        },
        _direct_speaker_catalog(),
        "en",
    )

    assert [block["source_text"] for block in blocks] == [
        "Despite the plan, Paul whispered, ",
        '"Stay ready."',
        " The room stilled.",
    ]
    assert [block["text"] for block in blocks] == [
        "Despite the plan, Paul whispered,",
        "Stay ready.",
        "The room stilled.",
    ]
    assert [block["speaker_id"] for block in blocks] == ["narrator", "paul", "narrator"]
    assert warnings == []


def test_direct_blocks_unknown_speaker_defaults_to_review_narrator() -> None:
    """
    @brief      Verify unknown direct-block speakers become narrator review blocks.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-07
    @version    0.1.0
    """
    blocks, _warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": '"Who speaks?"'},
        {
            "blocks": [
                {
                    "text": '"Who speaks?"',
                    "speaker_id": "mystery_voice",
                    "content_kind": "dialogue",
                    "confidence": "low",
                    "warning_flags": [],
                }
            ]
        },
        _direct_speaker_catalog(),
        "en",
    )

    assert len(blocks) == 1
    assert blocks[0]["speaker_id"] == "narrator"
    assert blocks[0]["text"] == "Who speaks?"
    assert "unknown_speaker" in blocks[0]["warning_flags"]
    assert "needs_review" in blocks[0]["warning_flags"]


def test_direct_blocks_preserve_source_gaps_and_reject_unmatched_text() -> None:
    """
    @brief      Verify direct normalization preserves missed source text and drops invented model text.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-07
    @version    0.1.0
    """
    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": "First. Second. Third."},
        {
            "blocks": [
                {
                    "text": "First.",
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "confidence": "high",
                    "warning_flags": [],
                },
                {
                    "text": "Invented.",
                    "speaker_id": "paul",
                    "content_kind": "dialogue",
                    "confidence": "medium",
                    "warning_flags": [],
                },
                {
                    "text": " Third.",
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "confidence": "high",
                    "warning_flags": [],
                },
            ]
        },
        _direct_speaker_catalog(),
        "en",
    )

    assert [block["source_text"] for block in blocks] == ["First.", " Second.", " Third."]
    assert [block["text"] for block in blocks] == ["First.", "Second.", "Third."]
    assert blocks[1]["speaker_id"] == "narrator"
    assert "needs_review" in blocks[1]["warning_flags"]
    assert "source_gap" in blocks[1]["warning_flags"]
    assert all(block["source_text"] != "Invented." for block in blocks)
    assert any("unmatched_model_text" in str(warning["reason"]) for warning in warnings)


def test_direct_blocks_ignore_whitespace_model_blocks_and_preserve_source_gaps() -> None:
    """
    @brief      Verify whitespace model blocks are ignored while missed source text remains reviewable.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-07
    @version    0.1.0
    """
    blocks, _warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": "A.\n\nB."},
        {
            "blocks": [
                {
                    "text": "\n\n",
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "confidence": "high",
                    "warning_flags": [],
                },
                {
                    "text": "B.",
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "confidence": "high",
                    "warning_flags": [],
                },
            ]
        },
        _direct_speaker_catalog(),
        "en",
    )

    assert [block["source_text"] for block in blocks] == ["A.\n\n", "B."]
    assert "source_gap" in blocks[0]["warning_flags"]
    assert "needs_review" in blocks[0]["warning_flags"]


def test_direct_blocks_split_long_blocks_to_tts_budget() -> None:
    """
    @brief      Verify long direct LLM blocks are split after attribution to fit the TTS budget.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-07
    @version    0.1.0
    """
    source_text = "One two. Three four. Five six."

    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        {"chunk_id": "chunk-0001", "text": source_text},
        {
            "blocks": [
                {
                    "text": source_text,
                    "speaker_id": "paul",
                    "content_kind": "dialogue",
                    "confidence": "high",
                    "warning_flags": [],
                }
            ]
        },
        _direct_speaker_catalog(),
        "en",
        tts_budget={"safe_word_count": 2},
    )

    assert [block["text"] for block in blocks] == ["One two.", "Three four.", "Five six."]
    assert [block["speaker_id"] for block in blocks] == ["paul", "paul", "paul"]
    assert [block["content_kind"] for block in blocks] == ["dialogue", "dialogue", "dialogue"]
    assert any("split after AI output" in str(warning["reason"]) for warning in warnings)


def _create_chunked_project(tmp_path, name: str):
    """
    @brief      Create one project fixture with deterministic chunking output.
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
        "imported_at": "2026-04-21T12:00:00+00:00",
        "size_bytes": 128,
    }
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
                        "chapter_label": "Chapter I",
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
                        "chapter_label": "Chapter I",
                        "text": 'Maria smiled. "Welcome."',
                        "source_start_line": 3,
                        "source_end_line": 3,
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


def _write_source_chunks(project_root, source_chunks: list[dict[str, object]]) -> None:
    """
    @brief      Overwrite the test chunking artifact with custom source chunks.
    @param[in]  project_root Active project root folder.
    @param[in]  source_chunks Source chunk payload list.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-28
    @version    0.1.0
    """
    chunk_payload = []
    for chunk in source_chunks:
        sequence_index = int(chunk.get("sequence_index", len(chunk_payload) + 1))
        chunk_payload.append(
            {
                "chunk_id": str(chunk.get("chunk_id", f"chunk-{sequence_index:04d}")),
                "sequence_index": sequence_index,
                "chapter_label": "Chapter I",
                "text": str(chunk.get("text", "")),
                "source_start_line": sequence_index,
                "source_end_line": sequence_index,
                "chunking_mode": "deterministic",
                "semantic_strategy": None,
                "scene_note": None,
            }
        )
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(build_chunking_document(chunk_payload), indent=2) + "\n",
        encoding="utf-8",
    )


def _seed_review_speech_blocks(project_root) -> None:
    """
    @brief      Write a minimal new-schema Speech Blocks review fixture.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    speech_blocks_payload = [
        {
            "speech_block_id": "0001-000001",
            "sequence_index": 1,
            "chunk_id": "chunk-0001",
            "source_language": "en",
            "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_DIALOGUE,
            "source_text": '"Hello."',
            "text": "Hello.",
            "warning_flags": ["ambiguous_speaker"],
            "approved": False,
            "approved_at": None,
        },
        {
            "speech_block_id": "0002-000001",
            "sequence_index": 1,
            "chunk_id": "chunk-0002",
            "source_language": "en",
            "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            "source_text": "Later narration.",
            "text": "Later narration.",
            "warning_flags": [],
            "approved": False,
            "approved_at": None,
        },
    ]
    speech_blocks_service.write_speech_blocks_document(
        project_root,
        {
            "status": "review_pending",
            "source": {"kind": "original", "language": "en", "fingerprint": "seed-fingerprint"},
            "ai_profile_id": "profile-1",
            "instructions": "",
            "scene_ambience": {"enabled": False},
            "response_contract": "direct_blocks",
            "token_usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "usage_available": False,
            },
            "budget_metadata": {},
            "checkpoint": {
                "next_chunk_index": 2,
                "run_token": "2026-04-24T10:00:00+00:00",
                "log_relative_path": "log_ai_speech_blocks_20260424T100000Z.log",
                "source_snapshot_fingerprint": "seed-fingerprint",
                "source_language": "en",
                "ai_profile_id": "profile-1",
                "additional_speech_block_instructions_fingerprint": "",
                "speech_blocks_response_contract": "direct_blocks",
            },
            "failure": None,
            "blocks": speech_blocks_payload,
        },
    )


def _write_translation_artifacts(
    project_root,
    approved_chunk_count: int,
    translated_chunks: list[dict[str, object]],
    target_language: str = "ro",
) -> None:
    """
    @brief      Write translated chunk artifacts for Speech Blocks source resolution tests.
    @param[in]  project_root Active project root folder.
    @param[in]  approved_chunk_count Number of approved translated chunks.
    @param[in]  translated_chunks Translated chunk payload list.
    @param[in]  target_language Translation target language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    strict_chunks = [
        {
            "chunk_id": str(chunk.get("chunk_id", "")),
            "translated_text": str(chunk.get("translated_text", "")),
            "approved": index < approved_chunk_count,
        }
        for index, chunk in enumerate(translated_chunks)
    ]
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        json.dumps(
            {
                "target_language": target_language,
                "status": "completed" if approved_chunk_count == len(strict_chunks) else "review_pending",
                "token_usage": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "usage_available": False,
                },
                "budget_metadata": {},
                "additional_translation_instructions": "",
                "chunks": strict_chunks,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _prepare_single_chunk_generation_project(monkeypatch, tmp_path, name: str, source_text: str | None = None):
    """
    @brief      Create a one-chunk Speech Blocks project fixture and patch prompt rendering.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  name Project display name.
    @param[in]  source_text Optional custom one-chunk source text.
    @return     Tuple containing project root and loaded manifest payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, name)
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    _write_source_chunks(
        project_root,
        [
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "text": source_text or 'Narration. "Hello there."',
            }
        ],
    )
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    return project_root, project_workspace_service.load_manifest(project_root)


def _valid_single_chunk_span_response() -> dict[str, object]:
    """
    @brief      Build one valid source-span selection response for the default one-chunk fixture.
    @return     Fake Speech Blocks model response.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    return {
        "payload": {
            "blocks": [
                {
                    "source_span_ids": ["s001"],
                    "speaker_id": "narrator",
                    "content_kind": "narration",
                    "confidence": "high",
                    "warning_flags": [],
                },
                {
                    "source_span_ids": ["s002"],
                    "speaker_id": "narrator",
                    "content_kind": "dialogue",
                    "confidence": "high",
                    "warning_flags": ["ambiguous_speaker"],
                },
            ]
        },
        "usage": {"input_tokens": 2, "output_tokens": 2, "total_tokens": 4, "usage_available": True},
    }


def _narrator_catalog_entry() -> dict[str, object]:
    """
    @brief      Build the minimal narrator speaker-catalog entry used by direct normalization tests.
    @return     Narrator speaker catalog entry.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    return {
        "speaker_id": "narrator",
        "speaker_kind": "narrator",
        "display_name": "Narrator",
    }


def _direct_speaker_catalog() -> dict[str, dict[str, object]]:
    """
    @brief      Build a minimal narrator-and-character speaker catalog for direct Speech Blocks tests.
    @return     Speaker catalog payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-07
    @version    0.1.0
    """
    return {
        "narrator": _narrator_catalog_entry(),
        "paul": {
            "speaker_id": "paul",
            "speaker_kind": "character",
            "display_name": "Paul",
            "aliases": ["Paul Atreides"],
        },
    }


def _profile_payload() -> dict[str, object]:
    """
    @brief      Build one enabled Speech Blocks AI profile payload.
    @return     AI profile payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    return {
        "id": "profile-1",
        "label": "Speech Blocks Profile",
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


# END OF FILE
