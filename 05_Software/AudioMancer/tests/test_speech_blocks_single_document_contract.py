#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_speech_blocks_single_document_contract.py
@brief Red-before-green contract tests for the single authoritative Speech Blocks document.
@details Verifies the one-file persistence contract, exact source references,
         report/operation-state projections, resume from the document
         checkpoint, non-object handling, root validation, and reset cleanup.
"""

# IMPORTS

import json
from pathlib import Path

import pytest

from audiomancer import config
from audiomancer.services import speech_blocks_service

# CONSTANTS

_DOCUMENT_FIELDS = {
    "status",
    "source",
    "ai_profile_id",
    "instructions",
    "scene_ambience",
    "response_contract",
    "token_usage",
    "budget_metadata",
    "checkpoint",
    "failure",
    "blocks",
}
def _block(speech_block_id: str, chunk_id: str, *, approved: bool, warnings: list[str] | None = None) -> dict:
    """Build one minimal persisted Speech Block payload for contract tests."""
    return {
        "speech_block_id": speech_block_id,
        "chunk_id": chunk_id,
        "sequence_index": int(chunk_id.split("-")[-1]),
        "speaker_kind": "narrator",
        "speaker_id": "narrator",
        "display_name": "Narrator",
        "content_kind": "narration",
        "text": f"Line for {speech_block_id}.",
        "approved": approved,
        "warning_flags": list(warnings or []),
    }


def _document(**overrides) -> dict:
    """Build one strictly valid single Speech Blocks document for contract tests."""
    document = {
        "status": "review_pending",
        "source": {"kind": "original", "language": "en", "fingerprint": "fingerprint-123"},
        "ai_profile_id": "profile-1",
        "instructions": "Keep narration calm.",
        "scene_ambience": {"enabled": False},
        "response_contract": "direct_blocks",
        "token_usage": {
            "input_tokens": 12,
            "output_tokens": 6,
            "total_tokens": 18,
            "usage_available": True,
        },
        "budget_metadata": {"text_budget_tokens": 100},
        "checkpoint": None,
        "failure": None,
        "blocks": [
            _block("chunk-0001-000001", "chunk-0001", approved=True),
            _block("chunk-0001-000002", "chunk-0001", approved=False, warnings=["model_text_modified"]),
        ],
    }
    document.update(overrides)
    return document


def test_document_round_trips_and_writes_only_one_artifact(tmp_path: Path) -> None:
    """
    @brief      Verify SPEC-SB-SINGLEDOC / REQ-FUNC-c71fbab4 one-document round trip.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document = _document()

    document_path = speech_blocks_service.write_speech_blocks_document(project_root, document)

    assert document_path.name == config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME
    assert config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME == "speech_blocks.json"
    assert set(document) == _DOCUMENT_FIELDS
    assert speech_blocks_service.load_speech_blocks_document(project_root) == document


def test_persisted_document_excludes_source_chunk_text(tmp_path: Path) -> None:
    """
    @brief      Verify SPEC-SB-NOSRCCOPY / REQ-FUNC-ecb5b678 drops the source-text copy.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document = _document()

    document_path = speech_blocks_service.write_speech_blocks_document(project_root, document)
    raw_text = document_path.read_text(encoding="utf-8")

    assert "source_chunks" not in raw_text
    assert set(document["source"]) == {"kind", "language", "fingerprint"}


def test_load_report_projection_matches_recomputed_counts(tmp_path: Path) -> None:
    """
    @brief      Verify SPEC-SB-PROJECTION / REQ-FUNC-74be10fd report projection equivalence.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document = _document()
    speech_blocks_service.write_speech_blocks_document(project_root, document)

    report = speech_blocks_service.load_speech_blocks_report(project_root)

    assert report is not None
    assert report["source_language"] == "en"
    assert report["source_kind"] == "original"
    assert report["ai_profile_id"] == "profile-1"
    assert report["speech_block_count"] == 2
    assert report["total_block_count"] == 2
    assert report["approved_block_count"] == 1
    assert report["warning_count"] == 1
    assert report["warnings"][0]["reason"] == "model_text_modified"
    assert report["speech_blocks_stage_status"] == "in_progress"
    assert report["additional_speech_block_instructions"] == "Keep narration calm."


def test_load_operation_state_projection_omits_source_chunks_and_exposes_checkpoint(tmp_path: Path) -> None:
    """
    @brief      Verify SPEC-SB-PROJECTION / REQ-FUNC-74be10fd state projection shape.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document = _document(
        status="running",
        checkpoint={
            "next_chunk_index": 1,
            "active_chunk_id": "chunk-0002",
            "next_source_offset": 25,
            "run_token": "2026-07-24T10:00:00+00:00",
            "log_relative_path": "log_ai_speech_blocks_20260724T100000Z.log",
        },
    )
    speech_blocks_service.write_speech_blocks_document(project_root, document)

    state = speech_blocks_service.load_operation_state(project_root)

    assert state is not None
    assert state["status"] == "running"
    metadata = state["metadata"]
    assert "source_chunks" not in metadata
    assert metadata["source_snapshot_fingerprint"] == "fingerprint-123"
    assert metadata["speech_blocks_response_contract"] == "direct_blocks"
    assert state["resume_checkpoint"]["next_chunk_index"] == 1


def test_resume_reads_source_offset_from_document_checkpoint(tmp_path: Path) -> None:
    """
    @brief      Verify SPEC-SB-RESUME / REQ-FUNC-6f65b68e resume cursor comes from the document.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document = _document(
        status="running",
        checkpoint={
            "next_chunk_index": 3,
            "active_chunk_id": "chunk-0004",
            "next_source_offset": 55,
            "run_token": "2026-07-24T10:00:00+00:00",
            "log_relative_path": "log_ai_speech_blocks_20260724T100000Z.log",
        },
    )
    speech_blocks_service.write_speech_blocks_document(project_root, document)

    resume_checkpoint = speech_blocks_service.load_operation_state(project_root)["resume_checkpoint"]

    assert resume_checkpoint["next_chunk_index"] == 3
    assert resume_checkpoint["active_chunk_id"] == "chunk-0004"
    assert resume_checkpoint["next_source_offset"] == 55


