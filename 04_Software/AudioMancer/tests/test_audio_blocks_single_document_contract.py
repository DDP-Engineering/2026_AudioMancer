#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_blocks_single_document_contract.py
@brief Red-before-green contract tests for the single authoritative Audio Blocks document.
@details Verifies the one-file persistence contract, the reduced block field
         set, report and operation-state compatibility projections, resume from
         the document checkpoint, generated-audio paths derived from
         speech_block_id, the removal of artifact remapping, legacy-artifact-as-
         absent handling, root-contract rejection, and reset cleanup required by
         .agentic/specs/audio_blocks_document.spec.md, mapped to
         REQ-FUNC-170ed96e, REQ-FUNC-a4c87ddc, REQ-FUNC-e18bb65f,
         REQ-FUNC-e9a6688e, REQ-FUNC-df8987d1, REQ-FUNC-4e8f2638,
         REQ-FUNC-39146520, REQ-FUNC-cf8803d2, and REQ-FUNC-65813be2.
@author Eng. Dan Dumitru Pasare
@date 2026-07-26
@version 0.1.0
"""

# IMPORTS

import json
from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import audio_blocks_artifact_service, audio_blocks_service, speech_blocks_service

# CONSTANTS

_DOCUMENT_FIELDS = {
    "status",
    "voice_language",
    "input_fingerprint",
    "checkpoint",
    "blocks",
}
_BLOCK_FIELDS = {
    "speech_block_id",
    "voice_target_id",
    "generated",
    "approved",
    "audio_can_play",
    "audio_duration_seconds",
    "generation_fingerprint",
}
_SPLIT_ONLY_BLOCK_FIELDS = {"split_part_count", "split_plan_fingerprint"}
_REMOVED_BLOCK_FIELDS = (
    "audio_relative_path",
    "metadata_relative_path",
    "generated_part_relative_paths",
    "chunk_id",
    "speaker_id",
    "content_kind",
    "sound_prompt",
    "negative_prompt",
    "duration_seconds",
    "ambience_position",
    "model_token_budget",
    "model_audio_seconds_budget",
    "runtime_result_summary",
    "split_strategy",
    "warning_flags",
    "voice_language",
    "prompt_format",
)
_REMOVED_CONFIG_CONSTANTS = (
    "AUDIO_BLOCKS_OUTPUT_FILE_NAME",
    "AUDIO_BLOCKS_REPORT_FILE_NAME",
    "AUDIO_BLOCKS_STATE_FILE_NAME",
)
_LEGACY_REPORT_FILE_NAME = "audio_blocks_report.json"
_LEGACY_STATE_FILE_NAME = "audio_blocks_state.json"


def _audio_block(speech_block_id: str, *, generated: bool, approved: bool) -> dict:
    """Build one minimal persisted Audio Block payload for contract tests."""
    return {
        "speech_block_id": speech_block_id,
        "voice_target_id": "narrator",
        "generated": generated,
        "approved": approved,
        "audio_can_play": generated,
        "audio_duration_seconds": 10.32 if generated else None,
        "generation_fingerprint": f"fingerprint-{speech_block_id}" if generated else None,
    }


def _document(**overrides) -> dict:
    """Build one strictly valid single Audio Blocks document for contract tests."""
    document = {
        "status": "in_progress",
        "voice_language": "en",
        "input_fingerprint": "input-fingerprint-123",
        "checkpoint": {
            "run_token": "2026-07-26T09:00:00+00:00",
            "current_phase": "generate_blocks",
            "current_block_id": "0001-000002",
            "next_speech_block_index": 1,
            "next_split_part_index": 0,
        },
        "blocks": [
            _audio_block("0001-000001", generated=True, approved=True),
            _audio_block("0001-000002", generated=False, approved=False),
        ],
    }
    document.update(overrides)
    return document


def _speech_block(speech_block_id: str, chunk_id: str) -> dict:
    """Build one minimal persisted Speech Block payload backing an Audio Block."""
    return {
        "speech_block_id": speech_block_id,
        "chunk_id": chunk_id,
        "sequence_index": int(speech_block_id.split("-")[-1]),
        "speaker_kind": "narrator",
        "speaker_id": "narrator",
        "display_name": "Narrator",
        "content_kind": "narration",
        "text": f"Line for {speech_block_id}.",
        "approved": True,
        "warning_flags": [],
    }


def _write_backing_speech_blocks(project_root: Path) -> None:
    """Persist the upstream Speech Blocks document the Audio Blocks projections read."""
    speech_blocks_service.write_speech_blocks_document(
        project_root,
        {
            "status": "completed",
            "source": {"kind": "original", "language": "en", "fingerprint": "fingerprint-123"},
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
            "checkpoint": None,
            "failure": None,
            "blocks": [
                _speech_block("0001-000001", "chunk-0001"),
                _speech_block("0001-000002", "chunk-0001"),
            ],
        },
    )


def test_document_round_trips_and_writes_only_one_artifact(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-170ed96e persists one Audio Blocks document only.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document = _document()

    document_path = audio_blocks_service.write_audio_blocks_document(project_root, document)

    assert document_path.name == config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME
    assert config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME == "audio_blocks.json"
    assert set(document) == _DOCUMENT_FIELDS
    assert audio_blocks_service.load_audio_blocks_document(project_root) == document
    assert not (project_root / _LEGACY_REPORT_FILE_NAME).exists()
    assert not (project_root / _LEGACY_STATE_FILE_NAME).exists()


def test_removed_report_and_state_config_constants_are_gone() -> None:
    """
    @brief      Verify REQ-FUNC-170ed96e removes the report and state artifact names.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    for constant_name in _REMOVED_CONFIG_CONSTANTS:
        assert not hasattr(config, constant_name), f"{constant_name} must be removed"


