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
         approval/edit state, selected-chunk re-splitting, and resumable
         chunk-based generation.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.3.1
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import (
    character_discovery_service,
    character_voices_service,
    project_workspace_service,
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
                        "text": "Narration. ",
                        "warning_flags": [],
                    },
                    {
                        "speaker_id": "maria",
                        "content_kind": "dialogue",
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
                        "speaker_id": "unknown_speaker",
                        "content_kind": "dialogue",
                        "text": '"Welcome."',
                        "warning_flags": [],
                    }
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

    speech_blocks_root = project_root / config.SPEECH_BLOCKS_FOLDER_NAME
    assert (speech_blocks_root / "input_source_chunks.json").is_file()
    assert (speech_blocks_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).is_file()
    assert (speech_blocks_root / config.SPEECH_BLOCKS_REPORT_FILE_NAME).is_file()
    assert (speech_blocks_root / config.OPERATION_STATE_FILE_NAME).is_file()
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert [block["speech_block_id"] for block in speech_blocks] == [
        "0001-000001",
        "0001-000002",
        "0002-000003",
        "0002-000004",
    ]
    assert [block["approved"] for block in speech_blocks] == [False, False, False, False]
    assert speech_blocks[0]["text"] == "Narration."
    assert speech_blocks[0]["ai_text"] == "Narration."
    assert speech_blocks[1]["speaker_id"] == "maria"
    assert speech_blocks[1]["text"] == "Hello there."
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


def test_approve_all_edit_and_reset_preserve_warning_cleared_state(tmp_path) -> None:
    """
    @brief      Verify approval plus selected-block edit/reset warning state semantics.
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
    assert edited_blocks[0]["text"] == "Wind against the shutters."

    reset_report = speech_blocks_service.reset_speech_block_to_ai_baseline(project_root, "0001-000001")
    reset_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert reset_report["warning_count"] == 0
    assert reset_blocks[0]["warning_flags"] == []
    assert reset_blocks[0]["approved"] is False
    assert reset_blocks[0]["content_kind"] == speech_blocks_service.CONTENT_KIND_DIALOGUE
    assert reset_blocks[0]["text"] == "Hello."


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
                        "text": 'Narration. "Hello there."',
                        "warning_flags": [],
                    }
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
    assert [block["speech_block_id"] for block in speech_blocks] == [
        "0001-000001",
        "0001-000002",
        "0002-000003",
    ]
    assert [block["chunk_id"] for block in speech_blocks] == ["chunk-0001", "chunk-0001", "chunk-0002"]
    assert speech_blocks[0]["approved"] is False
    assert speech_blocks[0]["text"] == "Narration."
    assert speech_blocks[1]["text"] == "Hello there."
    assert speech_blocks[2]["text"] == "Later narration."
    assert report["approved_block_count"] == 0
    assert report["total_block_count"] == 3


def test_normalize_chunk_blocks_preserves_dialogue_and_attribution_boundaries() -> None:
    """
    @brief      Verify deterministic source spans prevent dialogue and attribution text from being merged.
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
                "text": "Ottmar Drenthe watched the screen.",
                "warning_flags": [],
            },
            {
                "speaker_id": "ottmar_drenthe",
                "content_kind": "dialogue",
                "text": "Different how?",
                "warning_flags": [],
            },
            {
                "speaker_id": "ottmar_drenthe",
                "content_kind": "dialogue",
                "text": "I am Drenthe.",
                "warning_flags": [],
            },
            {
                "speaker_id": "narrator",
                "content_kind": "narration",
                "text": "Sure, absolutely, his agent said. But I have an offer.",
                "warning_flags": ["ambiguous_speaker"],
            },
        ]
    }

    blocks, warnings = speech_blocks_service._normalize_chunk_blocks(  # noqa: SLF001
        source_chunk,
        response_payload,
        speaker_catalog,
        0,
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
                    "text": "Where is the engineer now?",
                    "warning_flags": ["ambiguous_speaker"],
                }
            ]
        },
        speaker_catalog,
        0,
        "en",
    )

    assert blocks[0]["speaker_id"] == "ottmar_drenthe"
    assert blocks[0]["speaker_display_name"] == "Ottmar Drenthe"
    assert blocks[0]["warning_flags"] == ["ambiguous_speaker"]
    assert len(warnings) == 1


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
        speech_blocks_service._normalize_block_text('He said "Hello there."', "dialogue")  # noqa: SLF001
        == 'He said "Hello there."'
    )
    assert (
        speech_blocks_service._normalize_block_text('"Hello there."', "narration")  # noqa: SLF001
        == '"Hello there."'
    )