def test_missing_document_is_treated_as_not_started(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-ac0451b0 treats a missing document as not-started.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()

    assert speech_blocks_service.load_speech_blocks_document(project_root) is None
    assert speech_blocks_service.load_speech_blocks(project_root) == []
    assert speech_blocks_service.load_speech_blocks_report(project_root) is None
    assert speech_blocks_service.load_operation_state(project_root) is None


@pytest.mark.parametrize(
    ("invalid_bytes", "cause_type"),
    [
        (b"{", json.JSONDecodeError),
        (b"\xff", UnicodeDecodeError),
        (b"null", speech_blocks_service.SpeechBlocksDocumentError),
        (
            json.dumps([{"speech_block_id": "0001-000001"}]).encode("utf-8"),
            speech_blocks_service.SpeechBlocksDocumentError,
        ),
        (json.dumps({"status": "completed"}).encode("utf-8"), speech_blocks_service.SpeechBlocksDocumentError),
    ],
)
def test_existing_invalid_document_raises_typed_reset_recovery_error(
    tmp_path: Path,
    invalid_bytes: bytes,
    cause_type: type[BaseException],
) -> None:
    """
    @brief      Verify existing unreadable and invalid Speech Blocks documents fail closed with recovery guidance.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  invalid_bytes Existing invalid document bytes.
    @param[in]  cause_type Expected chained root failure type.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document_path = project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME
    document_path.write_bytes(invalid_bytes)

    with pytest.raises(speech_blocks_service.SpeechBlocksDocumentError) as captured_error:
        speech_blocks_service.load_speech_blocks_document(project_root)

    assert "Reset Speech Blocks to recover" in str(captured_error.value)
    assert isinstance(captured_error.value.__cause__, cause_type)


def test_unreadable_existing_document_chains_oserror(monkeypatch, tmp_path: Path) -> None:
    """
    @brief      Verify a filesystem read failure is chained into the typed Speech Blocks recovery error.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME).write_text("{}", encoding="utf-8")

    def _raise_permission_error(_artifact_path) -> None:
        """Raise the injected artifact read failure."""
        raise PermissionError("speech blocks denied")

    monkeypatch.setattr(speech_blocks_service, "load_optional_json_artifact", _raise_permission_error)

    with pytest.raises(speech_blocks_service.SpeechBlocksDocumentError) as captured_error:
        speech_blocks_service.load_speech_blocks_document(project_root)

    assert "Reset Speech Blocks to recover" in str(captured_error.value)
    assert isinstance(captured_error.value.__cause__, PermissionError)


def test_generation_does_not_overwrite_corrupt_speech_blocks_document(monkeypatch, tmp_path: Path) -> None:
    """
    @brief      Verify generation rejects corrupt Speech Blocks state before any replacement write.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document_path = project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME
    corrupt_bytes = b"{corrupt speech blocks"
    document_path.write_bytes(corrupt_bytes)
    monkeypatch.setattr(
        speech_blocks_service,
        "resolve_source_chunks",
        lambda *_args, **_kwargs: {
            "selected_source_language": "en",
            "source_kind": "original",
            "source_chunks": [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Narration."}],
        },
    )

    with pytest.raises(speech_blocks_service.SpeechBlocksDocumentError, match="Reset Speech Blocks to recover"):
        speech_blocks_service.start_or_continue_generation(
            project_root,
            {"voice_assignment_mode": "same_narrator"},
            {},
        )

    assert document_path.read_bytes() == corrupt_bytes


def test_reset_removes_document(tmp_path: Path) -> None:
    """
    @brief      Verify REQ-FUNC-a4d7fcde reset clears the authoritative document.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    document_path = speech_blocks_service.write_speech_blocks_document(project_root, _document())

    speech_blocks_service.reset_speech_blocks(project_root)

    assert not document_path.exists()


def test_invalid_root_contract_is_rejected(tmp_path: Path) -> None:
    """
    @brief      Verify SPEC-SB-SINGLEDOC / REQ-FUNC-c71fbab4 strict root validation.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    invalid_document = _document()
    invalid_document.pop("blocks")

    with pytest.raises(speech_blocks_service.SpeechBlocksDocumentError):
        speech_blocks_service.write_speech_blocks_document(project_root, invalid_document)


@pytest.mark.parametrize(
    "reader",
    [
        speech_blocks_service.load_operation_state,
        speech_blocks_service.load_speech_blocks_report,
        speech_blocks_service.load_speech_blocks,
    ],
)
def test_public_read_projections_do_not_hide_invalid_document(reader, tmp_path: Path) -> None:
    """Verify every public projection preserves strict document failures."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    document_path = project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME
    document_path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(speech_blocks_service.SpeechBlocksDocumentError, match="Reset Speech Blocks to recover"):
        reader(project_root)


# END OF FILE
