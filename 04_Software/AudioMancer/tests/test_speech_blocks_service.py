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
    project_workspace_service,
    prompt_template_service,
    speech_blocks_service,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_resolve_source_chunks_uses_original_language_selection(tmp_path) -> None:
    """
    @brief      Verify Speech Blocks uses chunking output when Character Voices selects the original language.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksOriginal")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")

    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)

    assert source_resolution["source_kind"] == "original"
    assert source_resolution["selected_source_language"] == "en"
    assert source_resolution["source_chunks"][0]["text"] == 'Narration. "Hello there."'


def test_resolve_source_chunks_requires_fully_approved_translation(tmp_path) -> None:
    """
    @brief      Verify translated Speech Blocks sources require full translation approval.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
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

    with pytest.raises(ValueError, match="Approve all translated chunks"):
        speech_blocks_service.resolve_source_chunks(project_root, manifest)


def test_resolve_source_chunks_uses_approved_translated_language_selection(tmp_path) -> None:
    """
    @brief      Verify Speech Blocks uses approved translated chunks when Character Voices selects the translated
                language.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
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
                "speech_blocks": [
                    {
                        "source_span_ids": ["s001"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "warning_flags": [],
                    },
                    {
                        "source_span_ids": ["s002"],
                        "speaker_id": "maria",
                        "content_kind": "dialogue",
                        "warning_flags": [],
                    },
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
        },
        {
            "payload": {
                "speech_blocks": [
                    {
                        "source_span_ids": ["s001"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "warning_flags": [],
                    },
                    {
                        "source_span_ids": ["s002"],
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
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
    assert (speech_blocks_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).is_file()
    assert (speech_blocks_root / config.SPEECH_BLOCKS_REPORT_FILE_NAME).is_file()
    assert (speech_blocks_root / config.SPEECH_BLOCKS_STATE_FILE_NAME).is_file()
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


def test_start_generation_repairs_malformed_source_span_json_once(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify malformed local-model JSON gets one compact Speech Blocks repair retry.
    @details    Covers SB3-SPEC-002 and REQ-FUNC-045.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    project_root, manifest = _prepare_single_chunk_generation_project(monkeypatch, tmp_path, "SpeechBlocksJsonRepair")
    calls: list[dict[str, object]] = []

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **kwargs):
        """
        @brief      Raise one malformed JSON failure, then return a valid repaired span selection.
        @param[in]  _profile Ignored AI profile payload.
        @param[in]  _system_prompt Ignored system prompt.
        @param[in]  user_prompt Captured prompt.
        @param[in]  kwargs Captured keyword arguments.
        @return     Fake repaired Speech Blocks model response.
        @exception  ValueError Raised on the first request to simulate malformed JSON.
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-01
        @version    0.1.0
        """
        calls.append({"user_prompt": str(user_prompt), "kwargs": dict(kwargs)})
        if len(calls) == 1:
            raise ValueError("AI response is not valid JSON.")
        return _valid_single_chunk_span_response()

    monkeypatch.setattr(speech_blocks_service.llm_provider_service, "chat_json", _fake_chat_json)

    speech_blocks_service.start_or_continue_generation(project_root, manifest, _profile_payload())

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert len(calls) == 2
    assert calls[1]["kwargs"].get("structured_output") is True
    assert "Narration." not in str(calls[1]["user_prompt"])
    assert [block["speaker_id"] for block in speech_blocks] == ["narrator", "narrator"]
    assert [block["text"] for block in speech_blocks] == ["Narration.", "Hello there."]
    assert all("source_span_selection_invalid" not in block["warning_flags"] for block in speech_blocks)


@pytest.mark.parametrize(
    ("first_response", "expected_error_token"),
    [
        (
            {
                "payload": {
                    "blocks": [
                        {
                            "source_span_ids": ["BAD SPAN"],
                            "speaker_id": "narrator",
                            "content_kind": "narration",
                            "confidence": "high",
                            "warning_flags": [],
                        }
                    ]
                },
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "usage_available": True},
            },
            "illegal_span_id",
        ),
        (
            {
                "payload": {
                    "blocks": [
                        {
                            "source_span_ids": ["s999"],
                            "speaker_id": "narrator",
                            "content_kind": "narration",
                            "confidence": "high",
                            "warning_flags": [],
                        }
                    ]
                },
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "usage_available": True},
            },
            "halo_span_id",
        ),
        (
            {
                "payload": {
                    "blocks": [
                        {
                            "source_span_ids": ["s001"],
                            "speaker_id": "narrator",
                            "content_kind": "narration",
                            "warning_flags": [],
                        },
                        {
                            "source_span_ids": ["s002"],
                            "speaker_id": "narrator",
                            "content_kind": "dialogue",
                            "warning_flags": ["ambiguous_speaker"],
                        },
                    ]
                },
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "usage_available": True},
            },
            "missing_confidence",
        ),
    ],
)
def test_start_generation_repairs_semantically_invalid_source_span_selection(
    monkeypatch,
    tmp_path,
    first_response: dict[str, object],
    expected_error_token: str,
) -> None:
    """
    @brief      Verify invalid source-span selections trigger one compact repair retry.
    @details    Covers SB3-SPEC-002, REQ-FUNC-045, and REQ-DATA-006.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  first_response Initial semantically invalid model response.
    @param[in]  expected_error_token Compact error token expected in the repair prompt.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    project_root, manifest = _prepare_single_chunk_generation_project(
        monkeypatch,
        tmp_path,
        f"SpeechBlocksSemanticRepair-{expected_error_token}",
    )
    responses = [first_response, _valid_single_chunk_span_response()]
    calls: list[dict[str, object]] = []

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **kwargs):
        """
        @brief      Return an invalid response followed by one repaired response.
        @param[in]  _profile Ignored AI profile payload.
        @param[in]  _system_prompt Ignored system prompt.
        @param[in]  user_prompt Captured prompt.
        @param[in]  kwargs Captured keyword arguments.
        @return     Fake Speech Blocks model response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-01
        @version    0.1.0
        """
        calls.append({"user_prompt": str(user_prompt), "kwargs": dict(kwargs)})
        return responses.pop(0)

    monkeypatch.setattr(speech_blocks_service.llm_provider_service, "chat_json", _fake_chat_json)

    speech_blocks_service.start_or_continue_generation(project_root, manifest, _profile_payload())

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert len(calls) == 2
    assert expected_error_token in str(calls[1]["user_prompt"])
    assert "Narration." not in str(calls[1]["user_prompt"])
    assert [block["source_text"] for block in speech_blocks] == ["Narration. ", '"Hello there."']
    assert [block["text"] for block in speech_blocks] == ["Narration.", "Hello there."]
    assert all("source_span_selection_invalid" not in block["warning_flags"] for block in speech_blocks)


