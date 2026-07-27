#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
"""
@file text_cleanup_service.py
@brief Single hybrid Cleanup V2 orchestration service.
@details Runs deterministic evidence collection, optional bounded AI
         adjudication, deterministic validation, and pure source-ledger render.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    cleanup_ai_adjudication_service,
    cleanup_analysis_service,
    cleanup_metadata_service,
    cleanup_renderer_service,
    project_workspace_service,
    source_ledger_service,
    token_usage_service,
)
from audiomancer.services.operation_runtime_service import (
    raise_if_cancelled,
    reset_operation_data,
)
from audiomancer.services.persistence_service import write_json_atomic, write_text_atomic
from audiomancer.services.time_service import utc_now_iso

CLEANUP_SCHEMA_VERSION = 2
PROMPT_SCHEMA_VERSION = 1
_TERMINAL_VALIDATION_STATES = frozenset(("passed", "passed_with_warnings"))
_ANALYSIS_COMPLETE_PERCENT = 5
_AI_COMPLETE_PERCENT = 90
_VALIDATION_PERCENT = 92
_PERSISTENCE_PERCENT = 98


class CleanupDocumentError(ValueError):
    """Raised when persisted Cleanup V2 artifacts are incompatible."""


def clean_text(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object] | None = None,
    progress_callback=None,
    cancel_requested=None,
) -> dict[str, object]:
    """Run the one hybrid Cleanup operation and persist its authoritative document."""
    root = Path(project_root)
    if not isinstance(manifest.get("source_document"), dict):
        raise ValueError("No imported source is available for Cleanup.")
    ledger = source_ledger_service.load_source_ledger(root)
    canonical_text = (root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    raise_if_cancelled(cancel_requested)
    _emit(progress_callback, 0, 1, 0, "Analyzing structural cleanup evidence...")
    analysis = cleanup_analysis_service.analyze_cleanup(canonical_text, ledger)
    deterministic_operations = _number_operations(list(analysis["operations"]))
    questions = _number_questions(list(analysis["questions"]))
    warnings = list(analysis["warnings"])
    _emit(
        progress_callback,
        0,
        1,
        _ANALYSIS_COMPLETE_PERCENT,
        "Structural cleanup analysis completed.",
    )

    log_path = root / f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}cleanup_{_timestamp_token()}.log"

    def _emit_ai_progress(current: int, total: int, message: str) -> None:
        bounded_total = max(1, int(total))
        bounded_current = max(0, min(int(current), bounded_total))
        ai_span = _AI_COMPLETE_PERCENT - _ANALYSIS_COMPLETE_PERCENT
        percent = _ANALYSIS_COMPLETE_PERCENT + (
            ai_span * bounded_current // bounded_total
        )
        _emit(
            progress_callback,
            bounded_current,
            bounded_total,
            percent,
            message,
        )

    ai_result = cleanup_ai_adjudication_service.adjudicate_questions(
        questions,
        ai_profile_payload,
        log_path=log_path,
        progress_callback=_emit_ai_progress,
        cancel_requested=cancel_requested,
    )
    warnings.extend(str(item) for item in ai_result["warnings"])
    combined_operations = _deduplicate_operations(
        deterministic_operations + list(ai_result["operations"])
    )
    combined_operations = _number_operations(combined_operations)
    raise_if_cancelled(cancel_requested)
    _emit(
        progress_callback,
        1,
        1,
        _VALIDATION_PERCENT,
        "Validating and rendering Cleanup...",
    )
    cleaned_text, render_metadata = cleanup_renderer_service.render_cleanup(
        canonical_text,
        ledger,
        combined_operations,
    )
    clean_metadata = _build_clean_text_metadata(cleaned_text, render_metadata)
    unresolved_count = len(questions) - sum(
        1 for item in ai_result["answers"] if bool(item.get("accepted", False))
    )
    if unresolved_count:
        warnings.append(f"{unresolved_count} uncertain Cleanup decisions were preserved.")
    validation_state = "passed_with_warnings" if warnings else "passed"
    now = utc_now_iso()
    document = {
        "schema_version": CLEANUP_SCHEMA_VERSION,
        "execution_status": "completed",
        "validation_state": validation_state,
        "started_at": now,
        "completed_at": now,
        "source_hash": source_ledger_service.text_sha256(canonical_text),
        "ledger_hash": _json_hash(ledger),
        "queue_hash": _json_hash(questions),
        "profile_fingerprint": _profile_fingerprint(ai_profile_payload),
        "prompt_schema_version": PROMPT_SCHEMA_VERSION,
        "document_profile": dict(analysis["document_profile"]),
        "operations": combined_operations,
        "questions": questions,
        "answers": list(ai_result["answers"]),
        "warnings": warnings,
        "token_usage": token_usage_service.coerce_token_usage(ai_result["token_usage"]),
        "output_hash": source_ledger_service.text_sha256(cleaned_text),
        "uncertainty_count": unresolved_count,
        "user_modified": False,
    }
    validate_cleanup_document(document, canonical_text=canonical_text, ledger=ledger)

    _emit(
        progress_callback,
        1,
        1,
        _PERSISTENCE_PERCENT,
        "Persisting Cleanup results...",
    )
    reset_operation_data(root, "cleanup", include_current=True)
    write_text_atomic(root / config.CLEANED_TEXT_FILE_NAME, cleaned_text)
    write_json_atomic(root / config.CLEANED_TEXT_METADATA_FILE_NAME, clean_metadata)
    write_json_atomic(root / config.CLEANUP_DOCUMENT_FILE_NAME, document)
    project_workspace_service.sync_manifest_operation_summary(
        root,
        "cleanup",
        _manifest_summary(document),
        current_stage="text_chunking_ready",
        extra_fields={"original_language": analysis["document_profile"].get("language")},
    )
    _emit(progress_callback, 1, 1, 100, "Cleanup completed.")
    return document


def load_cleanup_document(project_root: str | Path) -> dict[str, object] | None:
    """Load and strictly validate the authoritative Cleanup V2 document."""
    root = Path(project_root)
    path = root / config.CLEANUP_DOCUMENT_FILE_NAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CleanupDocumentError("cleanup.json is unreadable or malformed.") from error
    ledger = source_ledger_service.load_source_ledger(root)
    canonical_text = (root / config.EXTRACTED_TEXT_FILE_NAME).read_text(encoding="utf-8")
    validate_cleanup_document(payload, canonical_text=canonical_text, ledger=ledger)
    cleaned_path = root / config.CLEANED_TEXT_FILE_NAME
    if payload["execution_status"] == "completed":
        if not cleaned_path.is_file():
            raise CleanupDocumentError("Completed Cleanup requires cleaned_text.txt.")
        cleaned_text = cleaned_path.read_text(encoding="utf-8")
        if source_ledger_service.text_sha256(cleaned_text) != payload["output_hash"]:
            raise CleanupDocumentError("cleaned_text.txt does not match cleanup.json.")
    return payload


def save_user_cleaned_text(project_root: str | Path, cleaned_text: str) -> dict[str, object]:
    """Persist an operator edit and keep Cleanup valid for immediate Chunking."""
    root = Path(project_root)
    if not str(cleaned_text).strip():
        raise ValueError("Cleaned text cannot be empty.")
    document = load_cleanup_document(root)
    if document is None:
        raise CleanupDocumentError("Run Cleanup before editing cleaned text.")
    reset_operation_data(root, "chunking", include_current=True)
    write_text_atomic(root / config.CLEANED_TEXT_FILE_NAME, str(cleaned_text))
    write_json_atomic(
        root / config.CLEANED_TEXT_METADATA_FILE_NAME,
        _build_clean_text_metadata(
            str(cleaned_text),
            {"spans": []},
        ),
    )
    document["output_hash"] = source_ledger_service.text_sha256(str(cleaned_text))
    document["user_modified"] = True
    document["completed_at"] = utc_now_iso()
    write_json_atomic(root / config.CLEANUP_DOCUMENT_FILE_NAME, document)
    project_workspace_service.sync_manifest_operation_summary(
        root,
        "cleanup",
        _manifest_summary(document),
        current_stage="text_chunking_ready",
    )
    return document


def reset_cleanup_and_downstream(project_root: str | Path) -> None:
    """Remove Cleanup and all downstream artifacts while keeping Extraction."""
    reset_operation_data(project_root, "cleanup", include_current=True)


def validate_cleanup_document(
    payload: object,
    *,
    canonical_text: str,
    ledger: dict[str, object],
) -> None:
    """Validate the strict single-document Cleanup V2 contract."""
    if not isinstance(payload, dict):
        raise CleanupDocumentError("Cleanup document must be one JSON object.")
    required = {
        "schema_version",
        "execution_status",
        "validation_state",
        "started_at",
        "completed_at",
        "source_hash",
        "ledger_hash",
        "queue_hash",
        "profile_fingerprint",
        "prompt_schema_version",
        "document_profile",
        "operations",
        "questions",
        "answers",
        "warnings",
        "token_usage",
        "output_hash",
        "uncertainty_count",
        "user_modified",
    }
    if set(payload) != required or payload.get("schema_version") != CLEANUP_SCHEMA_VERSION:
        raise CleanupDocumentError("Cleanup document schema is incompatible; rerun Cleanup.")
    if payload.get("execution_status") != "completed":
        raise CleanupDocumentError("Cleanup document is not complete.")
    if payload.get("validation_state") not in _TERMINAL_VALIDATION_STATES:
        raise CleanupDocumentError("Cleanup validation did not pass.")
    if payload.get("source_hash") != source_ledger_service.text_sha256(canonical_text):
        raise CleanupDocumentError("Cleanup source hash no longer matches Extraction.")
    if payload.get("ledger_hash") != _json_hash(ledger):
        raise CleanupDocumentError("Cleanup ledger hash no longer matches Extraction.")
    if not isinstance(payload.get("warnings"), list) or not isinstance(payload.get("questions"), list):
        raise CleanupDocumentError("Cleanup warnings or questions are invalid.")
    if not isinstance(payload.get("uncertainty_count"), int) or int(payload["uncertainty_count"]) < 0:
        raise CleanupDocumentError("Cleanup uncertainty count is invalid.")
    cleanup_renderer_service.validate_operations(
        canonical_text,
        ledger,
        payload.get("operations"),
    )


def _number_operations(operations: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for index, operation in enumerate(operations):
        item = dict(operation)
        item["operation_id"] = f"op-{index + 1:06d}"
        result.append(item)
    return result


def _number_questions(questions: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for index, question in enumerate(questions):
        item = dict(question)
        item["question_id"] = f"q-{index + 1:06d}"
        result.append(item)
    return result


def _deduplicate_operations(operations: list[dict[str, object]]) -> list[dict[str, object]]:
    """Keep deterministic evidence first and prevent multiple actions per target."""
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for operation in operations:
        target = str(operation["target_id"])
        if target in seen:
            continue
        seen.add(target)
        result.append(dict(operation))
    return result


def _profile_fingerprint(profile: dict[str, object] | None) -> dict[str, object] | None:
    if profile is None:
        return None
    return {
        "id": str(profile.get("id") or ""),
        "backend_kind": str(profile.get("backend_kind") or ""),
        "model_name": str(profile.get("model_name") or ""),
        "context_window": int(profile.get("context_window", 0) or 0),
        "supports_structured_output": bool(profile.get("supports_structured_output", False)),
    }


def _manifest_summary(document: dict[str, object]) -> dict[str, object]:
    return {
        "status": "completed",
        "progress_current": 1,
        "progress_total": 1,
        "warning_count": len(document["warnings"]),
        "mode": "hybrid",
    }


def _build_clean_text_metadata(
    cleaned_text: str,
    render_metadata: dict[str, object],
) -> dict[str, object]:
    """Build downstream-compatible paragraph spans plus source-unit provenance."""
    records = cleanup_metadata_service.build_paragraph_records_from_text(cleaned_text)
    return {
        "schema_version": 1,
        "cleanup_mode": "hybrid",
        "paragraph_count": len(records),
        "page_break_repair_count": 0,
        "weak_boundary_count": 0,
        "paragraphs": [
            {
                key: value
                for key, value in record.items()
                if key != "text"
            }
            for record in records
        ],
        "source_spans": list(render_metadata.get("spans", [])),
    }


def _json_hash(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _timestamp_token() -> str:
    return utc_now_iso().replace(":", "").replace("-", "").replace("+", "_")


def _emit(callback, current: int, total: int, percent: int, message: str) -> None:
    if callable(callback):
        callback(current, total, max(0, min(int(percent), 100)), message)
