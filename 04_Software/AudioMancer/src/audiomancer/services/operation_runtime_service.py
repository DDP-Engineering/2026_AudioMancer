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
         behavior, timestamp helpers, JSON artifact IO, and progress helpers
         shared by long-running workflow operations.
@author Eng. Dan Dumitru Pasare
@date 2026-04-22
@version 0.11.2
"""

# IMPORTS

from collections.abc import Iterable
import json
import math
from pathlib import Path, PureWindowsPath

from audiomancer import config
from audiomancer.services.persistence_service import write_json_atomic
from audiomancer.services.time_service import utc_now_iso

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

# @brief Downstream reset operation kinds preserved when upstream text/character data is regenerated.
NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS = frozenset(("narrator_definition",))

# @brief Downstream operation kinds preserved when cleanup or chunking text is revised.
TEXT_REVISION_PRESERVED_OPERATION_KINDS = frozenset(
    (
        "character_discovery",
        "narrator_definition",
        "character_voices",
    )
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
        config.CLEANED_TEXT_METADATA_FILE_NAME,
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
        config.SELECTED_NARRATOR_METADATA_FILE_NAME,
        config.NARRATOR_PROFILE_GENERATION_REPORT_FILE_NAME,
        config.NARRATOR_PROFILE_GENERATION_STATE_FILE_NAME,
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
    "audio_assembly": (
        config.AUDIO_ASSEMBLY_REPORT_FILE_NAME,
        config.AUDIO_ASSEMBLY_STATE_FILE_NAME,
    ),
}

# @brief Optional operation-state file names that may be initialized on first page open.
_OPERATION_STATE_FILE_NAMES = {
    "extraction": config.EXTRACTION_STATE_FILE_NAME,
    "cleanup": config.CLEANUP_STATE_FILE_NAME,
    "chunking": config.CHUNKING_STATE_FILE_NAME,
    "translation": config.TRANSLATION_STATE_FILE_NAME,
    "character_discovery": config.CHARACTER_DISCOVERY_STATE_FILE_NAME,
    "speech_blocks": config.SPEECH_BLOCKS_STATE_FILE_NAME,
    "audio_blocks": config.AUDIO_BLOCKS_STATE_FILE_NAME,
    "audio_assembly": config.AUDIO_ASSEMBLY_STATE_FILE_NAME,
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
    @version    0.2.1
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
    @version    0.3.0
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


def default_operation_state(operation_kind: str) -> dict[str, object]:
    """
    @brief      Build one persisted default operation-state payload.
    @param[in]  operation_kind Stable workflow operation token.
    @return     Default operation-state payload.
    @exception  ValueError Raised when the operation kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    if operation_kind not in _OPERATION_ORDER:
        raise ValueError(f"Unsupported operation kind: {operation_kind}")
    return {
        "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        "status": "not_started",
        "input_paths": [],
        "output_paths": [],
        "artifact_paths": [],
        "progress_current": 0,
        "progress_total": 0,
        "mode": None,
        "started_at": None,
        "completed_at": None,
        "updated_at": None,
        "warning_count": 0,
        "metadata": _default_operation_metadata(operation_kind),
        "resume_checkpoint": None,
    }


