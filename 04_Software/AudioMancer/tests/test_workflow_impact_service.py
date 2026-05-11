#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_workflow_impact_service.py
@brief Focused tests for the v2 workflow-impact foundation service.
@details Verifies dependency ordering, impact summaries, stable identity policy,
         manifest refresh behavior, and safe generated-artifact deletion.
@author Eng. Dan Dumitru Pasare
@date 2026-05-04
@version 0.2.0
"""

# IMPORTS

import json
from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import project_workspace_service, workflow_impact_service

# PUBLIC API


def test_workflow_impact_operation_order_matches_current_workflow() -> None:
    """
    @brief      Verify v2 impact ordering matches the current workflow sequence.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    assert workflow_impact_service.downstream_operation_kinds("chunking") == (
        "translation",
        "character_discovery",
        "narrator_definition",
        "character_voices",
        "speech_blocks",
        "audio_blocks",
        "audio_assembly",
    )
    assert workflow_impact_service.downstream_operation_kinds("audio_blocks", include_current=True) == (
        "audio_blocks",
        "audio_assembly",
    )


def test_workflow_impact_rejects_unknown_operation_kind() -> None:
    """
    @brief      Verify unsupported operation kinds fail clearly.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    with pytest.raises(ValueError, match="Unsupported operation kind"):
        workflow_impact_service.operation_index("broken")


def test_workflow_impact_full_reset_summary_preserves_requested_operations() -> None:
    """
    @brief      Verify broad reset summaries exclude explicitly preserved operations.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    summary = workflow_impact_service.build_full_reset_impact_summary(
        "character_discovery",
        include_current=True,
        preserve_operation_kinds=("narrator_definition",),
        reason="Character profiles regenerated.",
    )

    assert summary.impact_kind == "full_reset"
    assert summary.reset_operation_kinds == (
        "character_discovery",
        "character_voices",
        "speech_blocks",
        "audio_blocks",
        "audio_assembly",
    )
    assert summary.preserved_operation_kinds == ("narrator_definition",)
    assert summary.audio_assembly_reset is True
    assert summary.as_dict()["reason"] == "Character profiles regenerated."


def test_workflow_impact_selective_summary_normalizes_affected_ids() -> None:
    """
    @brief      Verify selective summaries deduplicate affected IDs and metadata payloads.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    summary = workflow_impact_service.build_selective_invalidation_summary(
        "chunking",
        reason="Chunk edited.",
        affected_chunk_ids=(" chunk-0002 ", "chunk-0002", "chunk-0003"),
        reset_operation_kinds=("translation", "speech_blocks", "audio_blocks"),
        audio_assembly_reset=True,
    )
    metadata = workflow_impact_service.build_impact_metadata(summary)

    assert summary.affected_chunk_ids == ("chunk-0002", "chunk-0003")
    assert metadata["workflow_impact_version"] == 2
    assert metadata["reset_operation_kinds"] == ["translation", "speech_blocks", "audio_blocks"]
    assert metadata["audio_assembly_reset"] is True


def test_workflow_impact_stable_identity_policy_preserves_ids_when_resequencing() -> None:
    """
    @brief      Verify sequence updates do not rewrite stable identity fields.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    records = [
        {"chunk_id": "chunk-0007", "speech_block_id": "sb-7", "sequence_index": 10},
        {"chunk_id": "chunk-0002", "speech_block_id": "sb-2", "sequence_index": 20},
    ]

    resequenced = workflow_impact_service.resequence_records(records, start_index=1)

    assert workflow_impact_service.stable_identity_fields() == ("chunk_id", "speech_block_id", "voice_target_id")
    assert workflow_impact_service.is_stable_identity_field("chunk_id") is True
    assert [record["chunk_id"] for record in resequenced] == ["chunk-0007", "chunk-0002"]
    assert [record["speech_block_id"] for record in resequenced] == ["sb-7", "sb-2"]
    assert [record["sequence_index"] for record in resequenced] == [1, 2]


