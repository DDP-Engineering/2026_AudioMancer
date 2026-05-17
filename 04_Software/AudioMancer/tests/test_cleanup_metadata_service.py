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
@brief Focused tests for cleaned-text paragraph metadata persistence.
@details Verifies compact cleanup metadata omits duplicated text while
         downstream loaders rebuild paragraph text from canonical clean text.
@author Eng. Dan Dumitru Pasare
@date 2026-05-17
@version 0.1.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import cleanup_metadata_service


def test_cleanup_metadata_omits_text_and_reconstructs_from_clean_text(tmp_path) -> None:
    """
    @brief      Verify compact metadata omits paragraph text and reloads it from line spans.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-17
    @version    0.1.0
    """
    project_root = tmp_path / "MetadataProject"
    project_root.mkdir()
    cleaned_text = "First paragraph.\n\nSecond line one.\nSecond line two.\n"
    cleaned_text_path = project_root / config.CLEANED_TEXT_FILE_NAME
    cleaned_text_path.write_text(cleaned_text, encoding="utf-8")

    records = cleanup_metadata_service.build_paragraph_records_from_text(cleaned_text)
    cleanup_metadata_service.write_cleanup_metadata(project_root, None, cleaned_text_path, records, "manual_edit")

    metadata_payload = json.loads(
        cleanup_metadata_service.cleanup_metadata_path(project_root).read_text(encoding="utf-8")
    )
    assert "text" not in metadata_payload["paragraphs"][0]
    assert "text" not in metadata_payload["paragraphs"][1]

    loaded_records = cleanup_metadata_service.load_or_build_paragraph_records(project_root, cleaned_text)
    assert loaded_records[0]["text"] == "First paragraph."
    assert loaded_records[1]["text"] == "Second line one.\nSecond line two."


# END OF FILE