def build_operation_state_payload(
    status: str,
    input_paths: list[str],
    output_paths: list[str],
    artifact_paths: list[str],
    progress_current: int,
    progress_total: int,
    mode: str,
    started_at: str | None,
    completed_at: str | None,
    warning_count: int,
    metadata: dict[str, object],
    resume_checkpoint: dict[str, object] | None,
    folder_relative_path: str = config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
    updated_at: str | None = None,
) -> dict[str, object]:
    """
    @brief      Build the shared operation-state envelope.
    @param[in]  status Persisted operation status token.
    @param[in]  input_paths Project-relative input artifact paths.
    @param[in]  output_paths Project-relative output artifact paths.
    @param[in]  artifact_paths Project-relative report, log, and sidecar artifact paths.
    @param[in]  progress_current Completed progress count.
    @param[in]  progress_total Total progress count.
    @param[in]  mode Operation execution mode token.
    @param[in]  started_at Optional operation start timestamp.
    @param[in]  completed_at Optional operation completion timestamp.
    @param[in]  warning_count Persisted warning count.
    @param[in]  metadata Workflow-specific metadata payload.
    @param[in]  resume_checkpoint Optional workflow-specific resume checkpoint.
    @param[in]  folder_relative_path Project-relative operation folder token.
    @param[in]  updated_at Optional state update timestamp override.
    @return     JSON-ready operation-state payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    return {
        "folder_relative_path": str(folder_relative_path),
        "status": str(status),
        "input_paths": list(input_paths),
        "output_paths": list(output_paths),
        "artifact_paths": list(artifact_paths),
        "progress_current": int(progress_current),
        "progress_total": int(progress_total),
        "mode": str(mode),
        "started_at": started_at,
        "completed_at": completed_at,
        "updated_at": updated_at or utc_now_iso(),
        "warning_count": int(warning_count),
        "metadata": dict(metadata),
        "resume_checkpoint": None if resume_checkpoint is None else dict(resume_checkpoint),
    }


def _default_operation_metadata(operation_kind: str) -> dict[str, object]:
    """
    @brief      Build operation-specific default metadata for first page access.
    @param[in]  operation_kind Stable workflow operation token.
    @return     Default metadata payload for the operation.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    if operation_kind == "character_discovery":
        return {
            "ai_profile_id": "",
            "source_chunk_count": 0,
            "character_count": 0,
            "analyzed_window_count": 0,
            "merged_candidate_count": 0,
            "window_size": 0,
            "window_overlap": 0,
            "warnings": [],
            "input_fingerprint": "",
            "log_relative_path": "",
            "token_usage": {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "usage_available": False,
            },
        }
    if operation_kind == "audio_blocks":
        return {
            "voice_language": "",
            "input_fingerprint": "",
            "speech_block_count": 0,
            "generated_block_count": 0,
            "approved_block_count": 0,
            "clone_profile_count": 0,
            "prompt_count": 0,
            "reused_prompt_count": 0,
            "regenerated_prompt_count": 0,
            "current_phase": "",
            "current_block_id": "",
            "model_id": "",
            "model_token_budget": 0,
            "model_audio_seconds_budget": 0.0,
        }
    return {}


def ensure_default_operation_state(project_root: str | Path, operation_kind: str) -> Path | None:
    """
    @brief      Create one default operation-state file if the workflow page has no state yet.
    @param[in]  project_root Active project root folder.
    @param[in]  operation_kind Stable workflow operation token.
    @return     Created or existing state path, or `None` when the operation has no state file.
    @exception  ValueError Raised when the operation kind is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.1
    """
    if operation_kind not in _OPERATION_ORDER:
        raise ValueError(f"Unsupported operation kind: {operation_kind}")
    state_file_name = _OPERATION_STATE_FILE_NAMES.get(operation_kind)
    if state_file_name is None:
        return None
    state_path = build_operation_output_path(project_root, operation_kind, state_file_name)
    if not state_path.is_file():
        write_json_atomic(state_path, default_operation_state(operation_kind))
    return state_path


def load_operation_state_payload(
    project_root: str | Path,
    operation_kind: str,
    state_file_name: str,
) -> dict[str, object] | None:
    """
    @brief      Load one optional operation-state payload from a root-level artifact file.
    @param[in]  project_root Active project root folder.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  state_file_name Operation-state artifact file name.
    @return     Persisted operation-state payload or `None`.
    @exception  OSError Raised when the state file cannot be read.
    @exception  json.JSONDecodeError Raised when the state file is not valid JSON.
    @exception  TypeError Raised when the state payload is not dictionary-compatible.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    state_path = resolve_operation_path(project_root, operation_kind, state_file_name)
    if not state_path.is_file():
        return None
    return dict(json.loads(state_path.read_text(encoding="utf-8")))


def load_operation_state_file(state_path: str | Path) -> dict[str, object] | None:
    """
    @brief      Load one optional operation-state payload from an exact path.
    @param[in]  state_path Candidate operation-state file path.
    @return     Persisted operation-state payload or `None`.
    @exception  OSError Raised when the state file cannot be read.
    @exception  json.JSONDecodeError Raised when the state file is not valid JSON.
    @exception  TypeError Raised when the state payload is not dictionary-compatible.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    payload = load_optional_json_artifact(state_path)
    if payload is None:
        return None
    return dict(payload)


def load_optional_json_artifact(artifact_path: str | Path) -> object | None:
    """
    @brief      Load one optional JSON artifact from an exact path.
    @param[in]  artifact_path Candidate JSON artifact path.
    @return     Parsed JSON payload or `None` when the artifact is missing.
    @exception  OSError Raised when the artifact cannot be read.
    @exception  json.JSONDecodeError Raised when the artifact is not valid JSON.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    resolved_path = Path(artifact_path)
    if not resolved_path.is_file():
        return None
    return json.loads(resolved_path.read_text(encoding="utf-8"))


def load_project_json_artifact(project_root: str | Path, file_name: str) -> object | None:
    """
    @brief      Load one optional root-level project JSON artifact.
    @param[in]  project_root Active project root folder.
    @param[in]  file_name Root-level artifact file name.
    @return     Parsed JSON payload or `None` for missing, unreadable, or malformed artifacts.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    try:
        return load_optional_json_artifact(Path(project_root) / file_name)
    except (OSError, json.JSONDecodeError):
        return None


