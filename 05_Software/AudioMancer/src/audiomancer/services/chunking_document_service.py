#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chunking_document_service.py
@brief Chunking persistence and project-path projections.
@details Pure validation lives in chunking.document; this service owns canonical and checkpoint IO.
"""

# IMPORTS

from copy import deepcopy
import json
from pathlib import Path

from audiomancer import config
from audiomancer.chunking.document import (
    CHUNK_FIELDS as CHUNK_FIELDS,
)
from audiomancer.chunking.document import (
    DOCUMENT_FIELDS as DOCUMENT_FIELDS,
)
from audiomancer.chunking.document import (
    RESUMABLE_STATUSES as RESUMABLE_STATUSES,
)
from audiomancer.chunking.document import (
    SUPPORTED_MODES as SUPPORTED_MODES,
)
from audiomancer.chunking.document import (
    SUPPORTED_STATUSES as SUPPORTED_STATUSES,
)
from audiomancer.chunking.document import (
    TERMINAL_STATUSES as TERMINAL_STATUSES,
)
from audiomancer.chunking.document import (
    TOKEN_USAGE_FIELDS as TOKEN_USAGE_FIELDS,
)
from audiomancer.chunking.document import (
    ChunkingDocument as ChunkingDocument,
)
from audiomancer.chunking.document import (
    ChunkPayload as ChunkPayload,
)
from audiomancer.chunking.document import (
    IncompatibleChunkingDocumentError as IncompatibleChunkingDocumentError,
)
from audiomancer.chunking.document import (
    _chapter_count as _chapter_count,
)
from audiomancer.chunking.document import (
    build_document as build_document,
)
from audiomancer.chunking.document import (
    chapter_label_from_text as chapter_label_from_text,
)
from audiomancer.chunking.document import (
    derive_report as derive_report,
)
from audiomancer.chunking.document import (
    empty_token_usage as empty_token_usage,
)
from audiomancer.chunking.document import (
    source_fingerprint as source_fingerprint,
)
from audiomancer.chunking.document import (
    validate_chunking_document as validate_chunking_document,
)
from audiomancer.services.persistence_service import write_json_atomic

# CONSTANTS

_RESET_MESSAGE = "Chunking data is incompatible. Use Reset Chunking before continuing."

# PUBLIC API


def document_path(project_root: str | Path) -> Path:
    """
    @brief      Return the authoritative project-local Chunking document path.
    @param[in]  project_root Active project root.
    @return     Absolute or caller-relative document path.
    """
    return Path(project_root) / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHUNK_ARTIFACT_FILE_NAME


def load_chunking_document(project_root: str | Path, *, pending: bool = False) -> ChunkingDocument | None:
    """
    @brief      Load and strictly validate the authoritative Chunking document.
    @param[in]  project_root Active project root.
    @return     Defensive validated document or None when absent.
    @exception  IncompatibleChunkingDocumentError Raised for unreadable or invalid data.
    """
    path = (Path(project_root) / config.CHUNKING_PENDING_FILE_NAME) if pending else document_path(project_root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IncompatibleChunkingDocumentError(_RESET_MESSAGE) from error
    return validate_chunking_document(payload)


def write_chunking_document(project_root: str | Path, document: object) -> Path:
    """
    @brief      Validate and atomically replace the authoritative Chunking document.
    @param[in]  project_root Active project root.
    @param[in]  document Candidate exact document payload.
    @return     Persisted document path.
    @exception  IncompatibleChunkingDocumentError Raised for invalid data.
    """
    validated = validate_chunking_document(document)
    path = document_path(project_root)
    write_json_atomic(path, validated)
    return path


def load_chunks(project_root: str | Path) -> list[ChunkPayload]:
    """
    @brief      Return defensive copies of canonical chunks or an empty list when absent.
    @param[in]  project_root Active project root.
    @return     Ordered exact chunk payload copies.
    """
    document = load_chunking_document(project_root)
    if document is None:
        return []
    return deepcopy(document["chunks"])


def derive_operation_state(document: ChunkingDocument) -> dict[str, object]:
    """
    @brief      Derive the compact manifest and UI operation view without persistence.
    @param[in]  document Strict Chunking document.
    @return     Non-persisted operation-state projection.
    """
    report = derive_report(document)
    return {
        "status": report["status"],
        "mode": report["mode"],
        "warning_count": report["warning_count"],
        "metadata": {
            "warnings": report["warnings"],
            "chunk_count": report["chunk_count"],
            "detected_chapter_count": report["detected_chapter_count"],
            "semantic_strategy": report["semantic_strategy"],
            "token_usage": report["token_usage"],
            "manual_adjusted": report["manual_adjusted"],
            "next_paragraph": document["next_paragraph"],
            "additional_chunking_instructions": document["additional_chunking_instructions"],
        },
        "input_paths": [config.CLEANED_TEXT_FILE_NAME],
        "output_paths": [config.CHUNK_ARTIFACT_FILE_NAME],
        "artifact_paths": [],
    }


def load_checkpoint(project_root: str | Path) -> ChunkingDocument | None:
    """@brief Prefer an isolated replacement checkpoint over the published document."""
    return load_chunking_document(project_root, pending=True) or load_chunking_document(project_root)


def write_checkpoint(project_root: str | Path, document: object, *, pending: bool = False) -> Path:
    """@brief Checkpoint without overwriting a completed published result."""
    published = None if pending else load_chunking_document(project_root)
    if pending or (published is not None and published["status"] == "completed"):
        path = Path(project_root) / config.CHUNKING_PENDING_FILE_NAME
        write_json_atomic(path, validate_chunking_document(document))
        return path
    return write_chunking_document(project_root, document)


# END OF FILE