def test_start_generation_fallback_after_repair_failure_preserves_source_order_and_logs_compactly(
    monkeypatch,
    tmp_path,
    caplog,
) -> None:
    """
    @brief      Verify repair failure falls back to safe narrator blocks and compact validation logging.
    @details    Covers SB3-SPEC-003, SB3-SPEC-004, REQ-FUNC-046, and REQ-DATA-006.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  caplog Pytest log capture fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
    """
    source_text = 'Narration. "Hello there."'
    project_root, manifest = _prepare_single_chunk_generation_project(
        monkeypatch,
        tmp_path,
        "SpeechBlocksRepairFallback",
        source_text=source_text,
    )
    responses = [
        {
            "payload": {
                "blocks": [
                    {
                        "source_span_ids": ["s999"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    }
                ]
            },
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "usage_available": True},
        },
        {
            "payload": {
                "blocks": [
                    {
                        "source_span_ids": ["s999"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "confidence": "high",
                        "warning_flags": [],
                    }
                ]
            },
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "usage_available": True},
        },
    ]
    calls: list[str] = []

    def _fake_chat_json(_profile, _system_prompt, user_prompt, **_kwargs):
        """
        @brief      Return two unusable source-span selections.
        @param[in]  _profile Ignored AI profile payload.
        @param[in]  _system_prompt Ignored system prompt.
        @param[in]  user_prompt Captured prompt.
        @param[in]  _kwargs Ignored keyword arguments.
        @return     Fake invalid Speech Blocks model response.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-07-01
        @version    0.1.0
        """
        calls.append(str(user_prompt))
        return responses.pop(0)

    monkeypatch.setattr(speech_blocks_service.llm_provider_service, "chat_json", _fake_chat_json)
    caplog.set_level("INFO", logger="speech_blocks")

    speech_blocks_service.start_or_continue_generation(project_root, manifest, _profile_payload())

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert len(calls) == 2
    assert len(speech_blocks) == 1
    assert speech_blocks[0]["speaker_id"] == "narrator"
    assert speech_blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_NARRATION
    assert speech_blocks[0]["source_text"] == source_text
    assert speech_blocks[0]["text"] == "Narration. Hello there."
    assert "source_span_selection_invalid" in speech_blocks[0]["warning_flags"]
    assert "speech_blocks_source_span_validation_failed" in caplog.text
    assert "s999" in caplog.text
    assert source_text not in caplog.text


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
                "speech_blocks": [
                    {
                        "source_span_ids": ["s001"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "warning_flags": [],
                    },
                    {
                        "source_span_ids": ["s002"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
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
                "speech_blocks": [
                    {
                        "source_span_ids": ["s001", "s002"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "source_text": chunk_text,
                        "text": chunk_text,
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
                "speech_blocks": [
                    {
                        "source_span_ids": ["s001"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "source_text": segment_text,
                        "text": segment_text.strip(),
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

    assert restored == ([], [], 1)


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

    assert restored == ([], [], 1)


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


def test_speech_blocks_resume_preserves_same_narrator_boundary_state(tmp_path) -> None:
    """
    @brief      Verify same-narrator boundary-ID partial state remains resumable.
    @details    Covers SBCON-004 and REQ-FUNC-041.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-01
    @version    0.1.0
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
                "speech_blocks_response_contract": "narrator_boundary_ids",
            },
            "resume_checkpoint": {
                "next_chunk_index": 1,
                "source_snapshot_fingerprint": input_fingerprint,
                "source_language": "en",
                "speech_blocks_response_contract": "narrator_boundary_ids",
            },
        },
        None,
        input_fingerprint,
        "en",
        len(source_chunks),
        speech_blocks_service._compute_prompt_fingerprint(""),  # noqa: SLF001
    )

    assert restored == ([], [], 1)


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
    assert len(operation_state["metadata"]["source_chunks"]) == 2
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
    state_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.SPEECH_BLOCKS_STATE_FILE_NAME
    state_path.write_text(
        json.dumps(
            {
                "started_at": None,
                "artifact_paths": ["log_ai_speech_blocks_None.log"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

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
    state_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.SPEECH_BLOCKS_STATE_FILE_NAME
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    state_payload["started_at"] = "None"
    state_payload["completed_at"] = "null"
    state_payload["artifact_paths"] = ["speech_blocks_report.json", "log_ai_speech_blocks_None.log"]
    state_path.write_text(json.dumps(state_payload, indent=2) + "\n", encoding="utf-8")

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
    speech_blocks_path = (
        project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME
    )
    speech_blocks = json.loads(speech_blocks_path.read_text(encoding="utf-8"))
    speech_blocks[0]["speaker_kind"] = speech_blocks_service.SPEAKER_KIND_CHARACTER
    speech_blocks[0]["speaker_id"] = "alice"
    speech_blocks[0]["speaker_display_name"] = "Alice"
    speech_blocks[0]["approved"] = True
    speech_blocks[0]["approved_at"] = "2026-04-24T12:00:00+00:00"
    speech_blocks_path.write_text(json.dumps(speech_blocks, indent=2) + "\n", encoding="utf-8")

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
                "speech_blocks": [
                    {
                        "source_span_ids": ["s001"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "warning_flags": [],
                    },
                    {
                        "source_span_ids": ["s002"],
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
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


def test_normalize_chunk_blocks_flags_invalid_source_spans_and_modified_text() -> None:
    """
    @brief      Verify source-span validation annotates suspicious AI output.
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

    assert "source_coverage_mismatch" in blocks[0]["warning_flags"]
    assert "source_order_mismatch" in blocks[1]["warning_flags"]
    assert "model_text_modified" in blocks[1]["warning_flags"]
    assert {warning["reason"] for warning in warnings} >= {
        "Model source spans do not fully cover the chunk in reading order.",
        "Model source spans are not in chunk reading order.",
        "Model audio text differs from the source span beyond delimiter cleanup.",
    }


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
        speech_blocks_service._build_operation_state(  # noqa: SLF001
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
                "speech_blocks": [
                    {
                        "source_span_ids": ["s001"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "warning_flags": [],
                    },
                    {
                        "source_span_ids": ["s002"],
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
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
        speech_blocks_service._build_operation_state(  # noqa: SLF001
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
                "speech_blocks": [
                    {
                        "source_span_ids": ["s001"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "warning_flags": [],
                    },
                    {
                        "source_span_ids": ["s002"],
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
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
                "speech_blocks": [
                    {
                        "source_span_ids": ["s001"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "source_text": "Il dit : ",
                        "text": "Il dit :",
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
                        "source_span_ids": ["s003"],
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "source_text": " Elle sourit.",
                        "text": "Elle sourit.",
                        "warning_flags": [],
                    },
                ]
            },
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
        },
        {
            "payload": {
                "speech_blocks": [
                    {
                        "source_span_ids": ["s001"],
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
                        "source_text": "- Bonjour, dit-elle.",
                        "text": "- Bonjour, dit-elle.",
                        "warning_flags": ["ambiguous_speaker"],
                    },
                    {
                        "source_span_ids": ["s002"],
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
                        "source_text": " - Venez ici.",
                        "text": "- Venez ici.",
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


def test_start_generation_uses_narrator_only_prompt_for_same_narrator(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify same-narrator projects use the narrator-only prompt pair and force narrator blocks.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksNarratorOnly")
    manifest["original_language"] = "en"
    manifest["target_language"] = "en"
    manifest["selected_voice_language"] = "en"
    manifest["voice_assignment_mode"] = "same_narrator"
    manifest["project_options_locked"] = True
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    validated_prompt_names = []
    rendered_prompts = []
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "validate_required_prompts",
        lambda names: validated_prompt_names.extend(names),
    )

    def _render_prompt(name, variables):
        """
        @brief      Provide the render prompt test helper.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-05-02
        @version    0.1.0
        """
        rendered_prompts.append((name, dict(variables)))
        return f"prompt {name}"

    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "render_prompt", _render_prompt)
    responses = [
        {
            "payload": {
                "boundary_ids": ["b0002"],
            },
            "usage": {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10, "usage_available": True},
        },
        {
            "payload": {
                "boundary_ids": ["b0002"],
            },
            "usage": {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10, "usage_available": True},
        },
    ]
    monkeypatch.setattr(
        speech_blocks_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: responses.pop(0),
    )

    speech_blocks_service.start_or_continue_generation(project_root, manifest, _profile_payload())

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert validated_prompt_names == ["speech_blocks_narrator_only_system", "speech_blocks_narrator_only_user"]
    assert rendered_prompts[1][0] == "speech_blocks_narrator_only_user"
    assert rendered_prompts[1][1]["split_boundary_candidates_json"]
    assert rendered_prompts[1][1]["max_tts_tokens"]
    assert {block["speaker_id"] for block in speech_blocks} == {"narrator"}
    assert {block["content_kind"] for block in speech_blocks} == {speech_blocks_service.CONTENT_KIND_NARRATION}
    assert speech_blocks[0]["text"] == 'Narration. "Hello there."'


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
        (
            "same_narrator",
            "speech_blocks_narrator_only_system",
            "speech_blocks_narrator_only_user",
            False,
            ("Narration mode: same_narrator", '"boundary_id"'),
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
        assert "`unit_ids`" in rendered_system_prompt
        assert "`source_span_ids`" not in rendered_system_prompt
        assert "`source_text`" not in rendered_system_prompt
        assert "`text`" not in rendered_system_prompt
        assert "`speech_blocks`" not in rendered_system_prompt
        assert "Do not translate" in rendered_system_prompt
        assert "Romanian" in rendered_system_prompt
        assert "Do not select text from previous or next context" in rendered_prompt
        assert "Maria ridica mana" in rendered_prompt
        assert "Pilotul ii raspunse" in rendered_prompt
        assert "previous_context" in rendered_prompt
        assert "next_context" in rendered_prompt
        assert "h001" not in rendered_prompt
    else:
        assert "Candidate split boundaries:" in rendered_prompt
    for expected_snippet in expected_snippets:
        assert expected_snippet in rendered_prompt


def test_speech_blocks_prompt_uses_atomic_units_and_forbids_text_rewrites() -> None:
    """
    @brief      Verify the narrator-and-character prompt exposes atomic units, not model-owned text blocks.
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

    assert "Available atomic speech units:" in rendered_prompt
    assert '"atomic_unit_id": "u001"' in rendered_prompt
    assert '"structural_kind": "attribution"' in rendered_prompt
    assert '"source_span_id": "s001"' in rendered_prompt
    assert "assign speakers to existing atomic units only" in rendered_system_prompt
    assert "`unit_ids`" in rendered_system_prompt
    assert "`source_span_ids`" not in rendered_system_prompt
    assert "`source_text`" not in rendered_system_prompt
    assert "`text`" not in rendered_system_prompt


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


def test_speech_blocks_atomic_prompt_omits_separator_only_units() -> None:
    """
    @brief      Verify separator-only atomic units are not exposed as selectable prompt rows.
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
    assert '"text": "\\n"' not in rendered_prompt
    assert "selectable speakable atomic unit" in rendered_system_prompt
    assert "Separator-only" in rendered_system_prompt


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


def test_speech_blocks_atomic_prompt_includes_aliases_and_attribution_hints() -> None:
    """
    @brief      Verify source-language aliases and deterministic attribution hints are available to speaker assignment.
    @details    Covers SB-ATOMIC-004 and REQ-FUNC-053.
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
    assert '"speaker_hint_ids": [' in rendered_prompt
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
    @version    0.1.0
    """
    cleanup_prompt = (config.APP_PROMPTS_PATH / "text_cleanup_system.txt").read_text(encoding="utf-8")
    translation_prompt = (config.APP_PROMPTS_PATH / "text_translation_system.txt").read_text(encoding="utf-8")
    chunking_prompt = (config.APP_PROMPTS_PATH / "text_chunking_system.txt").read_text(encoding="utf-8")

    assert "Romanian guillemets" in cleanup_prompt
    assert "dash-led dialogue" in cleanup_prompt
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
    settings_source = (
        _REPO_ROOT / "04_Software/AudioMancer/src/audiomancer/services/settings_service.py"
    ).read_text(encoding="utf-8")

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


def test_normalize_narrator_boundary_blocks_builds_exact_source_spans() -> None:
    """
    @brief      Verify narrator-only boundary IDs are converted into exact deterministic source spans.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    source_chunk = {"chunk_id": "chunk-0001", "text": "First sentence. Second sentence."}

    blocks, warnings = speech_blocks_service._normalize_narrator_boundary_blocks(  # noqa: SLF001
        source_chunk,
        {"boundary_ids": ["b0001"]},
        "en",
        {"safe_word_count": 20},
    )

    assert [block["source_text"] for block in blocks] == ["First sentence. ", "Second sentence."]
    assert "".join(str(block["source_text"]) for block in blocks) == source_chunk["text"]
    assert [block["text"] for block in blocks] == ["First sentence.", "Second sentence."]
    assert {block["speaker_id"] for block in blocks} == {"narrator"}
    assert {block["content_kind"] for block in blocks} == {speech_blocks_service.CONTENT_KIND_NARRATION}
    assert warnings == []


def test_narrator_boundary_candidates_skip_open_quote_sentence_boundary() -> None:
    """
    @brief      Verify same-narrator boundary candidates do not split inside an open quote.
    @details    Covers SB-NARRATOR-QUOTE-001 and REQ-FUNC-055.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    source_text = (
        "He had been working on it for years.\n"
        '"As in, the credit is not coming together. See what I am saying?"\n'
        "Drenthe sighed."
    )
    unsafe_offset = source_text.index(" See what") + 1
    safe_quote_end_offset = source_text.index('"\n') + 1

    candidates = speech_blocks_service._narrator_split_boundary_candidates(  # noqa: SLF001
        source_text,
        safe_word_count=200,
    )

    candidate_offsets = {int(candidate["offset"]) for candidate in candidates}
    assert unsafe_offset not in candidate_offsets
    assert safe_quote_end_offset in candidate_offsets


def test_normalize_narrator_boundary_blocks_rejects_open_quote_split() -> None:
    """
    @brief      Verify same-narrator boundary normalization rejects in-quote selected boundaries.
    @details    Covers SB-NARRATOR-QUOTE-001 and REQ-FUNC-055.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-02
    @version    0.1.0
    """
    source_text = (
        "He had been working on it for years.\n"
        '"As in, the credit is not coming together. See what I am saying?"\n'
        "Drenthe sighed."
    )
    unsafe_offset = source_text.index(" See what") + 1
    source_chunk = {
        "chunk_id": "chunk-0001",
        "text": source_text,
        "narrator_boundary_candidates": [
            {
                "boundary_id": "b0001",
                "offset": unsafe_offset,
                "approx_words_since_previous": 8,
                "is_final": False,
                "context": "credit is not coming together. See what I am saying?",
            },
            {
                "boundary_id": "b0002",
                "offset": len(source_text),
                "approx_words_since_previous": 10,
                "is_final": True,
                "context": "See what I am saying? Drenthe sighed.",
            },
        ],
    }

    blocks, warnings = speech_blocks_service._normalize_narrator_boundary_blocks(  # noqa: SLF001
        source_chunk,
        {"boundary_ids": ["b0001"]},
        "en",
        {"safe_word_count": 200},
    )

    assert len(blocks) == 1
    assert blocks[0]["source_text"] == source_text
    assert "boundary_selection_fallback" in blocks[0]["warning_flags"]
    assert warnings[0]["reason"] == speech_blocks_service._speech_block_warning_reason(  # noqa: SLF001
        "boundary_selection_fallback"
    )


def test_normalize_narrator_boundary_blocks_falls_back_on_unusable_ids() -> None:
    """
    @brief      Verify narrator-only boundary failures become deterministic review warnings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-12
    @version    0.1.0
    """
    source_chunk = {"chunk_id": "chunk-0001", "text": "First sentence. Second sentence."}

    blocks, warnings = speech_blocks_service._normalize_narrator_boundary_blocks(  # noqa: SLF001
        source_chunk,
        {"boundary_ids": ["unknown-boundary"]},
        "en",
        {"safe_word_count": 20},
    )

    assert "".join(str(block["source_text"]) for block in blocks) == source_chunk["text"]
    assert "boundary_selection_fallback" in blocks[0]["warning_flags"]
    assert warnings[0]["reason"] == speech_blocks_service._speech_block_warning_reason(  # noqa: SLF001
        "boundary_selection_fallback"
    )


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
            ],
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
        json.dumps(chunk_payload, indent=2) + "\n",
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
    speech_blocks_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    source_chunks_payload = [
        {
            "chunk_id": "chunk-0001",
            "sequence_index": 1,
            "text": 'Narration. "Hello there."',
        },
        {
            "chunk_id": "chunk-0002",
            "sequence_index": 2,
            "text": 'Maria smiled. "Welcome."',
        },
    ]
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
    _ = source_chunks_payload
    (speech_blocks_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(speech_blocks_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (speech_blocks_root / config.SPEECH_BLOCKS_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "source_language": "en",
                "source_kind": "original",
                "ai_profile_id": "profile-1",
                "speech_blocks_stage_status": speech_blocks_service.SPEECH_BLOCKS_STAGE_IN_PROGRESS,
                "processed_chunk_count": 2,
                "total_chunk_count": 2,
                "speech_block_count": 2,
                "approved_block_count": 0,
                "total_block_count": 2,
                "warning_count": 1,
                "warnings": [],
                "token_usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "usage_available": False,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (speech_blocks_root / config.SPEECH_BLOCKS_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "status": "review_pending",
                "metadata": {
                    "source_language": "en",
                    "source_kind": "original",
                    "ai_profile_id": "profile-1",
                    "source_chunks": source_chunks_payload,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
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
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.TRANSLATION_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "target_language": target_language,
                "translated_chunk_count": len(translated_chunks),
                "approved_chunk_count": approved_chunk_count,
                "total_chunk_count": len(translated_chunks),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        json.dumps(translated_chunks, indent=2) + "\n",
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