def test_start_or_continue_generation_resumes_from_next_chunk(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify Speech Blocks resume continues from the next incomplete chunk.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    project_root, manifest = _create_chunked_project(tmp_path, "SpeechBlocksResume")
    manifest["original_language"] = "en"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    source_resolution = speech_blocks_service.resolve_source_chunks(project_root, manifest)
    existing_blocks = [
        {
            "speech_block_id": "0001-000001",
            "sequence_index": 1,
            "chunk_id": "chunk-0001",
            "chunk_sequence_index": 1,
            "source_language": "en",
            "speaker_kind": "narrator",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": "narration",
            "text": "Narration. ",
            "warning_flags": [],
        }
    ]
    fingerprint = speech_blocks_service._build_source_fingerprint(source_resolution["source_chunks"], "en", "original")  # noqa: SLF001
    report = speech_blocks_service._rebuild_report(  # noqa: SLF001
        existing_blocks,
        "en",
        "original",
        "profile-1",
        2,
        1,
        [],
        {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7, "usage_available": True},
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
            log_path=project_root / config.SPEECH_BLOCKS_FOLDER_NAME / "log_ai_transactions_resume.log",
            token_usage={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7, "usage_available": True},
            next_chunk_index=1,
        ),
    )
    monkeypatch.setattr(speech_blocks_service.prompt_template_service, "validate_required_prompts", lambda _names: None)
    monkeypatch.setattr(
        speech_blocks_service.prompt_template_service,
        "render_prompt",
        lambda _name, variables: f"prompt {variables}",
    )
    calls: list[str] = []
    monkeypatch.setattr(
        speech_blocks_service.llm_provider_service,
        "chat_json",
        lambda *_args, **_kwargs: (
            calls.append("called")
            or {
                "payload": {
                    "speech_blocks": [
                        {
                            "speaker_id": "narrator",
                            "content_kind": "narration",
                            "text": 'Maria smiled. "Welcome."',
                            "warning_flags": [],
                        }
                    ]
                },
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "usage_available": True},
            }
        ),
    )

    report = speech_blocks_service.start_or_continue_generation(project_root, manifest, _profile_payload())

    assert len(calls) == 1
    speech_blocks = speech_blocks_service.load_speech_blocks(project_root)
    assert len(speech_blocks) == 3
    assert speech_blocks[0]["chunk_id"] == "chunk-0001"
    assert speech_blocks[1]["chunk_id"] == "chunk-0002"
    assert speech_blocks[1]["text"] == "Maria smiled."
    assert speech_blocks[2]["text"] == "Welcome."
    assert report["processed_chunk_count"] == 2
    assert report["token_usage"]["total_tokens"] == 22


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
    (project_root / config.CHUNKING_FOLDER_NAME / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
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
    speech_blocks_root = project_root / config.SPEECH_BLOCKS_FOLDER_NAME
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
            "chunk_sequence_index": 1,
            "source_language": "en",
            "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_DIALOGUE,
            "text": "Hello.",
            "ai_speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
            "ai_speaker_id": "narrator",
            "ai_speaker_display_name": "Narrator",
            "ai_content_kind": speech_blocks_service.CONTENT_KIND_DIALOGUE,
            "ai_text": "Hello.",
            "warning_flags": ["ambiguous_speaker"],
            "approved": False,
            "approved_at": None,
        },
        {
            "speech_block_id": "0002-000002",
            "sequence_index": 2,
            "chunk_id": "chunk-0002",
            "chunk_sequence_index": 1,
            "source_language": "en",
            "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            "text": "Later narration.",
            "ai_speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
            "ai_speaker_id": "narrator",
            "ai_speaker_display_name": "Narrator",
            "ai_content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            "ai_text": "Later narration.",
            "warning_flags": [],
            "approved": False,
            "approved_at": None,
        },
    ]
    source_chunks_path = (
        speech_blocks_root / f"{config.OPERATION_INPUT_FILE_PREFIX}{config.SPEECH_BLOCKS_SOURCE_CHUNKS_FILE_NAME}"
    )
    source_chunks_path.write_text(
        json.dumps(source_chunks_payload, indent=2) + "\n",
        encoding="utf-8",
    )
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


def _write_translation_artifacts(
    project_root,
    approved_chunk_count: int,
    translated_chunks: list[dict[str, object]],
) -> None:
    """
    @brief      Write translated chunk artifacts for Speech Blocks source resolution tests.
    @param[in]  project_root Active project root folder.
    @param[in]  approved_chunk_count Number of approved translated chunks.
    @param[in]  translated_chunks Translated chunk payload list.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    (project_root / config.TRANSLATION_FOLDER_NAME / config.TRANSLATION_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "target_language": "ro",
                "translated_chunk_count": len(translated_chunks),
                "approved_chunk_count": approved_chunk_count,
                "total_chunk_count": len(translated_chunks),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / config.TRANSLATION_FOLDER_NAME / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        json.dumps(translated_chunks, indent=2) + "\n",
        encoding="utf-8",
    )


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
