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
@brief Strict persistence boundary for the authoritative Chunking document.
@details Validates and atomically stores the one supported `chunks_text.json`
         root-object contract and exposes defensive derived views to callers.
"""

# IMPORTS

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services.persistence_service import write_json_atomic

# CONSTANTS

DOCUMENT_FIELDS = frozenset(
    {
        "status",
        "mode",
        "manual_adjusted",
        "source_fingerprint",
        "semantic_strategy",
        "additional_chunking_instructions",
        "token_usage",
        "warnings",
        "next_paragraph",
        "context_window_fallback_count",
        "chunks",
    }
)
CHUNK_FIELDS = frozenset(
    {
        "chunk_id",
        "sequence_index",
        "text",
        "cleanup_boundary_confidence",
        "cleanup_joined_across_page_break",
        "cleanup_warning_flags",
        "cleanup_role",
        "starts_after_scene_separator",
    }
)
_ROMAN_NUMERAL_PATTERN = re.compile(
    r"(?=[MDCLXVI]+$)M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
)
_CHAPTER_PATTERNS = (
    re.compile(r"^(chapter|capitolul|scene|scena)\s+[\wIVXLCDM0-9][\wIVXLCDM0-9 .:-]*$", re.IGNORECASE),
    _ROMAN_NUMERAL_PATTERN,
)
TOKEN_USAGE_FIELDS = frozenset({"input_tokens", "output_tokens", "total_tokens", "usage_available"})
RESUMABLE_STATUSES = frozenset({"running", "cancelled", "failed"})
TERMINAL_STATUSES = frozenset({"completed"})
SUPPORTED_STATUSES = RESUMABLE_STATUSES | TERMINAL_STATUSES
SUPPORTED_MODES = frozenset({"deterministic", "ai_assisted"})
_FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_CHUNK_ID_PATTERN = re.compile(r"^chunk-[0-9]{4,}$")
_RESET_MESSAGE = "Chunking data is incompatible. Use Reset Chunking before continuing."

# TYPES

ChunkingDocument = dict[str, object]
ChunkPayload = dict[str, object]


class IncompatibleChunkingDocumentError(ValueError):
    """
    @brief      Signal that persisted Chunking data requires Reset Chunking.
    """


def chapter_label_from_text(chunk_text: str) -> str | None:
    """
    @brief      Return the first canonical chapter or scene heading in chunk text.
    @param[in]  chunk_text Text whose lines should be scanned in order.
    @return     Normalized first chapter label or `None`.
    @exception  None
    """
    for line in chunk_text.splitlines():
        normalized = line.strip()
        if len(normalized) > 100:
            continue
        if any(pattern.fullmatch(normalized) for pattern in _CHAPTER_PATTERNS):
            return normalized
    return None


def empty_token_usage() -> dict[str, object]:
    """
    @brief      Return the canonical empty cumulative token-usage object.
    @return     Exact unavailable token-usage payload with integer counters.
    """
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "usage_available": False,
    }


def source_fingerprint(source_text: str) -> str:
    """
    @brief      Return the canonical SHA-256 identity for cleaned source text.
    @param[in]  source_text Canonical cleaned source text.
    @return     Prefixed lowercase SHA-256 fingerprint.
    """
    return f"sha256:{sha256(source_text.encode('utf-8')).hexdigest()}"


def document_path(project_root: str | Path) -> Path:
    """
    @brief      Return the authoritative project-local Chunking document path.
    @param[in]  project_root Active project root.
    @return     Absolute or caller-relative document path.
    """
    return Path(project_root) / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHUNK_ARTIFACT_FILE_NAME


def load_chunking_document(project_root: str | Path) -> ChunkingDocument | None:
    """
    @brief      Load and strictly validate the authoritative Chunking document.
    @param[in]  project_root Active project root.
    @return     Defensive validated document or None when absent.
    @exception  IncompatibleChunkingDocumentError Raised for unreadable or invalid data.
    """
    path = document_path(project_root)
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


def validate_chunking_document(payload: object) -> ChunkingDocument:
    """
    @brief      Return a defensive validated document or raise Reset Chunking guidance.
    @param[in]  payload Candidate persisted root value.
    @return     Defensive exact document copy.
    @exception  IncompatibleChunkingDocumentError Raised for every incompatible value.
    """
    try:
        _validate_document_shape(payload)
    except (TypeError, ValueError, KeyError) as error:
        if isinstance(error, IncompatibleChunkingDocumentError):
            raise
        raise IncompatibleChunkingDocumentError(_RESET_MESSAGE) from error
    return deepcopy(payload)


def build_document(
    *,
    status: str,
    mode: str,
    source_text: str,
    chunks: list[ChunkPayload],
    semantic_strategy: str | None = None,
    additional_chunking_instructions: str = "",
    token_usage: dict[str, object] | None = None,
    warnings: list[str] | None = None,
    next_paragraph: int | None = None,
    context_window_fallback_count: int = 0,
    manual_adjusted: bool = False,
) -> ChunkingDocument:
    """
    @brief      Build one exact validated document from runtime values.
    @param[in]  status Operation status token under evaluation.
    @param[in]  mode Stable chunking mode token.
    @param[in]  source_text Canonical source text processed by the callable.
    @param[in]  chunks Ordered canonical chunk payloads.
    @param[in]  semantic_strategy Selected semantic chunking strategy token.
    @param[in]  additional_chunking_instructions Optional operator-supplied chunking rules.
    @param[in]  token_usage Cumulative AI token-usage metadata.
    @param[in]  warnings Ordered persisted contract warnings.
    @param[in]  next_paragraph Absolute index of the next paragraph awaiting processing.
    @param[in]  context_window_fallback_count Number of context-window fallback retries.
    @param[in]  manual_adjusted Whether an operator manually changed canonical chunks.
    @return     Defensive strict document payload.
    @exception  IncompatibleChunkingDocumentError Raised when runtime values violate the contract.
    """
    document: ChunkingDocument = {
        "status": status,
        "mode": mode,
        "manual_adjusted": manual_adjusted,
        "source_fingerprint": source_fingerprint(source_text),
        "semantic_strategy": semantic_strategy,
        "additional_chunking_instructions": additional_chunking_instructions,
        "token_usage": deepcopy(token_usage) if token_usage is not None else empty_token_usage(),
        "warnings": list(warnings or []),
        "next_paragraph": next_paragraph,
        "context_window_fallback_count": context_window_fallback_count,
        "chunks": deepcopy(chunks),
    }
    return validate_chunking_document(document)


def derive_report(document: ChunkingDocument) -> dict[str, object]:
    """
    @brief      Derive the transient report view used by callers and exports.
    @param[in]  document Strict Chunking document.
    @return     Non-persisted report projection.
    """
    validated = validate_chunking_document(document)
    chunks = list(validated["chunks"])
    return {
        "warnings": list(validated["warnings"]),
        "warning_count": len(validated["warnings"]),
        "chunk_count": len(chunks),
        "detected_chapter_count": _chapter_count(chunks),
        "chunking_mode": validated["mode"],
        "mode": validated["mode"],
        "semantic_strategy": validated["semantic_strategy"],
        "additional_chunking_instructions": validated["additional_chunking_instructions"],
        "token_usage": deepcopy(validated["token_usage"]),
        "context_window_fallback_count": validated["context_window_fallback_count"],
        "manual_adjusted": validated["manual_adjusted"],
        "status": validated["status"],
    }


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


def _validate_document_shape(payload: object) -> None:
    """
    @brief      Validate exact root, lifecycle, usage, and chunk invariants.
    @param[in]  payload Candidate root value.
    @return     None.
    @exception  TypeError Raised when invalid chunks.
    @exception  ValueError Raised when resumable document requires next paragraph.
    """
    if not isinstance(payload, dict) or set(payload) != DOCUMENT_FIELDS:
        raise TypeError("invalid root fields")
    status = payload["status"]
    mode = payload["mode"]
    if status not in SUPPORTED_STATUSES or mode not in SUPPORTED_MODES:
        raise ValueError("invalid status or mode")
    if not isinstance(payload["manual_adjusted"], bool):
        raise TypeError("invalid manual flag")
    fingerprint = payload["source_fingerprint"]
    if not isinstance(fingerprint, str) or _FINGERPRINT_PATTERN.fullmatch(fingerprint) is None:
        raise ValueError("invalid source fingerprint")
    strategy = payload["semantic_strategy"]
    if mode == "deterministic" and strategy is not None:
        raise ValueError("deterministic strategy must be null")
    if mode == "ai_assisted" and strategy not in config.AI_CHUNKING_STRATEGY_OPTIONS:
        raise ValueError("invalid AI strategy")
    instructions = payload["additional_chunking_instructions"]
    if not isinstance(instructions, str) or (mode == "deterministic" and instructions):
        raise TypeError("invalid instructions")
    _validate_token_usage(payload["token_usage"])
    warnings = payload["warnings"]
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
        raise TypeError("invalid warnings")
    next_paragraph = payload["next_paragraph"]
    if status == "completed" and next_paragraph is not None:
        raise ValueError("completed document cannot retain a checkpoint")
    if status in RESUMABLE_STATUSES and (
        not isinstance(next_paragraph, int) or isinstance(next_paragraph, bool) or next_paragraph < 1
    ):
        raise ValueError("resumable document requires next paragraph")
    fallback_count = payload["context_window_fallback_count"]
    if not isinstance(fallback_count, int) or isinstance(fallback_count, bool) or fallback_count < 0:
        raise TypeError("invalid fallback count")
    chunks = payload["chunks"]
    if not isinstance(chunks, list):
        raise TypeError("invalid chunks")
    seen_ids: set[str] = set()
    for expected_index, chunk in enumerate(chunks, start=1):
        _validate_chunk(chunk, expected_index, seen_ids)


def _validate_token_usage(payload: object) -> None:
    """
    @brief      Validate exact cumulative token-usage fields and arithmetic.
    @param[in]  payload Candidate usage object.
    @return     None.
    @exception  TypeError Raised when invalid usage flag.
    @exception  ValueError Raised when token totals do not balance.
    """
    if not isinstance(payload, dict) or set(payload) != TOKEN_USAGE_FIELDS:
        raise TypeError("invalid token usage fields")
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        value = payload[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise TypeError("invalid token count")
    if payload["total_tokens"] != payload["input_tokens"] + payload["output_tokens"]:
        raise ValueError("token totals do not balance")
    if not isinstance(payload["usage_available"], bool):
        raise TypeError("invalid usage flag")


def _validate_chunk(chunk: object, expected_index: int, seen_ids: set[str]) -> None:
    """
    @brief      Validate one exact canonical chunk record.
    @param[in]  chunk Candidate chunk value.
    @param[in]  expected_index Required sequence index.
    @param[in,out] seen_ids Previously validated stable identifiers.
    @return     None.
    @exception  TypeError Raised when invalid cleanup warning flags.
    @exception  ValueError Raised when invalid chunk ordering.
    """
    if not isinstance(chunk, dict) or set(chunk) != CHUNK_FIELDS:
        raise TypeError("invalid chunk fields")
    chunk_id = chunk["chunk_id"]
    if not isinstance(chunk_id, str) or _CHUNK_ID_PATTERN.fullmatch(chunk_id) is None or chunk_id in seen_ids:
        raise ValueError("invalid chunk id")
    seen_ids.add(chunk_id)
    if chunk["sequence_index"] != expected_index:
        raise ValueError("invalid chunk ordering")
    if not isinstance(chunk["text"], str):
        raise TypeError("invalid chunk text")
    confidence = chunk["cleanup_boundary_confidence"]
    if confidence is not None and not isinstance(confidence, str):
        raise TypeError("invalid cleanup confidence")
    if not isinstance(chunk["cleanup_joined_across_page_break"], bool):
        raise TypeError("invalid page-break flag")
    flags = chunk["cleanup_warning_flags"]
    if not isinstance(flags, list) or any(not isinstance(item, str) for item in flags):
        raise TypeError("invalid cleanup warning flags")
    if chunk["cleanup_role"] not in {
        "body",
        "heading",
        "scene_separator",
        "list_item",
        "verse",
        "preformatted",
        "footnote",
    }:
        raise ValueError("invalid cleanup role")
    if not isinstance(chunk["starts_after_scene_separator"], bool):
        raise TypeError("invalid scene-separator boundary flag")


def _chapter_count(chunks: list[ChunkPayload]) -> int:
    """
    @brief      Derive the count of distinct chapter-like headings from chunk text.
    @param[in]  chunks Ordered canonical chunks.
    @return     Number of distinct consecutive headings.
    """
    labels: list[str] = []
    for chunk in chunks:
        chapter_label = chapter_label_from_text(str(chunk.get("text", "")))
        if chapter_label is not None and (not labels or labels[-1] != chapter_label):
            labels.append(chapter_label)
    return len(labels)


# END OF FILE
