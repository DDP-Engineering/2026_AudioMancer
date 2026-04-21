#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file import_service.py
@brief Functional source registration helpers for AudioMancer.
@details Validates one supported source file, copies it into the project
         workspace, and returns normalized source metadata for `project.json`.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.1.0
"""

# IMPORTS

from datetime import UTC, datetime
from pathlib import Path
import shutil

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function

# CONSTANTS

# @brief Component logger used by the source-import workflow.
_IMPORT_LOGGER = get_component_logger("import_service")
# @brief Normalized source-document payload type persisted in the project manifest.
SourceDocumentPayload = dict[str, object]


# PUBLIC API


@trace_function(_IMPORT_LOGGER)
def import_source(
    project_root: str | Path,
    source_path: str | Path,
) -> SourceDocumentPayload:
    """
    @brief      Validate and copy one supported source file into the project.
    @param[in]  project_root Root path of the active project workspace.
    @param[in]  source_path Path to the source file selected by the operator.
    @return     Normalized source-document payload for manifest persistence.
    @exception  FileNotFoundError Raised when the source file is missing.
    @exception  ValueError Raised when the file type is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    resolved_source = Path(source_path)
    if not resolved_source.is_file():
        raise FileNotFoundError(f"Source file does not exist: {resolved_source}")

    suffix = resolved_source.suffix.lower()
    file_type = config.SUPPORTED_SOURCE_SUFFIXES.get(suffix)
    if file_type is None:
        raise ValueError(f"Unsupported source format: {suffix}")

    resolved_project_root = Path(project_root)
    destination_path = _build_unique_destination(
        resolved_project_root,
        resolved_source.name,
    )
    shutil.copy2(resolved_source, destination_path)

    return {
        "original_name": resolved_source.name,
        "stored_relative_path": destination_path.relative_to(resolved_project_root).as_posix(),
        "file_type": file_type,
        "imported_at": _utc_now_iso(),
        "size_bytes": destination_path.stat().st_size,
    }


# HELPER FUNCTIONS


def _utc_now_iso() -> str:
    """
    @brief      Build one current UTC timestamp in stable ISO-8601 format.
    @return     UTC timestamp string without microseconds.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _build_unique_destination(destination_dir: Path, file_name: str) -> Path:
    """
    @brief      Build a non-colliding destination path under the project root.
    @param[in]  destination_dir Target project directory.
    @param[in]  file_name Original file name selected by the operator.
    @return     Unique destination path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    candidate = destination_dir / file_name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    index = 1
    while True:
        candidate = destination_dir / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


# END OF FILE
