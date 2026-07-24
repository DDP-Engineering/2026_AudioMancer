#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_chunking_state_service.py
@brief Text Chunking state-service tests for AudioMancer.
@details Verifies chunking-page notes reflect running and resumable AI chunking
         states and manual selected-chunk edits correctly.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.5.3
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import narrator_definition_service, project_workspace_service, text_chunking_state_service
from chunking_test_support import build_chunking_document, write_chunking_document


def test_build_text_chunking_notes_shows_in_progress_note_for_running_ai_chunking() -> None:
    """
    @brief      Verify running AI chunking shows only the in-progress note instead of the ready note.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    notes = text_chunking_state_service.build_text_chunking_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        cleaned_text="Cleaned text",
        chunking_report_payload=None,
        chunking_operation_state={
            "status": "running",
            "mode": "ai_assisted",
            "progress_current": 1,
            "progress_total": 29,
            "metadata": {"semantic_strategy": "scene"},
        },
        has_ai_profiles=True,
        language="en",
    )

    assert any("in progress at 1/29" in note for note in notes)
    assert not any("is ready for the current cleaned text" in note for note in notes)


def test_build_text_chunking_notes_shows_resume_note_for_failed_ai_chunking() -> None:
    """
    @brief      Verify failed AI chunking shows the resume note instead of the in-progress note.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    notes = text_chunking_state_service.build_text_chunking_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        cleaned_text="Cleaned text",
        chunking_report_payload=None,
        chunking_operation_state={
            "status": "failed",
            "mode": "ai_assisted",
            "progress_current": 1,
            "progress_total": 29,
            "metadata": {"semantic_strategy": "scene"},
        },
        has_ai_profiles=True,
        language="en",
    )

    assert any("was not finalized" in note for note in notes)
    assert not any("in progress at 1/29" in note for note in notes)


def test_build_text_chunking_notes_shows_resume_note_for_cancelled_chunking() -> None:
    """
    @brief      Verify REQ-FUNC-034 cancelled chunking shows the resumable note.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-10
    @version    0.1.0
    """
    notes = text_chunking_state_service.build_text_chunking_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        cleaned_text="Cleaned text",
        chunking_report_payload=None,
        chunking_operation_state={
            "status": "cancelled",
            "mode": "deterministic",
            "progress_current": 1,
            "progress_total": 3,
            "metadata": {},
        },
        has_ai_profiles=True,
        language="en",
    )

    assert any("was not finalized" in note for note in notes)
    assert not any("is ready" in note for note in notes)


def test_build_text_chunking_notes_shows_persisted_token_usage_summary() -> None:
    """
    @brief      Verify AI chunking notes include one persisted token-usage summary.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.0
    """
    notes = text_chunking_state_service.build_text_chunking_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        cleaned_text="Cleaned text",
        chunking_report_payload={
            "chunk_count": 4,
            "detected_chapter_count": 1,
            "chunking_mode": "ai_assisted",
            "semantic_strategy": "scene",
            "warnings": [],
            "token_usage": {
                "input_tokens": 120,
                "output_tokens": 30,
                "total_tokens": 150,
                "usage_available": True,
            },
        },
        chunking_operation_state={
            "status": "completed",
            "mode": "ai_assisted",
            "metadata": {"semantic_strategy": "scene"},
        },
        has_ai_profiles=True,
        language="en",
    )

    assert any("Input tokens: 120 | Output tokens: 30 | Total: 150" in note for note in notes)


