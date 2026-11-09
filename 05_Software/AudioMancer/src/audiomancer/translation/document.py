#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file document.py
@brief AI Translation document and source policy.
@details Validates persisted records and projects source-aligned review and narration text.
"""

# IMPORTS

from collections.abc import Iterable
from hashlib import sha256
import re

from audiomancer import config
from audiomancer.services import token_usage_service

# CONSTANTS

_TRANSLATION_LANGUAGE_LABELS = dict(config.TRANSLATION_LANGUAGE_OPTIONS)

TRANSLATION_STATUS_NOT_STARTED = "not_started"
TRANSLATION_STATUS_RUNNING = "running"
TRANSLATION_STATUS_IN_PROGRESS = "in_progress"
TRANSLATION_STATUS_CANCELLED = "cancelled"
TRANSLATION_STATUS_FAILED = "failed"
TRANSLATION_STATUS_REVIEW_PENDING = "review_pending"
TRANSLATION_STATUS_COMPLETED = "completed"
TRANSLATION_STATUS_INVALID = "invalid"

_PERSISTED_STATUSES = frozenset(
    (
        TRANSLATION_STATUS_RUNNING,
        TRANSLATION_STATUS_IN_PROGRESS,
        TRANSLATION_STATUS_CANCELLED,
        TRANSLATION_STATUS_FAILED,
        TRANSLATION_STATUS_REVIEW_PENDING,
        TRANSLATION_STATUS_COMPLETED,
    )
)
_RESUMABLE_STATUSES = frozenset(
    (
        TRANSLATION_STATUS_RUNNING,
        TRANSLATION_STATUS_IN_PROGRESS,
        TRANSLATION_STATUS_CANCELLED,
        TRANSLATION_STATUS_FAILED,
    )
)
_DOCUMENT_FIELDS = frozenset(
    (
        "target_language",
        "status",
        "token_usage",
        "budget_metadata",
        "additional_translation_instructions",
        "chunks",
    )
)
_CHUNK_FIELDS = frozenset(("chunk_id", "translated_text", "approved"))

TranslationDocumentPayload = dict[str, object]


class TranslationDocumentError(ValueError):
    """
    @brief      Raised when persisted translation data does not match the strict contract.
    """


# PUBLIC API


def build_translation_summary(
    source_chunks: list[dict[str, object]],
    document: TranslationDocumentPayload | None,
) -> dict[str, object]:
    """
    @brief      Derive counts and effective status from canonical chunks and one document.
    @param[in]  source_chunks Ordered canonical source-chunk records.
    @param[in]  document Authoritative operation document payload.
    @return     Constructed translation summary.
    """
    total_count = len(canonical_source_chunks(source_chunks))
    if document is None:
        return {
            "status": TRANSLATION_STATUS_NOT_STARTED,
            "translated_count": 0,
            "approved_count": 0,
            "total_count": total_count,
            "warning_count": 0,
            "target_language": "",
            "token_usage": token_usage_service.empty_token_usage(),
        }
    canonical_chunks = aligned_chunks(source_chunks, document)
    translated_count = sum(item is not None and bool(str(item["translated_text"]).strip()) for item in canonical_chunks)
    approved_count = sum(
        item is not None and bool(item["approved"]) and bool(str(item["translated_text"]).strip())
        for item in canonical_chunks
    )
    persisted_status = str(document["status"])
    if persisted_status in {
        TRANSLATION_STATUS_RUNNING,
        TRANSLATION_STATUS_CANCELLED,
        TRANSLATION_STATUS_FAILED,
    }:
        effective_status = persisted_status
    elif _is_fully_approved(document, canonical_chunks):
        effective_status = TRANSLATION_STATUS_COMPLETED
    elif total_count > 0 and translated_count == total_count:
        effective_status = TRANSLATION_STATUS_REVIEW_PENDING
    else:
        effective_status = TRANSLATION_STATUS_IN_PROGRESS
    return {
        "status": effective_status,
        "translated_count": translated_count,
        "approved_count": approved_count,
        "total_count": total_count,
        "warning_count": 0,
        "target_language": str(document["target_language"]),
        "token_usage": dict(document["token_usage"]),
    }


def validate_translation_document(payload: object) -> None:
    """
    @brief      Validate exact root and chunk fields without migrating legacy payloads.
    @param[in]  payload Candidate structured payload.
    @return     None.
    @exception  Exception Raised when an empty translation cannot be approved.
    """
    if not isinstance(payload, dict):
        raise incompatible_document_error("The root must be an object.")
    if not _DOCUMENT_FIELDS <= set(payload) <= _DOCUMENT_FIELDS | {"request_fingerprint"}:
        raise incompatible_document_error("The root fields do not match the current contract.")
    if not isinstance(payload["target_language"], str) or not str(payload["target_language"]).strip():
        raise incompatible_document_error("target_language must be a non-empty string.")
    if payload["target_language"] not in _TRANSLATION_LANGUAGE_LABELS:
        raise incompatible_document_error("target_language is not supported.")
    request = payload.get("request_fingerprint")
    if request is not None and not _valid_fingerprint(request):
        raise incompatible_document_error("request_fingerprint is invalid.")
    if not isinstance(payload["status"], str) or payload["status"] not in _PERSISTED_STATUSES:
        raise incompatible_document_error("status is not supported.")
    if not isinstance(payload["token_usage"], dict):
        raise incompatible_document_error("token_usage must be an object.")
    if not isinstance(payload["budget_metadata"], dict):
        raise incompatible_document_error("budget_metadata must be an object.")
    if not isinstance(payload["additional_translation_instructions"], str):
        raise incompatible_document_error("additional_translation_instructions must be a string.")
    chunks = payload["chunks"]
    if not isinstance(chunks, list):
        raise incompatible_document_error("chunks must be an array.")
    chunk_ids: set[str] = set()
    for item in chunks:
        if not isinstance(item, dict) or not _CHUNK_FIELDS <= set(item) <= _CHUNK_FIELDS | {"source_fingerprint"}:
            raise incompatible_document_error(
                "Each chunk must contain the translation fields and optional source fingerprint."
            )
        chunk_id = item["chunk_id"]
        if not isinstance(chunk_id, str) or not chunk_id.strip() or chunk_id in chunk_ids:
            raise incompatible_document_error("Each chunk_id must be a unique non-empty string.")
        if not isinstance(item["translated_text"], str) or type(item["approved"]) is not bool:
            raise incompatible_document_error("Each chunk requires string translated_text and boolean approved.")
        if item["approved"] and not item["translated_text"].strip():
            raise incompatible_document_error("An empty translation cannot be approved.")
        fingerprint = item.get("source_fingerprint")
        if fingerprint is not None and not _valid_fingerprint(fingerprint):
            raise incompatible_document_error("source_fingerprint is invalid.")
        chunk_ids.add(chunk_id)


def new_translation_document(
    source_chunks: list[dict[str, object]],
    target_language: str,
    instructions: str,
) -> TranslationDocumentPayload:
    """@brief Build a new strict document in canonical source order."""
    return {
        "target_language": target_language,
        "status": TRANSLATION_STATUS_IN_PROGRESS,
        "token_usage": token_usage_service.empty_token_usage(),
        "budget_metadata": {},
        "additional_translation_instructions": instructions,
        "chunks": [
            {
                "chunk_id": str(item.get("chunk_id", "")),
                "translated_text": "",
                "approved": False,
                "source_fingerprint": source_fingerprint(item),
            }
            for item in canonical_source_chunks(source_chunks)
        ],
    }


def synchronize_document_chunks(
    document: TranslationDocumentPayload,
    source_chunks: list[dict[str, object]],
    invalidated_chunk_ids: list[str] | tuple[str, ...] | set[str],
) -> bool:
    """
    @brief      Align document chunks to canonical IDs while preserving unaffected records.
    @param[in]  document Authoritative operation document payload.
    @param[in]  source_chunks Ordered canonical source-chunk records.
    @param[in]  invalidated_chunk_ids Canonical chunk identifiers invalidated by the change.
    @return     True when synchronization changed the persisted chunk records.
    """
    synchronized_chunks = aligned_chunks(source_chunks, document, invalidated_chunk_ids)
    changed = synchronized_chunks != document["chunks"]
    if changed:
        document["chunks"] = synchronized_chunks
    return changed


def incompatible_document_error(reason: str) -> TranslationDocumentError:
    """@brief Build the operator-facing strict-contract error."""
    return TranslationDocumentError(
        f"Translation data is incompatible: {reason} Use Reset Translation before continuing."
    )


def canonical_source_chunks(source_chunks: list[dict[str, object]]) -> list[dict[str, object]]:
    """@brief Return nonempty canonical source chunks ordered by sequence index."""
    return sorted(
        (chunk for chunk in source_chunks if str(chunk["text"]).strip()),
        key=lambda item: int(item["sequence_index"]),
    )


def review_status(chunks: object) -> str:
    """
    @brief      Derive the persisted review status after a durable non-operation action.
    @param[in]  chunks Ordered canonical chunk payloads.
    @return     Effective persisted review-status token.
    """
    chunk_items = list(chunks) if isinstance(chunks, list) else []
    if chunk_items and all(str(item["translated_text"]).strip() for item in chunk_items):
        if all(bool(item["approved"]) for item in chunk_items):
            return TRANSLATION_STATUS_COMPLETED
        return TRANSLATION_STATUS_REVIEW_PENDING
    return TRANSLATION_STATUS_IN_PROGRESS


def _valid_fingerprint(value: object) -> bool:
    """@brief Check the persisted SHA-256 representation."""
    return isinstance(value, str) and re.fullmatch(r"sha256:[a-f0-9]{64}", value) is not None


def source_fingerprint(chunk: dict[str, object]) -> str:
    """@brief Identify the exact canonical text that a translation represents."""
    return "sha256:" + sha256(str(chunk["text"]).encode("utf-8")).hexdigest()


def aligned_chunks(
    source_chunks: list[dict[str, object]],
    document: TranslationDocumentPayload,
    invalidated_ids: Iterable[str] = (),
) -> list[dict[str, object]]:
    """@brief Project current rows, clearing stale text and withholding unverified legacy approval."""
    existing = {row["chunk_id"]: row for row in document["chunks"]}
    invalidated = set(invalidated_ids)
    rows = []
    for source in canonical_source_chunks(source_chunks):
        chunk_id = source["chunk_id"]
        fingerprint = source_fingerprint(source)
        row = existing.get(chunk_id)
        if row is None or chunk_id in invalidated or row.get("source_fingerprint") not in (None, fingerprint):
            row = {"chunk_id": chunk_id, "translated_text": "", "approved": False, "source_fingerprint": fingerprint}
        elif row.get("source_fingerprint") is None:
            row = {**row, "approved": False}
        else:
            row = dict(row)
        rows.append(row)
    return rows


def resolve_approved_translation(
    source_chunks: list[dict[str, object]],
    document: object,
    target_language: str | None = None,
) -> list[dict[str, object]] | None:
    """@brief Return canonical rows carrying verified approved text, or None for original-text fallback."""
    if not isinstance(document, dict) or document["status"] != TRANSLATION_STATUS_COMPLETED:
        return None
    if target_language is not None and document["target_language"] != target_language:
        return None
    sources = canonical_source_chunks(source_chunks)
    rows = aligned_chunks(sources, document)
    if not _is_fully_approved(document, rows):
        return None
    return [{**source, "text": row["translated_text"]} for source, row in zip(sources, rows, strict=True)]


def _is_fully_approved(document: TranslationDocumentPayload, rows: list[dict[str, object]]) -> bool:
    """@brief Check status and complete approval across exactly the current nonempty rows."""
    return (
        document["status"] == TRANSLATION_STATUS_COMPLETED
        and bool(rows)
        and len(rows) == len(document["chunks"])
        and all(row["approved"] and row["translated_text"].strip() for row in rows)
    )


# END OF FILE
