#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_cleanup_metadata_service.py
@brief Checks for paragraph offsets embedded in cleanup.json.
@details Verifies the sole metadata document omits duplicate paragraph text
         while its offsets reconstruct the canonical Cleanup output.
@author Eng. Dan Dumitru Pasare
@date 2026-07-28
@version 0.2.0
"""

from audiomancer import config
from audiomancer.services import text_cleanup_service
from cleanup_test_support import build_ledger, build_project


def test_cleanup_paragraph_offsets_reconstruct_clean_text_without_sidecar(tmp_path) -> None:
    """Cover S-0007 and REQ-FUNC-6ac5f253-1b2b-4661-b772-e79f36a9b1b8."""
    canonical_text, ledger = build_ledger(
        ["First paragraph.", "Second line one.\nSecond line two."],
        kinds=["paragraph", "paragraph"],
        boundaries=[("\n\n", "native_paragraph")],
        origins=["native", "native"],
        structure_quality="native",
    )
    project_root, manifest = build_project(tmp_path, "EmbeddedMetadata", canonical_text, ledger)

    document = text_cleanup_service.clean_text(project_root, manifest)
    cleaned_text = (project_root / config.CLEANED_TEXT_FILE_NAME).read_text(encoding="utf-8")

    reconstructed = [
        cleaned_text[int(item["output_start"]) : int(item["output_end"])]
        for item in document["paragraphs"]
    ]
    assert reconstructed == ["First paragraph.", "Second line one.\nSecond line two."]
    assert all("text" not in item for item in document["paragraphs"])
    assert not (project_root / "clean_text_metadata.json").exists()


# END OF FILE