def test_save_chunk_text_edit_persists_text_and_selectively_resets_downstream(tmp_path) -> None:
    """
    @brief      Verify selected chunk edits persist and preserve unrelated downstream data.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.3.0
    """
    project_root, manifest = project_workspace_service.create_project(
        "ChunkEditProject",
        tmp_path,
    )
    chunking_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    chunking_root.mkdir(exist_ok=True)
    chunk_artifact_path = chunking_root / config.CHUNK_ARTIFACT_FILE_NAME
    write_chunking_document(
        chunking_root,
        [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Original chunk"}],
    )
    translation_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    translation_root.mkdir(exist_ok=True)
    (translation_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        json.dumps(
            {
                "target_language": "en",
                "status": "completed",
                "token_usage": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "usage_available": False,
                },
                "budget_metadata": {},
                "additional_translation_instructions": "",
                "chunks": [{"chunk_id": "chunk-0001", "translated_text": "Translated chunk", "approved": True}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    narrator_definition_service.ensure_narrator_voice_document(project_root)
    (project_root / config.CHARACTERS_DOCUMENT_FILE_NAME).write_text(
        json.dumps(
            {
                "status": "completed",
                "source": {
                    "kind": "translated",
                    "language": "en",
                    "fingerprint": "fixture",
                },
                "instructions": "",
                "token_usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "usage_available": False,
                },
                "checkpoint": None,
                "failure": None,
                "characters": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME).write_text("[]\n", encoding="utf-8")
    manifest["current_stage"] = "character_discovery_ready"
    manifest["narrator_profile_name"] = "Warm Narrator"
    manifest["narrator_language"] = "fr"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["translation"]["status"] = "completed"
    manifest["operations"]["character_discovery"]["status"] = "completed"
    manifest["operations"]["narrator_definition"]["status"] = "completed"
    manifest["operations"]["character_voices"]["status"] = "completed"
    manifest["operations"]["speech_blocks"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)

    updated_manifest = text_chunking_state_service.save_chunk_text_edit(
        project_root,
        manifest,
        "chunk-0001",
        "Edited chunk",
    )

    document = json.loads(chunk_artifact_path.read_text(encoding="utf-8"))
    assert document["chunks"][0]["text"] == "Edited chunk"
    assert document["manual_adjusted"] is True
    assert updated_manifest["current_stage"] == "translation_ready"
    assert updated_manifest["operations"]["chunking"]["status"] == "completed"
    assert updated_manifest["operations"]["translation"]["status"] == "in_progress"
    assert updated_manifest["operations"]["character_discovery"]["status"] == "not_started"
    assert updated_manifest["operations"]["narrator_definition"]["status"] == "completed"
    assert updated_manifest["operations"]["character_voices"]["status"] == "not_started"
    assert updated_manifest["operations"]["speech_blocks"]["status"] == "not_started"
    assert updated_manifest["narrator_profile_name"] == "Warm Narrator"
    assert updated_manifest["narrator_language"] == "fr"
    translation_document = json.loads(
        (translation_root / config.TRANSLATED_CHUNKS_FILE_NAME).read_text(encoding="utf-8")
    )
    assert translation_document["chunks"][0]["translated_text"] == ""
    assert translation_document["chunks"][0]["approved"] is False
    assert (project_root / config.NARRATOR_VOICE_FILE_NAME).is_file()
    assert not (project_root / config.CHARACTERS_DOCUMENT_FILE_NAME).exists()
    assert not (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).exists()


def test_insert_chunk_preserves_existing_chunk_ids_and_translation(tmp_path) -> None:
    """
    @brief      Verify manual chunk insertion preserves existing ids and translations.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ChunkInsertProject", tmp_path)
    _write_chunks(project_root, ("First chunk", "Second chunk"))
    _write_translations(
        project_root,
        (("chunk-0001", "First chunk", "Primul"), ("chunk-0002", "Second chunk", "Al doilea")),
    )
    manifest["current_stage"] = "audio_blocks_ready"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["translation"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)

    updated_manifest = text_chunking_state_service.insert_chunk_after_selected(
        project_root,
        manifest,
        "chunk-0001",
    )

    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert [chunk["chunk_id"] for chunk in chunks] == ["chunk-0001", "chunk-0003", "chunk-0002"]
    assert [chunk["sequence_index"] for chunk in chunks] == [1, 2, 3]
    translated_chunks = json.loads((project_root / config.TRANSLATED_CHUNKS_FILE_NAME).read_text(encoding="utf-8"))[
        "chunks"
    ]
    assert [chunk["chunk_id"] for chunk in translated_chunks] == ["chunk-0001", "chunk-0003", "chunk-0002"]
    assert translated_chunks[0]["translated_text"] == "Primul"
    assert translated_chunks[1]["translated_text"] == ""
    assert translated_chunks[1]["approved"] is False
    assert translated_chunks[2]["translated_text"] == "Al doilea"
    assert updated_manifest["current_stage"] == "translation_ready"


def test_insert_chunk_creates_first_manual_chunk_when_no_chunks_exist(tmp_path) -> None:
    """
    @brief      Verify manual insertion can start a new chunk artifact before generated chunks exist.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ManualChunkStartProject", tmp_path)
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("First line\nSecond line", encoding="utf-8")

    updated_manifest = text_chunking_state_service.insert_chunk_after_selected(
        project_root,
        manifest,
        "",
    )

    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "chunk-0001"
    assert chunks[0]["sequence_index"] == 1
    assert chunks[0]["text"] == ""
    assert set(chunks[0]) == {
        "chunk_id",
        "sequence_index",
        "text",
        "cleanup_boundary_confidence",
        "cleanup_joined_across_page_break",
        "cleanup_warning_flags",
    }
    assert updated_manifest["current_stage"] == "translation_ready"


def test_delete_chunk_removes_only_selected_translation_record(tmp_path) -> None:
    """
    @brief      Verify manual chunk deletion removes only selected downstream Translation data.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ChunkDeleteProject", tmp_path)
    _write_chunks(project_root, ("First chunk", "Second chunk"))
    _write_translations(
        project_root,
        (("chunk-0001", "First chunk", "Primul"), ("chunk-0002", "Second chunk", "Al doilea")),
    )

    text_chunking_state_service.delete_selected_chunk(project_root, manifest, "chunk-0001")

    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert [chunk["chunk_id"] for chunk in chunks] == ["chunk-0002"]
    assert chunks[0]["sequence_index"] == 1
    translated_chunks = json.loads((project_root / config.TRANSLATED_CHUNKS_FILE_NAME).read_text(encoding="utf-8"))[
        "chunks"
    ]
    assert [chunk["chunk_id"] for chunk in translated_chunks] == ["chunk-0002"]
    assert translated_chunks[0]["translated_text"] == "Al doilea"


def _write_chunks(project_root, texts: tuple[str, ...]) -> None:
    """
    @brief      Write deterministic chunk fixture records.
    @param[in]  project_root Project root folder.
    @param[in]  texts Ordered chunk text values.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    chunks = [
        {
            "chunk_id": f"chunk-{index:04d}",
            "sequence_index": index,
            "text": text,
            "source_start_line": index,
            "source_end_line": index,
            "chunking_mode": "deterministic",
            "semantic_strategy": None,
            "scene_note": None,
        }
        for index, text in enumerate(texts, start=1)
    ]
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(build_chunking_document(chunks), indent=2) + "\n",
        encoding="utf-8",
    )


def _write_translations(project_root, records: tuple[tuple[str, str, str], ...]) -> None:
    """
    @brief      Write approved translation fixture records.
    @param[in]  project_root Project root folder.
    @param[in]  records Ordered chunk id, source text, and translated text tuples.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    translated_chunks = [
        {
            "chunk_id": chunk_id,
            "translated_text": translated_text,
            "approved": True,
        }
        for chunk_id, _source_text, translated_text in records
    ]
    (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text(
        json.dumps(
            {
                "target_language": "en",
                "status": "completed",
                "token_usage": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "usage_available": False,
                },
                "budget_metadata": {},
                "additional_translation_instructions": "",
                "chunks": translated_chunks,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# END OF FILE
