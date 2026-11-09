#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chunking_edit_service.py
@brief Stable-ID manual Chunking changes and selective downstream impact.
@details Prepares stable-ID edits, insertion and deletion with conservative metadata,
         then stages selective downstream invalidation for recoverable publication.
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.chunking.materialization import manual_metadata
from audiomancer.services import (
    ai_translation_service,
    audio_blocks_service,
    character_discovery_service,
    chunking_document_service,
    chunking_publication_service,
    operation_runtime_service,
    project_workspace_service,
    speech_blocks_service,
    text_cleanup_state_service,
    workflow_impact_service,
)
from audiomancer.services.logging_service import get_component_logger
from audiomancer.services.translation_publication_service import source_dependent_operations

# CONSTANTS

# @brief Component logger used for Text Chunking state mutations.
_TEXT_CHUNKING_STATE_LOGGER = get_component_logger("deterministic_chunking")
_RESUMABLE_CHUNKING_MUTATION_MESSAGE = "Finish, resume, or reset the current Chunking run before editing chunks."

# PUBLIC API


def save_chunk_text_edit(
    project_root: Path,
    manifest: dict[str, object],
    chunk_id: str,
    chunk_text: str,
) -> dict[str, object]:
    """
    @brief      Persist one selected chunk text edit and selectively reset downstream state.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Current project manifest payload.
    @param[in]  chunk_id Stable chunk identifier to update.
    @param[in]  chunk_text Edited selected chunk text.
    @return     Updated manifest payload.
    @exception  ValueError Raised when the chunk artifact or selected chunk is unavailable.
    """
    chunk_artifact_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHUNK_ARTIFACT_FILE_NAME
    if not chunk_artifact_path.is_file():
        raise ValueError("No chunk artifact is available to edit.")
    chunks = chunking_document_service.load_chunks(project_root)
    selected_index = next(
        (index for index, chunk in enumerate(chunks) if str(chunk.get("chunk_id", "")) == chunk_id),
        -1,
    )
    if selected_index < 0:
        raise ValueError("The selected chunk is no longer available.")
    if str(chunks[selected_index].get("text", "")) == chunk_text:
        _TEXT_CHUNKING_STATE_LOGGER.info(
            "Skipped manual chunk text edit because the selected chunk was unchanged: chunk_id=%s",
            chunk_id,
        )
        return dict(manifest)
    _TEXT_CHUNKING_STATE_LOGGER.info(
        "Applying manual chunk text edit: chunk_id=%s chunk_count=%s",
        chunk_id,
        len(chunks),
    )
    chunks[selected_index] = manual_metadata(chunks[selected_index], chunk_text)
    resequenced_chunks = workflow_impact_service.resequence_records(chunks, start_index=1)
    return _persist_manual_chunk_change(
        project_root,
        manifest,
        resequenced_chunks,
        affected_chunk_ids=(chunk_id,),
        reason="manual_chunk_edit",
    )


def insert_chunk_after_selected(
    project_root: Path,
    manifest: dict[str, object],
    selected_chunk_id: str,
) -> dict[str, object]:
    """
    @brief      Insert one empty chunk after the selected persisted chunk or create the first manual chunk.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Current project manifest payload.
    @param[in]  selected_chunk_id Stable chunk identifier used as the insertion anchor, or empty for first insert.
    @return     Updated manifest payload.
    @exception  ValueError Raised when the selected chunk is unavailable or cleaned text is unavailable.
    """
    chunks = chunking_document_service.load_chunks(project_root)
    if not chunks and not str(selected_chunk_id).strip():
        inserted_chunk = _build_initial_manual_chunk_payload(project_root)
        return _persist_manual_chunk_change(
            project_root,
            manifest,
            [inserted_chunk],
            affected_chunk_ids=(str(inserted_chunk["chunk_id"]),),
            reason="manual_chunk_insert",
        )
    selected_index = next(
        (index for index, chunk in enumerate(chunks) if str(chunk.get("chunk_id", "")) == selected_chunk_id),
        -1,
    )
    if selected_index < 0:
        raise ValueError("The selected chunk is no longer available.")
    inserted_chunk = _build_inserted_chunk_payload(chunks[selected_index], _next_chunk_id(chunks))
    updated_chunks = [dict(chunk) for chunk in chunks]
    updated_chunks.insert(selected_index + 1, inserted_chunk)
    resequenced_chunks = workflow_impact_service.resequence_records(updated_chunks, start_index=1)
    return _persist_manual_chunk_change(
        project_root,
        manifest,
        resequenced_chunks,
        affected_chunk_ids=(str(inserted_chunk["chunk_id"]),),
        reason="manual_chunk_insert",
    )


