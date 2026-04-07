#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file operation_runtime_service.py
@brief Shared runtime helpers for cancelable workflow operations.
@details Centralizes numbered-folder lookup, operation-local path building,
         downstream reset behavior, and progress helpers shared by extraction,
         cleanup, and future long-running workflow operations.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.1.2
"""

# IMPORTS

import math
import shutil
from pathlib import Path

from audiomancer import config

# CONSTANTS

# @brief Mapping from operation kind to its numbered project-workspace folder.
_OPERATION_FOLDER_NAMES = {
    "extraction": config.EXTRACTION_FOLDER_NAME,
    "cleanup": config.CLEANUP_FOLDER_NAME,
    "chunking": "20_chunking",
    "translation": "30_translation",
    "character_discovery": "40_character_discovery",
}
# @brief Stable execution order used for downstream reset calculations.
_OPERATION_ORDER = tuple(_OPERATION_FOLDER_NAMES.keys())


# DATA MODELS / TYPEDEFINITIONS


class OperationCancelledError(RuntimeError):
    """
    @brief      Raised when one cancelable operation stops cooperatively.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """


# PUBLIC API


def operation_folder_name(operation_kind: str) -> str:
    """
    @brief      Resolve one operation kind to its numbered project folder.
    @param[in]  operation_kind Stable workflow operation token.
    @return     Project-relative folder name.
    @exception  KeyError Raised when the operation kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return _OPERATION_FOLDER_NAMES[operation_kind]


def downstream_operation_kinds(
    operation_kind: str,
    include_current: bool = False,
) -> tuple[str, ...]:
    """
    @brief      Return ordered downstream operation kinds for one workflow step.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  include_current True to include the selected operation itself.
    @return     Ordered operation-kind tuple.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if operation_kind not in _OPERATION_ORDER:
        return tuple()
    start_index = _OPERATION_ORDER.index(operation_kind)
    if not include_current:
        start_index += 1
    return _OPERATION_ORDER[start_index:]


def build_operation_input_snapshot_path(
    project_root: str | Path,
    operation_kind: str,
    original_name: str,
) -> Path:
    """
    @brief      Build one operation-local input snapshot path.
    @param[in]  project_root Active project root.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  original_name Original imported source file name.
    @return     Absolute operation-local input snapshot path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    operation_root = Path(project_root) / operation_folder_name(operation_kind)
    operation_root.mkdir(parents=True, exist_ok=True)
    return operation_root / f"{config.OPERATION_INPUT_FILE_PREFIX}{Path(original_name).name}"


def build_operation_output_path(
    project_root: str | Path,
    operation_kind: str,
    file_name: str,
) -> Path:
    """
    @brief      Build one operation-local file path.
    @param[in]  project_root Active project root.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  file_name Operation-local file name.
    @return     Absolute operation-local file path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    operation_root = Path(project_root) / operation_folder_name(operation_kind)
    operation_root.mkdir(parents=True, exist_ok=True)
    return operation_root / file_name


def build_operation_artifact_path(
    project_root: str | Path,
    operation_kind: str,
    file_name: str,
) -> Path:
    """
    @brief      Build one operation-local artifact file path.
    @param[in]  project_root Active project root.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  file_name Operation artifact file name.
    @return     Absolute operation-local artifact file path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return build_operation_output_path(project_root, operation_kind, file_name)


def relative_to_project(project_root: str | Path, artifact_path: str | Path) -> str:
    """
    @brief      Convert one project-local path into a manifest-relative string.
    @param[in]  project_root Active project root.
    @param[in]  artifact_path Absolute project-local artifact path.
    @return     POSIX-style project-relative string.
    @exception  ValueError Raised when the path is outside the project root.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    return Path(artifact_path).relative_to(Path(project_root)).as_posix()


def progress_percent(progress_current: int, progress_total: int) -> int:
    """
    @brief      Convert unit-based progress into one stable UI percent value.
    @param[in]  progress_current Completed work-unit count.
    @param[in]  progress_total Total work-unit count.
    @return     Integer percent in the inclusive 0-100 range.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if progress_total <= 0:
        return 0
    resolved_percent = math.floor((max(progress_current, 0) / progress_total) * 100)
    return max(0, min(resolved_percent, 100))


def reset_operation_data(
    project_root: str | Path,
    operation_kind: str,
    include_current: bool = True,
    keep_input_snapshots: bool = False,
) -> None:
    """
    @brief      Clear one workflow step and optional downstream runtime folders.
    @param[in]  project_root Active project root.
    @param[in]  operation_kind Selected workflow operation token.
    @param[in]  include_current True to clear the selected operation folder too.
    @param[in]  keep_input_snapshots True to preserve files prefixed with `input_`.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """
    operation_kinds = downstream_operation_kinds(
        operation_kind,
        include_current=include_current,
    )
    for selected_kind in operation_kinds:
        folder_path = Path(project_root) / operation_folder_name(selected_kind)
        folder_path.mkdir(parents=True, exist_ok=True)
        for child in list(folder_path.iterdir()):
            if (
                keep_input_snapshots
                and child.is_file()
                and child.name.startswith(config.OPERATION_INPUT_FILE_PREFIX)
            ):
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()


def raise_if_cancelled(cancel_requested) -> None:
    """
    @brief      Raise one cooperative cancellation when the caller requested it.
    @param[in]  cancel_requested Optional zero-argument callable.
    @return     None.
    @exception  OperationCancelledError Raised when cancellation is requested.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if callable(cancel_requested) and bool(cancel_requested()):
        raise OperationCancelledError("The operation was cancelled by the operator.")


# END OF FILE
