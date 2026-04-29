#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_speech_blocks_report_state_service.py
@brief Focused tests for Speech Blocks report and state shaping helpers.
@details Verifies extracted report, warning, source-path, and operation-state
         payload construction behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-29
@version 0.1.0
"""

# IMPORTS

from pathlib import Path

from audiomancer import config
from audiomancer.services import speech_blocks_report_state_service


def test_rebuild_report_reflects_stage_counts_and_warnings() -> None:
    """
    @brief      Verify report shaping derives status, counts, warnings, and token usage.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    speech_blocks = [
        {
            "speech_block_id": "0001-000001",
            "chunk_id": "chunk-0001",
            "approved": True,
            "warning_flags": ["model_text_modified", "model_text_modified"],
        },
        {
            "speech_block_id": "0001-000002",
            "chunk_id": "chunk-0001",
            "approved": False,
            "warning_flags": [],
        },
    ]

    report = speech_blocks_report_state_service.rebuild_report(
        speech_blocks,
        "en",
        "original",
        "profile-1",
        total_chunk_count=1,
        processed_chunk_count=1,
        warning_records=[],
        token_usage={"input_tokens": 4, "output_tokens": 2, "total_tokens": 6, "usage_available": True},
        budget_metadata={"text_budget_tokens": 10},
        updated_at="2026-04-29T12:00:00+00:00",
    )

    assert report["speech_blocks_stage_status"] == "in_progress"
    assert report["approved_block_count"] == 1
    assert report["warning_count"] == 1
    assert report["warnings"][0]["reason"] == "model_text_modified"
    assert report["budget_metadata"] == {"text_budget_tokens": 10}


def test_build_operation_state_shapes_paths_metadata_and_resume_checkpoint(tmp_path: Path) -> None:
    """
    @brief      Verify operation-state shaping keeps relative paths, metadata, and resume data.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    project_root = tmp_path / "Project"
    project_root.mkdir()
    source_chunks = [{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Hello."}]
    speech_blocks = [
        {
            "speech_block_id": "0001-000001",
            "chunk_id": "chunk-0001",
            "approved": False,
            "warning_flags": ["ambiguous_speaker"],
        }
    ]
    log_path = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / "log_ai_transactions.log"

    state = speech_blocks_report_state_service.build_operation_state(
        project_root,
        source_chunks,
        speech_blocks,
        status="running",
        started_at="2026-04-29T12:00:00+00:00",
        completed_at=None,
        source_language="en",
        source_kind="original",
        profile_id="profile-1",
        warning_records=[],
        input_fingerprint="fingerprint",
        log_path=log_path,
        token_usage={"input_tokens": 4, "output_tokens": 2, "total_tokens": 6, "usage_available": True},
        next_chunk_index=1,
        budget_metadata={"text_budget_tokens": 10},
    )

    assert state["input_paths"] == [config.CHUNK_ARTIFACT_FILE_NAME]
    assert state["output_paths"] == [config.SPEECH_BLOCKS_OUTPUT_FILE_NAME]
    assert state["progress_current"] == 1
    assert state["warning_count"] == 1
    assert state["metadata"]["source_chunks"] == source_chunks
    assert state["resume_checkpoint"]["next_chunk_index"] == 1
    assert state["resume_checkpoint"]["budget_metadata"] == {"text_budget_tokens": 10}


def test_source_chunks_input_path_selects_original_or_translated(tmp_path: Path) -> None:
    """
    @brief      Verify Speech Blocks source artifact path selection by source kind.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    assert speech_blocks_report_state_service.source_chunks_input_path(tmp_path, "original") == (
        tmp_path / config.CHUNK_ARTIFACT_FILE_NAME
    )
    assert speech_blocks_report_state_service.source_chunks_input_path(tmp_path, "translated") == (
        tmp_path / config.TRANSLATED_CHUNKS_FILE_NAME
    )


# END OF FILE