def test_workflow_impact_deletes_audio_artifacts_for_affected_speech_block_only(tmp_path) -> None:
    """
    @brief      Verify selective Audio Blocks deletion leaves unrelated files untouched.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("SelectiveAudioArtifacts", tmp_path)
    audio_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    audio_root.mkdir()
    affected_wav = audio_root / "affected.wav"
    affected_json = audio_root / "affected.json"
    preserved_wav = audio_root / "preserved.wav"
    affected_part = audio_root / "parts" / "affected_part001.wav"
    affected_part.parent.mkdir()
    for artifact_path in (affected_wav, affected_json, preserved_wav, affected_part):
        artifact_path.write_bytes(b"artifact")
    audio_blocks = [
        {
            "speech_block_id": "sb-1",
            "chunk_id": "chunk-0001",
            "voice_target_id": "narrator",
            "audio_relative_path": affected_wav.relative_to(project_root).as_posix(),
            "metadata_relative_path": affected_json.relative_to(project_root).as_posix(),
            "generated_part_relative_paths": [affected_part.relative_to(project_root).as_posix()],
        },
        {
            "speech_block_id": "sb-2",
            "chunk_id": "chunk-0002",
            "voice_target_id": "character_alice",
            "audio_relative_path": preserved_wav.relative_to(project_root).as_posix(),
            "metadata_relative_path": None,
            "generated_part_relative_paths": [],
        },
    ]

    summary = workflow_impact_service.delete_audio_block_artifacts(
        project_root,
        audio_blocks,
        speech_block_ids=("sb-1",),
    )

    assert summary.deleted_count == 3
    assert sorted(summary.deleted_paths) == [
        "audio_blocks/affected.json",
        "audio_blocks/affected.wav",
        "audio_blocks/parts/affected_part001.wav",
    ]
    assert summary.preserved_paths == ("audio_blocks/preserved.wav",)
    assert not affected_wav.exists()
    assert not affected_json.exists()
    assert not affected_part.exists()
    assert preserved_wav.is_file()


def test_workflow_impact_can_skip_preserved_audio_artifact_collection(tmp_path) -> None:
    """
    @brief      Verify selective Audio Blocks deletion can avoid unaffected file checks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("SelectiveAudioArtifactsFast", tmp_path)
    audio_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    audio_root.mkdir()
    affected_wav = audio_root / "affected.wav"
    preserved_wav = audio_root / "preserved.wav"
    affected_wav.write_bytes(b"affected")
    preserved_wav.write_bytes(b"preserved")
    audio_blocks = [
        {
            "speech_block_id": "sb-1",
            "chunk_id": "chunk-0001",
            "voice_target_id": "narrator",
            "audio_relative_path": affected_wav.relative_to(project_root).as_posix(),
        },
        {
            "speech_block_id": "sb-2",
            "chunk_id": "chunk-0002",
            "voice_target_id": "character_alice",
            "audio_relative_path": preserved_wav.relative_to(project_root).as_posix(),
        },
    ]

    summary = workflow_impact_service.delete_audio_block_artifacts(
        project_root,
        audio_blocks,
        speech_block_ids=("sb-1",),
        collect_preserved_paths=False,
    )

    assert summary.deleted_paths == ("audio_blocks/affected.wav",)
    assert summary.preserved_paths == ()
    assert not affected_wav.exists()
    assert preserved_wav.is_file()


def test_workflow_impact_skips_unsafe_audio_artifact_paths(tmp_path) -> None:
    """
    @brief      Verify selective deletion rejects persisted paths outside the project.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("UnsafeAudioArtifacts", tmp_path)
    outside_path = tmp_path / "outside.wav"
    outside_path.write_bytes(b"outside")

    summary = workflow_impact_service.delete_audio_block_artifacts(
        project_root,
        [{"speech_block_id": "sb-1", "audio_relative_path": "../outside.wav"}],
        speech_block_ids=("sb-1",),
    )

    assert summary.deleted_paths == ()
    assert summary.skipped_paths == ("../outside.wav",)
    assert outside_path.is_file()


def test_workflow_impact_requires_exact_ids_for_audio_artifact_deletion(tmp_path) -> None:
    """
    @brief      Verify selective deletion refuses unconstrained calls.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("ExactIdsRequired", tmp_path)

    with pytest.raises(ValueError, match="requires at least one affected ID"):
        workflow_impact_service.delete_audio_block_artifacts(project_root, [])


