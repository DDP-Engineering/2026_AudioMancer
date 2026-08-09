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
@details Verifies the one-file persistence contract, exact block field set,
         report and operation-state projections, resume from the document
         checkpoint, generated-audio paths derived from speech_block_id,
         non-object handling, root-contract rejection, and reset cleanup
         required by .agentic/specs/audio_blocks_document.spec.md, mapped to
         REQ-FUNC-170ed96e, REQ-FUNC-a4c87ddc, REQ-FUNC-e18bb65f,
         REQ-FUNC-e9a6688e, REQ-FUNC-df8987d1, REQ-FUNC-39146520,
         REQ-FUNC-cf8803d2, and REQ-FUNC-65813be2.
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
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document = _document()

    document_path = audio_blocks_service.write_audio_blocks_document(project_root, document)

    assert document_path.name == config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME
    assert config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME == "audio_blocks.json"
    assert set(document) == _DOCUMENT_FIELDS
    assert audio_blocks_service.load_audio_blocks_document(project_root) == document


def test_persisted_block_carries_only_the_contracted_field_set(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-a4c87ddc keeps only the reduced Audio Block field set.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()

    document_path = audio_blocks_service.write_audio_blocks_document(project_root, _document())
    persisted = json.loads(document_path.read_text(encoding="utf-8"))

    for block in persisted["blocks"]:
        assert set(block) == _BLOCK_FIELDS


def test_split_fields_are_persisted_only_for_split_blocks(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-a4c87ddc emits split fields only when a block was split.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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
    """
    project_root = tmp_path / "project"
    project_root.mkdir()

    part_path = audio_blocks_artifact_service.audio_part_artifact_path(project_root, "0001-000004", 0)

    expected = (
        project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "parts" / "0001-000004_part001.wav"
    )
    assert part_path == expected


def test_load_report_projection_matches_recomputed_counts(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-e18bb65f projects the report from the document.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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


def test_missing_document_is_treated_as_not_started(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-39146520 treats a missing document as not-started.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()

    assert audio_blocks_service.load_audio_blocks_document(project_root) is None
    assert audio_blocks_service.load_audio_blocks(project_root) == []
    assert audio_blocks_service.load_operation_state(project_root) is None
    assert audio_blocks_service.load_audio_blocks_report(project_root) is None


@pytest.mark.parametrize(
    ("invalid_bytes", "cause_type"),
    [
        (b"{", json.JSONDecodeError),
        (b"\xff", UnicodeDecodeError),
        (b"null", audio_blocks_service.AudioBlocksDocumentError),
        (
            json.dumps([{"speech_block_id": "0001-000001"}]).encode("utf-8"),
            audio_blocks_service.AudioBlocksDocumentError,
        ),
        (json.dumps({"status": "completed"}).encode("utf-8"), audio_blocks_service.AudioBlocksDocumentError),
    ],
)
def test_existing_invalid_document_raises_typed_reset_recovery_error(
    tmp_path: Path,
    invalid_bytes: bytes,
    cause_type: type[BaseException],
) -> None:
    """
    @brief      Verify existing unreadable and invalid Audio Blocks documents fail closed with recovery guidance.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  invalid_bytes Existing invalid document bytes.
    @param[in]  cause_type Expected chained root failure type.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document_path = project_root / config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME
    document_path.write_bytes(invalid_bytes)

    with pytest.raises(audio_blocks_service.AudioBlocksDocumentError) as captured_error:
        audio_blocks_service.load_audio_blocks_document(project_root)

    assert "Reset Audio Blocks to recover" in str(captured_error.value)
    assert isinstance(captured_error.value.__cause__, cause_type)


def test_unreadable_existing_document_chains_oserror(monkeypatch, tmp_path: Path) -> None:
    """
    @brief      Verify a filesystem read failure is chained into the typed Audio Blocks recovery error.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME).write_text("{}", encoding="utf-8")

    def _raise_permission_error(_artifact_path) -> None:
        """Raise the injected artifact read failure."""
        raise PermissionError("audio blocks denied")

    monkeypatch.setattr(audio_blocks_service, "load_optional_json_artifact", _raise_permission_error)

    with pytest.raises(audio_blocks_service.AudioBlocksDocumentError) as captured_error:
        audio_blocks_service.load_audio_blocks_document(project_root)

    assert "Reset Audio Blocks to recover" in str(captured_error.value)
    assert isinstance(captured_error.value.__cause__, PermissionError)


def test_generation_does_not_overwrite_corrupt_audio_blocks_document(monkeypatch, tmp_path: Path) -> None:
    """
    @brief      Verify generation rejects corrupt Audio Blocks state before any replacement write.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document_path = project_root / config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME
    corrupt_bytes = b"{corrupt audio blocks"
    document_path.write_bytes(corrupt_bytes)
    monkeypatch.setattr(audio_blocks_service, "_resolve_generation_context", lambda *_args, **_kwargs: {})

    with pytest.raises(audio_blocks_service.AudioBlocksDocumentError, match="Reset Audio Blocks to recover"):
        audio_blocks_service.start_or_continue_generation(project_root, {}, {})

    assert document_path.read_bytes() == corrupt_bytes


def test_invalid_root_contract_is_rejected(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-cf8803d2 rejects an invalid Audio Blocks root contract.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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
    with pytest.raises(audio_blocks_service.AudioBlocksDocumentError, match="Reset Audio Blocks to recover"):
        audio_blocks_service.load_audio_blocks_document(project_root)


@pytest.mark.parametrize(
    "reader",
    [
        audio_blocks_service.load_operation_state,
        audio_blocks_service.load_audio_blocks_report,
        audio_blocks_service.load_audio_blocks,
    ],
)
def test_public_read_projections_do_not_hide_invalid_document(reader, tmp_path: Path) -> None:
    """Verify every public projection preserves strict document failures."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    document_path = project_root / config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME
    document_path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(audio_blocks_service.AudioBlocksDocumentError, match="Reset Audio Blocks to recover"):
        reader(project_root)


def test_reset_removes_document(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-65813be2 clears the authoritative document.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    audio_blocks_service.write_audio_blocks_document(project_root, _document())

    audio_blocks_service.reset_audio_blocks(project_root)

    assert not (project_root / config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME).exists()


# END OF FILE
