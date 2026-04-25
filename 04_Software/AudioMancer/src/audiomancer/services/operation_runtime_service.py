#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file operation_runtime_service.py
@brief Shared runtime helpers for cancelable workflow operations.
@details Centralizes root-level artifact path building, downstream reset
         behavior, and progress helpers shared by long-running workflow
         operations.
@author Eng. Dan Dumitru Pasare
@date 2026-04-22
@version 0.3.0
"""

# IMPORTS

import math
from pathlib import Path

from audiomancer import config

# CONSTANTS

# @brief Stable execution order used for downstream reset calculations.
_OPERATION_ORDER = (
    "extraction",
    "cleanup",
    "chunking",
    "translation",
    "character_discovery",
    "narrator_definition",
    "character_voices",
    "speech_blocks",
    "audio_blocks",
    "audio_assembly",
)

# @brief Root-level runtime artifact files owned by each resettable operation.
_OPERATION_ARTIFACT_FILE_NAMES = {
    "extraction": (
        config.EXTRACTED_TEXT_FILE_NAME,
        config.EXTRACTION_REPORT_FILE_NAME,
        config.EXTRACTION_STATE_FILE_NAME,
    ),
    "cleanup": (
        config.CLEANED_TEXT_FILE_NAME,
        config.CLEANUP_REPORT_FILE_NAME,
        config.CLEANUP_STATE_FILE_NAME,
    ),
    "chunking": (
        config.CHUNK_ARTIFACT_FILE_NAME,
        config.CHUNKING_REPORT_FILE_NAME,
        config.CHUNKING_STATE_FILE_NAME,
    ),
    "translation": (
        config.TRANSLATED_CHUNKS_FILE_NAME,
        config.TRANSLATION_REPORT_FILE_NAME,
        config.TRANSLATION_STATE_FILE_NAME,
    ),
    "character_discovery": (
        config.CHARACTER_PROFILE_FILE_NAME,
        config.CHARACTER_DISCOVERY_REPORT_FILE_NAME,
        config.CHARACTER_DISCOVERY_STATE_FILE_NAME,
    ),
    "narrator_definition": (
        config.NARRATOR_PROFILE_FILE_NAME,
        config.NARRATOR_SELECTION_FILE_NAME,
        config.SELECTED_NARRATOR_AUDIO_FILE_NAME,
    ),
    "character_voices": (config.CHARACTER_VOICES_TARGETS_FILE_NAME,),
    "speech_blocks": (
        config.SPEECH_BLOCKS_OUTPUT_FILE_NAME,
        config.SPEECH_BLOCKS_REPORT_FILE_NAME,
        config.SPEECH_BLOCKS_STATE_FILE_NAME,
    ),
    "audio_blocks": (
        config.AUDIO_BLOCKS_OUTPUT_FILE_NAME,
        config.AUDIO_BLOCKS_REPORT_FILE_NAME,
        config.AUDIO_BLOCKS_STATE_FILE_NAME,
        config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME,
    ),
    "audio_assembly": (),
}


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
    @brief      Resolve one operation kind to its project-relative artifact root.
    @param[in]  operation_kind Stable workflow operation token.
    @return     Project-relative artifact-root name.
    @exception  KeyError Raised when the operation kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    if operation_kind not in _OPERATION_ORDER:
        raise ValueError(f"Unsupported operation kind: {operation_kind}")
    return config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH


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
        return ()
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
    @brief      Reject operation-local input snapshot path creation.
    @param[in]  project_root Active project root.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  original_name Original imported source file name.
    @return     Never returns.
    @exception  RuntimeError Raised because input snapshots are no longer supported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    _ = project_root
    _ = operation_kind
    _ = original_name
    raise RuntimeError("Operation-local input snapshots are not supported by the flat project layout.")


def resolve_operation_path(
    project_root: str | Path,
    operation_kind: str,
    file_name: str,
) -> Path:
    """
    @brief      Resolve one project-local operation artifact path without mutating the project tree.
    @param[in]  project_root Active project root.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  file_name Operation artifact file name.
    @return     Absolute project-local artifact path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.2.0
    """
    _ = operation_kind
    return Path(project_root) / file_name


def build_operation_output_path(
    project_root: str | Path,
    operation_kind: str,
    file_name: str,
) -> Path:
    """
    @brief      Build one project-local artifact path and ensure the root exists.
    @param[in]  project_root Active project root.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  file_name Operation artifact file name.
    @return     Absolute project-local artifact path.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.3.0
    """
    Path(project_root).mkdir(parents=True, exist_ok=True)
    return resolve_operation_path(project_root, operation_kind, file_name)


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
    @brief      Clear one workflow step and optional downstream root-level runtime artifacts.
    @param[in]  project_root Active project root.
    @param[in]  operation_kind Selected workflow operation token.
    @param[in]  include_current True to clear the selected operation folder too.
    @param[in]  keep_input_snapshots Ignored; input snapshots are no longer created.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    _ = keep_input_snapshots
    operation_kinds = downstream_operation_kinds(
        operation_kind,
        include_current=include_current,
    )
    root_path = Path(project_root)
    for selected_kind in operation_kinds:
        for file_name in _OPERATION_ARTIFACT_FILE_NAMES.get(selected_kind, ()):
            artifact_path = root_path / file_name
            if artifact_path.is_file():
                artifact_path.unlink()
        for log_path in root_path.glob(f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}{selected_kind}_*.log"):
            if log_path.is_file():
                log_path.unlink()
        if selected_kind == "audio_blocks":
            audio_blocks_root = root_path / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
            if audio_blocks_root.is_dir():
                for child in audio_blocks_root.rglob("*"):
                    if child.is_file():
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
