#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chunking_input_service.py
@brief Load verified Cleanup paragraphs for Chunking.
@details Keeps filesystem and Cleanup document loading outside the pure Chunking core.
"""

# IMPORTS

from pathlib import Path

from audiomancer.services import cleanup_metadata_service

# PUBLIC API


def load_paragraph_records(cleaned_text: str, project_root: str | Path | None = None) -> list[dict[str, object]]:
    """
    @brief      Build the paragraph records.
    @param[in]  cleaned_text Text value for `cleaned_text`.
    @return     Derived helper result.
    """
    if project_root is not None:
        paragraph_records = cleanup_metadata_service.load_completed_paragraph_records(
            project_root,
            cleaned_text,
        )
    else:
        paragraph_records = cleanup_metadata_service.build_paragraph_records_from_text(cleaned_text)
    records: list[dict[str, object]] = []
    for number, record in enumerate(paragraph_records, 1):
        records.append(
            {
                **dict(record),
                "paragraph_number": number,
                "line_start": int(record.get("source_start_line", 1)),
                "line_end": int(record.get("source_end_line", record.get("source_start_line", 1))),
            }
        )
    return records


# END OF FILE
