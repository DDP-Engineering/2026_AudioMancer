#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_cleanup_service.py
@brief Focused orchestration checks for the approved Cleanup operation.
@details Retains progress, status-copy, and source-projection coverage while
         replacing the obsolete versioned document and sidecar assumptions;
         covers whitespace role realignment through deterministic Chunking.
@author Eng. Dan Dumitru Pasare
@date 2026-07-28
@version 0.4.0
"""

# IMPORTS

from __future__ import annotations

import json

import pytest

from audiomancer import config
from audiomancer.services import (
    cleanup_renderer_service,
    deterministic_chunking_service,
    text_cleanup_service,
)
from cleanup_test_support import build_ledger, build_project

# TESTS


def test_cleanup_without_ai_reports_monotonic_phase_progress(tmp_path) -> None:
    """
    @brief      Cover monotonic Cleanup progress without AI.
    @version    0.1.0
    """
    canonical_text, ledger = build_ledger(["A wrapped line", "continues safely."])
    project_root, manifest = build_project(tmp_path, "ProgressWithoutAi", canonical_text, ledger)
    progress: list[tuple[int, int, int, str]] = []

    text_cleanup_service.clean_text(
        project_root,
        manifest,
        progress_callback=lambda current, total, percent, message: progress.append(
            (current, total, percent, message)
        ),
    )

    percentages = [item[2] for item in progress]
    assert percentages == sorted(percentages)
    assert percentages[0] == 0
    assert percentages[-1] == 100
    assert 100 not in percentages[:-1]
    assert any("ambiguous boundaries" in item[3] for item in progress)
    assert any("estimated" in item[3] and "AI requests" in item[3] for item in progress)


def test_renderer_rejects_replacement_text_and_unknown_actions() -> None:
    """
    @brief      Cover rejection of replacement text and unknown actions.
    @version    0.1.0
    """
    canonical_text, ledger = build_ledger(["Source text."])

    with pytest.raises(cleanup_renderer_service.CleanupRenderError, match="Unsupported"):
        cleanup_renderer_service.render_cleanup(
            canonical_text,
            ledger,
            [
                {
                    "operation_id": "op-000001",
                    "action": "replace_text",
                    "target_id": "u-000001",
                    "replacement": "Invented text.",
                }
            ],
            [],
        )


def test_completed_cleanup_reports_only_runtime_quality_metrics(tmp_path) -> None:
    """
    @brief      Cover the production-only Cleanup quality metric contract.
    @version    0.1.0
    """
    canonical_text, ledger = build_ledger(["A paragraph ends here."])
    project_root, manifest = build_project(tmp_path, "RuntimeMetrics", canonical_text, ledger)

    document = text_cleanup_service.clean_text(project_root, manifest)

    assert document["quality_report"]["introduced_fusion_count"] == 0
    assert document["quality_report"]["projection_violation_count"] == 0
    assert "f1" not in document["quality_report"]
    assert "precision" not in document["quality_report"]
    assert "recall" not in document["quality_report"]


def test_whitespace_merge_split_preserves_narratable_prose(tmp_path) -> None:
    """
    @brief      Cover issue #32 merge/split role realignment through Chunking.
    @details    Covers S-0001 through S-0006,
                REQ-FUNC-807c56f0-12b7-42e9-bd8f-0d562c903e70, and
                REQ-FUNC-376f4f7a-a9e4-4653-845b-edbba25cf170.
    @version    0.1.0
    """
    source_paragraphs = [
        "Opening one.",
        "Opening two.",
        "CHAPTER TWO",
        "* * *",
        "Closing one.",
        "Closing two first. Closing two second.",
    ]
    canonical_text, ledger = build_ledger(
        source_paragraphs,
        kinds=[
            "paragraph",
            "paragraph",
            "heading",
            "scene_separator",
            "paragraph",
            "paragraph",
        ],
        boundaries=[("\n\n", "native_paragraph")] * 5,
        origins=["native"] * 6,
        structure_quality="native",
    )
    project_root, manifest = build_project(
        tmp_path,
        "WhitespaceRoleRealignment",
        canonical_text,
        ledger,
    )
    text_cleanup_service.clean_text(project_root, manifest)

    edited = text_cleanup_service.save_user_cleaned_text(
        project_root,
        (
            "Opening one. Opening two.\n\n"
            "CHAPTER TWO\n\n"
            "* * *\n\n"
            "Closing one.\n\n"
            "Closing two first.\n\n"
            "Closing two second.\n"
        ),
    )

    assert [item["role"] for item in edited["paragraphs"]] == [
        "body",
        "heading",
        "scene_separator",
        "body",
        "body",
        "body",
    ]

    deterministic_chunking_service.chunk_text(project_root, manifest)

    chunks = json.loads(
        (project_root / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8")
    )["chunks"]
    materialized_text = "\n".join(str(item["text"]) for item in chunks)
    assert "* * *" not in materialized_text
    for prose in (
        "Opening one. Opening two.",
        "CHAPTER TWO",
        "Closing one.",
        "Closing two first.",
        "Closing two second.",
    ):
        assert prose in materialized_text


def test_whitespace_role_realign_falls_back_for_ambiguous_content(tmp_path) -> None:
    """
    @brief      Cover classifier-only fallback for ambiguous normalized content.
    @details    Covers S-0005 and
                REQ-FUNC-807c56f0-12b7-42e9-bd8f-0d562c903e70.
    @version    0.1.0
    """
    canonical_text, ledger = build_ledger(
        ["CHAPTER TWO", "CHAPTER TWO", "Narration."],
        kinds=["heading", "heading", "paragraph"],
        boundaries=[("\n\n", "native_paragraph")] * 2,
        origins=["native"] * 3,
        structure_quality="native",
    )
    project_root, manifest = build_project(
        tmp_path,
        "AmbiguousWhitespaceRoles",
        canonical_text,
        ledger,
    )
    text_cleanup_service.clean_text(project_root, manifest)

    edited = text_cleanup_service.save_user_cleaned_text(
        project_root,
        "CHAPTER   TWO\n\nCHAPTER TWO\n\nNarration.\n",
    )

    assert [item["role"] for item in edited["paragraphs"]] == [
        "body",
        "body",
        "body",
    ]


def test_whitespace_realign_failure_records_diagnostic(tmp_path, caplog) -> None:
    """
    @brief      Cover S-0001 and REQ-FUNC-1179da33-b65d-4192-a875-353a38c37ab7.
    @version    0.1.0
    """
    canonical_text, ledger = build_ledger(["Alpha  beta."])
    project_root, manifest = build_project(
        tmp_path,
        "WhitespaceRealignDiagnostic",
        canonical_text,
        ledger,
    )
    text_cleanup_service.clean_text(project_root, manifest)

    with caplog.at_level("WARNING"):
        edited = text_cleanup_service.save_user_cleaned_text(
            project_root,
            "Alpha beta.\n",
        )

    assert edited["warnings"].count("user_whitespace_realign_incomplete") == 1
    assert any(
        "could not realign Cleanup boundaries" in record.getMessage()
        for record in caplog.records
    )


# END OF FILE
