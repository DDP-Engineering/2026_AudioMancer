#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
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
         using one minimal root-level `project.json` manifest contract.
@author Eng. Dan Dumitru Pasare
@date 2026-04-20
@version    2.0.6
"""

# IMPORTS

from functools import partial
import json
from pathlib import Path
from uuid import uuid4

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    load_project_json_artifact as _load_json_artifact,
)
from audiomancer.services.operation_runtime_service import (
    optional_string as _shared_optional_string,
)
from audiomancer.services.operation_runtime_service import (
    project_artifact_exists as _artifact_exists,
)
from audiomancer.services.operation_runtime_service import (
    project_relative_path_exists,
    resolve_project_relative_path,
    validate_project_relative_path,
)
from audiomancer.services.operation_runtime_service import (
    project_text_artifact_has_content as _text_artifact_has_content,
)
from audiomancer.services.persistence_service import write_json_atomic
from audiomancer.services.time_service import utc_now_iso as _utc_now_iso

# CONSTANTS

# @brief Component logger used by project workspace lifecycle helpers.
_PROJECT_WORKSPACE_LOGGER = get_component_logger("project_workspace")
# @brief Manifest optional strings preserve existing whitespace semantics while dropping null-like text.
_raw_optional_string = partial(_shared_optional_string, strip=False)
# @brief Canonical project-manifest payload type persisted in `project.json`.
ProjectManifestPayload = dict[str, object]
# @brief Normalized project-open result payload returned by open helpers.
ProjectOpenResult = dict[str, object]
# @brief Old numbered workflow folders rejected by the flattened project layout.
_UNSUPPORTED_LEGACY_WORKFLOW_FOLDERS = (
    "00_extraction",
    "10_cleanup",
    "20_chunking",
    "30_translation",
    "40_character_discovery",
    "50_narrator_definition",
    "60_character_voices",
    "70_speech_blocks",
    "80_audio_blocks",
    "90_audio_assembly",
)
# @brief Workflow milestone promoted by each completed operation.
_OPERATION_STAGE_BY_KIND = {
    "cleanup": "text_cleanup_ready",
    "chunking": "text_chunking_ready",
    "translation": "translation_ready",
    "character_discovery": "character_discovery_ready",
    "narrator_definition": "narrator_definition_ready",
    "character_voices": "character_voices_ready",
    "speech_blocks": "speech_blocks_ready",
    "audio_blocks": "audio_blocks_ready",
    "audio_assembly": "audio_assembly_ready",
}
# @brief Ordered operation kinds that can be verified from local artifacts.
_HEALABLE_OPERATION_ORDER = (
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
        @version    0.3.0
    """
    if not name or not name.strip():
        raise ValueError("Project name cannot be empty.")
    if name in config.LINUX_RESERVED_DIRECTORY_NAMES:
        raise ValueError("Project name cannot be '.' or '..'.")
    if any(character in config.INVALID_PROJECT_NAME_CHARACTERS for character in name):
        raise ValueError("Project name contains unsupported folder characters.")
    if any(ord(character) < 32 for character in name):
        raise ValueError("Project name contains unsupported control characters.")
    if name.endswith((" ", ".")):
        raise ValueError("Project name cannot end with a space or dot.")

    normalized_upper = name.strip().upper()
    reserved_base = normalized_upper.split(".", maxsplit=1)[0]
    if reserved_base in config.WINDOWS_RESERVED_DIRECTORY_NAMES:
        raise ValueError("Project name uses a reserved Windows device name.")


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
        @version    0.5.0
    """
    validate_project_name(name)
    resolved_parent = Path(parent_path)
    if not resolved_parent.is_dir():
        raise FileNotFoundError(f"Project parent folder was not found: {resolved_parent}")

    project_root = resolved_parent / name
    if project_root.exists() and any(project_root.iterdir()):
        raise FileExistsError(f"Project folder is not empty: {project_root}")

    project_root.mkdir(parents=True, exist_ok=True)

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
    @version    0.3.1
    """
    normalized_manifest = validate_project_manifest(manifest)
    normalized_manifest["updated_at"] = _utc_now_iso()
    resolved_project_root = Path(project_root)
    _validate_project_scoped_manifest_paths(normalized_manifest, resolved_project_root)
    manifest_path = resolved_project_root / config.PROJECT_MANIFEST_FILE_NAME
    write_json_atomic(manifest_path, normalized_manifest)


