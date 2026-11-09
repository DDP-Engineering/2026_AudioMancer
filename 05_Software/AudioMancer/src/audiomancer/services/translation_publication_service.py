#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file translation_publication_service.py
@brief Publish translation review and its workflow effects recoverably.
@details Compare verified narration sources before retiring dependent files.
"""

# IMPORTS

from pathlib import Path
import tempfile

from audiomancer import config
from audiomancer.services import chunking_document_service, operation_runtime_service, project_workspace_service
from audiomancer.services.logging_service import get_component_logger, trace_function
from audiomancer.services.persistence_service import replace_project_files, validate_publication_path
from audiomancer.translation.document import (
    TRANSLATION_STATUS_COMPLETED,
    TranslationDocumentError,
    build_translation_summary,
    canonical_source_chunks,
    resolve_approved_translation,
)

# CONSTANTS

_LOGGER = get_component_logger("translation_publication")

# PUBLIC API


def source_dependent_operations() -> tuple[str, ...]:
    """@brief Identify the operations whose results depend on the selected narration text."""
    return tuple(
        kind
        for kind in operation_runtime_service.downstream_operation_kinds("translation")
        if kind not in operation_runtime_service.NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS
    )


@trace_function(_LOGGER)
def publish_translation(
    project_root: str | Path,
    candidate: dict[str, object] | None,
    source_chunks: list[dict[str, object]],
    *,
    check_cancelled=None,
) -> dict[str, object]:
    """@brief Publish the candidate, workflow summary and source-dependent reset together.
    @param[in] candidate Prepared translation document, or None for a confirmed reset.
    @param[in] source_chunks Canonical source snapshot used by the operation.
    @param[in] check_cancelled Optional final cancellation check before replacing live files.
    @return Current translation summary after successful publication.
    @exception OSError Publication failed and was recovered, or originals remain in a named backup.
    """
    # The orchestrator owns the disk document API and calls this publication boundary.
    from audiomancer.services import ai_translation_service

    root = Path(project_root).resolve()
    manifest_path = root / config.PROJECT_MANIFEST_FILE_NAME
    before = manifest_path.read_bytes()
    manifest = project_workspace_service.load_manifest(root)
    target = ai_translation_service.manifest_target_language(manifest)
    if canonical_source_chunks(source_chunks) != canonical_source_chunks(chunking_document_service.load_chunks(root)):
        raise ValueError("The canonical chunks changed during translation. Retry the operation.")

    invalid_document = False
    try:
        previous = ai_translation_service.load_translation_document(root)
    except TranslationDocumentError:
        if candidate is not None:
            raise
        previous = None
        invalid_document = True

    before_source = resolve_approved_translation(source_chunks, previous, target)
    after_source = resolve_approved_translation(source_chunks, candidate, target)
    source_changed = invalid_document or before_source != after_source
    downstream = operation_runtime_service.downstream_operation_kinds("translation", include_current=False)
    reset_kinds = set(source_dependent_operations()) if source_changed else set()
    if candidate is None:
        reset_kinds.add("translation")
    original_stage = manifest.get("current_stage")
    updated = project_workspace_service.build_manifest_after_operation_reset(
        manifest, "translation", preserve_operation_kinds=set(downstream) - reset_kinds
    )
    summary = build_translation_summary(source_chunks, candidate)
    if candidate is not None:
        updated["operations"]["translation"] = project_workspace_service.project_manifest_operation_summary(
            "translation",
            {
                "status": summary["status"],
                "mode": "ai_assisted",
                "progress_current": summary["translated_count"],
                "progress_total": summary["total_count"],
            },
        )
    if source_changed or original_stage in {"translation_ready", "text_chunking_ready"}:
        if candidate is None:
            updated["current_stage"] = "text_chunking_ready"
        elif summary["status"] == TRANSLATION_STATUS_COMPLETED:
            updated["current_stage"] = "character_discovery_ready"
        else:
            updated["current_stage"] = "translation_ready"
    else:
        updated["current_stage"] = original_stage

    artifacts = {
        path for kind in reset_kinds for path in operation_runtime_service.operation_reset_artifact_paths(root, kind)
    }
    doc_name = Path(config.TRANSLATED_CHUNKS_FILE_NAME)
    source = manifest.get("source_document")
    if isinstance(source, dict):
        relative = Path(operation_runtime_service.validate_project_relative_path(source["stored_relative_path"]))
        if root / relative in artifacts or relative in {doc_name, Path(manifest_path.name)}:
            raise ValueError("Registered source overlaps a Translation-owned artifact.")
    changes = {path.relative_to(root): None for path in sorted(artifacts)}
    validate_publication_path(root, root / doc_name, "Translation")
    with tempfile.TemporaryDirectory(prefix=".translation-stage-", dir=root) as name:
        stage = Path(name)
        if candidate is not None:
            changes[doc_name] = ai_translation_service.write_translation_document(stage, candidate)
        project_workspace_service.save_manifest(updated, stage)
        changes[Path(manifest_path.name)] = stage / manifest_path.name
        if check_cancelled is not None:
            check_cancelled()
        replace_project_files(root, changes, manifest_path, before, "Translation")
    return summary


# END OF FILE
