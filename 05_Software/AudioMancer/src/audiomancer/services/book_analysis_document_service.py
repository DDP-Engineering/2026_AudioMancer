#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file book_analysis_document_service.py
@brief Own the strict atomic Book Analysis project document.
@details Separates the last completed layered report from one resumable
         candidate, derives safe source/profile fingerprints, and validates the
         sole authoritative JSON shape before every read or replacement.
"""

# IMPORTS

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from audiomancer import config
from audiomancer.services.persistence_service import write_json_atomic

# CONSTANTS

# @brief Current strict Book Analysis document schema version.
BOOK_ANALYSIS_SCHEMA_VERSION = 1

# @brief Candidate lifecycle states accepted in the authoritative document.
CANDIDATE_STATUS_OPTIONS = frozenset(("running", "cancelled", "failed", "completed"))

# @brief Candidate phases accepted by the hierarchical operation.
CANDIDATE_PHASE_OPTIONS = frozenset(("leaf", "consolidation", "final", "completed"))

_ROOT_FIELDS = frozenset(("schema_version", "completed_report", "candidate_run"))
_SOURCE_FIELDS = frozenset(("fingerprint", "chunk_count"))
_COMPLETED_FIELDS = frozenset(
    (
        "source",
        "target_language",
        "profile_id",
        "profile_fingerprint",
        "completed_at",
        "report",
        "token_usage",
    )
)
_CANDIDATE_FIELDS = frozenset(
    (
        "run_id",
        "status",
        "source",
        "target_language",
        "profile_id",
        "profile_fingerprint",
        "reasoning_mode",
        "budget",
        "phase",
        "chunk_cursor",
        "progress_current",
        "progress_total",
        "leaf_summaries",
        "consolidation_levels",
        "token_usage",
        "failure",
        "started_at",
        "updated_at",
    )
)
_INTERMEDIATE_FIELDS = frozenset(
    (
        "summary",
        "characters",
        "subjects",
        "themes",
        "settings",
        "narrative_notes",
        "audiobook_notes",
        "uncertainties",
    )
)
_LEAF_FIELDS = frozenset(
    (
        "index",
        "chunk_ids",
        "first_sequence",
        "last_sequence",
        "summary",
        "usage",
    )
)
_CONSOLIDATION_FIELDS = frozenset(("index", "source_indices", "summary", "usage"))
_CONCISE_FIELDS = frozenset(
    (
        "book_type",
        "genres",
        "subjects",
        "setting_time",
        "summary",
        "main_characters",
        "themes",
    )
)
_DETAIL_FIELDS = frozenset(
    (
        "detailed_summary",
        "supporting_characters",
        "narrative_perspective",
        "narrative_structure",
        "tone",
        "pacing",
        "diction",
        "emotional_range",
        "audiobook_guidance",
        "uncertainties",
        "source_evidence",
    )
)
_TOKEN_USAGE_FIELDS = frozenset(
    ("input_tokens", "output_tokens", "total_tokens", "usage_available")
)
_PROHIBITED_SECRET_FIELDS = frozenset(
    ("api_key", "authorization", "access_token", "secret", "password")
)


# DATA MODELS / TYPEDEFINITIONS


class BookAnalysisDocumentError(ValueError):
    """@brief Raised when the sole Book Analysis document is incompatible."""


# PUBLIC API


def document_path(project_root: str | Path) -> Path:
    """@brief Return the authoritative Book Analysis document path."""
    return Path(project_root) / config.BOOK_ANALYSIS_DOCUMENT_FILE_NAME


def empty_document() -> dict[str, object]:
    """@brief Return a new empty document with independent durable slots."""
    return {
        "schema_version": BOOK_ANALYSIS_SCHEMA_VERSION,
        "completed_report": None,
        "candidate_run": None,
    }


def load_document(project_root: str | Path) -> dict[str, object] | None:
    """
    @brief      Load and validate the authoritative Book Analysis document.
    @param[in]  project_root Active project root.
    @return     Validated document or `None` when Book Analysis never started.
    @exception  BookAnalysisDocumentError Raised for malformed or incompatible data.
    """
    path = document_path(project_root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error_object:
        raise _incompatible(str(error_object)) from error_object
    return validate_document(payload)


def write_document(project_root: str | Path, document: object) -> Path:
    """
    @brief      Validate and atomically replace the Book Analysis document.
    @param[in]  project_root Active project root.
    @param[in]  document Candidate authoritative payload.
    @return     Written document path.
    @exception  BookAnalysisDocumentError Raised for invalid data.
    @exception  OSError Propagated when atomic publication fails.
    """
    validated = validate_document(document)
    path = document_path(project_root)
    write_json_atomic(path, validated)
    return path


def validate_document(payload: object) -> dict[str, object]:
    """@brief Validate and return a shallowly detached authoritative document."""
    if not isinstance(payload, dict) or frozenset(payload) != _ROOT_FIELDS:
        raise _incompatible("the root fields do not match schema version 1")
    if payload.get("schema_version") != BOOK_ANALYSIS_SCHEMA_VERSION:
        raise _incompatible("the schema version is unsupported")
    _validate_no_secrets(payload)
    completed_report = payload.get("completed_report")
    candidate_run = payload.get("candidate_run")
    if completed_report is not None:
        _validate_completed_report(completed_report)
    if candidate_run is not None:
        _validate_candidate(candidate_run)
    return dict(payload)


def validate_intermediate_summary(payload: object) -> dict[str, object]:
    """@brief Validate and defensively copy one hierarchical summary payload."""
    _validate_intermediate_summary(payload)
    return deepcopy(payload)


def validate_layered_report(payload: object) -> dict[str, object]:
    """@brief Validate and defensively copy one final layered report payload."""
    _validate_report(payload)
    return deepcopy(payload)


def canonical_source_descriptor(chunks: list[dict[str, object]]) -> dict[str, object]:
    """@brief Hash ordered canonical chunk identity, sequence, and text."""
    canonical = [
        {
            "chunk_id": str(chunk.get("chunk_id", "")),
            "sequence_index": int(chunk.get("sequence_index", -1)),
            "text": str(chunk.get("text", "")),
        }
        for chunk in chunks
    ]
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "fingerprint": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "chunk_count": len(canonical),
    }


def safe_profile_fingerprint(profile_payload: dict[str, object]) -> str:
    """@brief Hash request semantics without API keys or other credential material."""
    safe_request_fields = {
        field_name: profile_payload.get(field_name)
        for field_name in (
            "backend_kind",
            "base_url",
            "model_name",
            "context_window",
            "output_reserve_tokens",
            "request_timeout_seconds",
            "temperature",
            "supports_structured_output",
            "reasoning_mode",
        )
    }
    if profile_payload.get("backend_kind") == "chatgpt_subscription":
        from audiomancer.services.chatgpt_catalog_service import requested_effort

        safe_request_fields["reasoning_effort"] = requested_effort(profile_payload)
    encoded = json.dumps(
        safe_request_fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def candidate_resume_matches(
    candidate: object,
    *,
    source: dict[str, object],
    target_language: str,
    profile_id: str,
    profile_fingerprint: str,
) -> bool:
    """@brief Return whether one candidate can resume with the exact current inputs."""
    return bool(
        isinstance(candidate, dict)
        and candidate.get("source") == source
        and candidate.get("target_language") == target_language
        and candidate.get("profile_id") == profile_id
        and candidate.get("profile_fingerprint") == profile_fingerprint
        and candidate.get("status") in CANDIDATE_STATUS_OPTIONS
    )


def completed_report_is_stale(
    completed_report: object,
    source: dict[str, object],
    target_language: str,
) -> bool:
    """@brief Compare report freshness using canonical source and project language only."""
    return not (
        isinstance(completed_report, dict)
        and completed_report.get("source") == source
        and completed_report.get("target_language") == target_language
    )


def derive_operation_state(document: object) -> dict[str, object]:
    """@brief Project one Book Analysis document into a compact manifest summary."""
    default = {
        "status": "not_started",
        "progress_current": 0,
        "progress_total": 0,
        "mode": None,
        "warning_count": 0,
    }
    if not isinstance(document, dict):
        return default
    candidate = document.get("candidate_run")
    if isinstance(candidate, dict):
        return {
            "status": str(candidate.get("status", "not_started")),
            "progress_current": max(0, int(candidate.get("progress_current", 0))),
            "progress_total": max(0, int(candidate.get("progress_total", 0))),
            "mode": "ai_assisted",
            "warning_count": 0,
        }
    if isinstance(document.get("completed_report"), dict):
        return {
            "status": "completed",
            "progress_current": 1,
            "progress_total": 1,
            "mode": "ai_assisted",
            "warning_count": 0,
        }
    return default


# LOCAL HELPERS


def _validate_completed_report(payload: object) -> None:
    """@brief Validate completed-report identity, report fields and usage."""
    if not isinstance(payload, dict) or frozenset(payload) != _COMPLETED_FIELDS:
        raise _incompatible("completed_report fields are invalid")
    _validate_source(payload.get("source"))
    _require_non_empty_strings(
        payload,
        ("target_language", "profile_id", "profile_fingerprint", "completed_at"),
    )
    _validate_report(payload.get("report"))
    _validate_token_usage(payload.get("token_usage"))


def _validate_candidate(payload: object) -> None:
    """@brief Validate resumable candidate state and ordered checkpoint structures."""
    if not isinstance(payload, dict) or frozenset(payload) != _CANDIDATE_FIELDS:
        raise _incompatible("candidate_run fields are invalid")
    _require_non_empty_strings(
        payload,
        (
            "run_id",
            "target_language",
            "profile_id",
            "profile_fingerprint",
            "reasoning_mode",
            "started_at",
            "updated_at",
        ),
    )
    if payload.get("status") not in CANDIDATE_STATUS_OPTIONS:
        raise _incompatible("candidate_run status is invalid")
    if payload.get("phase") not in CANDIDATE_PHASE_OPTIONS:
        raise _incompatible("candidate_run phase is invalid")
    _validate_source(payload.get("source"))
    _validate_non_negative_int(payload.get("chunk_cursor"), "candidate_run.chunk_cursor")
    _validate_non_negative_int(payload.get("progress_current"), "candidate_run.progress_current")
    _validate_non_negative_int(payload.get("progress_total"), "candidate_run.progress_total")
    if not isinstance(payload.get("budget"), dict):
        raise _incompatible("candidate_run budget is invalid")
    if payload.get("failure") is not None and not isinstance(payload.get("failure"), str):
        raise _incompatible("candidate_run failure is invalid")
    leaf_summaries = payload.get("leaf_summaries")
    if not isinstance(leaf_summaries, list):
        raise _incompatible("candidate_run leaf_summaries is invalid")
    for expected_index, checkpoint in enumerate(leaf_summaries):
        _validate_leaf_checkpoint(checkpoint, expected_index)
    levels = payload.get("consolidation_levels")
    if not isinstance(levels, list):
        raise _incompatible("candidate_run consolidation_levels is invalid")
    for level in levels:
        if not isinstance(level, list):
            raise _incompatible("candidate_run consolidation level is invalid")
        for expected_index, checkpoint in enumerate(level):
            _validate_consolidation_checkpoint(checkpoint, expected_index)
    _validate_token_usage(payload.get("token_usage"))


def _validate_source(payload: object) -> None:
    """@brief Validate canonical source fingerprint and nonnegative chunk count."""
    if not isinstance(payload, dict) or frozenset(payload) != _SOURCE_FIELDS:
        raise _incompatible("source descriptor fields are invalid")
    _require_non_empty_strings(payload, ("fingerprint",))
    _validate_non_negative_int(payload.get("chunk_count"), "source.chunk_count")


def _validate_leaf_checkpoint(payload: object, expected_index: int) -> None:
    """@brief Validate leaf checkpoint ordering, source range, summary and usage."""
    if not isinstance(payload, dict) or frozenset(payload) != _LEAF_FIELDS:
        raise _incompatible("leaf checkpoint fields are invalid")
    if payload.get("index") != expected_index:
        raise _incompatible("leaf checkpoint indices are not consecutive")
    _validate_string_list(payload.get("chunk_ids"), allow_empty=False)
    _validate_non_negative_int(payload.get("first_sequence"), "leaf.first_sequence")
    _validate_non_negative_int(payload.get("last_sequence"), "leaf.last_sequence")
    _validate_intermediate_summary(payload.get("summary"))
    _validate_token_usage(payload.get("usage"))


def _validate_consolidation_checkpoint(payload: object, expected_index: int) -> None:
    """@brief Validate consolidation ordering, input indices, summary and usage."""
    if not isinstance(payload, dict) or frozenset(payload) != _CONSOLIDATION_FIELDS:
        raise _incompatible("consolidation checkpoint fields are invalid")
    if payload.get("index") != expected_index:
        raise _incompatible("consolidation checkpoint indices are not consecutive")
    source_indices = payload.get("source_indices")
    if not isinstance(source_indices, list) or not source_indices:
        raise _incompatible("consolidation source_indices are invalid")
    for source_index in source_indices:
        _validate_non_negative_int(source_index, "consolidation source index")
    _validate_intermediate_summary(payload.get("summary"))
    _validate_token_usage(payload.get("usage"))


def _validate_intermediate_summary(payload: object) -> None:
    """@brief Validate intermediate summary text, characters and metadata lists."""
    if not isinstance(payload, dict) or frozenset(payload) != _INTERMEDIATE_FIELDS:
        raise _incompatible("intermediate summary fields are invalid")
    if not isinstance(payload.get("summary"), str) or not str(payload["summary"]).strip():
        raise _incompatible("intermediate summary text is invalid")
    _validate_character_list(payload.get("characters"), supporting=False)
    for field_name in (
        "subjects",
        "themes",
        "settings",
        "narrative_notes",
        "audiobook_notes",
        "uncertainties",
    ):
        _validate_string_list(payload.get(field_name))


def _validate_report(payload: object) -> None:
    """@brief Validate both report layers, audiobook guidance and source evidence."""
    if not isinstance(payload, dict) or frozenset(payload) != frozenset(("concise", "details")):
        raise _incompatible("layered report fields are invalid")
    concise = payload.get("concise")
    details = payload.get("details")
    if not isinstance(concise, dict) or frozenset(concise) != _CONCISE_FIELDS:
        raise _incompatible("concise report fields are invalid")
    if not isinstance(details, dict) or frozenset(details) != _DETAIL_FIELDS:
        raise _incompatible("detailed report fields are invalid")
    _require_non_empty_strings(concise, ("book_type", "summary"))
    for field_name in ("genres", "subjects", "setting_time", "themes"):
        _validate_string_list(concise.get(field_name))
    _validate_character_list(concise.get("main_characters"), supporting=False)
    _require_non_empty_strings(
        details,
        (
            "detailed_summary",
            "narrative_perspective",
            "narrative_structure",
            "pacing",
            "diction",
        ),
    )
    _validate_character_list(details.get("supporting_characters"), supporting=True)
    for field_name in ("tone", "emotional_range", "uncertainties"):
        _validate_string_list(details.get(field_name))
    guidance = details.get("audiobook_guidance")
    if not isinstance(guidance, dict) or frozenset(guidance) != frozenset(
        ("narration_style", "character_voice_notes")
    ):
        raise _incompatible("audiobook guidance fields are invalid")
    _require_non_empty_strings(guidance, ("narration_style",))
    _validate_string_list(guidance.get("character_voice_notes"))
    evidence = details.get("source_evidence")
    if not isinstance(evidence, list):
        raise _incompatible("source evidence is invalid")
    for item in evidence:
        if not isinstance(item, dict) or frozenset(item) != frozenset(("chunk_ids", "note")):
            raise _incompatible("source evidence item is invalid")
        _validate_string_list(item.get("chunk_ids"), allow_empty=False)
        _require_non_empty_strings(item, ("note",))


def _validate_character_list(payload: object, *, supporting: bool) -> None:
    """@brief Validate character records and supporting-character relationships."""
    if not isinstance(payload, list):
        raise _incompatible("character collection is invalid")
    expected_fields = (
        frozenset(("name", "role", "relationships"))
        if supporting
        else frozenset(("name", "role"))
    )
    for item in payload:
        if not isinstance(item, dict) or frozenset(item) != expected_fields:
            raise _incompatible("character entry is invalid")
        _require_non_empty_strings(item, ("name", "role"))
        if supporting:
            _validate_string_list(item.get("relationships"))


def _validate_token_usage(payload: object) -> None:
    """@brief Validate normalized token counts and usage availability."""
    if not isinstance(payload, dict) or frozenset(payload) != _TOKEN_USAGE_FIELDS:
        raise _incompatible("token usage is invalid")
    usage_available = payload.get("usage_available")
    if not isinstance(usage_available, bool):
        raise _incompatible("token_usage.usage_available is invalid")
    for field_name in ("input_tokens", "output_tokens", "total_tokens"):
        field_value = payload.get(field_name)
        if not usage_available and field_value is None:
            continue
        _validate_non_negative_int(field_value, f"token_usage.{field_name}")


def _validate_string_list(payload: object, *, allow_empty: bool = True) -> None:
    """@brief Require a list of nonempty strings with optional empty-list support."""
    if not isinstance(payload, list) or (not allow_empty and not payload):
        raise _incompatible("string collection is invalid")
    if any(not isinstance(value, str) or not value.strip() for value in payload):
        raise _incompatible("string collection item is invalid")


def _require_non_empty_strings(payload: dict[str, object], field_names: tuple[str, ...]) -> None:
    """@brief Reject missing or blank required string fields."""
    for field_name in field_names:
        if not isinstance(payload.get(field_name), str) or not str(payload[field_name]).strip():
            raise _incompatible(f"{field_name} is invalid")


def _validate_non_negative_int(value: object, field_name: str) -> None:
    """@brief Reject booleans, nonintegers and negative counts."""
    if type(value) is not int or int(value) < 0:
        raise _incompatible(f"{field_name} is invalid")


def _validate_no_secrets(payload: object) -> None:
    """@brief Recursively reject credential fields before project persistence."""
    if isinstance(payload, dict):
        for field_name, field_value in payload.items():
            if str(field_name).strip().lower() in _PROHIBITED_SECRET_FIELDS:
                raise _incompatible("secret fields may not be persisted")
            _validate_no_secrets(field_value)
    elif isinstance(payload, list):
        for item in payload:
            _validate_no_secrets(item)


def _incompatible(reason: str) -> BookAnalysisDocumentError:
    return BookAnalysisDocumentError(f"Book Analysis document is incompatible: {reason}.")


# END OF FILE
