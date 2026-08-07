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
"""

# IMPORTS

import json

import pytest

from audiomancer import config
from audiomancer.services import narrator_definition_service, project_workspace_service, text_chunking_state_service
from chunking_test_support import build_chunking_document, write_chunking_document


def test_build_text_chunking_notes_shows_in_progress_note_for_running_ai_chunking() -> None:
    """
    @brief      Verify running AI chunking shows only the in-progress note instead of the ready note.
    @return     None.
    @exception  None
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

    assert any("in progress from the saved checkpoint using the scene strategy" in note for note in notes)
    assert not any("is ready for the current cleaned text" in note for note in notes)


def test_build_text_chunking_notes_shows_resume_note_for_failed_ai_chunking() -> None:
    """
    @brief      Verify failed AI chunking shows the resume note instead of the in-progress note.
    @return     None.
    @exception  None
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


@pytest.mark.parametrize(
    ("status", "mode", "strategy", "language", "expected_note"),
    [
        ("running", "deterministic", None, "en", "Deterministic chunking is in progress"),
        ("running", "ai_assisted", "scene", "ro", "Segmentarea asistata de AI este in curs"),
        ("failed", "ai_assisted", "meaning", "en", "was not finalized"),
        ("cancelled", "deterministic", None, "en", "was not finalized"),
        ("completed", "ai_assisted", "scene", "en", "AI-assisted chunking produced"),
    ],
)
def test_build_text_chunking_state_uses_persisted_lifecycle_without_fabricated_progress(
    tmp_path,
    status: str,
    mode: str,
    strategy: str | None,
    language: str,
    expected_note: str,
) -> None:
    """
    @brief      Verify production page state exposes durable Chunking lifecycle facts.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @param[in]  status Persisted Chunking lifecycle state under evaluation.
    @param[in]  mode Persisted Chunking mode under evaluation.
    @param[in]  strategy Persisted AI strategy when applicable.
    @param[in]  language Operator language used to render notes.
    @param[in]  expected_note Required localized lifecycle text fragment.
    @return     None.
    """
    project_root, manifest = project_workspace_service.create_project("ChunkingLifecycleState", tmp_path)
    source_text = "Committed chunk.\n\nUncommitted paragraph.\n"
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text(source_text, encoding="utf-8")
    manifest["source_document"] = {"original_name": "story.txt"}
    write_chunking_document(
        project_root,
        [{"text": "Committed chunk."}],
        mode=mode,
        semantic_strategy=strategy,
        source_text=source_text,
        status=status,
        warnings=["Persisted fallback warning."],
        next_paragraph=None if status == "completed" else 2,
        token_usage={
            "input_tokens": 120,
            "output_tokens": 30,
            "total_tokens": 150,
            "usage_available": True,
        },
    )

    state = text_chunking_state_service.build_text_chunking_state(
        project_root,
        manifest,
        language,
        settings_payload={"llm_profiles": [{"id": "profile", "enabled": True}]},
    )
    notes = "\n".join(state["notes"])

    assert expected_note in notes
    assert "Persisted fallback warning." in notes
    assert "0/0" not in notes
    assert "0 / 0" not in notes
    if mode == "ai_assisted":
        assert "120" in notes
        assert strategy in notes
        if status in {"running", "failed"}:
            assert state["selected_strategy"] == strategy
    if status == "running":
        assert "ready" not in notes.lower()
        assert "produced" not in notes.lower()
        assert "Running AI-assisted chunking again" not in notes
    if status in {"failed", "cancelled"}:
        assert "in progress" not in notes.lower()
    if status == "completed":
        assert "Running AI-assisted chunking again" in notes


def test_build_text_chunking_state_retains_ready_guidance_without_a_document(tmp_path) -> None:
    """
    @brief      Verify production page state retains not-started readiness guidance.
    @param[in]  tmp_path Pytest temporary-path fixture used for isolated project data.
    @return     None.
    """
    project_root, manifest = project_workspace_service.create_project("ChunkingReadyState", tmp_path)
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Cleaned text\n", encoding="utf-8")
    manifest["source_document"] = {"original_name": "story.txt"}

    state = text_chunking_state_service.build_text_chunking_state(
        project_root,
        manifest,
        "en",
        settings_payload={"llm_profiles": [{"id": "profile", "enabled": True}]},
    )

    notes = "\n".join(state["notes"])
    assert "ready to run" in notes
    assert "AI-assisted chunking is ready" in notes


def test_save_chunk_text_edit_persists_text_and_selectively_resets_downstream(tmp_path) -> None:
    """
    @brief      Verify selected chunk edits persist and preserve unrelated downstream data.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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
                "character_profile_id_last_used": "profile-1",
                "rejected_candidates": [],
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
        "cleanup_role",
        "starts_after_scene_separator",
    }
    assert chunks[0]["cleanup_role"] == "body"
    assert chunks[0]["starts_after_scene_separator"] is False
    assert updated_manifest["current_stage"] == "translation_ready"