def project_artifact_exists(project_root: str | Path, file_name: str) -> bool:
    """
    @brief      Return whether one root-level project artifact exists.
    @param[in]  project_root Active project root folder.
    @param[in]  file_name Root-level artifact file name.
    @return     True when the artifact exists.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    return (Path(project_root) / file_name).exists()


def project_text_artifact_has_content(project_root: str | Path, file_name: str) -> bool:
    """
    @brief      Return whether one root-level text artifact exists with non-empty content.
    @param[in]  project_root Active project root folder.
    @param[in]  file_name Root-level artifact file name.
    @return     True when the text artifact is present and non-empty.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    path = Path(project_root) / file_name
    try:
        return path.is_file() and bool(path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def write_operation_json_artifact(
    project_root: str | Path,
    operation_kind: str,
    file_name: str,
    payload: object,
) -> Path:
    """
    @brief      Persist one operation JSON artifact through the shared atomic writer.
    @param[in]  project_root Active project root folder.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  file_name Operation artifact file name.
    @param[in]  payload JSON-serializable artifact payload.
    @return     Final artifact path.
    @exception  TypeError Raised when the payload is not JSON-serializable.
    @exception  OSError Raised when the artifact cannot be written.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    output_path = build_operation_output_path(project_root, operation_kind, file_name)
    write_json_atomic(output_path, payload)
    return output_path


def relative_to_project(project_root: str | Path, artifact_path: str | Path) -> str:
    """
    @brief      Convert one project-local path into a manifest-relative string.
    @param[in]  project_root Active project root.
    @param[in]  artifact_path Absolute project-local artifact path.
    @return     POSIX-style project-relative string.
    @exception  ValueError Raised when the path is outside the project root.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    resolved_project_root = Path(project_root).resolve()
    resolved_artifact_path = Path(artifact_path).resolve()
    try:
        return resolved_artifact_path.relative_to(resolved_project_root).as_posix()
    except ValueError as exc:
        raise ValueError("Artifact path is outside the active project.") from exc


def is_path_inside_project(project_root: str | Path, candidate_path: str | Path) -> bool:
    """
    @brief      Return whether one candidate path is equal to or below the project root.
    @param[in]  project_root Active project root folder.
    @param[in]  candidate_path Candidate filesystem path.
    @return     True when the resolved candidate path is inside the project root.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    resolved_project_root = Path(project_root).resolve()
    resolved_candidate_path = Path(candidate_path).resolve()
    try:
        resolved_candidate_path.relative_to(resolved_project_root)
    except ValueError:
        return False
    return True


def validate_project_relative_path(relative_path: str | Path) -> str:
    """
    @brief      Normalize one manifest project-relative path and reject unsafe forms.
    @param[in]  relative_path Candidate project-relative path value.
    @return     POSIX-style project-relative path.
    @exception  ValueError Raised when the path is empty, absolute, or contains parent traversal.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    normalized_text = str(relative_path).strip()
    if not normalized_text:
        raise ValueError("Project-relative path is empty.")
    candidate = Path(normalized_text)
    windows_candidate = PureWindowsPath(normalized_text)
    if (
        candidate.is_absolute()
        or candidate.drive
        or candidate.root
        or windows_candidate.is_absolute()
        or windows_candidate.drive
        or windows_candidate.root
    ):
        raise ValueError("Project-relative path must not be absolute.")
    if ".." in candidate.parts or ".." in windows_candidate.parts:
        raise ValueError("Project-relative path must not contain parent traversal.")
    return normalized_text.replace("\\", "/")


def resolve_project_relative_path(project_root: str | Path, relative_path: str | Path) -> Path:
    """
    @brief      Resolve one trusted project-relative path under the active project root.
    @param[in]  project_root Active project root folder.
    @param[in]  relative_path Candidate project-relative path value.
    @return     Resolved absolute path below the project root.
    @exception  ValueError Raised when the path escapes the active project.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    safe_relative_path = validate_project_relative_path(relative_path)
    resolved_project_root = Path(project_root).resolve()
    resolved_candidate = (resolved_project_root / safe_relative_path).resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_project_root)
    except ValueError as exc:
        raise ValueError("Project-relative path resolves outside the active project.") from exc
    return resolved_candidate


def try_resolve_project_relative_path(project_root: str | Path, relative_path: object) -> Path | None:
    """
    @brief      Resolve a persisted project-relative path and return `None` when unsafe.
    @param[in]  project_root Active project root folder.
    @param[in]  relative_path Candidate persisted project-relative path.
    @return     Resolved project-local path or `None` for missing or invalid input.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    normalized_relative_path = optional_string(relative_path)
    if not normalized_relative_path:
        return None
    try:
        return resolve_project_relative_path(project_root, normalized_relative_path)
    except (OSError, ValueError):
        return None


def project_relative_path_exists(project_root: str | Path, relative_path: str | Path) -> bool:
    """
    @brief      Return whether one safe project-relative path exists below the project root.
    @param[in]  project_root Active project root folder.
    @param[in]  relative_path Candidate project-relative path value.
    @return     True when the resolved path stays below the project root and exists.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    try:
        return resolve_project_relative_path(project_root, relative_path).exists()
    except (OSError, ValueError):
        return False


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


def emit_progress_update(
    progress_callback,
    progress_current: int,
    progress_total: int,
    message: str,
    token_usage: dict[str, object] | None = None,
    *,
    include_token_usage: bool = True,
) -> None:
    """
    @brief      Emit one standardized workflow progress callback payload.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  progress_current Completed work-unit count.
    @param[in]  progress_total Total work-unit count.
    @param[in]  message Operator-facing progress text.
    @param[in]  token_usage Optional token-usage payload.
    @param[in]  include_token_usage True when the callback accepts a token-usage argument.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.2.0
    """
    if callable(progress_callback):
        percent_value = progress_percent(progress_current, progress_total)
        if include_token_usage:
            progress_callback(progress_current, progress_total, percent_value, message, token_usage)
        else:
            progress_callback(progress_current, progress_total, percent_value, message)


def optional_string(value: object, *, strip: bool = True) -> str | None:
    """
    @brief      Normalize one optional persisted string value.
    @param[in]  value Candidate optional value.
    @param[in]  strip True to trim leading and trailing whitespace.
    @return     Normalized string or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    if value in (None, ""):
        return None
    normalized_value = str(value)
    if strip:
        normalized_value = normalized_value.strip()
    return normalized_value or None


def is_missing_runtime_value(value: object) -> bool:
    """
    @brief      Return whether one persisted runtime value is missing or null-like.
    @param[in]  value Candidate runtime value.
    @return     True when the value represents a missing runtime field.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    return str(value).strip().casefold() in {"", "none", "null"}


def valid_runtime_value(value: object) -> str:
    """
    @brief      Return one persisted runtime value unless it is null-like.
    @param[in]  value Candidate runtime value.
    @return     String value or an empty string for null-like values.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    text = str(value).strip() if value is not None else ""
    return "" if is_missing_runtime_value(text) else text


def reset_operation_data(
    project_root: str | Path,
    operation_kind: str,
    include_current: bool = True,
    keep_input_snapshots: bool = False,
    preserve_operation_kinds: Iterable[str] | None = None,
) -> None:
    """
    @brief      Clear one workflow step and optional downstream root-level runtime artifacts.
    @param[in]  project_root Active project root.
    @param[in]  operation_kind Selected workflow operation token.
    @param[in]  include_current True to clear the selected operation folder too.
    @param[in]  keep_input_snapshots Ignored; input snapshots are no longer created.
    @param[in]  preserve_operation_kinds Optional operation kinds excluded from clearing.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.3.0
    """
    _ = keep_input_snapshots
    preserved_operation_kinds = _normalized_operation_kind_set(preserve_operation_kinds)
    operation_kinds = downstream_operation_kinds(
        operation_kind,
        include_current=include_current,
    )
    root_path = Path(project_root)
    for selected_kind in operation_kinds:
        if selected_kind in preserved_operation_kinds:
            continue
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
        if selected_kind == "audio_assembly":
            audiobook_root = root_path / config.AUDIOBOOK_OUTPUT_FOLDER_NAME
            if audiobook_root.is_dir():
                for child in audiobook_root.rglob("*"):
                    if child.is_file():
                        child.unlink()


def _normalized_operation_kind_set(operation_kinds: Iterable[str] | None) -> frozenset[str]:
    """
    @brief      Normalize optional operation-kind preservation input.
    @param[in]  operation_kinds Optional operation-kind iterable.
    @return     Clean operation-kind set.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    if operation_kinds is None:
        return frozenset()
    return frozenset(str(operation_kind).strip() for operation_kind in operation_kinds if str(operation_kind).strip())


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
