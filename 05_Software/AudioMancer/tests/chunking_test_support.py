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
    if (
        status in {"running", "cancelled", "failed"}
        and source_text
        and (Path(document_root) / config.CLEANUP_DOCUMENT_FILE_NAME).is_file()
    ):
        from audiomancer.chunking import materialization
        from audiomancer.services.chunking_input_service import load_paragraph_records

        records = load_paragraph_records(source_text, document_root)
        document["plan_fingerprint"] = materialization.plan_fingerprint(records)
        cursor = 0
        for chunk in document["chunks"]:
            while cursor < len(records) and not materialization._is_narratable_record(records[cursor]):
                cursor += 1
            start = cursor
            combined = ""
            while cursor < len(records) and combined != chunk["text"]:
                combined = "\n\n".join(str(item["text"]) for item in records[start : cursor + 1]).strip()
                cursor += 1
            if combined == chunk["text"]:
                chunk.update(
                    materialization._build_chunk_from_range(records, start, cursor - 1, chunk["sequence_index"])
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
        "plan_fingerprint": None,
        "request_fingerprint": None,
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
    """
    payload = json.loads((Path(document_root) / config.CHUNK_ARTIFACT_FILE_NAME).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError("Expected a strict Chunking document fixture.")
    return payload


def write_cleanup_input(
    document_root: str | Path,
    source_text: str,
    *,
    status: str = "completed",
    paragraphs: list[dict[str, object]] | None = None,
) -> Path:
    """@brief Write the strict Cleanup subset consumed by Chunking tests."""
    paragraph_records = paragraphs or _cleanup_paragraphs(source_text)
    payload = {
        "status": status,
        "phase": "done" if status == "completed" else "adjudication",
        "started_at": "2026-07-28T12:00:00+00:00",
        "updated_at": "2026-07-28T12:00:01+00:00",
        "completed_at": "2026-07-28T12:00:01+00:00" if status == "completed" else None,
        "source_hash": "0" * 64,
        "ledger_hash": "1" * 64,
        "policy_hash": "2" * 64,
        "prompt_hash": "3" * 64,
        "profile_fingerprint": None,
        "document_profile": {
            "source_format": "txt",
            "structure_quality": "text_only",
            "language": "en",
        },
        "unit_operations": [],
        "boundaries": [],
        "paragraphs": paragraph_records,
        "progress": {
            "question_count": 0,
            "batch_order": [],
            "next_batch_index": 0,
            "completed_request_count": 0,
            "estimated_request_count": 0,
            "estimated_input_tokens": 0,
        },
        "warnings": [],
        "token_usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "usage_available": False,
        },
        "quality_report": {
            "introduced_fusion_count": 0,
            "projection_violation_count": 0,
            "invalid_operation_count": 0,
            "unclassified_boundary_count": 0,
            "low_confidence_count": 0,
            "fallback_count": 0,
            "override_count": 0,
            "override_rate": 0.0,
            "failed_batch_count": 0,
            "online_fragment_count": 0,
            "online_backend": None,
        },
        "output_hash": sha256(source_text.encode("utf-8")).hexdigest(),
        "user_modified": False,
        "structure_source": "cleanup_roles",
    }
    root = Path(document_root)
    (root / config.CLEANED_TEXT_FILE_NAME).write_text(source_text, encoding="utf-8")
    output_path = root / config.CLEANUP_DOCUMENT_FILE_NAME
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _normalize_chunk(item: dict[str, object], sequence_index: int) -> dict[str, object]:
    """
    @brief Project a compact test record into the exact chunk field set.
    @param[in]  item Candidate list item being validated.
    @param[in]  sequence_index Expected zero-based canonical sequence position.
    @return     Normalized chunk.
    """
    return {
        "chunk_id": str(item.get("chunk_id", f"chunk-{sequence_index:04d}")),
        "sequence_index": sequence_index,
        "text": str(item.get("text", "")),
        "source_paragraph_start": item.get("source_paragraph_start"),
        "source_paragraph_end": item.get("source_paragraph_end"),
        "cleanup_boundary_confidence": item.get("cleanup_boundary_confidence"),
        "cleanup_joined_across_page_break": bool(item.get("cleanup_joined_across_page_break", False)),
        "cleanup_warning_flags": list(item.get("cleanup_warning_flags", [])),
        "cleanup_role": str(item.get("cleanup_role") or "body"),
        "starts_after_scene_separator": bool(item.get("starts_after_scene_separator", False)),
    }


def _inferred_mode(chunks: list[dict[str, object]]) -> str:
    """
    @brief Infer a valid document-level mode from optional compact fixture metadata.
    @param[in]  chunks Ordered canonical chunk payloads.
    @return     Inferred strict chunking mode token.
    """
    if chunks and chunks[0].get("chunking_mode") == "ai_assisted":
        return "ai_assisted"
    return "deterministic"


def _cleanup_paragraphs(source_text: str) -> list[dict[str, object]]:
    """@brief Build body-role Cleanup paragraph offsets from blank-line-separated text."""
    records = []
    start = 0
    for index, paragraph in enumerate(
        [item for item in source_text.strip().split("\n\n") if item.strip()],
        start=1,
    ):
        output_start = source_text.index(paragraph, start)
        output_end = output_start + len(paragraph)
        start = output_end
        records.append(
            {
                "paragraph_id": f"paragraph-{index:06d}",
                "output_start": output_start,
                "output_end": output_end,
                "role": "body",
                "confidence": "strong",
                "reason_codes": ["test_fixture"],
                "source_page_start": None,
                "source_page_end": None,
                "starts_after_page_transition": False,
                "crosses_page_transition": False,
                "source_unit_ids": [],
                "provenance_available": False,
            }
        )
    return records



def bind_translation_source(project_root, translated_chunks):
    """@brief Build verified translation fixture rows from the current canonical text."""
    chunks = read_chunking_document(project_root)["chunks"]
    fingerprints = {
        chunk["chunk_id"]: "sha256:" + sha256(chunk["text"].encode("utf-8")).hexdigest()
        for chunk in chunks
    }
    return [
        {**chunk, "source_fingerprint": fingerprints[chunk["chunk_id"]]}
        if chunk["chunk_id"] in fingerprints else dict(chunk)
        for chunk in translated_chunks
    ]


# END OF FILE
