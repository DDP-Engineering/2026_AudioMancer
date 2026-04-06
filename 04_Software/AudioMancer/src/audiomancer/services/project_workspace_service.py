#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file project_workspace_service.py
@brief Functional project workspace persistence helpers for AudioMancer.
@details Creates, validates, saves, and opens file-based project workspaces
         using one minimal `project.json` manifest contract.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.4.0
"""

# IMPORTS

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function

# CONSTANTS

_PROJECT_WORKSPACE_LOGGER = get_component_logger("project_workspace")
ProjectManifestPayload = dict[str, object]
ProjectOpenResult = dict[str, object]
_STEP_FOLDERS_IN_ORDER = tuple(config.PROJECT_REQUIRED_SUBDIRECTORIES[:-1])


# PUBLIC API


@trace_function(_PROJECT_WORKSPACE_LOGGER)
def validate_project_name(name: str) -> None:
    """
    @brief      Validate one project name for cross-platform folder safety.
    @param[in]  name Candidate exact folder name entered by the operator.
    @return     None.
    @exception  ValueError Raised when the name is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not name or not name.strip():
        raise ValueError("Project name cannot be empty.")
    if name in config.LINUX_RESERVED_DIRECTORY_NAMES:
        raise ValueError(
            "Project name cannot be '.' or '..'."
        )
    if any(character in config.INVALID_PROJECT_NAME_CHARACTERS for character in name):
        raise ValueError(
            "Project name contains unsupported folder characters."
        )
    if any(ord(character) < 32 for character in name):
        raise ValueError(
            "Project name contains unsupported control characters."
        )
    if name.endswith((" ", ".")):
        raise ValueError(
            "Project name cannot end with a space or dot."
        )

    normalized_upper = name.strip().upper()
    reserved_base = normalized_upper.split(".", maxsplit=1)[0]
    if reserved_base in config.WINDOWS_RESERVED_DIRECTORY_NAMES:
        raise ValueError(
            "Project name uses a reserved Windows device name."
        )


