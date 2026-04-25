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
@version    1.7.0
"""

# IMPORTS

from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function

# CONSTANTS

# @brief Component logger used by project workspace lifecycle helpers.
_PROJECT_WORKSPACE_LOGGER = get_component_logger("project_workspace")
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
    @version    0.2.0
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
    @version    0.4.0
    """
    resolved_root = Path(project_root)
    manifest_path = resolved_root / config.PROJECT_MANIFEST_FILE_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Project manifest file was not found: {manifest_path}")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest_identity_fields(payload)
    legacy_folder = _first_unsupported_legacy_directory(resolved_root)
    if legacy_folder is not None:
        raise ValueError(
            f"Project uses the unsupported legacy numbered runtime layout: {legacy_folder}. "
            "Create a new flattened project; migration is not supported."
        )
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
    @version    0.2.0
    """
    project_root = Path(str(repair_request["project_root"]))
    manifest_path = project_root / config.PROJECT_MANIFEST_FILE_NAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest_identity_fields(payload)

    if not bool(repair_request.get("metadata_only", False)):
        raise ValueError("Folder-based project repair is not supported by the flattened project layout.")

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
    @version    0.2.0
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
        "original_language": _optional_string(payload.get("original_language")),
        "narrator_profile_name": _optional_string(payload.get("narrator_profile_name")),
        "narrator_language": _optional_string(payload.get("narrator_language")),
        "selected_voice_language": _optional_string(payload.get("selected_voice_language")),
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
    @version    0.1.0
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


def _repair_stage_for_folder(folder_name: str, payload: dict[str, object]) -> str:
    """
    @brief      Resolve the stage token to keep after one folder-based repair.
    @param[in]  folder_name Corrupted step folder name.
    @param[in]  payload Parsed manifest payload.
    @return     Conservatively trusted stage token that remains valid after repair.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.4.0
    """
    current_stage = str(payload.get("current_stage", config.DEFAULT_WORKFLOW_STAGE)).strip()
    stage_before_folder = {
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH: "project_created",
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH: "source_selected",
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH: "text_cleanup_ready",
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH: "text_chunking_ready",
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH: "translation_ready",
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH: "character_discovery_ready",
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH: "narrator_definition_ready",
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH: "character_voices_ready",
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH: "speech_blocks_ready",
        config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH: "audio_blocks_ready",
    }.get(folder_name)
    if stage_before_folder is None:
        return _derive_trustworthy_stage(payload)

    if current_stage not in config.PROJECT_WORKFLOW_STAGES:
        current_stage = _derive_trustworthy_stage(payload)
    return min(current_stage, stage_before_folder, key=_stage_rank)


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


def _folders_to_reset_from(corrupted_step: str) -> tuple[str, ...]:
    """
    @brief      Build the ordered folder list to recreate from one corrupted step.
    @param[in]  corrupted_step Corrupted step folder name.
    @return     Tuple of affected folder names in reset order.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.4.0
    """
    _ = corrupted_step
    return ()


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
    @version    0.2.0
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
        "notes": str(payload.get("notes", "")),
    }
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
    @version    0.1.0
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
    if not isinstance(file_type, str) or file_type not in config.SUPPORTED_SOURCE_SUFFIXES.values():
        raise ValueError("Project manifest field 'source_document.file_type' is invalid.")
    if not isinstance(imported_at, str) or not imported_at.strip():
        raise ValueError("Project manifest field 'source_document.imported_at' is invalid.")
    if not isinstance(size_bytes, int) or size_bytes < 0:
        raise ValueError("Project manifest field 'source_document.size_bytes' is invalid.")

    return {
        "original_name": original_name,
        "stored_relative_path": stored_relative_path,
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


def _folder_name_for_operation(operation_kind: str) -> str:
    """
    @brief      Map one operation token to its project folder name.
    @param[in]  operation_kind Stable operation-kind token.
    @return     Matching project-relative folder name.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.3.0
    """
    _ = operation_kind
    return config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH


# END OF FILE