@trace_function(_PROJECT_WORKSPACE_LOGGER)
def lock_project_options(
    project_root: str | Path,
    target_language: str,
    voice_assignment_mode: str,
) -> ProjectManifestPayload:
    """
    @brief      Persist the immutable project-level audiobook options.
    @param[in]  project_root Active project root folder.
    @param[in]  target_language Selected audiobook translation and voice language code.
    @param[in]  voice_assignment_mode Selected narration mode.
    @return     Updated project manifest payload.
    @exception  ValueError Raised when options are invalid or already locked.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    manifest = load_manifest(project_root)
    if bool(manifest.get("project_options_locked", False)):
        raise ValueError("Project options are already locked for this project.")
    normalized_target_language = _normalize_target_language(target_language)
    normalized_voice_assignment_mode = str(voice_assignment_mode).strip()
    if normalized_voice_assignment_mode not in config.TTS_VOICE_ASSIGNMENT_MODE_OPTIONS:
        raise ValueError("Project narration mode is invalid.")
    manifest["target_language"] = normalized_target_language
    manifest["selected_voice_language"] = normalized_target_language
    manifest["voice_assignment_mode"] = normalized_voice_assignment_mode
    manifest["project_options_locked"] = True
    save_manifest(manifest, project_root)
    return load_manifest(project_root)


@trace_function(_PROJECT_WORKSPACE_LOGGER)
def resolve_project_root(selected_path: str | Path) -> Path:
    """
    @brief      Resolve the project root from a selected root or child folder.
    @param[in]  selected_path Folder path selected by the operator.
    @return     Resolved project root path.
    @exception  FileNotFoundError Raised when no project root can be resolved.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    current_path = Path(selected_path)
    if not current_path.exists():
        raise FileNotFoundError(f"Selected project folder was not found: {current_path}")

    if current_path.is_file():
        current_path = current_path.parent

    for candidate in (current_path, *current_path.parents):
        if (candidate / config.PROJECT_MANIFEST_FILE_NAME).is_file():
            return candidate

    raise FileNotFoundError(f"No {config.PROJECT_MANIFEST_FILE_NAME} was found in the selected folder hierarchy.")


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
    @version    0.6.0
    """
    resolved_root = Path(project_root)
    manifest_path = resolved_root / config.PROJECT_MANIFEST_FILE_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Project manifest file was not found: {manifest_path}")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest_identity_fields(payload)
    _validate_project_scoped_manifest_paths(payload, resolved_root)
    legacy_folder = _first_unsupported_legacy_directory(resolved_root)
    if legacy_folder is not None:
        raise ValueError(
            f"Project uses the unsupported legacy numbered runtime layout: {legacy_folder}. "
            "Create a new flattened project; migration is not supported."
        )
    repair_result = _build_project_manifest_healing_result(payload, resolved_root)
    if repair_result is not None:
        return repair_result

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
    @version    0.2.0
    """
    resolved_project_root = Path(project_root)
    manifest_path = resolved_project_root / config.PROJECT_MANIFEST_FILE_NAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest_identity_fields(payload)
    _validate_project_scoped_manifest_paths(payload, resolved_project_root)
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
    @version    0.3.0
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
    @version    0.3.0
    """
    project_root = Path(str(repair_request["project_root"]))
    manifest_path = project_root / config.PROJECT_MANIFEST_FILE_NAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest_identity_fields(payload)

    if not bool(repair_request.get("metadata_only", False)):
        raise ValueError("Folder-based project repair is not supported by the flattened project layout.")

    normalized_manifest = repair_request.get("normalized_manifest")
    if isinstance(normalized_manifest, dict):
        repaired_manifest = validate_project_manifest(normalized_manifest)
    else:
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
    @date       2026-04-18
    @version    0.8.0
    """
    resolved_timestamp = timestamp_iso or _utc_now_iso()
    return {
        "project_id": str(uuid4()),
        "display_name": display_name,
        "created_at": resolved_timestamp,
        "updated_at": resolved_timestamp,
        "current_stage": config.DEFAULT_WORKFLOW_STAGE,
        "source_document": None,
        "extracted_text_relative_path": None,
        "extraction_report_relative_path": None,
        "extraction_warning_count": 0,
        "operations": _build_default_operation_states(),
        "project_options_locked": False,
        "target_language": config.DEFAULT_TRANSLATION_TARGET_LANGUAGE,
        "original_language": None,
        "narrator_profile_name": None,
        "narrator_language": None,
        "selected_voice_language": None,
        "voice_assignment_mode": config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE,
        "audio_assembly_settings": _default_audio_assembly_settings(),
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
    @date       2026-04-18
    @version    0.7.0
    """
    _validate_manifest_payload(payload)
    assert isinstance(payload, dict)
    current_stage = str(payload.get("current_stage", config.DEFAULT_WORKFLOW_STAGE))
    if current_stage not in config.PROJECT_WORKFLOW_STAGES:
        current_stage = config.DEFAULT_WORKFLOW_STAGE
    voice_assignment_mode = str(payload.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)).strip()
    if voice_assignment_mode not in config.TTS_VOICE_ASSIGNMENT_MODE_OPTIONS:
        voice_assignment_mode = config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE
    target_language = _normalize_target_language(
        payload.get("target_language", config.DEFAULT_TRANSLATION_TARGET_LANGUAGE)
    )
    project_options_locked = bool(payload.get("project_options_locked", False))
    selected_voice_language = _optional_string(payload.get("selected_voice_language"))
    if project_options_locked:
        selected_voice_language = target_language
    return {
        "project_id": str(payload["project_id"]),
        "display_name": str(payload["display_name"]),
        "created_at": str(payload["created_at"]),
        "updated_at": str(payload["updated_at"]),
        "current_stage": current_stage,
        "source_document": _normalize_source_document(payload.get("source_document")),
        "extracted_text_relative_path": _optional_string(payload.get("extracted_text_relative_path")),
        "extraction_report_relative_path": _optional_string(payload.get("extraction_report_relative_path")),
        "extraction_warning_count": _non_negative_int(payload.get("extraction_warning_count", 0)),
        "operations": _normalize_operations(payload.get("operations")),
        "project_options_locked": project_options_locked,
        "target_language": target_language,
        "original_language": _optional_string(payload.get("original_language")),
        "narrator_profile_name": _optional_string(payload.get("narrator_profile_name")),
        "narrator_language": _optional_string(payload.get("narrator_language")),
        "selected_voice_language": selected_voice_language,
        "voice_assignment_mode": voice_assignment_mode,
        "audio_assembly_settings": _normalize_audio_assembly_settings(payload.get("audio_assembly_settings")),
        "notes": str(payload.get("notes", "")),
    }


def project_manifest_operation_summary(
    operation_kind: str,
    operation_payload: object | None = None,
) -> dict[str, object]:
    """
    @brief      Project one detailed operation payload into the compact manifest summary shape.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  operation_payload Candidate detailed or compact operation payload.
    @return     Compact operation summary payload for `project.json`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.1.1
    """
    default_summary = _default_operation_state(operation_kind)
    if not isinstance(operation_payload, dict):
        return default_summary
    return {
        "folder_relative_path": str(
            operation_payload.get(
                "folder_relative_path",
                default_summary["folder_relative_path"],
            )
        ),
        "status": str(operation_payload.get("status", default_summary["status"])),
        "progress_current": _non_negative_int(
            operation_payload.get(
                "progress_current",
                default_summary["progress_current"],
            )
        ),
        "progress_total": _non_negative_int(
            operation_payload.get(
                "progress_total",
                default_summary["progress_total"],
            )
        ),
        "mode": _optional_string(operation_payload.get("mode")),
        "started_at": _optional_string(operation_payload.get("started_at")),
        "completed_at": _optional_string(operation_payload.get("completed_at")),
        "updated_at": _optional_string(operation_payload.get("updated_at")),
        "warning_count": _non_negative_int(
            operation_payload.get(
                "warning_count",
                default_summary["warning_count"],
            )
        ),
    }


def sync_manifest_operation_summary(
    project_root: str | Path,
    operation_kind: str,
    operation_payload: object | None,
    current_stage: str | None = None,
    extra_fields: dict[str, object] | None = None,
) -> ProjectManifestPayload:
    """
    @brief      Persist one backend operation summary directly into `project.json`.
    @param[in]  project_root Active project root folder.
    @param[in]  operation_kind Stable workflow operation token.
    @param[in]  operation_payload Candidate operation-state payload.
    @param[in]  current_stage Optional workflow stage to persist with the summary.
    @param[in]  extra_fields Optional additional manifest fields to merge.
    @return     Reloaded project manifest payload.
    @exception  ValueError Raised when the operation kind or stage is unsupported.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-10
    @version    0.1.0
    """
    manifest = load_manifest(project_root)
    operations = _normalize_operations(manifest.get("operations"))
    if operation_kind not in operations:
        raise ValueError(f"Unsupported operation kind: {operation_kind}")
    operations[operation_kind] = project_manifest_operation_summary(operation_kind, operation_payload)
    manifest["operations"] = operations
    if current_stage is not None:
        normalized_stage = str(current_stage).strip()
        if normalized_stage not in config.PROJECT_WORKFLOW_STAGES:
            raise ValueError(f"Unsupported workflow stage: {current_stage}")
        manifest["current_stage"] = normalized_stage
    if isinstance(extra_fields, dict):
        for field_name, field_value in extra_fields.items():
            manifest[str(field_name)] = field_value
    save_manifest(manifest, project_root)
    return load_manifest(project_root)


def _build_project_manifest_healing_result(
    payload: dict[str, object],
    project_root: Path,
) -> ProjectOpenResult | None:
    """
    @brief      Build one optional metadata-only project-manifest healing report.
    @param[in]  payload Parsed project manifest payload.
    @param[in]  project_root Active project root folder.
    @return     Repair-required result payload or `None` when no repair is needed.
    @exception  ValueError Raised when non-repairable manifest fields are invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    current_stage_is_invalid = _is_invalid_current_stage(payload)
    base_stage = (
        _derive_consistent_stage(payload, project_root) if current_stage_is_invalid else str(payload["current_stage"])
    )
    if current_stage_is_invalid:
        candidate_manifest = _build_repaired_manifest(payload, base_stage)
    else:
        candidate_manifest = validate_project_manifest(payload)

    changes: list[str] = []
    warnings: list[str] = []
    verified_stage = _verified_source_stage(candidate_manifest, project_root)
    contiguous = verified_stage == "source_selected"

    for operation_kind in _HEALABLE_OPERATION_ORDER:
        evidence = _operation_completion_evidence(project_root, operation_kind, warnings)
        if evidence is None:
            contiguous = False
            continue
        _heal_operation_summary(candidate_manifest, operation_kind, evidence, changes)
        if operation_kind == "extraction":
            _heal_extraction_manifest_fields(candidate_manifest, evidence, changes)
        elif operation_kind == "narrator_definition":
            _heal_narrator_manifest_fields(candidate_manifest, evidence, changes)
        elif operation_kind == "character_voices":
            _heal_character_voice_manifest_fields(candidate_manifest, evidence, changes)
        if contiguous and operation_kind in _OPERATION_STAGE_BY_KIND:
            verified_stage = _OPERATION_STAGE_BY_KIND[operation_kind]
        elif operation_kind != "extraction":
            contiguous = False

    existing_stage = str(payload.get("current_stage", config.DEFAULT_WORKFLOW_STAGE))
    target_stage = max(base_stage, verified_stage, key=_stage_rank)
    if current_stage_is_invalid:
        _record_field_change(changes, "current_stage", existing_stage, target_stage)
    elif _stage_rank(target_stage) > _stage_rank(str(candidate_manifest["current_stage"])):
        _record_field_change(changes, "current_stage", candidate_manifest["current_stage"], target_stage)
    candidate_manifest["current_stage"] = target_stage

    if not changes and not current_stage_is_invalid:
        return None

    normalized_manifest = validate_project_manifest(candidate_manifest)
    return {
        "status": "repair_required",
        "project_root": project_root,
        "corrupted_step": "metadata.current_stage" if current_stage_is_invalid else "metadata.project_manifest",
        "reset_stage": target_stage,
        "message": "Project metadata can be normalized from local workflow artifacts.",
        "metadata_only": True,
        "changes": changes,
        "warnings": warnings,
        "normalized_manifest": normalized_manifest,
    }


def _validate_project_scoped_manifest_paths(payload: dict[str, object], project_root: Path) -> None:
    """
    @brief      Reject manifest paths that cannot be safely scoped to the active project.
    @param[in]  payload Parsed project manifest payload.
    @param[in]  project_root Active project root folder.
    @return     None.
    @exception  ValueError Raised when a manifest path escapes the project root.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    source_document = payload.get("source_document")
    if isinstance(source_document, dict):
        stored_relative_path = _optional_string(source_document.get("stored_relative_path"))
        if stored_relative_path is not None:
            _resolve_manifest_path(project_root, stored_relative_path, "source_document.stored_relative_path")
    for field_name in ("extracted_text_relative_path", "extraction_report_relative_path"):
        relative_path = _optional_string(payload.get(field_name))
        if relative_path is not None:
            _resolve_manifest_path(project_root, relative_path, field_name)
    operations = payload.get("operations")
    if not isinstance(operations, dict):
        return
    for operation_kind, operation_payload in operations.items():
        if not isinstance(operation_payload, dict):
            continue
        folder_relative_path = _optional_string(operation_payload.get("folder_relative_path"))
        if folder_relative_path is not None:
            _resolve_manifest_path(
                project_root,
                folder_relative_path,
                f"operations.{operation_kind}.folder_relative_path",
            )
        for field_name in ("input_paths", "output_paths", "artifact_paths"):
            for index, relative_path in enumerate(_operation_path_list(operation_payload, field_name)):
                _resolve_manifest_path(
                    project_root,
                    relative_path,
                    f"operations.{operation_kind}.{field_name}[{index}]",
                )


def _resolve_manifest_path(project_root: Path, relative_path: str, field_name: str) -> Path:
    """
    @brief      Resolve one manifest path or raise a field-specific validation error.
    @param[in]  project_root Active project root folder.
    @param[in]  relative_path Candidate project-relative path.
    @param[in]  field_name Manifest field name used for diagnostics.
    @return     Resolved project-local path.
    @exception  ValueError Raised when the path escapes the project root.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    try:
        return resolve_project_relative_path(project_root, relative_path)
    except ValueError as exc:
        raise ValueError(f"Project manifest field '{field_name}' is not a safe project-relative path.") from exc


def _verified_source_stage(manifest: dict[str, object], project_root: Path) -> str:
    """
    @brief      Verify whether the manifest-selected source file still exists.
    @param[in]  manifest Normalized manifest payload.
    @param[in]  project_root Active project root folder.
    @return     `source_selected` when source evidence is valid, otherwise default stage.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    source_document = manifest.get("source_document")
    if not isinstance(source_document, dict):
        return config.DEFAULT_WORKFLOW_STAGE
    stored_relative_path = str(source_document.get("stored_relative_path", "")).strip()
    if stored_relative_path and _project_relative_path_exists(project_root, stored_relative_path):
        return "source_selected"
    return config.DEFAULT_WORKFLOW_STAGE


def _operation_completion_evidence(
    project_root: Path,
    operation_kind: str,
    warnings: list[str],
) -> dict[str, object] | None:
    """
    @brief      Resolve completed-operation evidence for one workflow step.
    @param[in]  project_root Active project root folder.
    @param[in]  operation_kind Stable operation-kind token.
    @param[out] warnings Non-destructive repair warnings appended by the check.
    @return     Completed operation evidence payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    evidence_builders = {
        "extraction": _extraction_completion_evidence,
        "cleanup": _cleanup_completion_evidence,
        "chunking": _chunking_completion_evidence,
        "translation": _translation_completion_evidence,
        "character_discovery": _character_discovery_completion_evidence,
        "narrator_definition": _narrator_definition_completion_evidence,
        "character_voices": _character_voices_completion_evidence,
        "speech_blocks": _speech_blocks_completion_evidence,
        "audio_blocks": _audio_blocks_completion_evidence,
        "audio_assembly": _audio_assembly_completion_evidence,
    }
    return evidence_builders[operation_kind](project_root, warnings)


def _extraction_completion_evidence(project_root: Path, warnings: list[str]) -> dict[str, object] | None:
    """
    @brief      Verify completed Extraction artifacts.
    @param[in]  project_root Active project root folder.
    @param[out] warnings Non-destructive repair warnings appended by the check.
    @return     Completed operation evidence payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _ = warnings
    state = _load_json_artifact(project_root, config.EXTRACTION_STATE_FILE_NAME)
    report = _load_json_artifact(project_root, config.EXTRACTION_REPORT_FILE_NAME)
    if (
        not _status_is_completed(state)
        or not isinstance(report, dict)
        or not _text_artifact_has_content(project_root, config.EXTRACTED_TEXT_FILE_NAME)
    ):
        return None
    return {"operation": state, "report": report}


def _cleanup_completion_evidence(project_root: Path, warnings: list[str]) -> dict[str, object] | None:
    """
    @brief      Verify completed Text Cleanup artifacts.
    @param[in]  project_root Active project root folder.
    @param[out] warnings Non-destructive repair warnings appended by the check.
    @return     Completed operation evidence payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _ = warnings
    state = _load_json_artifact(project_root, config.CLEANUP_STATE_FILE_NAME)
    report = _load_json_artifact(project_root, config.CLEANUP_REPORT_FILE_NAME)
    if (
        not _status_is_completed(state)
        or not isinstance(report, dict)
        or not _text_artifact_has_content(project_root, config.CLEANED_TEXT_FILE_NAME)
    ):
        return None
    return {"operation": state, "report": report}


def _chunking_completion_evidence(project_root: Path, warnings: list[str]) -> dict[str, object] | None:
    """
    @brief      Verify completed Text Chunking artifacts.
    @param[in]  project_root Active project root folder.
    @param[out] warnings Non-destructive repair warnings appended by the check.
    @return     Completed operation evidence payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _ = warnings
    state = _load_json_artifact(project_root, config.CHUNKING_STATE_FILE_NAME)
    report = _load_json_artifact(project_root, config.CHUNKING_REPORT_FILE_NAME)
    chunks = _load_json_artifact(project_root, config.CHUNK_ARTIFACT_FILE_NAME)
    if not _status_is_completed(state) or not isinstance(report, dict) or not _non_empty_payload_list(chunks):
        return None
    return {"operation": state, "report": report}


def _translation_completion_evidence(project_root: Path, warnings: list[str]) -> dict[str, object] | None:
    """
    @brief      Verify fully approved Translation artifacts.
    @param[in]  project_root Active project root folder.
    @param[out] warnings Non-destructive repair warnings appended by the check.
    @return     Completed operation evidence payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    _ = warnings
    state = _load_json_artifact(project_root, config.TRANSLATION_STATE_FILE_NAME)
    report = _load_json_artifact(project_root, config.TRANSLATION_REPORT_FILE_NAME)
    translations = _load_json_artifact(project_root, config.TRANSLATED_CHUNKS_FILE_NAME)
    if (
        not _status_is_completed(state)
        or not isinstance(report, dict)
        or not _non_empty_payload_list(translations)
        or not any(_payload_has_text(item, ("translated_text", "text")) for item in translations)
        or not _translation_report_is_fully_approved(report)
    ):
        return None
    return {"operation": state, "report": report}


def _character_discovery_completion_evidence(project_root: Path, warnings: list[str]) -> dict[str, object] | None:
    """
    @brief      Verify completed Character Discovery artifacts.
    @param[in]  project_root Active project root folder.
    @param[out] warnings Non-destructive repair warnings appended by the check.
    @return     Completed operation evidence payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _ = warnings
    state = _load_json_artifact(project_root, config.CHARACTER_DISCOVERY_STATE_FILE_NAME)
    report = _load_json_artifact(project_root, config.CHARACTER_DISCOVERY_REPORT_FILE_NAME)
    profiles = _load_json_artifact(project_root, config.CHARACTER_PROFILE_FILE_NAME)
    if not _status_is_completed(state) or not isinstance(report, dict) or not _non_empty_payload_list(profiles):
        return None
    return {"operation": state, "report": report}


def _narrator_definition_completion_evidence(project_root: Path, warnings: list[str]) -> dict[str, object] | None:
    """
    @brief      Verify completed Narrator Definition artifacts.
    @param[in]  project_root Active project root folder.
    @param[out] warnings Non-destructive repair warnings appended by the check.
    @return     Completed operation evidence payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.1
    """
    _ = warnings
    profiles = _load_json_artifact(project_root, config.NARRATOR_PROFILE_FILE_NAME)
    selection = _load_json_artifact(project_root, config.NARRATOR_SELECTION_FILE_NAME)
    if not _non_empty_payload_list(profiles) or not isinstance(selection, dict):
        return None
    selected_profile = _selected_narrator_profile(profiles, selection)
    if selected_profile is None:
        return None
    sample_metadata = selected_profile.get("sample_metadata")
    timestamp = _first_optional_string(
        selection,
        sample_metadata if isinstance(sample_metadata, dict) else {},
        selected_profile,
        "selected_at",
        "updated_at",
        "created_at",
        "generated_at",
    )
    operation = {
        "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        "status": "completed",
        "progress_current": 1,
        "progress_total": 1,
        "mode": "manual",
        "started_at": timestamp,
        "completed_at": timestamp,
        "updated_at": timestamp,
        "warning_count": 0,
    }
    return {"operation": operation, "selection": selection, "profile": selected_profile}


def _character_voices_completion_evidence(project_root: Path, warnings: list[str]) -> dict[str, object] | None:
    """
    @brief      Verify completed Character Voices artifacts.
    @param[in]  project_root Active project root folder.
    @param[out] warnings Non-destructive repair warnings appended by the check.
    @return     Completed operation evidence payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _ = warnings
    targets = _load_json_artifact(project_root, config.CHARACTER_VOICES_TARGETS_FILE_NAME)
    if not _non_empty_payload_list(targets) or not all(_voice_target_is_usable(target) for target in targets):
        return None
    timestamp = _first_optional_string(*[target for target in targets if isinstance(target, dict)], "updated_at")
    operation = {
        "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        "status": "completed",
        "progress_current": len(targets),
        "progress_total": len(targets),
        "mode": "manual",
        "started_at": timestamp,
        "completed_at": timestamp,
        "updated_at": timestamp,
        "warning_count": 0,
    }
    return {"operation": operation, "targets": targets}


def _speech_blocks_completion_evidence(project_root: Path, warnings: list[str]) -> dict[str, object] | None:
    """
    @brief      Verify completed Speech Blocks artifacts.
    @param[in]  project_root Active project root folder.
    @param[out] warnings Non-destructive repair warnings appended by the check.
    @return     Completed operation evidence payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    state = _load_json_artifact(project_root, config.SPEECH_BLOCKS_STATE_FILE_NAME)
    report = _load_json_artifact(project_root, config.SPEECH_BLOCKS_REPORT_FILE_NAME)
    speech_blocks = _load_json_artifact(project_root, config.SPEECH_BLOCKS_OUTPUT_FILE_NAME)
    if (
        not isinstance(report, dict)
        or str(report.get("speech_blocks_stage_status", "")).strip() != "completed"
        or not _non_empty_payload_list(speech_blocks)
        or not all(isinstance(block, dict) and bool(block.get("approved", False)) for block in speech_blocks)
    ):
        if _artifact_exists(project_root, config.SPEECH_BLOCKS_OUTPUT_FILE_NAME):
            warnings.append("Speech Blocks artifacts exist but do not prove a completed, fully approved stage.")
        return None
    return _completed_or_report_healed_operation(
        "speech_blocks",
        state,
        report,
        warnings,
        config.SPEECH_BLOCKS_STATE_FILE_NAME,
    )


def _audio_blocks_completion_evidence(project_root: Path, warnings: list[str]) -> dict[str, object] | None:
    """
    @brief      Verify completed Audio Blocks artifacts.
    @param[in]  project_root Active project root folder.
    @param[out] warnings Non-destructive repair warnings appended by the check.
    @return     Completed operation evidence payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    state = _load_json_artifact(project_root, config.AUDIO_BLOCKS_STATE_FILE_NAME)
    report = _load_json_artifact(project_root, config.AUDIO_BLOCKS_REPORT_FILE_NAME)
    audio_blocks = _load_json_artifact(project_root, config.AUDIO_BLOCKS_OUTPUT_FILE_NAME)
    if not _audio_blocks_report_is_completed(report) or not _non_empty_payload_list(audio_blocks):
        if _artifact_exists(project_root, config.AUDIO_BLOCKS_OUTPUT_FILE_NAME):
            warnings.append("Audio Blocks artifacts exist but do not prove a completed stage.")
        return None
    if not _audio_block_files_exist(project_root, audio_blocks, state):
        warnings.append(
            "Audio Blocks completion was not healed because at least one referenced audio artifact is missing."
        )
        return None
    return _completed_or_report_healed_operation(
        "audio_blocks",
        state,
        report,
        warnings,
        config.AUDIO_BLOCKS_STATE_FILE_NAME,
    )


def _audio_assembly_completion_evidence(project_root: Path, warnings: list[str]) -> dict[str, object] | None:
    """
    @brief      Verify completed Audio Assembly artifacts.
    @param[in]  project_root Active project root folder.
    @param[out] warnings Non-destructive repair warnings appended by the check.
    @return     Completed operation evidence payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    state = _load_json_artifact(project_root, config.AUDIO_ASSEMBLY_STATE_FILE_NAME)
    report = _load_json_artifact(project_root, config.AUDIO_ASSEMBLY_REPORT_FILE_NAME)
    if not _status_is_completed(state) or not isinstance(report, dict):
        return None
    output_paths = _operation_path_list(state, "output_paths") + _report_output_paths(report)
    if not output_paths or not all(_project_relative_path_exists(project_root, path) for path in output_paths):
        warnings.append(
            "Audio Assembly completion was not healed because one or more final audiobook outputs are missing."
        )
        return None
    return {"operation": state, "report": report}


def _completed_or_report_healed_operation(
    operation_kind: str,
    state: object,
    report: dict[str, object],
    warnings: list[str],
    state_file_name: str,
) -> dict[str, object]:
    """
    @brief      Prefer completed state evidence, or heal manifest summary from completed report evidence.
    @param[in]  operation_kind Stable operation-kind token.
    @param[in]  state Parsed operation-state payload.
    @param[in]  report Parsed completed report payload.
    @param[out] warnings Non-destructive repair warnings appended by the check.
    @param[in]  state_file_name Operation-state file name used in the warning.
    @return     Completed operation evidence payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if _status_is_completed(state):
        return {"operation": state, "report": report}
    operation = dict(state) if isinstance(state, dict) else {}
    timestamp = _first_optional_string(report, operation, "updated_at", "completed_at", "generated_at")
    operation.update(
        {
            "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
            "status": "completed",
            "completed_at": _optional_string(operation.get("completed_at")) or timestamp,
            "updated_at": _optional_string(operation.get("updated_at")) or timestamp,
            "warning_count": _non_negative_int(operation.get("warning_count", report.get("warning_count", 0))),
        }
    )
    if operation_kind == "audio_blocks":
        total_count = _non_negative_int(report.get("total_block_count", 0))
        operation["progress_current"] = _non_negative_int(report.get("generated_block_count", total_count))
        operation["progress_total"] = total_count
    elif operation_kind == "speech_blocks":
        total_count = _non_negative_int(report.get("total_block_count", report.get("speech_block_count", 0)))
        operation["progress_current"] = _non_negative_int(report.get("approved_block_count", total_count))
        operation["progress_total"] = total_count
    warnings.append(
        f"{state_file_name} status is stale; project.json metadata will be healed from completed report and "
        "output artifacts."
    )
    return {"operation": operation, "report": report}


def _heal_operation_summary(
    manifest: dict[str, object],
    operation_kind: str,
    evidence: dict[str, object],
    changes: list[str],
) -> None:
    """
    @brief      Copy one completed operation summary into the candidate manifest.
    @param[in,out] manifest Candidate manifest payload.
    @param[in]  operation_kind Stable operation-kind token.
    @param[in]  evidence Completed operation evidence payload.
    @param[out] changes Human-readable metadata changes.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    operations = manifest.get("operations")
    if not isinstance(operations, dict):
        return
    healed_summary = project_manifest_operation_summary(operation_kind, evidence.get("operation"))
    old_summary = operations.get(operation_kind)
    operations[operation_kind] = healed_summary
    if isinstance(old_summary, dict) and old_summary != healed_summary:
        old_status = old_summary.get("status")
        new_status = healed_summary.get("status")
        if old_status != new_status:
            changes.append(f"{operation_kind}: {old_status} -> {new_status}")
        else:
            changes.append(f"{operation_kind}: summary metadata normalized")


def _heal_extraction_manifest_fields(
    manifest: dict[str, object],
    evidence: dict[str, object],
    changes: list[str],
) -> None:
    """
    @brief      Align extraction shortcut fields in the candidate manifest.
    @param[in,out] manifest Candidate manifest payload.
    @param[in]  evidence Completed extraction evidence payload.
    @param[out] changes Human-readable metadata changes.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    report = evidence.get("report")
    operation = evidence.get("operation")
    extracted_path = _first_optional_string(report, operation, "extracted_text_relative_path")
    if extracted_path is None:
        extracted_path = config.EXTRACTED_TEXT_FILE_NAME
    _record_manifest_value_change(manifest, "extracted_text_relative_path", extracted_path, changes)
    existing_report_path = _optional_string(manifest.get("extraction_report_relative_path"))
    healed_report_path = existing_report_path or config.EXTRACTION_REPORT_FILE_NAME
    _record_manifest_value_change(manifest, "extraction_report_relative_path", healed_report_path, changes)
    warnings_value = 0
    if isinstance(report, dict):
        warnings_value = _non_negative_int(report.get("warning_count", len(report.get("warnings", []))))
    _record_manifest_value_change(manifest, "extraction_warning_count", warnings_value, changes)


def _heal_narrator_manifest_fields(
    manifest: dict[str, object],
    evidence: dict[str, object],
    changes: list[str],
) -> None:
    """
    @brief      Align narrator shortcut fields in the candidate manifest.
    @param[in,out] manifest Candidate manifest payload.
    @param[in]  evidence Completed narrator-definition evidence payload.
    @param[out] changes Human-readable metadata changes.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    profile = evidence.get("profile")
    selection = evidence.get("selection")
    narrator_name = _first_optional_string(selection, profile, "display_name", "profile_name", "name", "voice_name")
    narrator_language = _first_optional_string(selection, profile, "selected_language", "language", "voice_language")
    if narrator_name is not None:
        _record_manifest_value_change(manifest, "narrator_profile_name", narrator_name, changes)
    if narrator_language is not None:
        _record_manifest_value_change(manifest, "narrator_language", narrator_language, changes)


def _heal_character_voice_manifest_fields(
    manifest: dict[str, object],
    evidence: dict[str, object],
    changes: list[str],
) -> None:
    """
    @brief      Align selected voice language in the candidate manifest.
    @param[in,out] manifest Candidate manifest payload.
    @param[in]  evidence Completed character-voices evidence payload.
    @param[out] changes Human-readable metadata changes.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    if bool(manifest.get("project_options_locked", False)):
        _record_manifest_value_change(manifest, "selected_voice_language", manifest.get("target_language"), changes)
        return
    targets = evidence.get("targets")
    if not isinstance(targets, list):
        return
    languages = {
        language
        for target in targets
        if isinstance(target, dict)
        for language in (_first_optional_string(target, "voice_language", "target_language", "language"),)
        if language is not None
    }
    if len(languages) == 1:
        _record_manifest_value_change(manifest, "selected_voice_language", next(iter(languages)), changes)


def _record_manifest_value_change(
    manifest: dict[str, object],
    field_name: str,
    new_value: object,
    changes: list[str],
) -> None:
    """
    @brief      Update one manifest field and append a readable change entry.
    @param[in,out] manifest Candidate manifest payload.
    @param[in]  field_name Manifest field name.
    @param[in]  new_value Normalized field value.
    @param[out] changes Human-readable metadata changes.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    old_value = manifest.get(field_name)
    if old_value == new_value:
        return
    manifest[field_name] = new_value
    _record_field_change(changes, field_name, old_value, new_value)


def _record_field_change(changes: list[str], field_name: str, old_value: object, new_value: object) -> None:
    """
    @brief      Append one readable field-change entry.
    @param[out] changes Human-readable metadata changes.
    @param[in]  field_name Manifest field name.
    @param[in]  old_value Previous field value.
    @param[in]  new_value New field value.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    changes.append(f"{field_name}: {old_value} -> {new_value}")


def _status_is_completed(payload: object) -> bool:
    """
    @brief      Return whether a parsed payload has `status == completed`.
    @param[in]  payload Candidate parsed payload.
    @return     True when the status is completed.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return isinstance(payload, dict) and str(payload.get("status", "")).strip() == "completed"


def _translation_report_is_fully_approved(report: object) -> bool:
    """
    @brief      Return whether one translation report proves full approval.
    @param[in]  report Candidate translation report payload.
    @return     True when every translated chunk is approved.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    if not isinstance(report, dict):
        return False
    total_count = int(report.get("total_chunk_count", 0) or 0)
    translated_count = int(report.get("translated_chunk_count", 0) or 0)
    approved_count = int(report.get("approved_chunk_count", 0) or 0)
    stage_status = str(report.get("translation_stage_status", "")).strip()
    if stage_status not in {"approved", "completed"}:
        return False
    return total_count > 0 and translated_count >= total_count and approved_count >= total_count


def _non_empty_payload_list(payload: object) -> bool:
    """
    @brief      Return whether a parsed payload is a non-empty list.
    @param[in]  payload Candidate parsed payload.
    @return     True when the payload is a non-empty list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return isinstance(payload, list) and bool(payload)


def _payload_has_text(payload: object, field_names: tuple[str, ...]) -> bool:
    """
    @brief      Return whether one parsed dictionary has any non-empty text field.
    @param[in]  payload Candidate parsed payload.
    @param[in]  field_names Candidate field names.
    @return     True when a field contains text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return isinstance(payload, dict) and any(str(payload.get(field_name, "")).strip() for field_name in field_names)


def _selected_narrator_profile(profiles: object, selection: dict[str, object]) -> dict[str, object] | None:
    """
    @brief      Resolve the selected narrator profile from persisted profile data.
    @param[in]  profiles Parsed narrator profile list.
    @param[in]  selection Parsed narrator selection payload.
    @return     Matching profile payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if not isinstance(profiles, list):
        return None
    selected_identifier = _first_optional_string(selection, "selected_profile_id", "profile_id", "id")
    selected_name = _first_optional_string(selection, "selected_profile_name", "profile_name", "name", "display_name")
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        profile_identifiers = {
            value
            for value in (
                _first_optional_string(profile, "profile_id", "id"),
                _first_optional_string(profile, "profile_name", "name", "display_name"),
            )
            if value is not None
        }
        if selected_identifier in profile_identifiers or selected_name in profile_identifiers:
            return profile
    return None


def _voice_target_is_usable(target: object) -> bool:
    """
    @brief      Return whether one character-voice target contains a usable assignment.
    @param[in]  target Candidate target payload.
    @return     True when the target has a voice assignment marker.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return isinstance(target, dict) and any(
        _first_optional_string(target, field_name) is not None
        for field_name in (
            "voice_profile_id",
            "selected_voice_id",
            "target_voice_id",
            "profile_id",
            "voice_sample_relative_path",
            "sample_relative_path",
            "audio_relative_path",
            "voice_definition_prompt",
        )
    )


def _audio_blocks_report_is_completed(report: object) -> bool:
    """
    @brief      Return whether an Audio Blocks report proves completion.
    @param[in]  report Parsed Audio Blocks report.
    @return     True when report counts are completed and consistent.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if not isinstance(report, dict) or str(report.get("audio_blocks_stage_status", "")).strip() != "completed":
        return False
    total_count = _non_negative_int(report.get("total_block_count", 0))
    generated_count = _non_negative_int(report.get("generated_block_count", 0))
    approved_count = _non_negative_int(report.get("approved_block_count", 0))
    return total_count > 0 and generated_count == total_count and approved_count == total_count


def _audio_block_files_exist(project_root: Path, audio_blocks: object, state: object) -> bool:
    """
    @brief      Return whether referenced Audio Blocks audio files exist.
    @param[in]  project_root Active project root folder.
    @param[in]  audio_blocks Parsed Audio Blocks payload.
    @param[in]  state Parsed Audio Blocks operation-state payload.
    @return     True when referenced generated audio artifacts exist.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if not isinstance(audio_blocks, list):
        return False
    audio_paths: list[str] = []
    for block in audio_blocks:
        if not isinstance(block, dict):
            continue
        block_paths = [_optional_string(block.get("audio_relative_path"))]
        generated_part_paths = block.get("generated_part_relative_paths")
        if isinstance(generated_part_paths, list):
            block_paths.extend(_optional_string(value) for value in generated_part_paths)
        audio_paths.extend(path for path in block_paths if path is not None)
    if isinstance(state, dict):
        audio_paths.extend(
            path
            for path in _operation_path_list(state, "output_paths") + _operation_path_list(state, "artifact_paths")
            if Path(path).suffix.lower() in {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}
        )
    return bool(audio_paths) and all(_project_relative_path_exists(project_root, path) for path in audio_paths)


def _operation_path_list(payload: object, field_name: str) -> list[str]:
    """
    @brief      Return one operation path list as normalized strings.
    @param[in]  payload Candidate operation payload.
    @param[in]  field_name Path-list field name.
    @return     Normalized path strings.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    if not isinstance(payload, dict) or not isinstance(payload.get(field_name), list):
        return []
    return [str(path).strip() for path in payload[field_name] if str(path).strip()]


def _report_output_paths(report: dict[str, object]) -> list[str]:
    """
    @brief      Extract output paths from an Audio Assembly report.
    @param[in]  report Parsed Audio Assembly report.
    @return     Normalized project-relative output paths.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    outputs = report.get("outputs")
    if not isinstance(outputs, list):
        return []
    return [
        str(output.get("audio_relative_path", "")).strip()
        for output in outputs
        if isinstance(output, dict) and str(output.get("audio_relative_path", "")).strip()
    ]


def _project_relative_path_exists(project_root: Path, relative_path: str) -> bool:
    """
    @brief      Return whether one project-relative path exists below the project root.
    @param[in]  project_root Active project root folder.
    @param[in]  relative_path Candidate project-relative path.
    @return     True when the path resolves under the project root and exists.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    return project_relative_path_exists(project_root, relative_path)


def _optional_string(value: object) -> str | None:
    """
    @brief      Normalize one optional manifest string and reject null-like persisted text.
    @param[in]  value Candidate optional value.
    @return     Normalized string or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-10
    @version    0.1.0
    """
    normalized_value = _raw_optional_string(value)
    if normalized_value is None:
        return None
    if normalized_value.strip().casefold() in {"none", "null"}:
        return None
    return normalized_value


def _first_optional_string(*payloads_and_fields: object) -> str | None:
    """
    @brief      Resolve the first non-empty string from dictionaries and candidate fields.
    @param[in]  payloads_and_fields Dictionaries followed by field-name strings.
    @return     First normalized value or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    payloads: list[dict[str, object]] = []
    field_names: list[str] = []
    for item in payloads_and_fields:
        if isinstance(item, dict):
            payloads.append(item)
        elif isinstance(item, str):
            field_names.append(item)
    for payload in payloads:
        for field_name in field_names:
            value = _optional_string(payload.get(field_name))
            if value is not None and value != "None":
                return value
    return None


def _validate_manifest_payload(payload: object) -> None:
    """
    @brief      Validate the minimal JSON payload contract for `project.json`.
    @param[in]  payload Raw parsed JSON value.
    @return     None.
    @exception  ValueError Raised when the payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    _validate_manifest_identity_fields(payload)
    assert isinstance(payload, dict)
    current_stage = payload.get("current_stage")
    if not isinstance(current_stage, str) or not current_stage.strip():
        raise ValueError("Project manifest field 'current_stage' is missing or invalid.")

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
    @version    0.2.0
    """
    if not isinstance(payload, dict):
        raise ValueError("Project manifest payload must be a JSON object.")
    for field_name in ("project_id", "display_name", "created_at", "updated_at"):
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Project manifest field '{field_name}' is missing or invalid.")


def _first_unsupported_legacy_directory(project_root: Path) -> str | None:
    """
    @brief      Return the first legacy workflow folder present in one project root.
    @param[in]  project_root Candidate project root folder.
    @return     Unsupported legacy folder name or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    for folder_name in _UNSUPPORTED_LEGACY_WORKFLOW_FOLDERS:
        if not (project_root / folder_name).is_dir():
            continue
        return folder_name
    return None


def _is_invalid_current_stage(payload: dict[str, object]) -> bool:
    """
    @brief      Determine whether the manifest current stage is repairable metadata.
    @param[in]  payload Parsed manifest payload.
    @return     True when the current stage is missing or unsupported.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
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
    @version    0.1.1
    """
    _ = project_root
    return _derive_trustworthy_stage(payload)


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
    @date       2026-04-18
    @version    0.3.0
    """
    repaired_manifest = {
        "project_id": str(payload["project_id"]),
        "display_name": str(payload["display_name"]),
        "created_at": str(payload["created_at"]),
        "updated_at": str(payload["updated_at"]),
        "current_stage": (
            reset_stage if reset_stage in config.PROJECT_WORKFLOW_STAGES else config.DEFAULT_WORKFLOW_STAGE
        ),
        "source_document": _normalize_source_document(payload.get("source_document")),
        "extracted_text_relative_path": _optional_string(payload.get("extracted_text_relative_path")),
        "extraction_report_relative_path": _optional_string(payload.get("extraction_report_relative_path")),
        "extraction_warning_count": _non_negative_int(payload.get("extraction_warning_count", 0)),
        "operations": _normalize_operations(payload.get("operations")),
        "project_options_locked": bool(payload.get("project_options_locked", False)),
        "target_language": _normalize_target_language(
            payload.get("target_language", config.DEFAULT_TRANSLATION_TARGET_LANGUAGE)
        ),
        "original_language": _optional_string(payload.get("original_language")),
        "narrator_profile_name": _optional_string(payload.get("narrator_profile_name")),
        "narrator_language": _optional_string(payload.get("narrator_language")),
        "selected_voice_language": _optional_string(payload.get("selected_voice_language")),
        "voice_assignment_mode": (
            str(payload.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)).strip()
            if str(payload.get("voice_assignment_mode", config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE)).strip()
            in config.TTS_VOICE_ASSIGNMENT_MODE_OPTIONS
            else config.DEFAULT_TTS_VOICE_ASSIGNMENT_MODE
        ),
        "audio_assembly_settings": _normalize_audio_assembly_settings(payload.get("audio_assembly_settings")),
        "notes": str(payload.get("notes", "")),
    }
    if bool(repaired_manifest.get("project_options_locked", False)):
        repaired_manifest["selected_voice_language"] = repaired_manifest["target_language"]
    if _stage_rank(str(repaired_manifest["current_stage"])) < _stage_rank("narrator_definition_ready"):
        repaired_manifest["narrator_profile_name"] = None
        repaired_manifest["narrator_language"] = None
    repaired_manifest["operations"] = _reset_operations_for_stage(
        dict(repaired_manifest["operations"]),
        str(repaired_manifest["current_stage"]),
    )
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
    if _normalize_source_document(payload.get("source_document")) is not None:
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


