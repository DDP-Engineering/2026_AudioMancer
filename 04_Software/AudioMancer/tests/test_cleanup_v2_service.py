#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_cleanup_v2_service.py
@brief Focused orchestration checks for the approved Cleanup V2 operation.
@details Retains progress, status-copy, and source-projection coverage while
         replacing the obsolete versioned document and sidecar assumptions.
@author Eng. Dan Dumitru Pasare
@date 2026-07-28
@version 0.2.0
"""

from __future__ import annotations

import pytest

from audiomancer.services import cleanup_renderer_service, text_cleanup_service
from cleanup_v2_test_support import build_ledger, build_project


def test_cleanup_without_ai_reports_monotonic_phase_progress(tmp_path) -> None:
    """Cover S-0005/S-0010 and REQ-UX-61dacc39-d0e3-453a-8ce9-3820cd5816bf."""
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
    """Cover S-0001/S-0013 and REQ-FUNC-e42171cc-9c36-4327-87ba-c0f13da05c8c."""
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
    """Cover S-0012 and REQ-FUNC-f9125c01-1a7a-4e84-8451-60b63f4b5dc8."""
    canonical_text, ledger = build_ledger(["A paragraph ends here."])
    project_root, manifest = build_project(tmp_path, "RuntimeMetrics", canonical_text, ledger)

    document = text_cleanup_service.clean_text(project_root, manifest)

    assert document["quality_report"]["introduced_fusion_count"] == 0
    assert document["quality_report"]["projection_violation_count"] == 0
    assert "f1" not in document["quality_report"]
    assert "precision" not in document["quality_report"]
    assert "recall" not in document["quality_report"]


# END OF FILE