def test_workflow_impact_resets_audio_assembly_outputs_only(tmp_path) -> None:
    """
    @brief      Verify assembly reset deletes only assembly state/report and audiobook files.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("AssemblyOnlyReset", tmp_path)
    (project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME).write_text("{}\n", encoding="utf-8")
    (project_root / config.AUDIO_ASSEMBLY_STATE_FILE_NAME).write_text("{}\n", encoding="utf-8")
    audio_block_path = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "keep.wav"
    audio_block_path.parent.mkdir()
    audio_block_path.write_bytes(b"audio")
    audiobook_path = project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME / "book.wav"
    audiobook_path.parent.mkdir()
    audiobook_path.write_bytes(b"book")

    summary = workflow_impact_service.reset_audio_assembly_outputs(project_root)

    assert sorted(summary.deleted_paths) == [
        "audio_assembly_report.json",
        "audio_assembly_state.json",
        "audiobook/book.wav",
    ]
    assert not audiobook_path.exists()
    assert audio_block_path.is_file()


def test_workflow_impact_refreshes_manifest_from_completed_artifacts(tmp_path) -> None:
    """
    @brief      Verify manifest refresh saves metadata healed from persisted artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("RefreshManifest", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("Story", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-05-04T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("Story", encoding="utf-8")
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Story", encoding="utf-8")
    _write_json(project_root / config.EXTRACTION_STATE_FILE_NAME, _operation_state("completed", 1, 1))
    _write_json(project_root / config.EXTRACTION_REPORT_FILE_NAME, {"warning_count": 0})
    _write_json(project_root / config.CLEANUP_STATE_FILE_NAME, _operation_state("completed", 1, 1))
    _write_json(project_root / config.CLEANUP_REPORT_FILE_NAME, {"warning_count": 0})

    refreshed_manifest = workflow_impact_service.refresh_manifest_from_artifacts(project_root)
    saved_manifest = project_workspace_service.load_manifest(project_root)

    assert refreshed_manifest["current_stage"] == "text_cleanup_ready"
    assert saved_manifest["operations"]["cleanup"]["status"] == "completed"


def test_workflow_impact_full_reset_wrapper_keeps_existing_broad_reset_behavior(tmp_path) -> None:
    """
    @brief      Verify the v2 wrapper delegates to the existing broad reset service.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("FullResetWrapper", tmp_path)
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("clean", encoding="utf-8")
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text("[]\n", encoding="utf-8")

    summary = workflow_impact_service.apply_full_operation_reset(
        project_root,
        "cleanup",
        include_current=True,
        reason="Cleanup rerun.",
    )

    assert summary.reset_operation_kinds[0] == "cleanup"
    assert not (project_root / config.CLEANED_TEXT_FILE_NAME).exists()
    assert not (project_root / config.CHUNK_ARTIFACT_FILE_NAME).exists()
    assert not (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).exists()


def _operation_state(status: str, current: int, total: int) -> dict[str, object]:
    """
    @brief      Build a compact operation-state fixture.
    @param[in]  status Operation status token.
    @param[in]  current Current progress count.
    @param[in]  total Total progress count.
    @return     Operation-state fixture payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    completed_at = "2026-05-04T12:01:00+00:00" if status == "completed" else None
    return {
        "folder_relative_path": ".",
        "status": status,
        "progress_current": current,
        "progress_total": total,
        "mode": "test",
        "started_at": "2026-05-04T12:00:00+00:00",
        "completed_at": completed_at,
        "updated_at": "2026-05-04T12:01:00+00:00",
        "warning_count": 0,
    }


def _write_json(path: Path, payload: object) -> None:
    """
    @brief      Write one JSON fixture file.
    @param[in]  path Target file path.
    @param[in]  payload JSON-serializable payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# END OF FILE