def delete_selected_chunk(
    project_root: Path,
    manifest: dict[str, object],
    chunk_id: str,
) -> dict[str, object]:
    """
    @brief      Delete one selected chunk and selectively reset dependent records.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Current project manifest payload.
    @param[in]  chunk_id Stable chunk identifier to delete.
    @return     Updated manifest payload.
    @exception  ValueError Raised when the selected chunk is unavailable.
    """
    chunks = chunking_document_service.load_chunks(project_root)
    selected_index = next(
        (index for index, chunk in enumerate(chunks) if str(chunk.get("chunk_id", "")) == chunk_id),
        -1,
    )
    if selected_index < 0:
        raise ValueError("The selected chunk is no longer available.")
    updated_chunks = [dict(chunk) for chunk in chunks]
    if bool(updated_chunks[selected_index].get("starts_after_scene_separator", False)) and selected_index + 1 < len(
        updated_chunks
    ):
        updated_chunks[selected_index + 1]["starts_after_scene_separator"] = True
    del updated_chunks[selected_index]
    if not updated_chunks:
        raise ValueError("At least one chunk must remain in the project.")
    resequenced_chunks = workflow_impact_service.resequence_records(updated_chunks, start_index=1)
    return _persist_manual_chunk_change(
        project_root,
        manifest,
        resequenced_chunks,
        affected_chunk_ids=(chunk_id,),
        reason="manual_chunk_delete",
    )


def _apply_manual_chunk_change(
    project_root: Path,
    manifest: dict[str, object],
    chunks: list[dict[str, object]],
    affected_chunk_ids: tuple[str, ...],
    reason: str,
) -> dict[str, object]:
    """
    @brief      Persist a manual chunk-list change and apply selective impact.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Current project manifest payload.
    @param[in]  chunks Full updated chunk payload list.
    @param[in]  affected_chunk_ids Exact chunk ids changed by the operation.
    @param[in]  reason Stable impact reason token.
    @return     Updated manifest payload.
    @exception  ValueError Raised when the authoritative document is resumable.
    """
    document = chunking_document_service.load_chunking_document(project_root)
    if document is not None and document["status"] in chunking_document_service.RESUMABLE_STATUSES:
        raise ValueError(_RESUMABLE_CHUNKING_MUTATION_MESSAGE)
    used_translation = ai_translation_service.translation_is_completed(project_root)
    _write_chunk_artifact(project_root, chunks)
    target_language = ai_translation_service.manifest_target_language(manifest)
    ai_translation_service.sync_translation_after_chunk_change(
        project_root,
        target_language,
        affected_chunk_ids,
    )
    if used_translation != ai_translation_service.translation_is_completed(project_root):
        for kind in source_dependent_operations():
            for path in operation_runtime_service.operation_reset_artifact_paths(project_root, kind):
                path.unlink()
        updated_manifest = _build_manifest_after_selective_chunk_change(project_root, manifest)
        project_workspace_service.save_manifest(updated_manifest, project_root)
        return updated_manifest

    character_source_invalidated = character_discovery_service.invalidate_if_source_changed(project_root)
    if not character_source_invalidated:
        character_discovery_service.drop_character_evidence_for_chunks(
            project_root,
            affected_chunk_ids,
        )
    _audio_report, audio_artifact_summary = audio_blocks_service.remove_audio_blocks_for_chunks(
        project_root,
        affected_chunk_ids,
    )
    speech_blocks_service.remove_speech_blocks_for_chunks(project_root, affected_chunk_ids)
    workflow_impact_service.reset_audio_assembly_outputs(project_root)
    impact_summary = workflow_impact_service.build_selective_invalidation_summary(
        "chunking",
        reason=reason,
        affected_chunk_ids=affected_chunk_ids,
        reset_operation_kinds=("speech_blocks", "audio_blocks", "audio_assembly"),
        audio_assembly_reset=True,
        artifact_deletion=audio_artifact_summary,
    )
    _TEXT_CHUNKING_STATE_LOGGER.info(
        "Applied manual chunk mutation: chunk_count=%s affected_chunks=%s reason=%s",
        len(chunks),
        len(impact_summary.affected_chunk_ids),
        impact_summary.reason,
    )
    updated_manifest = _build_manifest_after_selective_chunk_change(project_root, manifest)
    project_workspace_service.save_manifest(updated_manifest, project_root)
    return updated_manifest


def _write_chunk_artifact(project_root: Path, chunks: list[dict[str, object]]) -> None:
    """
    @brief      Persist the canonical chunk artifact.
    @param[in]  project_root Active project root folder.
    @param[in]  chunks Full chunk payload list.
    @return     None.
    @exception  None
    """
    document = chunking_document_service.load_chunking_document(project_root)
    if document is None:
        cleaned_text = text_cleanup_state_service.read_optional_project_text(
            project_root,
            f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}",
        )
        if cleaned_text is None or not cleaned_text.strip():
            raise ValueError("Cleaned text is required before manual chunk insertion.")
        document = chunking_document_service.build_document(
            status="completed",
            mode="deterministic",
            source_text=cleaned_text,
            chunks=chunks,
            manual_adjusted=True,
        )
    else:
        document["status"] = "completed"
        document["manual_adjusted"] = True
        document["next_paragraph"] = None
        document["chunks"] = chunks
    chunking_document_service.write_chunking_document(project_root, document)