@trace_function(_PROJECT_WORKSPACE_LOGGER)
def create_project(
    name: str,
    parent_path: str | Path,
) -> tuple[Path, ProjectManifestPayload]:
    """
    @brief      Create a new project workspace and initial manifest.
    @param[in]  name Operator-facing project name and folder name.
    @param[in]  parent_path Existing parent directory selected by the operator.
    @return     Tuple of created project root path and manifest payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    validate_project_name(name)
    resolved_parent = Path(parent_path)
    if not resolved_parent.is_dir():
        raise FileNotFoundError(f"Project parent folder was not found: {resolved_parent}")

    project_root = resolved_parent / name
    if project_root.exists() and any(project_root.iterdir()):
        raise FileExistsError(f"Project folder is not empty: {project_root}")

    project_root.mkdir(parents=True, exist_ok=True)
    for folder_name in config.PROJECT_REQUIRED_SUBDIRECTORIES:
        (project_root / folder_name).mkdir(parents=True, exist_ok=True)

    now_iso = _utc_now_iso()
    manifest = build_project_manifest(name, now_iso)
    save_manifest(manifest, project_root)
    return project_root, manifest


@trace_function(_PROJECT_WORKSPACE_LOGGER)
def save_manifest(
    manifest: ProjectManifestPayload,
    project_root: str | Path,
) -> None:
    """
    @brief      Persist the current project manifest into `project.json`.
    @param[in,out] manifest Manifest payload updated with a fresh timestamp.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    normalized_manifest = validate_project_manifest(manifest)
    normalized_manifest["updated_at"] = _utc_now_iso()
    manifest_path = Path(project_root) / config.PROJECT_MANIFEST_FILE_NAME
    manifest_path.write_text(
        json.dumps(normalized_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


@trace_function(_PROJECT_WORKSPACE_LOGGER)
def resolve_project_root(selected_path: str | Path) -> Path:
    """
    @brief      Resolve the project root from a selected root or child folder.
    @param[in]  selected_path Folder path selected by the operator.
    @return     Resolved project root path.
    @exception  FileNotFoundError Raised when no project root can be resolved.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    current_path = Path(selected_path)
    if not current_path.exists():
        raise FileNotFoundError(f"Selected project folder was not found: {current_path}")

    if current_path.is_file():
        current_path = current_path.parent

    for candidate in (current_path, *current_path.parents):
        if (candidate / config.PROJECT_MANIFEST_FILE_NAME).is_file():
            return candidate

    raise FileNotFoundError(
        f"No {config.PROJECT_MANIFEST_FILE_NAME} was found in the selected folder hierarchy."
    )


@trace_function(_PROJECT_WORKSPACE_LOGGER)
def validate_project(project_root: str | Path) -> ProjectOpenResult:
    """
    @brief      Validate one project folder structure and minimal manifest data.
    @param[in]  project_root Resolved candidate project root folder.
    @return     Tagged project validation result dictionary.
    @exception  FileNotFoundError Raised when required files or folders are missing.
    @exception  ValueError Raised when required manifest fields are invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.3.0
    """
    resolved_root = Path(project_root)
    manifest_path = resolved_root / config.PROJECT_MANIFEST_FILE_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Project manifest file was not found: {manifest_path}"
        )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest_identity_fields(payload)
    first_missing_directory = _first_missing_required_directory(resolved_root)
    if first_missing_directory is not None:
        return {
            "status": "repair_required",
            "project_root": resolved_root,
            "corrupted_step": first_missing_directory,
            "reset_stage": _repair_stage_for_folder(first_missing_directory, payload),
            "message": (
                "Project structure is incomplete. "
                f"The step folder '{first_missing_directory}' is missing."
            ),
            "metadata_only": False,
        }
    if _is_invalid_current_stage(payload):
        return {
            "status": "repair_required",
            "project_root": resolved_root,
            "corrupted_step": "metadata.current_stage",
            "reset_stage": _derive_consistent_stage(payload, resolved_root),
            "message": "Project metadata is inconsistent. The current stage must be repaired.",
            "metadata_only": True,
        }
    return {
        "status": "ok",
        "project_root": resolved_root,
        "manifest": validate_project_manifest(payload),
    }


@trace_function(_PROJECT_WORKSPACE_LOGGER)
def load_manifest(project_root: str | Path) -> ProjectManifestPayload:
    """
    @brief      Load one validated project manifest from disk.
    @param[in]  project_root Resolved project root folder.
    @return     Loaded project manifest payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """
    manifest_path = Path(project_root) / config.PROJECT_MANIFEST_FILE_NAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return validate_project_manifest(payload)


@trace_function(_PROJECT_WORKSPACE_LOGGER)
def open_project(
    selected_path: str | Path,
) -> ProjectOpenResult:
    """
    @brief      Open an existing project from its root or one child folder.
    @param[in]  selected_path Folder path selected by the operator.
    @return     Tagged project-open result dictionary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    project_root = resolve_project_root(selected_path)
    return validate_project(project_root)


@trace_function(_PROJECT_WORKSPACE_LOGGER)
def repair_project(
    repair_request: dict[str, object],
) -> ProjectOpenResult:
    """
    @brief      Repair one recoverable project corruption and reopen the project.
    @param[in]  repair_request Tagged repair-required result dictionary.
    @return     Tagged repaired project-open result dictionary.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    project_root = Path(str(repair_request["project_root"]))
    manifest_path = project_root / config.PROJECT_MANIFEST_FILE_NAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest_identity_fields(payload)

    if not bool(repair_request.get("metadata_only", False)):
        for folder_name in _folders_to_reset_from(
            str(repair_request["corrupted_step"])
        ):
            folder_path = project_root / folder_name
            if folder_path.exists():
                shutil.rmtree(folder_path)
            folder_path.mkdir(parents=True, exist_ok=True)

    repaired_manifest = _build_repaired_manifest(
        payload,
        str(repair_request["reset_stage"]),
    )
    save_manifest(repaired_manifest, project_root)
    return {
        "status": "ok",
        "project_root": project_root,
        "manifest": load_manifest(project_root),
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


@trace_function(_PROJECT_WORKSPACE_LOGGER)
def build_project_manifest(
    display_name: str,
    timestamp_iso: str | None = None,
) -> ProjectManifestPayload:
    """
    @brief      Build the minimal manifest payload for one new project.
    @param[in]  display_name Operator-facing project name.
    @param[in]  timestamp_iso Optional shared creation timestamp.
    @return     New normalized manifest payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    resolved_timestamp = timestamp_iso or _utc_now_iso()
    return {
        "project_id": str(uuid4()),
        "display_name": display_name,
        "created_at": resolved_timestamp,
        "updated_at": resolved_timestamp,
        "current_stage": config.DEFAULT_WORKFLOW_STAGE,
        "source_document_name": None,
        "narrator_profile_name": None,
        "narrator_language": None,
        "notes": "",
    }


@trace_function(_PROJECT_WORKSPACE_LOGGER)
def validate_project_manifest(payload: object) -> ProjectManifestPayload:
    """
    @brief      Normalize and validate one `project.json` payload.
    @param[in]  payload Raw parsed manifest payload.
    @return     Normalized manifest dictionary.
    @exception  ValueError Raised when the payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    _validate_manifest_payload(payload)
    assert isinstance(payload, dict)
    current_stage = str(payload.get("current_stage", config.DEFAULT_WORKFLOW_STAGE))
    if current_stage not in config.PROJECT_WORKFLOW_STAGES:
        current_stage = config.DEFAULT_WORKFLOW_STAGE
    return {
        "project_id": str(payload["project_id"]),
        "display_name": str(payload["display_name"]),
        "created_at": str(payload["created_at"]),
        "updated_at": str(payload["updated_at"]),
        "current_stage": current_stage,
        "source_document_name": _optional_string(payload.get("source_document_name")),
        "narrator_profile_name": _optional_string(
            payload.get("narrator_profile_name")
        ),
        "narrator_language": _optional_string(payload.get("narrator_language")),
        "notes": str(payload.get("notes", "")),
    }


def _validate_manifest_payload(payload: object) -> None:
    """
    @brief      Validate the minimal JSON payload contract for `project.json`.
    @param[in]  payload Raw parsed JSON value.
    @return     None.
    @exception  ValueError Raised when the payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    _validate_manifest_identity_fields(payload)
    assert isinstance(payload, dict)
    current_stage = payload.get("current_stage")
    if not isinstance(current_stage, str) or not current_stage.strip():
        raise ValueError(
            "Project manifest field 'current_stage' is missing or invalid."
        )

    if str(payload["current_stage"]) not in config.PROJECT_WORKFLOW_STAGES:
        raise ValueError("Project manifest field 'current_stage' is unsupported.")


def _validate_manifest_identity_fields(payload: object) -> None:
    """
    @brief      Validate the non-repairable minimal manifest identity fields.
    @param[in]  payload Raw parsed JSON value.
    @return     None.
    @exception  ValueError Raised when the payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if not isinstance(payload, dict):
        raise ValueError("Project manifest payload must be a JSON object.")
    for field_name in ("project_id", "display_name", "created_at", "updated_at"):
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Project manifest field '{field_name}' is missing or invalid."
            )


def _first_missing_required_directory(project_root: Path) -> str | None:
    """
    @brief      Return the first missing workflow folder in stable step order.
    @param[in]  project_root Candidate project root folder.
    @return     Missing folder name or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    for folder_name in config.PROJECT_REQUIRED_SUBDIRECTORIES:
        if not (project_root / folder_name).is_dir():
            return folder_name
    return None


def _repair_stage_for_folder(folder_name: str, payload: dict[str, object]) -> str:
    """
    @brief      Resolve the stage token to keep after one folder-based repair.
    @param[in]  folder_name Corrupted step folder name.
    @param[in]  payload Parsed manifest payload.
    @return     Conservatively trusted stage token that remains valid after repair.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    _ = folder_name
    return _derive_trustworthy_stage(payload)


def _is_invalid_current_stage(payload: dict[str, object]) -> bool:
    """
    @brief      Determine whether the manifest current stage is repairable metadata.
    @param[in]  payload Parsed manifest payload.
    @return     True when the current stage is missing or unsupported.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    current_stage = payload.get("current_stage")
    return (
        not isinstance(current_stage, str)
        or not current_stage.strip()
        or current_stage not in config.PROJECT_WORKFLOW_STAGES
    )


def _derive_consistent_stage(
    payload: dict[str, object],
    project_root: Path,
) -> str:
    """
    @brief      Derive the highest current-stage token still consistent with the project.
    @param[in]  payload Parsed manifest payload.
    @param[in]  project_root Candidate project root folder.
    @return     Conservatively trusted stage token for repaired metadata.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    _ = project_root
    return _derive_trustworthy_stage(payload)


def _folders_to_reset_from(corrupted_step: str) -> tuple[str, ...]:
    """
    @brief      Build the ordered folder list to recreate from one corrupted step.
    @param[in]  corrupted_step Corrupted step folder name.
    @return     Tuple of affected folder names in reset order.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if corrupted_step not in _STEP_FOLDERS_IN_ORDER:
        return tuple()
    start_index = _STEP_FOLDERS_IN_ORDER.index(corrupted_step)
    return _STEP_FOLDERS_IN_ORDER[start_index:]


def _build_repaired_manifest(
    payload: dict[str, object],
    reset_stage: str,
) -> ProjectManifestPayload:
    """
    @brief      Build one normalized manifest payload after a repair action.
    @param[in]  payload Parsed manifest payload before repair.
    @param[in]  reset_stage Stage token to keep after repair.
    @return     Repaired manifest payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    repaired_manifest = {
        "project_id": str(payload["project_id"]),
        "display_name": str(payload["display_name"]),
        "created_at": str(payload["created_at"]),
        "updated_at": str(payload["updated_at"]),
        "current_stage": (
            reset_stage
            if reset_stage in config.PROJECT_WORKFLOW_STAGES
            else config.DEFAULT_WORKFLOW_STAGE
        ),
        "source_document_name": _optional_string(payload.get("source_document_name")),
        "narrator_profile_name": _optional_string(
            payload.get("narrator_profile_name")
        ),
        "narrator_language": _optional_string(payload.get("narrator_language")),
        "notes": str(payload.get("notes", "")),
    }
    if _stage_rank(str(repaired_manifest["current_stage"])) < _stage_rank(
        "narrator_definition_ready"
    ):
        repaired_manifest["narrator_profile_name"] = None
        repaired_manifest["narrator_language"] = None
    return repaired_manifest


def _derive_trustworthy_stage(payload: dict[str, object]) -> str:
    """
    @brief      Derive the highest workflow stage justified by current manifest metadata.
    @param[in]  payload Parsed manifest payload.
    @return     Conservatively trusted stage token.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if _optional_string(payload.get("source_document_name")) is not None:
        return "source_selected"
    return config.DEFAULT_WORKFLOW_STAGE


def _stage_rank(stage_token: str) -> int:
    """
    @brief      Convert one stage token into a sortable order index.
    @param[in]  stage_token Stage token to resolve.
    @return     Zero-based stage order index.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if stage_token not in config.PROJECT_WORKFLOW_STAGES:
        return -1
    return config.PROJECT_WORKFLOW_STAGES.index(stage_token)


def _optional_string(value: object) -> str | None:
    """
    @brief      Normalize one optional string manifest field.
    @param[in]  value Raw decoded JSON value.
    @return     Normalized string or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    if value in (None, ""):
        return None
    return str(value)


# END OF FILE
