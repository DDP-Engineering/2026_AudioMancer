#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file extraction_publication_service.py
@brief Publish validated extraction outputs and reset dependent data as one recoverable change.
@details Stages originals under their project-relative names and restores them on IO failure.
"""

# IMPORTS

from pathlib import Path
import shutil
import tempfile

from audiomancer import config
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.operation_runtime_service import operation_reset_artifact_paths

# CONSTANTS

_LOGGER = get_component_logger("extraction_publication")

# PUBLIC API


@trace_function(_LOGGER)
def publish_extraction(root: Path, manifest: dict[str, object], staged: Path, original_manifest: bytes) -> None:
    """
    @brief Replace extraction and invalidate dependent results only after complete validation.
    @param[in] root Resolved project workspace.
    @param[in] manifest Input manifest snapshot used by the extraction worker.
    @param[in] staged Validated new text, ledger and metadata in the same filesystem.
    @param[in] original_manifest Manifest bytes captured before parsing.
    @return None.
    @exception OSError Publication failed; originals restored or retained in a named recovery folder.
    @exception ValueError Project state or artifact paths changed before publication.
    """
    # Local import keeps Project Lifecycle's extraction-reader dependency acyclic.
    from audiomancer.services import project_workspace_service

    manifest_path = root / config.PROJECT_MANIFEST_FILE_NAME
    if manifest_path.read_bytes() != original_manifest:
        raise ValueError("Project changed during extraction; run extraction again.")
    updated = project_workspace_service.build_manifest_after_operation_reset(manifest, "extraction")
    project_workspace_service.save_manifest(updated, staged)
    originals = {manifest_path}
    for kind in config.PROJECT_OPERATION_KINDS:
        originals.update(operation_reset_artifact_paths(root, kind))
    source = root / str(manifest["source_document"]["stored_relative_path"])
    if source in originals:
        raise ValueError("The registered source overlaps a generated extraction artifact.")
    replacements = [
        staged / name
        for name in (
            config.EXTRACTED_TEXT_FILE_NAME,
            config.SOURCE_LEDGER_FILE_NAME,
            config.EXTRACTION_METADATA_FILE_NAME,
            config.PROJECT_MANIFEST_FILE_NAME,
        )
    ]
    for path in [*originals, *(root / item.name for item in replacements)]:
        if path.resolve() != path or path.is_symlink() or not path.is_relative_to(root):
            raise ValueError(f"Extraction artifact is redirected or outside the project: {path}")
    backup = Path(tempfile.mkdtemp(prefix=".extraction-backup-", dir=root))
    moved = []
    published = []
    recovered = False
    try:
        for path in sorted(originals):
            destination = backup / path.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            path.replace(destination)
            moved.append((path, destination))
        for path in replacements:
            destination = root / path.name
            published.append(destination)
            path.replace(destination)
        recovered = True
    except (OSError, ValueError):
        try:
            for path in published:
                path.unlink(missing_ok=True)
            for path, original in reversed(moved):
                original.replace(path)
            recovered = True
        except OSError as error:
            raise OSError(f"Extraction recovery could not finish; originals retained in {backup}") from error
        raise
    finally:
        if recovered:
            try:
                shutil.rmtree(backup)
            except OSError:
                _LOGGER.exception("Could not remove extraction backup %s", backup)


# END OF FILE