def _normalize_target_language(value: object) -> str:
    """
    @brief      Normalize one project target-language value.
    @param[in]  value Candidate language code.
    @return     Supported target-language code.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    normalized_value = str(value or "").strip()
    supported_languages = dict(config.TRANSLATION_LANGUAGE_OPTIONS)
    if normalized_value in supported_languages:
        return normalized_value
    return config.DEFAULT_TRANSLATION_TARGET_LANGUAGE


def _non_negative_int(value: object) -> int:
    """
    @brief      Normalize one optional integer manifest field to a non-negative value.
    @param[in]  value Raw decoded JSON value.
    @return     Normalized non-negative integer.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    try:
        resolved_value = int(value)
    except (TypeError, ValueError):
        return 0
    return max(resolved_value, 0)


def _default_audio_assembly_settings() -> dict[str, object]:
    """
    @brief      Build default Audio Assembly settings for one project manifest.
    @return     Default Audio Assembly settings payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    return {
        "output_mode": config.DEFAULT_AUDIO_ASSEMBLY_OUTPUT_MODE,
        "max_duration_minutes": config.DEFAULT_AUDIO_ASSEMBLY_MAX_DURATION_MINUTES,
        "output_format": config.DEFAULT_AUDIO_ASSEMBLY_OUTPUT_FORMAT,
        "inter_block_silence_ms": config.DEFAULT_AUDIO_ASSEMBLY_INTER_BLOCK_SILENCE_MS,
        "inter_chunk_silence_ms": config.DEFAULT_AUDIO_ASSEMBLY_INTER_CHUNK_SILENCE_MS,
    }


def _normalize_audio_assembly_settings(value: object) -> dict[str, object]:
    """
    @brief      Normalize one optional Audio Assembly settings manifest payload.
    @param[in]  value Raw decoded settings value.
    @return     Normalized Audio Assembly settings payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    defaults = _default_audio_assembly_settings()
    payload = value if isinstance(value, dict) else {}
    output_mode = str(payload.get("output_mode", defaults["output_mode"])).strip()
    if output_mode not in config.AUDIO_ASSEMBLY_OUTPUT_MODE_OPTIONS:
        output_mode = str(defaults["output_mode"])
    output_format = str(payload.get("output_format", defaults["output_format"])).strip().lower()
    if output_format not in config.AUDIO_ASSEMBLY_OUTPUT_FORMAT_OPTIONS:
        output_format = str(defaults["output_format"])
    return {
        "output_mode": output_mode,
        "max_duration_minutes": _bounded_int(
            payload.get("max_duration_minutes", defaults["max_duration_minutes"]),
            1,
            24 * 60,
            int(defaults["max_duration_minutes"]),
        ),
        "output_format": output_format,
        "inter_block_silence_ms": _bounded_int(
            payload.get("inter_block_silence_ms", defaults["inter_block_silence_ms"]),
            0,
            60_000,
            int(defaults["inter_block_silence_ms"]),
        ),
        "inter_chunk_silence_ms": _bounded_int(
            payload.get("inter_chunk_silence_ms", defaults["inter_chunk_silence_ms"]),
            0,
            60_000,
            int(defaults["inter_chunk_silence_ms"]),
        ),
    }