def test_delete_chunk_removes_only_selected_translation_record(tmp_path) -> None:
    """
    @brief      Verify manual chunk deletion removes only selected downstream Translation data.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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


def test_manual_chunk_mutations_preserve_leading_scene_boundary(tmp_path) -> None:
    """Cover S-0017 and REQ-FUNC-2048d415-09d9-44bb-94ec-ba5c822ccff5."""
    project_root, manifest = project_workspace_service.create_project("SceneBoundaryEdit", tmp_path)
    _write_chunks(
        project_root,
        ("First chunk", "Second chunk", "Third chunk"),
        starts_after_scene_separator=(False, True, False),
    )

    manifest = text_chunking_state_service.save_chunk_text_edit(
        project_root,
        manifest,
        "chunk-0002",
        "Edited second chunk",
    )
    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert next(item for item in chunks if item["chunk_id"] == "chunk-0002")[
        "starts_after_scene_separator"
    ] is True

    manifest = text_chunking_state_service.insert_chunk_after_selected(
        project_root,
        manifest,
        "chunk-0001",
    )
    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert next(item for item in chunks if item["chunk_id"] == "chunk-0004")[
        "starts_after_scene_separator"
    ] is False

    text_chunking_state_service.delete_selected_chunk(project_root, manifest, "chunk-0002")
    chunks = json.loads((project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))["chunks"]
    assert next(item for item in chunks if item["chunk_id"] == "chunk-0003")[
        "starts_after_scene_separator"
    ] is True


@pytest.mark.parametrize("status", ("running", "cancelled", "failed"))
@pytest.mark.parametrize("operation", ("edit", "insert", "delete"))
def test_manual_chunk_mutations_reject_resumable_documents_without_side_effects(
    tmp_path,
    status: str,
    operation: str,
) -> None:
    """
    @brief      Verify REQ-FUNC-18dd9ec2 rejects every resumable manual mutation before side effects.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  status Resumable Chunking lifecycle status under test.
    @param[in]  operation Public manual mutation operation under test.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("ResumableChunkMutation", tmp_path)
    document_path = write_chunking_document(
        project_root,
        [
            {"chunk_id": "chunk-0001", "text": "First chunk."},
            {"chunk_id": "chunk-0002", "text": "Second chunk."},
        ],
        mode="ai_assisted",
        semantic_strategy="scene",
        status=status,
        source_text="First chunk.\n\nSecond chunk.\n\nThird paragraph.\n",
        additional_chunking_instructions="Keep scene transitions intact.",
        token_usage={
            "input_tokens": 40,
            "output_tokens": 10,
            "total_tokens": 50,
            "usage_available": True,
        },
        warnings=["Provider retry pending."],
        next_paragraph=3,
        context_window_fallback_count=2,
    )
    manifest["current_stage"] = "audio_assembly_ready"
    manifest["operations"]["chunking"]["status"] = status
    manifest["operations"]["translation"]["status"] = "completed"
    manifest["operations"]["character_discovery"]["status"] = "completed"
    manifest["operations"]["speech_blocks"]["status"] = "completed"
    manifest["operations"]["audio_blocks"]["status"] = "completed"
    manifest["operations"]["audio_assembly"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    downstream_paths = (
        project_root / config.TRANSLATED_CHUNKS_FILE_NAME,
        project_root / config.CHARACTERS_DOCUMENT_FILE_NAME,
        project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME,
        project_root / config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME,
        project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME,
        project_root / config.AUDIO_ASSEMBLY_STATE_FILE_NAME,
        project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "chunk-0001.wav",
        project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME / "book.wav",
    )
    for path in downstream_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"fixture:{path.name}".encode())
    snapshot_paths = (
        document_path,
        project_root / config.PROJECT_MANIFEST_FILE_NAME,
        *downstream_paths,
    )
    snapshots = {path: path.read_bytes() for path in snapshot_paths}

    with pytest.raises(
        ValueError,
        match="Finish, resume, or reset the current Chunking run before editing chunks.",
    ):
        if operation == "edit":
            text_chunking_state_service.save_chunk_text_edit(
                project_root,
                manifest,
                "chunk-0001",
                "Edited first chunk.",
            )
        elif operation == "insert":
            text_chunking_state_service.insert_chunk_after_selected(project_root, manifest, "chunk-0001")
        else:
            text_chunking_state_service.delete_selected_chunk(project_root, manifest, "chunk-0001")

    assert {path: path.read_bytes() for path in snapshot_paths} == snapshots


def _write_chunks(
    project_root,
    texts: tuple[str, ...],
    *,
    starts_after_scene_separator: tuple[bool, ...] | None = None,
) -> None:
    """
    @brief      Write deterministic chunk fixture records.
    @param[in]  project_root Project root folder.
    @param[in]  texts Ordered chunk text values.
    @return     None.
    @exception  None
    """
    boundary_flags = starts_after_scene_separator or tuple(False for _text in texts)
    if len(boundary_flags) != len(texts):
        raise ValueError("Scene-boundary fixture count must match chunk text count.")
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
            "starts_after_scene_separator": boundary_flags[index - 1],
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
