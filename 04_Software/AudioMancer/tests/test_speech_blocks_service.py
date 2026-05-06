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
@version 0.9.0
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import (
    character_discovery_service,
    character_voices_service,
    project_workspace_service,
    prompt_template_service,
    speech_blocks_service,
)


def test_resolve_source_chunks_uses_original_language_selection(tmp_path) -> None:
    """
    @brief      Verify Speech Blocks uses chunking output when Character Voices selects the original language.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
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
    @version    0.1.0
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
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "source_text": "Narration. ",
                        "text": "Narration.",
                        "warning_flags": [],
                    },
                    {
                        "speaker_id": "maria",
                        "content_kind": "dialogue",
                        "source_text": '"Hello there."',
                        "text": '"Hello there."',
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
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "source_text": "Maria smiled. ",
                        "text": "Maria smiled.",
                        "warning_flags": [],
                    },
                    {
                        "speaker_id": "unknown_speaker",
                        "content_kind": "dialogue",
                        "source_text": '"Welcome."',
                        "text": '"Welcome."',
                        "warning_flags": [],
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
                "warnings": [],
            },
            "resume_checkpoint": {
                "next_chunk_index": 1,
                "source_snapshot_fingerprint": input_fingerprint,
                "source_language": "en",
                "ai_profile_id": "profile-1",
                "budget_metadata": previous_budget,
            },
        },
        input_fingerprint,
        "en",
    )

    assert restored == ([], [], 1)


def test_load_speech_blocks_rejects_legacy_global_sequence_schema(tmp_path) -> None:
    """
    @brief      Verify legacy global Speech Blocks artifacts require reset/regeneration.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksLegacySchema")
    output_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME
    output_path.write_text(
        json.dumps(
            [
                {
                    "speech_block_id": "0002-000004",
                    "sequence_index": 4,
                    "chunk_sequence_index": 1,
                    "chunk_id": "chunk-0002",
                    "source_language": "en",
                    "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
                    "speaker_id": "narrator",
                    "speaker_display_name": "Narrator",
                    "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                    "text": "Legacy block.",
                    "warning_flags": [],
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="legacy global-sequence schema"):
        speech_blocks_service.load_speech_blocks(project_root)


def test_insert_speech_block_renumbers_selected_chunk_only(tmp_path) -> None:
    """
    @brief      Verify manual insertion before a selected block resequences only that chunk.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksInsert")
    _seed_review_speech_blocks(project_root)

    _report, inserted_id = speech_blocks_service.insert_speech_block(project_root, "chunk-0001", "0001-000001")

    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert inserted_id == "0001-000002"
    assert [block["speech_block_id"] for block in speech_blocks] == [
        "0001-000002",
        "0001-000001",
        "0002-000001",
    ]
    assert speech_blocks[0]["speaker_id"] == "narrator"
    assert speech_blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_NARRATION
    assert speech_blocks[0]["text"] == ""
    assert speech_blocks[0]["approved"] is False
    assert speech_blocks[1]["text"] == "Hello."
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
        speech_blocks_service.CONTENT_KIND_BACKGROUND_NOISE,
        "Wind against the shutters.",
    )
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert speech_blocks[0]["speaker_kind"] == speech_blocks_service.SPEAKER_KIND_OPERATION
    assert speech_blocks[0]["speaker_id"] == speech_blocks_service.CONTENT_KIND_BACKGROUND_NOISE
    assert speech_blocks[0]["speaker_display_name"] == "Background Noise"
    assert speech_blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_BACKGROUND_NOISE


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
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksApprovalEdit")
    _seed_review_speech_blocks(project_root)

    approved_report = speech_blocks_service.approve_all_speech_blocks(project_root)
    assert approved_report["approved_block_count"] == 2
    assert approved_report["total_block_count"] == 2
    assert approved_report["speech_blocks_stage_status"] == speech_blocks_service.SPEECH_BLOCKS_STAGE_COMPLETED

    edited_report = speech_blocks_service.update_speech_block(
        project_root,
        "0001-000001",
        "narrator",
        speech_blocks_service.CONTENT_KIND_BACKGROUND_NOISE,
        "Wind against the shutters.",
    )
    edited_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert edited_report["warning_count"] == 0
    assert edited_blocks[0]["warning_flags"] == []
    assert edited_blocks[0]["approved"] is False
    assert edited_blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_BACKGROUND_NOISE
    assert edited_blocks[0]["speaker_kind"] == speech_blocks_service.SPEAKER_KIND_OPERATION
    assert edited_blocks[0]["speaker_id"] == speech_blocks_service.CONTENT_KIND_BACKGROUND_NOISE
    assert edited_blocks[0]["speaker_display_name"] == "Background Noise"
    assert edited_blocks[0]["text"] == "Wind against the shutters."


def test_approve_selected_speech_block_only_marks_target_block(tmp_path) -> None:
    """
    @brief      Verify selected Speech Block approval does not approve sibling blocks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    project_root, _manifest = _create_chunked_project(tmp_path, "SpeechBlocksSelectedApproval")
    _seed_review_speech_blocks(project_root)

    report = speech_blocks_service.approve_speech_block(project_root, "0001-000001")
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)

    assert report["approved_block_count"] == 1
    assert report["total_block_count"] == 2
    assert report["speech_blocks_stage_status"] == speech_blocks_service.SPEECH_BLOCKS_STAGE_IN_PROGRESS
    assert speech_blocks[0]["approved"] is True
    assert speech_blocks[0]["approved_at"] is not None
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
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "source_text": "Narration. ",
                        "text": "Narration.",
                        "warning_flags": [],
                    },
                    {
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
                        "source_text": '"Hello there."',
                        "text": '"Hello there."',
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
                        "speaker_id": "narrator",
                        "content_kind": "narration",
                        "source_text": "Maria smiled. ",
                        "text": "Maria smiled.",
                        "warning_flags": [],
                    },
                    {
                        "speaker_id": "narrator",
                        "content_kind": "dialogue",
                        "source_text": '"Welcome."',
                        "text": '"Welcome."',
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
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
        },
        {
            "payload": {
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
    @version    0.1.0
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
                "speech_blocks": [
                    {
                        "speaker_id": "maria",
                        "content_kind": "dialogue",
                        "source_text": 'Narration. "Hello there."',
                        "text": 'Narration. "Hello there."',
                        "warning_flags": [],
                    }
                ]
            },
            "usage": {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10, "usage_available": True},
        },
        {
            "payload": {
                "speech_blocks": [
                    {
                        "speaker_id": "maria",
                        "content_kind": "dialogue",
                        "source_text": 'Maria smiled. "Welcome."',
                        "text": 'Maria smiled. "Welcome."',
                        "warning_flags": [],
                    }
                ]
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
    assert rendered_prompts[1][1]["voice_assignment_mode"] == "same_narrator"
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
            ("Voice assignment mode: narrator_and_characters", '"speaker_id": "maria"'),
        ),
        (
            "same_narrator",
            "speech_blocks_narrator_only_system",
            "speech_blocks_narrator_only_user",
            False,
            ("Voice assignment mode: same_narrator", '"speaker_id": "narrator"'),
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
        }

    rendered_system_prompt = prompt_template_service.render_prompt(system_prompt_name, {})
    rendered_prompt = speech_blocks_service._chunk_user_prompt(  # noqa: SLF001
        {"chunk_id": "chunk-contract-0001", "text": 'Contract narration. "Hello there."'},
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
    assert "Allowed speaker catalog:" in rendered_prompt
    for expected_snippet in expected_snippets:
        assert expected_snippet in rendered_prompt


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