def _bounded_int(value: object, minimum: int, maximum: int, fallback: int) -> int:
    """
    @brief      Normalize one integer within inclusive bounds.
    @param[in]  value Candidate value.
    @param[in]  minimum Minimum accepted value.
    @param[in]  maximum Maximum accepted value.
    @param[in]  fallback Fallback value for invalid input.
    @return     Normalized bounded integer.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(resolved, maximum))


def _normalize_source_document(value: object) -> dict[str, object] | None:
    """
    @brief      Normalize one optional structured source-document payload.
    @param[in]  value Raw decoded JSON value.
    @return     Normalized source-document payload or `None`.
    @exception  ValueError Raised when the payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        raise ValueError("Project manifest field 'source_document' is invalid.")

    original_name = value.get("original_name")
    stored_relative_path = value.get("stored_relative_path")
    file_type = value.get("file_type")
    imported_at = value.get("imported_at")
    size_bytes = value.get("size_bytes")

    if not isinstance(original_name, str) or not original_name.strip():
        raise ValueError("Project manifest field 'source_document.original_name' is invalid.")
    if not isinstance(stored_relative_path, str) or not stored_relative_path.strip():
        raise ValueError("Project manifest field 'source_document.stored_relative_path' is invalid.")
    try:
        normalized_stored_relative_path = validate_project_relative_path(stored_relative_path)
    except ValueError as exc:
        raise ValueError("Project manifest field 'source_document.stored_relative_path' is invalid.") from exc
    if not isinstance(file_type, str) or file_type not in config.SUPPORTED_SOURCE_SUFFIXES.values():
        raise ValueError("Project manifest field 'source_document.file_type' is invalid.")
    if not isinstance(imported_at, str) or not imported_at.strip():
        raise ValueError("Project manifest field 'source_document.imported_at' is invalid.")
    if not isinstance(size_bytes, int) or size_bytes < 0:
        raise ValueError("Project manifest field 'source_document.size_bytes' is invalid.")

    return {
        "original_name": original_name,
        "stored_relative_path": normalized_stored_relative_path,
        "file_type": file_type,
        "imported_at": imported_at,
        "size_bytes": size_bytes,
    }


