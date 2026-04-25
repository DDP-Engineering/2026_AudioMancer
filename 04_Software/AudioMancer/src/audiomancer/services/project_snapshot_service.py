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
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.2.0
"""

# IMPORTS

from collections.abc import Iterator
from datetime import datetime
import os
from pathlib import Path
import re
import zipfile

from audiomancer.services import operation_runtime_service

# CONSTANTS

# @brief Default archive extension used by project snapshots.
SNAPSHOT_EXTENSION = ".zip"


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    snapshot_timestamp = timestamp or datetime.now()
    project_name = str(
        (manifest or {}).get("display_name")
        or (manifest or {}).get("project_name")
        or Path(project_root).name
        or "AudioMancer"
    )
    return f"{_safe_file_stem(project_name)}_snapshot_{snapshot_timestamp:%Y%m%d_%H%M%S}{SNAPSHOT_EXTENSION}"


def ensure_snapshot_extension(snapshot_path: str | Path) -> Path:
    """
    @brief      Ensure one selected snapshot path ends in `.zip`.
    @param[in]  snapshot_path Candidate save-file path.
    @return     Path with the required snapshot extension.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    resolved_path = Path(snapshot_path)
    if resolved_path.suffix.lower() == SNAPSHOT_EXTENSION:
        return resolved_path
    return resolved_path.with_suffix(SNAPSHOT_EXTENSION)


def is_path_inside_project(project_root: str | Path, snapshot_path: str | Path) -> bool:
    """
    @brief      Determine whether a snapshot destination is inside the project root.
    @param[in]  project_root Active project root folder.
    @param[in]  snapshot_path Candidate ZIP destination path.
    @return     True when the destination equals or sits below the project root.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    resolved_root = Path(project_root).resolve()
    resolved_snapshot_path = Path(snapshot_path).resolve()
    try:
        resolved_snapshot_path.relative_to(resolved_root)
    except ValueError:
        return False
    return True


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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
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
        if temporary_path.exists():
            temporary_path.unlink()
        raise

    return {
        "snapshot_path": str(final_path),
        "file_count": file_count,
        "archive_root": archive_root_name,
    }


# LOCAL HELPERS


def _iter_project_files(project_root: Path) -> Iterator[Path]:
    """
    @brief      Yield regular project files without following symlink directories.
    @param[in]  project_root Resolved active project root.
    @return     Iterator over regular non-symlink files in stable path order.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    for current_root, directory_names, file_names in os.walk(project_root, followlinks=False):
        directory_names[:] = sorted(
            directory_name
            for directory_name in directory_names
            if not (Path(current_root) / directory_name).is_symlink()
        )
        for file_name in sorted(file_names):
            file_path = Path(current_root) / file_name
            if file_path.is_file() and not file_path.is_symlink():
                yield file_path


def _emit_progress(progress_callback, current: int, total: int, message: str) -> None:
    """
    @brief      Emit one optional snapshot progress update.
    @param[in]  progress_callback Optional UI progress callback.
    @param[in]  current Completed file count.
    @param[in]  total Total file count.
    @param[in]  message Operator-facing progress message.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if progress_callback is None:
        return
    percent = 100 if total <= 0 else min(100, int((max(current, 0) / total) * 100))
    progress_callback(current, total, percent, message)


def _raise_if_cancelled(cancel_requested) -> None:
    """
    @brief      Raise the shared operation-cancelled exception when requested.
    @param[in]  cancel_requested Optional cancellation predicate.
    @return     None.
    @exception  OperationCancelledError Raised when cancellation is requested.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if cancel_requested is not None and bool(cancel_requested()):
        raise operation_runtime_service.OperationCancelledError("Project ZIP export cancelled.")


def _safe_file_stem(value: str) -> str:
    """
    @brief      Normalize one operator-facing name into a safe file stem.
    @param[in]  value Raw project name.
    @return     Filesystem-safe file stem.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    normalized = normalized.strip("._-")
    return normalized or "AudioMancer"


# END OF FILE
