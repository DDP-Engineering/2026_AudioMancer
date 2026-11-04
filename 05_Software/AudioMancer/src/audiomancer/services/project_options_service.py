#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file project_options_service.py
@brief Source-ready project creation and confirmed project option changes.
@details Keeps workspace publication and option reset policy independent of Qt.
"""

# IMPORTS

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import tempfile

from audiomancer import config
from audiomancer.services import import_service, operation_runtime_service, project_workspace_service
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.persistence_service import write_bytes_atomic, write_json_atomic

# CONSTANTS

# @brief Shared project-lifecycle logger for publication and reset failures.
_PROJECT_OPTIONS_LOGGER = get_component_logger("project_workspace")

# DATA MODELS


@dataclass(frozen=True)
class ProjectOptionsChange:
    """@brief Read-only impact snapshot shared by confirmation and application."""

    project_root: Path
    original_manifest_bytes: bytes
    manifest: dict[str, object]
    target_language: str
    voice_assignment_mode: str
    reset_operations: tuple[str, ...]
    affected_operations: tuple[str, ...]
    artifact_paths: tuple[Path, ...]
    replacement_targets: list[dict[str, object]] | None
    original_targets_bytes: bytes | None

    @property
    def changed(self) -> bool:
        """@brief Return whether an actual option value changed."""
        return self.language_changed or self.voice_assignment_mode != self.manifest["voice_assignment_mode"]

    @property
    def language_changed(self) -> bool:
        """@brief Return whether the translation and voice language must change."""
        return self.target_language != self.manifest["target_language"]

    @property
    def requires_confirmation(self) -> bool:
        """@brief Confirm every new mode and language changes with persisted effects."""
        return self.changed and (
            self.voice_assignment_mode != self.manifest["voice_assignment_mode"] or bool(self.affected_operations)
        )


# PUBLIC API


@trace_function(_PROJECT_OPTIONS_LOGGER)
def create_project_with_source(
    name: str,
    parent_path: str | Path,
    source_path: str | Path,
) -> tuple[Path, dict[str, object]]:
    """
    @brief      Publish a complete project only after its source has been copied.
    @param[in]  name Validated project folder and display name.
    @param[in]  parent_path Existing project parent directory.
    @param[in]  source_path Supported book selected by the operator.
    @return     Published project root and its persisted manifest.
    @exception  OSError Raised on filesystem failure, preserving the old destination.
    @exception  ValueError Raised for invalid names or unsupported documents.
    """
    project_workspace_service.validate_project_name(name)
    parent = Path(parent_path)
    if not parent.is_dir():
        raise FileNotFoundError(f"Project parent folder was not found: {parent}")
    destination = parent / name
    if destination.is_symlink() or destination.is_file():
        raise FileExistsError(f"Project path already exists: {destination}")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Project folder is not empty: {destination}")
    with tempfile.TemporaryDirectory(prefix=".audiomancer-new-", dir=parent) as temporary_parent:
        staged_root, manifest = project_workspace_service.create_project(name, temporary_parent)
        persisted = import_initial_source(
            staged_root, source_path, manifest["target_language"], manifest["voice_assignment_mode"]
        )
        existing_empty_folder = destination.is_dir()
        if existing_empty_folder:
            destination.rmdir()
        try:
            staged_root.rename(destination)
        except OSError:
            if existing_empty_folder:
                destination.mkdir(exist_ok=True)
            raise
    return destination, persisted


@trace_function(_PROJECT_OPTIONS_LOGGER)
def import_initial_source(
    project_root: str | Path, source_path: str | Path, target_language: str, voice_assignment_mode: str
) -> dict[str, object]:
    """
    @brief      Register a first source and options together, including legacy empty projects.
    @param[in]  project_root Workspace with no registered book.
    @param[in]  source_path Supported document to copy.
    @param[in]  target_language Selected target and voice language.
    @param[in]  voice_assignment_mode Selected narration mode.
    @return     Persisted source-ready manifest.
    @exception  ValueError Raised for a registered book or unsupported options.
    @exception  OSError Raised after restoring a failed initial import.
    """
    if target_language not in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
        raise ValueError("Project target language is invalid.")
    if voice_assignment_mode not in config.TTS_VOICE_ASSIGNMENT_MODE_OPTIONS:
        raise ValueError("Project narration mode is invalid.")
    root = Path(project_root).resolve()
    manifest_path = root / config.PROJECT_MANIFEST_FILE_NAME
    original_bytes = manifest_path.read_bytes()
    manifest = project_workspace_service.load_manifest(root)
    if manifest.get("source_document") is not None:
        raise ValueError("This project already has a registered book.")
    source_document = import_service.import_source(root, source_path)
    manifest.update(
        source_document=source_document,
        current_stage="source_selected",
        target_language=target_language,
        selected_voice_language=target_language,
        voice_assignment_mode=voice_assignment_mode,
        project_options_locked=True,
    )
    try:
        project_workspace_service.save_manifest(manifest, root)
        return project_workspace_service.load_manifest(root)
    except (OSError, ValueError):
        (root / source_document["stored_relative_path"]).unlink(missing_ok=True)
        if manifest_path.read_bytes() != original_bytes:
            write_bytes_atomic(manifest_path, original_bytes)
        raise


@trace_function(_PROJECT_OPTIONS_LOGGER)
def plan_project_options_change(
    project_root: str | Path, target_language: str, voice_assignment_mode: str
) -> ProjectOptionsChange:
    """
    @brief      Calculate exactly which existing results an option change affects.
    @param[in]  project_root Active workspace.
    @param[in]  target_language Supported target-language code.
    @param[in]  voice_assignment_mode Supported narration mode.
    @return     Read-only change plan; no operation defaults are initialized.
    @exception  ValueError Raised for invalid options or unsafe ownership metadata.
    @exception  OSError Raised when project evidence cannot be read.
    """
    if target_language not in dict(config.TRANSLATION_LANGUAGE_OPTIONS):
        raise ValueError("Project target language is invalid.")
    if voice_assignment_mode not in config.TTS_VOICE_ASSIGNMENT_MODE_OPTIONS:
        raise ValueError("Project narration mode is invalid.")
    root = Path(project_root).resolve()
    manifest_path = root / config.PROJECT_MANIFEST_FILE_NAME
    original_bytes = manifest_path.read_bytes()
    manifest = project_workspace_service.load_manifest(root)
    language_changed = target_language != manifest["target_language"]
    mode_changed = voice_assignment_mode != manifest["voice_assignment_mode"]
    reset_operations = ()
    if language_changed or mode_changed:
        reset_operations = operation_runtime_service.downstream_operation_kinds(
            "translation" if language_changed else "character_voices", include_current=True
        )
        if language_changed:
            reset_operations += ("book_analysis",)
    targets_path = root / config.CHARACTER_VOICES_TARGETS_FILE_NAME
    replacement_targets = None
    original_targets_bytes = None
    if mode_changed and not language_changed and targets_path.is_file():
        original_targets_bytes = targets_path.read_bytes()
        targets = json.loads(original_targets_bytes)
        if not isinstance(targets, list) or any(not isinstance(target, dict) for target in targets):
            raise ValueError("Character Voices target metadata is invalid.")
        replacement_targets = deepcopy(targets)
        for target in replacement_targets:
            if target.get("target_kind") == "character":
                target["sample_audio_path"] = None
                target["sample_metadata"] = None
    protected_paths = set()
    if not language_changed:
        protected_paths.update(root.glob("audio_narator_*.wav"))
        if replacement_targets is not None:
            for target in replacement_targets:
                if target.get("target_kind") == "narrator" and target.get("sample_audio_path"):
                    protected_paths.add(
                        root / operation_runtime_service.validate_project_relative_path(target["sample_audio_path"])
                    )
    source = manifest.get("source_document")
    if isinstance(source, dict):
        protected_paths.add(
            root / operation_runtime_service.validate_project_relative_path(source["stored_relative_path"])
        )
    artifacts = set()
    affected = []
    for kind in reset_operations:
        paths = set(operation_runtime_service.operation_reset_artifact_paths(root, kind)) - protected_paths
        target_metadata_changed = False
        if kind == "character_voices" and not language_changed:
            paths.discard(targets_path)
            target_metadata_changed = replacement_targets is not None and replacement_targets != json.loads(
                original_targets_bytes
            )
        summary = manifest["operations"].get(kind, {})
        if (
            paths
            or target_metadata_changed
            or summary.get("status", "not_started") not in {"not_started", "pending", ""}
        ):
            affected.append(kind)
        artifacts.update(paths)
    return ProjectOptionsChange(
        root,
        original_bytes,
        manifest,
        target_language,
        voice_assignment_mode,
        reset_operations,
        tuple(affected),
        tuple(sorted(artifacts)),
        replacement_targets,
        original_targets_bytes,
    )


@trace_function(_PROJECT_OPTIONS_LOGGER)
def apply_project_options_change(plan: ProjectOptionsChange) -> dict[str, object]:
    """
    @brief      Publish the confirmed plan, restoring staged originals on failure.
    @param[in]  plan Exact plan shown to the operator, while no worker is active.
    @return     Persisted manifest, with affected progress reset coherently.
    @exception  ValueError Raised when the manifest or voice plan changed since planning.
    @exception  OSError Raised after rollback on staging or publication failure.
    """
    root = plan.project_root
    manifest_path = root / config.PROJECT_MANIFEST_FILE_NAME
    if manifest_path.read_bytes() != plan.original_manifest_bytes:
        raise ValueError("Project changed while confirming options; select the option again.")
    if not plan.changed:
        return plan.manifest
    targets_path = root / config.CHARACTER_VOICES_TARGETS_FILE_NAME
    if plan.original_targets_bytes is not None and targets_path.read_bytes() != plan.original_targets_bytes:
        raise ValueError("Character Voices changed while confirming options; select the option again.")
    updated = deepcopy(plan.manifest)
    for kind in plan.reset_operations:
        updated["operations"][kind] = project_workspace_service.project_manifest_operation_summary(kind)
    boundary = "text_chunking_ready" if plan.language_changed else "narrator_definition_ready"
    stages = config.PROJECT_WORKFLOW_STAGES
    if stages.index(str(updated["current_stage"])) > stages.index(boundary):
        updated["current_stage"] = boundary
    if plan.language_changed:
        updated["narrator_profile_name"] = None
        updated["narrator_language"] = None
        updated["selected_voice_language"] = plan.target_language
    updated["target_language"] = plan.target_language
    updated["voice_assignment_mode"] = plan.voice_assignment_mode
    staged_paths = list(plan.artifact_paths)
    if plan.replacement_targets is not None:
        staged_paths.append(targets_path)
    staged_paths.append(manifest_path)
    for path in staged_paths:
        if path.resolve() != path or path.is_symlink() or not path.is_relative_to(root):
            raise ValueError(f"Reset artifact path is redirected or outside the project: {path}")
    backup_root = Path(tempfile.mkdtemp(prefix=".audiomancer-options-", dir=root))
    moved = []
    published = []
    recovered = False
    try:
        for path in staged_paths:
            # Relative names keep every original identifiable if rollback is denied.
            backup = backup_root / path.relative_to(root)
            backup.parent.mkdir(parents=True, exist_ok=True)
            path.replace(backup)
            moved.append((path, backup))
        if plan.replacement_targets is not None:
            write_json_atomic(targets_path, plan.replacement_targets)
            published.append(targets_path)
        project_workspace_service.save_manifest(updated, root)
        published.append(manifest_path)
        result = project_workspace_service.load_manifest(root)
        recovered = True
        return result
    except (OSError, ValueError):
        try:
            for path in published:
                path.unlink(missing_ok=True)
            for path, backup in reversed(moved):
                backup.replace(path)
            recovered = True
        except OSError as recovery_error:
            raise OSError(
                f"Could not restore project files; recovery originals retained in {backup_root}"
            ) from recovery_error
        raise
    finally:
        if recovered:
            try:
                shutil.rmtree(backup_root)
            except OSError:
                _PROJECT_OPTIONS_LOGGER.exception("Could not remove option-change backup %s", backup_root)


# END OF FILE