def _build_default_operation_states() -> dict[str, dict[str, object]]:
    """
    @brief      Build the default operation-state mapping for one new project.
    @return     Default project-local operation-state map.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.2.0
    """
    return {
        operation_kind: _default_operation_state(operation_kind)
        for operation_kind in (
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
    }


def _default_operation_state(operation_kind: str) -> dict[str, object]:
    """
    @brief      Build one default operation-state payload.
    @param[in]  operation_kind Stable operation-kind token.
    @return     Default operation-state payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.3.0
    """
    return {
        "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        "status": "not_started",
        "progress_current": 0,
        "progress_total": 0,
        "mode": None,
        "started_at": None,
        "completed_at": None,
        "updated_at": None,
        "warning_count": 0,
    }


def _normalize_operations(value: object) -> dict[str, dict[str, object]]:
    """
    @brief      Normalize one optional manifest operations mapping.
    @param[in]  value Raw decoded JSON value.
    @return     Normalized operations mapping with every required operation key.
    @exception  ValueError Raised when the operations payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.2.0
    """
    operations = _build_default_operation_states()
    if value in (None, ""):
        return operations
    if not isinstance(value, dict):
        raise ValueError("Project manifest field 'operations' is invalid.")
    for operation_kind in operations:
        candidate = value.get(operation_kind)
        if candidate in (None, ""):
            continue
        if not isinstance(candidate, dict):
            raise ValueError(f"Project manifest field 'operations.{operation_kind}' is invalid.")
        operations[operation_kind] = project_manifest_operation_summary(
            operation_kind,
            candidate,
        )
    return operations


def _reset_operations_for_stage(
    operations: dict[str, dict[str, object]],
    current_stage: str,
) -> dict[str, dict[str, object]]:
    """
    @brief      Reset downstream operation-state entries that are not justified by one stage token.
    @param[in]  operations Current normalized operations mapping.
    @param[in]  current_stage Current repaired project stage token.
    @return     Operations mapping with downstream steps reset.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    allowed_operations = _allowed_operations_for_stage(current_stage)

    normalized_operations = dict(operations)
    for operation_kind in tuple(normalized_operations.keys()):
        if operation_kind not in allowed_operations:
            normalized_operations[operation_kind] = _default_operation_state(operation_kind)
    return normalized_operations


def _allowed_operations_for_stage(current_stage: str) -> set[str]:
    """
    @brief      Resolve the operation kinds that remain valid for one workflow stage.
    @param[in]  current_stage Current repaired project stage token.
    @return     Set of operation kinds that should be preserved.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
    """
    if current_stage == "source_selected":
        return {"extraction"}
    if current_stage == "text_cleanup_ready":
        return {"extraction", "cleanup"}
    if current_stage == "text_chunking_ready":
        return {"extraction", "cleanup", "chunking"}
    if current_stage == "translation_ready":
        return {"extraction", "cleanup", "chunking", "translation"}
    if current_stage == "character_discovery_ready":
        return {
            "extraction",
            "cleanup",
            "chunking",
            "translation",
            "character_discovery",
        }
    if current_stage == "narrator_definition_ready":
        return {
            "extraction",
            "cleanup",
            "chunking",
            "translation",
            "character_discovery",
            "narrator_definition",
        }
    if current_stage == "character_voices_ready":
        return {
            "extraction",
            "cleanup",
            "chunking",
            "translation",
            "character_discovery",
            "narrator_definition",
            "character_voices",
        }
    if current_stage == "speech_blocks_ready":
        return {
            "extraction",
            "cleanup",
            "chunking",
            "translation",
            "character_discovery",
            "narrator_definition",
            "character_voices",
            "speech_blocks",
        }
    if current_stage == "audio_blocks_ready":
        return {
            "extraction",
            "cleanup",
            "chunking",
            "translation",
            "character_discovery",
            "narrator_definition",
            "character_voices",
            "speech_blocks",
            "audio_blocks",
        }
    if current_stage == "audio_assembly_ready":
        return {
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
        }
    return set()


# END OF FILE