def test_persisted_block_carries_only_the_contracted_field_set(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-a4c87ddc keeps only the reduced Audio Block field set.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root = tmp_path / "project"
    project_root.mkdir()

    document_path = audio_blocks_service.write_audio_blocks_document(project_root, _document())
    persisted = json.loads(document_path.read_text(encoding="utf-8"))

    for block in persisted["blocks"]:
        assert set(block) == _BLOCK_FIELDS
        for removed_field in _REMOVED_BLOCK_FIELDS:
            assert removed_field not in block, f"{removed_field} must not be persisted"


def test_split_fields_are_persisted_only_for_split_blocks(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-a4c87ddc emits split fields only when a block was split.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    split_block = _audio_block("0001-000003", generated=True, approved=True)
    split_block["split_part_count"] = 3
    split_block["split_plan_fingerprint"] = "split-fingerprint"
    document = _document(blocks=[_audio_block("0001-000001", generated=True, approved=True), split_block])

    document_path = audio_blocks_service.write_audio_blocks_document(project_root, document)
    persisted = json.loads(document_path.read_text(encoding="utf-8"))

    single_block, persisted_split_block = persisted["blocks"]
    assert set(single_block) == _BLOCK_FIELDS
    assert set(persisted_split_block) == _BLOCK_FIELDS | _SPLIT_ONLY_BLOCK_FIELDS


def test_generated_audio_path_is_derived_from_speech_block_id(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-df8987d1 derives the WAV path from speech_block_id alone.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root = tmp_path / "project"
    project_root.mkdir()

    audio_path = audio_blocks_artifact_service.audio_artifact_path(project_root, "0001-000004")

    expected = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "0001-000004.wav"
    assert audio_path == expected
    assert "narrator" not in audio_path.name


def test_split_part_paths_are_derived_from_speech_block_id(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-df8987d1 derives split-part paths from speech_block_id.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root = tmp_path / "project"
    project_root.mkdir()

    part_path = audio_blocks_artifact_service.audio_part_artifact_path(project_root, "0001-000004", 0)

    expected = (
        project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "parts" / "0001-000004_part001.wav"
    )
    assert part_path == expected


def test_artifact_remap_helper_is_removed() -> None:
    """
    @brief      Verify REQ-FUNC-4e8f2638 removes generated-artifact remapping.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    assert not hasattr(audio_blocks_service, "_remap_audio_block_artifacts")


def test_load_report_projection_matches_recomputed_counts(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-e18bb65f projects the report from the document.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_backing_speech_blocks(project_root)
    audio_blocks_service.write_audio_blocks_document(project_root, _document())

    report = audio_blocks_service.load_audio_blocks_report(project_root)

    assert report is not None
    assert report["voice_language"] == "en"
    assert report["generated_block_count"] == 1
    assert report["approved_block_count"] == 1
    assert report["total_block_count"] == 2
    assert report["audio_blocks_stage_status"] == audio_blocks_service.AUDIO_BLOCKS_STAGE_IN_PROGRESS
    assert "warnings" not in report
    assert "reused_prompt_count" not in report
    assert "regenerated_prompt_count" not in report


def test_load_operation_state_projection_exposes_checkpoint(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-e18bb65f and REQ-FUNC-e9a6688e project the resume checkpoint.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_backing_speech_blocks(project_root)
    audio_blocks_service.write_audio_blocks_document(project_root, _document())

    state = audio_blocks_service.load_operation_state(project_root)

    assert state is not None
    assert state["status"] == "in_progress"
    assert state["progress_current"] == 1
    assert state["progress_total"] == 2
    assert state["metadata"]["voice_language"] == "en"
    assert state["metadata"]["input_fingerprint"] == "input-fingerprint-123"
    assert state["metadata"]["current_block_id"] == "0001-000002"
    checkpoint = state["resume_checkpoint"]
    assert checkpoint["run_token"] == "2026-07-26T09:00:00+00:00"
    assert checkpoint["next_speech_block_index"] == 1
    assert checkpoint["next_split_part_index"] == 0
    assert "next_profile_index" not in checkpoint


def test_legacy_list_artifact_is_treated_as_absent(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-39146520 treats a legacy list payload as not-started.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    legacy_blocks = [
        {
            "speech_block_id": "0001-000001",
            "chunk_id": "chunk-0001",
            "audio_relative_path": "audio_blocks/0001_000001_narrator.wav",
            "generated": "2026-07-24T21:44:46+00:00",
        }
    ]
    (project_root / "audio_blocks.json").write_text(json.dumps(legacy_blocks), encoding="utf-8")
    (project_root / _LEGACY_REPORT_FILE_NAME).write_text(
        json.dumps({"audio_blocks_stage_status": "completed"}), encoding="utf-8"
    )

    assert audio_blocks_service.load_audio_blocks_document(project_root) is None
    assert audio_blocks_service.load_audio_blocks(project_root) == []
    assert audio_blocks_service.load_operation_state(project_root) is None
    assert audio_blocks_service.load_audio_blocks_report(project_root) is None


def test_invalid_root_contract_is_rejected(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-cf8803d2 rejects an invalid Audio Blocks root contract.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    invalid_document = _document()
    invalid_document.pop("input_fingerprint")

    with pytest.raises(audio_blocks_service.AudioBlocksDocumentError):
        audio_blocks_service.write_audio_blocks_document(project_root, invalid_document)

    (project_root / "audio_blocks.json").write_text(
        json.dumps({"status": "completed", "unexpected_key": True}), encoding="utf-8"
    )
    assert audio_blocks_service.load_audio_blocks_document(project_root) is None


def test_reset_removes_document_and_residual_legacy_files(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-65813be2 clears the document and residual legacy files.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    audio_blocks_service.write_audio_blocks_document(project_root, _document())
    (project_root / _LEGACY_REPORT_FILE_NAME).write_text("{}", encoding="utf-8")
    (project_root / _LEGACY_STATE_FILE_NAME).write_text("{}", encoding="utf-8")

    audio_blocks_service.reset_audio_blocks(project_root)

    assert not (project_root / config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME).exists()
    assert not (project_root / _LEGACY_REPORT_FILE_NAME).exists()
    assert not (project_root / _LEGACY_STATE_FILE_NAME).exists()


# END OF FILE
