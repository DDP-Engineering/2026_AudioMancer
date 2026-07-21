#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file chunking_test_support.py
@brief Shared strict Chunking-document fixtures for AudioMancer tests.
@details Builds compact, exact root-object fixtures without production-service coupling.
@author Eng. Dan Dumitru Pasare
@date 2026-07-20
@version 0.1.0
"""

# IMPORTS

from hashlib import sha256
import json
from pathlib import Path

from audiomancer import config


def write_chunking_document(
    document_root: str | Path,
    chunks: list[dict[str, object]],
    *,
    mode: str | None = None,
    semantic_strategy: str | None = None,
    manual_adjusted: bool = False,
    source_text: str = "",
    status: str = "completed",
    additional_chunking_instructions: str = "",
    token_usage: dict[str, object] | None = None,
    warnings: list[str] | None = None,
    next_paragraph: int | None = None,
    context_window_fallback_count: int = 0,
) -> Path:
    """
    @brief Write a strict Chunking document from compact test records.
    @param[in]  document_root Candidate root object of the strict chunking document.
    @param[in]  chunks Ordered canonical chunk payloads.
    @param[in]  mode Stable chunking mode token.
    @param[in]  semantic_strategy Selected semantic chunking strategy token.
    @param[in]  manual_adjusted Whether an operator manually changed canonical chunks.
    @param[in]  source_text Canonical source text processed by the callable.
    @param[in]  status Operation status token under evaluation.
    @param[in]  additional_chunking_instructions Optional operator-supplied chunking rules.
    @param[in]  token_usage Cumulative AI token-usage metadata.
    @param[in]  warnings Ordered persisted contract warnings.
    @param[in]  next_paragraph Absolute index of the next paragraph awaiting processing.
    @param[in]  context_window_fallback_count Number of context-window fallback retries.
    @return     Resolved filesystem path.
    @version 0.1.0
    """
    document = build_chunking_document(
        chunks,
        mode=mode,
        semantic_strategy=semantic_strategy,
        manual_adjusted=manual_adjusted,
        source_text=source_text,
        status=status,
        additional_chunking_instructions=additional_chunking_instructions,
        token_usage=token_usage,
        warnings=warnings,
        next_paragraph=next_paragraph,
        context_window_fallback_count=context_window_fallback_count,
    )
    output_path = Path(document_root) / config.CHUNK_ARTIFACT_FILE_NAME
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def build_chunking_document(
    chunks: list[dict[str, object]],
    *,
    mode: str | None = None,
    semantic_strategy: str | None = None,
    manual_adjusted: bool = False,
    source_text: str = "",
    status: str = "completed",
    additional_chunking_instructions: str = "",
    token_usage: dict[str, object] | None = None,
    warnings: list[str] | None = None,
    next_paragraph: int | None = None,
    context_window_fallback_count: int = 0,
) -> dict[str, object]:
    """
    @brief Build a strict Chunking document from compact test records.
    @param[in]  chunks Ordered canonical chunk payloads.
    @param[in]  mode Stable chunking mode token.
    @param[in]  semantic_strategy Selected semantic chunking strategy token.
    @param[in]  manual_adjusted Whether an operator manually changed canonical chunks.
    @param[in]  source_text Canonical source text processed by the callable.
    @param[in]  status Operation status token under evaluation.
    @param[in]  additional_chunking_instructions Optional operator-supplied chunking rules.
    @param[in]  token_usage Cumulative AI token-usage metadata.
    @param[in]  warnings Ordered persisted contract warnings.
    @param[in]  next_paragraph Absolute index of the next paragraph awaiting processing.
    @param[in]  context_window_fallback_count Number of context-window fallback retries.
    @return     Constructed chunking document.
    @version 0.1.0
    """
    normalized_chunks = [_normalize_chunk(item, index) for index, item in enumerate(chunks, start=1)]
    inferred_mode = mode or _inferred_mode(chunks)
    inferred_strategy = semantic_strategy
    if inferred_strategy is None and inferred_mode == "ai_assisted" and chunks:
        candidate = chunks[0].get("semantic_strategy")
        inferred_strategy = str(candidate) if candidate is not None else "paragraph"
    document = {
        "status": status,
        "mode": inferred_mode,
        "manual_adjusted": manual_adjusted,
        "source_fingerprint": f"sha256:{sha256(source_text.encode('utf-8')).hexdigest()}",
        "semantic_strategy": inferred_strategy if inferred_mode == "ai_assisted" else None,
        "additional_chunking_instructions": additional_chunking_instructions,
        "token_usage": token_usage
        or {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "usage_available": False,
        },
        "warnings": list(warnings or []),
        "next_paragraph": next_paragraph,
        "context_window_fallback_count": context_window_fallback_count,
        "chunks": normalized_chunks,
    }
    return document


def read_chunking_document(document_root: str | Path) -> dict[str, object]:
    """
    @brief Read one strict Chunking document fixture.
    @param[in]  document_root Candidate root object of the strict chunking document.
    @return     Loaded chunking document.
    @exception  AssertionError Raised when expected a strict Chunking document fixture.
    @version 0.1.0
    """
    payload = json.loads((Path(document_root) / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError("Expected a strict Chunking document fixture.")
    return payload


def _normalize_chunk(item: dict[str, object], sequence_index: int) -> dict[str, object]:
    """
    @brief Project a compact test record into the exact chunk field set.
    @param[in]  item Candidate list item being validated.
    @param[in]  sequence_index Expected zero-based canonical sequence position.
    @return     Normalized chunk.
    @version 0.1.0
    """
    return {
        "chunk_id": str(item.get("chunk_id", f"chunk-{sequence_index:04d}")),
        "sequence_index": sequence_index,
        "text": str(item.get("text", "")),
        "cleanup_boundary_confidence": item.get("cleanup_boundary_confidence"),
        "cleanup_joined_across_page_break": bool(item.get("cleanup_joined_across_page_break", False)),
        "cleanup_warning_flags": list(item.get("cleanup_warning_flags", [])),
    }


def _inferred_mode(chunks: list[dict[str, object]]) -> str:
    """
    @brief Infer a valid document-level mode from optional compact fixture metadata.
    @param[in]  chunks Ordered canonical chunk payloads.
    @return     Inferred strict chunking mode token.
    @version 0.1.0
    """
    if chunks and chunks[0].get("chunking_mode") == "ai_assisted":
        return "ai_assisted"
    return "deterministic"


# END OF FILE