def _build_manifest_after_selective_chunk_change(
    project_root: Path,
    manifest: dict[str, object],
) -> dict[str, object]:
    """
    @brief      Refresh manifest summaries after selective chunk invalidation.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Current project manifest payload.
    @return     Updated manifest payload.
    @exception  None
    """
    updated_manifest = dict(manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    default_operations = text_cleanup_state_service.normalized_manifest_operations({})
    operations["chunking"] = project_workspace_service.project_manifest_operation_summary(
        "chunking",
        chunking_document_service.derive_operation_state(
            chunking_document_service.load_chunking_document(project_root)
        ),
    )
    translation_summary = ai_translation_service.load_translation_summary(project_root)
    operations["translation"] = {
        "status": str(translation_summary["status"]),
        "progress_current": int(translation_summary["translated_count"]),
        "progress_total": int(translation_summary["total_count"]),
        "mode": "ai_assisted",
        "warning_count": int(translation_summary["warning_count"]),
    }
    character_document = character_discovery_service.load_character_document(project_root)
    operations["character_discovery"] = (
        default_operations["character_discovery"]
        if character_document is None
        else character_discovery_service.character_operation_summary(character_document)
    )
    if character_document is None:
        operations["character_voices"] = default_operations["character_voices"]
    operations["speech_blocks"] = project_workspace_service.project_manifest_operation_summary(
        "speech_blocks",
        speech_blocks_service.load_operation_state(project_root),
    )
    operations["audio_blocks"] = project_workspace_service.project_manifest_operation_summary(
        "audio_blocks",
        audio_blocks_service.load_operation_state(project_root),
    )
    operations["audio_assembly"] = default_operations["audio_assembly"]
    updated_manifest["operations"] = operations
    updated_manifest["current_stage"] = "translation_ready"
    return updated_manifest


def _build_inserted_chunk_payload(source_chunk: dict[str, object], chunk_id: str) -> dict[str, object]:
    """
    @brief      Build the default payload for a manually inserted empty chunk.
    @param[in]  source_chunk Selected anchor chunk payload.
    @param[in]  chunk_id New stable chunk identifier.
    @return     Inserted chunk payload.
    @exception  None
    """
    return {
        "chunk_id": chunk_id,
        "sequence_index": int(source_chunk.get("sequence_index", 1)) + 1,
        "text": "",
        "source_paragraph_start": None,
        "source_paragraph_end": None,
        "cleanup_boundary_confidence": None,
        "cleanup_joined_across_page_break": False,
        "cleanup_warning_flags": [],
        "cleanup_role": "body",
        "starts_after_scene_separator": False,
    }


def _build_initial_manual_chunk_payload(project_root: Path) -> dict[str, object]:
    """
    @brief      Build the first empty chunk payload for a fully manual chunking session.
    @param[in]  project_root Active project root folder.
    @return     Initial manual chunk payload.
    @exception  ValueError Raised when cleaned text is unavailable.
    """
    cleaned_text = text_cleanup_state_service.read_optional_project_text(
        project_root,
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CLEANED_TEXT_FILE_NAME}",
    )
    if cleaned_text is None or not cleaned_text.strip():
        raise ValueError("Cleaned text is required before manual chunk insertion.")
    return {
        "chunk_id": "chunk-0001",
        "sequence_index": 1,
        "text": "",
        "source_paragraph_start": None,
        "source_paragraph_end": None,
        "cleanup_boundary_confidence": None,
        "cleanup_joined_across_page_break": False,
        "cleanup_warning_flags": [],
        "cleanup_role": "body",
        "starts_after_scene_separator": False,
    }


def _next_chunk_id(chunks: list[dict[str, object]]) -> str:
    """
    @brief      Return the next unused stable chunk id.
    @param[in]  chunks Current chunk payload list.
    @return     Next `chunk-####` identifier.
    @exception  None
    """
    max_number = 0
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id", "")).strip()
        if not chunk_id.startswith("chunk-"):
            continue
        try:
            max_number = max(max_number, int(chunk_id.removeprefix("chunk-")))
        except ValueError:
            continue
    return f"chunk-{max_number + 1:04d}"


def _persist_manual_chunk_change(project_root, manifest, chunks, affected_chunk_ids, reason):
    """@brief Prepare selective impact off the live project before recoverable publication."""
    checkpoint = chunking_document_service.load_checkpoint(project_root)
    if checkpoint is not None and checkpoint["status"] in chunking_document_service.RESUMABLE_STATUSES:
        raise ValueError(_RESUMABLE_CHUNKING_MUTATION_MESSAGE)
    return chunking_publication_service.publish_manual_change(
        project_root,
        lambda stage: _apply_manual_chunk_change(
            stage, project_workspace_service.load_manifest(project_root), chunks, affected_chunk_ids, reason
        ),
    )


# END OF FILE
