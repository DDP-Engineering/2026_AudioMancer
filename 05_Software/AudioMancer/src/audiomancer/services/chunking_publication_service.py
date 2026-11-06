#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chunking_publication_service.py
@brief Recoverable publication of Chunking and selective manual changes.
@details Prepares results off the live project, moves owned originals into a
         relative backup and retains identifiable originals if restoration fails.
"""

# IMPORTS

import filecmp
import os
from pathlib import Path
import shutil
import tempfile

from audiomancer import config
from audiomancer.services import chunking_document_service as documents
from audiomancer.services import operation_runtime_service as runtime
from audiomancer.services import project_workspace_service as workspace
from audiomancer.services.logging_service import get_component_logger, trace_function

# CONSTANTS

_LOGGER = get_component_logger("chunking_publication")
_AUDIO_SUFFIXES = frozenset((".wav", ".mp3", ".m4b", ".flac", ".ogg", ".aac", ".opus", ".mp4"))

# PUBLIC API


@trace_function(_LOGGER)
def publish_chunks(root: Path, document: dict, *, check_cancelled=None) -> None:
    """@brief Stage completed chunks and manifest, then recoverably reset dependent work.
    @exception OSError Publication failed; originals restored or retained in the named backup.
    """
    root = root.resolve()
    document = documents.validate_chunking_document(document)
    if document["status"] != "completed":
        raise ValueError("Only completed Chunking results can be published.")
    preserved = runtime.TEXT_REVISION_PRESERVED_OPERATION_KINDS
    kinds = tuple(
        kind for kind in runtime.downstream_operation_kinds("chunking", include_current=True) if kind not in preserved
    )
    originals = {
        path
        for path in _owned_paths(root, kinds)
        if not path.name.startswith(f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}chunking_")
    }
    manifest_path = root / config.PROJECT_MANIFEST_FILE_NAME
    before = manifest_path.read_bytes()
    manifest = workspace.build_manifest_after_operation_reset(
        workspace.load_manifest(root), "chunking", preserve_operation_kinds=preserved
    )
    manifest["operations"]["chunking"] = workspace.project_manifest_operation_summary(
        "chunking", documents.derive_operation_state(document)
    )
    manifest["current_stage"] = "translation_ready"
    with tempfile.TemporaryDirectory(prefix=".chunking-stage-", dir=root) as name:
        stage = Path(name)
        documents.write_chunking_document(stage, document)
        workspace.save_manifest(manifest, stage)
        changes = {path.relative_to(root): None for path in originals}
        for filename in (config.CHUNK_ARTIFACT_FILE_NAME, config.PROJECT_MANIFEST_FILE_NAME):
            changes[Path(filename)] = stage / filename
        if check_cancelled is not None:
            check_cancelled()
        _publish(root, changes, before)


@trace_function(_LOGGER)
def publish_manual_change(root: Path, mutation):
    """@brief Apply selective services to a staged snapshot, then publish changed owned files.
    @param[in] mutation Callable accepting the isolated project root and returning its manifest.
    @exception OSError Preparation or publication failed without a partially applied live edit.
    """
    root = root.resolve()
    kinds = runtime.downstream_operation_kinds("chunking", include_current=True)
    originals = _owned_paths(root, kinds)
    manifest_path = root / config.PROJECT_MANIFEST_FILE_NAME
    before = manifest_path.read_bytes()
    with tempfile.TemporaryDirectory(prefix=".chunking-edit-", dir=root) as name:
        stage = Path(name)
        for path in originals:
            destination = stage / path.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix.lower() in _AUDIO_SUFFIXES:
                try:
                    os.link(path, destination)
                    continue
                except OSError:
                    pass
            shutil.copy2(path, destination)
        # First manual insertion needs the verified Cleanup input, which remains read-only.
        for filename in (config.CLEANED_TEXT_FILE_NAME, config.CLEANUP_DOCUMENT_FILE_NAME):
            path = root / filename
            if path.is_file():
                _validate_path(root, path)
                shutil.copy2(path, stage / filename)
        result = mutation(stage)
        staged = _owned_paths(stage, kinds)
        relative_names = {path.relative_to(root) for path in originals} | {path.relative_to(stage) for path in staged}
        changes = {}
        for relative in relative_names:
            live, candidate = root / relative, stage / relative
            if (
                live.is_file()
                and candidate.is_file()
                and (os.path.samefile(live, candidate) or filecmp.cmp(live, candidate, shallow=False))
            ):
                continue
            changes[relative] = candidate if candidate.is_file() else None
        _publish(root, changes, before)
        return result


# LOCAL HELPERS


def _owned_paths(root: Path, kinds) -> set[Path]:
    """@brief Collect existing operation-owned artifacts with manifest and source-overlap checks."""
    paths = {root / config.PROJECT_MANIFEST_FILE_NAME}
    for kind in kinds:
        paths.update(runtime.operation_reset_artifact_paths(root, kind))
    manifest = workspace.load_manifest(root)
    source = manifest.get("source_document")
    source_path = (
        None
        if not isinstance(source, dict)
        else root / runtime.validate_project_relative_path(source["stored_relative_path"])
    )
    for path in paths:
        _validate_path(root, path)
        if path == source_path:
            raise ValueError("Registered source overlaps a Chunking-owned artifact.")
    return paths


def _validate_path(root: Path, path: Path) -> None:
    """@brief Reject redirected or escaped publication destinations before changing files."""
    if not path.is_relative_to(root) or path == root or path.resolve() != path or path.is_symlink():
        raise ValueError(f"Chunking artifact is redirected or outside the project: {path}")


def _publish(root: Path, changes: dict[Path, Path | None], original_manifest: bytes) -> None:
    """@brief Replace a prepared set, restoring originals on every caught publication failure."""
    for relative in changes:
        _validate_path(root, root / relative)
    if (root / config.PROJECT_MANIFEST_FILE_NAME).read_bytes() != original_manifest:
        raise ValueError("Project changed during Chunking publication; retry the operation.")
    backup = Path(tempfile.mkdtemp(prefix=".chunking-backup-", dir=root))
    moved, published = [], []
    recovered = False
    try:
        for relative in sorted(changes):
            path = root / relative
            if path.is_file():
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                path.replace(saved)
                moved.append((path, saved))
        for relative, candidate in changes.items():
            if candidate is not None:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                candidate.replace(destination)
                published.append(destination)
        recovered = True
    except Exception:
        try:
            for path in reversed(published):
                path.unlink(missing_ok=True)
            for path, saved in reversed(moved):
                saved.replace(path)
            recovered = True
        except OSError as error:
            raise OSError(f"Chunking recovery could not finish; originals retained in {backup}") from error
        raise
    finally:
        if recovered:
            try:
                shutil.rmtree(backup)
            except OSError:
                _LOGGER.exception("Could not remove Chunking backup %s", backup)


# END OF FILE
