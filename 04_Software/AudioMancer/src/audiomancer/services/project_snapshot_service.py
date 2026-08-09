#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file project_snapshot_service.py
@brief Whole-project ZIP snapshot service for AudioMancer.
@details Creates complete external ZIP snapshots of active project folders
         without registering the archive as a project runtime artifact.
"""

# IMPORTS

from collections.abc import Iterator
from datetime import datetime
from functools import partial
import os
from pathlib import Path
import zipfile

from audiomancer import config
from audiomancer.services import operation_runtime_service
from audiomancer.services.logging_service import get_component_logger

# CONSTANTS

# @brief Default archive extension used by project snapshots.
SNAPSHOT_EXTENSION = ".zip"
_PROJECT_SNAPSHOT_LOGGER = get_component_logger("project_snapshot")
_emit_progress = partial(operation_runtime_service.emit_progress_update, include_token_usage=False)


# PUBLIC API


def default_snapshot_file_name(
    project_root: str | Path,
    manifest: dict[str, object] | None = None,
    timestamp: datetime | None = None,
) -> str:
    """
    @brief      Build the default external ZIP snapshot file name.
    @param[in]  project_root Active project root folder.
    @param[in]  manifest Optional active project manifest.
    @param[in]  timestamp Optional timestamp override for deterministic tests.
    @return     Filesystem-safe ZIP file name.
    @exception  None
    """
    snapshot_timestamp = timestamp or datetime.now()
    project_name = str(
        (manifest or {}).get("display_name")
        or (manifest or {}).get("project_name")
        or Path(project_root).name
        or "AudioMancer"
    )
    safe_project_name = operation_runtime_service.safe_file_stem(project_name)
    return f"{safe_project_name}_snapshot_{snapshot_timestamp:%Y%m%d_%H%M%S}{SNAPSHOT_EXTENSION}"


def ensure_snapshot_extension(snapshot_path: str | Path) -> Path:
    """
    @brief      Ensure one selected snapshot path ends in `.zip`.
    @param[in]  snapshot_path Candidate save-file path.
    @return     Path with the required snapshot extension.
    @exception  None
    """
    return operation_runtime_service.append_required_extension(
        snapshot_path,
        SNAPSHOT_EXTENSION,
    )


def is_path_inside_project(project_root: str | Path, snapshot_path: str | Path) -> bool:
    """
    @brief      Determine whether a snapshot destination is inside the project root.
    @param[in]  project_root Active project root folder.
    @param[in]  snapshot_path Candidate ZIP destination path.
    @return     True when the destination equals or sits below the project root.
    @exception  None
    """
    return operation_runtime_service.is_path_inside_project(project_root, snapshot_path)


def create_project_snapshot(
    project_root: str | Path,
    snapshot_path: str | Path,
    progress_callback=None,
    cancel_requested=None,
) -> dict[str, object]:
    """
    @brief      Create one complete ZIP snapshot of an active project folder.
    @param[in]  project_root Active project root folder.
    @param[in]  snapshot_path External ZIP destination path.
    @param[in]  progress_callback Optional callback receiving current, total, percent, and message.
    @param[in]  cancel_requested Optional callable returning True when export should cancel.
    @return     Snapshot result metadata with final path and file count.
    @exception  FileNotFoundError Raised when the project root does not exist.
    @exception  ValueError Raised when the destination is inside the project root.
    @exception  OSError Raised when ZIP creation or replacement fails.
    """
    resolved_project_root = Path(project_root).resolve()
    if not resolved_project_root.is_dir():
        raise FileNotFoundError(f"Project root does not exist: {resolved_project_root}")

    final_path = ensure_snapshot_extension(snapshot_path).resolve()
    if is_path_inside_project(resolved_project_root, final_path):
        raise ValueError("Snapshot destination must be outside the active project folder.")

    final_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = final_path.with_name(f".{final_path.name}.tmp")
    archive_root_name = resolved_project_root.name or "project"
    project_files = list(_iter_project_files(resolved_project_root))
    total_files = len(project_files)
    file_count = 0
    _PROJECT_SNAPSHOT_LOGGER.info(
        "Creating project ZIP snapshot project_root=%s snapshot_path=%s file_count=%s",
        resolved_project_root,
        final_path,
        total_files,
    )

    if temporary_path.exists():
        temporary_path.unlink()

    try:
        _raise_if_cancelled(cancel_requested)
        _emit_progress(progress_callback, 0, total_files, "Preparing project ZIP snapshot...")
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in project_files:
                _raise_if_cancelled(cancel_requested)
                archive_name = Path(archive_root_name) / file_path.relative_to(resolved_project_root)
                zip_file.write(file_path, archive_name.as_posix())
                file_count += 1
                _emit_progress(
                    progress_callback,
                    file_count,
                    total_files,
                    f"Archiving {file_count}/{total_files}: {file_path.name}",
                )
        _raise_if_cancelled(cancel_requested)
        os.replace(temporary_path, final_path)
    except Exception:
        _PROJECT_SNAPSHOT_LOGGER.exception("Project ZIP snapshot failed snapshot_path=%s", final_path)
        if temporary_path.exists():
            temporary_path.unlink()
        raise

    _PROJECT_SNAPSHOT_LOGGER.info("Created project ZIP snapshot snapshot_path=%s file_count=%s", final_path, file_count)

    return {
        "snapshot_path": str(final_path),
        "file_count": file_count,
        "archive_root": archive_root_name,
    }


# LOCAL HELPERS


def _iter_project_files(project_root: Path) -> Iterator[Path]:
    """
    @brief      Yield regular project files while excluding symlinks and AI transaction logs.
    @param[in]  project_root Resolved active project root.
    @return     Iterator over regular non-symlink files in stable path order.
    @exception  None
    """
    for current_root, directory_names, file_names in os.walk(project_root, followlinks=False):
        directory_names[:] = sorted(
            directory_name
            for directory_name in directory_names
            if not (Path(current_root) / directory_name).is_symlink()
        )
        for file_name in sorted(file_names):
            file_path = Path(current_root) / file_name
            if file_path.is_file() and not file_path.is_symlink() and not _is_ai_transaction_log(file_path):
                yield file_path


def _is_ai_transaction_log(file_path: Path) -> bool:
    """
    @brief      Determine whether one project file is an AI transaction log.
    @param[in]  file_path Candidate project file path.
    @return     True when the file follows the configured AI log naming pattern.
    @exception  None
    """
    file_name = file_path.name
    return file_name.startswith(config.AI_TRANSACTION_LOG_FILE_PREFIX) and file_name.endswith(
        config.AI_TRANSACTION_LOG_FILE_EXTENSION
    )


def _raise_if_cancelled(cancel_requested) -> None:
    """
    @brief      Raise the shared operation-cancelled exception when requested.
    @param[in]  cancel_requested Optional cancellation predicate.
    @return     None.
    @exception  OperationCancelledError Raised when cancellation is requested.
    """
    if cancel_requested is not None and bool(cancel_requested()):
        raise operation_runtime_service.OperationCancelledError("Project ZIP export cancelled.")


# END OF FILE
