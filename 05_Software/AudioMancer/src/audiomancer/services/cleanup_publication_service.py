#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file cleanup_publication_service.py
@brief Recoverable publication of validated Cleanup results.
@details Stages the text, metadata and manifest before moving reset-owned
         originals into a relative-path backup and restoring them on IO failure.
"""

# IMPORTS

from pathlib import Path
import shutil
import tempfile

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import (
    downstream_operation_kinds,
    operation_reset_artifact_paths,
)
from audiomancer.services.persistence_service import write_json_atomic, write_text_atomic

# CONSTANTS

_LOGGER = get_component_logger("cleanup_publication")

# PUBLIC API


@trace_function(_LOGGER)
def publish_cleanup(
    root: Path, text: str, document: dict[str, object], summary: dict[str, object], *, check_cancelled=None
) -> None:
    """
    @brief Publish a validated result and reset downstream artifacts as one recoverable change.
    @param[in] root Active project root.
    @param[in] text Validated cleaned text.
    @param[in] document Validated completed Cleanup metadata.
    @param[in] summary Compact manifest operation summary.
    @param[in] check_cancelled Caller checkpoint raising before mutation.
    @exception OSError IO failed; originals restored or retained in a named recovery folder.
    @exception ValueError Unsafe paths or concurrent manifest changes.
    """
    # Project Lifecycle imports Cleanup loaders; keep this dependency acyclic.
    from audiomancer.services import project_workspace_service

    root = root.resolve()
    manifest_path = root / config.PROJECT_MANIFEST_FILE_NAME
    original_manifest = manifest_path.read_bytes()
    manifest = project_workspace_service.load_manifest(root)
    updated = project_workspace_service.build_manifest_after_operation_reset(manifest, "chunking")
    updated["operations"]["cleanup"] = project_workspace_service.project_manifest_operation_summary("cleanup", summary)
    updated["original_language"] = document["document_profile"].get("language")
    originals = {manifest_path}
    for kind in downstream_operation_kinds("chunking", include_current=True):
        originals.update(operation_reset_artifact_paths(root, kind))
    names = (config.CLEANED_TEXT_FILE_NAME, config.CLEANUP_DOCUMENT_FILE_NAME, config.PROJECT_MANIFEST_FILE_NAME)
    for name in (*names, config.CLEANUP_PENDING_FILE_NAME):
        path = root / name
        if path.exists():
            originals.add(path)
    for path in [*originals, *(root / name for name in names)]:
        if path.resolve() != path or path.is_symlink() or not path.is_relative_to(root):
            raise ValueError(f"Cleanup artifact is redirected or outside the project: {path}")
    source = root / str(manifest["source_document"]["stored_relative_path"])
    if source in originals:
        raise ValueError("Registered source overlaps a Cleanup artifact.")

    with tempfile.TemporaryDirectory(prefix=".cleanup-stage-", dir=root) as stage_name:
        stage = Path(stage_name)
        write_text_atomic(stage / config.CLEANED_TEXT_FILE_NAME, text)
        write_json_atomic(stage / config.CLEANUP_DOCUMENT_FILE_NAME, document)
        project_workspace_service.save_manifest(updated, stage)
        if check_cancelled is not None:
            check_cancelled()
        if manifest_path.read_bytes() != original_manifest:
            raise ValueError("Project changed during Cleanup publication; run Cleanup again.")
        backup = Path(tempfile.mkdtemp(prefix=".cleanup-backup-", dir=root))
        moved = []
        published = []
        recovered = False
        try:
            for path in sorted(originals):
                destination = backup / path.relative_to(root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                path.replace(destination)
                moved.append((path, destination))
            for name in names:
                destination = root / name
                published.append(destination)
                (stage / name).replace(destination)
            recovered = True
        except (OSError, ValueError):
            try:
                for path in published:
                    path.unlink(missing_ok=True)
                for path, saved in reversed(moved):
                    saved.replace(path)
                recovered = True
            except OSError as error:
                raise OSError(f"Cleanup recovery could not finish; originals retained in {backup}") from error
            raise
        finally:
            if recovered:
                try:
                    shutil.rmtree(backup)
                except OSError:
                    _LOGGER.exception("Could not remove Cleanup backup %s", backup)


# END OF FILE
