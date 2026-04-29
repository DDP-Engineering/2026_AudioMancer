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
@version 0.2.1
"""

# IMPORTS

from datetime import UTC, datetime
from pathlib import Path
import shutil

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import resolve_project_relative_path

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
    previous_source_document: dict[str, object] | None = None,
) -> SourceDocumentPayload:
    """
    @brief      Validate and copy one supported source file into the project.
    @param[in]  project_root Root path of the active project workspace.
    @param[in]  source_path Path to the source file selected by the operator.
    @param[in]  previous_source_document Optional previous manifest source to replace.
    @return     Normalized source-document payload for manifest persistence.
    @exception  FileNotFoundError Raised when the source file is missing.
    @exception  ValueError Raised when the file type is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    resolved_source = Path(source_path)
    if not resolved_source.is_file():
        raise FileNotFoundError(f"Source file does not exist: {resolved_source}")

    suffix = resolved_source.suffix.lower()
    file_type = config.SUPPORTED_SOURCE_SUFFIXES.get(suffix)
    if file_type is None:
        raise ValueError(f"Unsupported source format: {suffix}")

    resolved_project_root = Path(project_root)
    _delete_previous_source_file(
        resolved_project_root,
        previous_source_document,
        resolved_source,
    )
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


def _delete_previous_source_file(
    project_root: Path,
    previous_source_document: dict[str, object] | None,
    selected_source: Path,
) -> None:
    """
    @brief      Delete the previous imported source file before replacement.
    @param[in]  project_root Active project root.
    @param[in]  previous_source_document Previous source-document manifest payload.
    @param[in]  selected_source Newly selected source path.
    @return     None.
    @exception  ValueError Raised when the previous path resolves outside the project.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    if not isinstance(previous_source_document, dict):
        return
    stored_relative_path = str(previous_source_document.get("stored_relative_path") or "").strip()
    if not stored_relative_path:
        return
    previous_path = resolve_project_relative_path(project_root, stored_relative_path)
    try:
        if previous_path == selected_source.resolve():
            return
    except FileNotFoundError:
        pass
    if previous_path.is_file():
        previous_path.unlink()


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
