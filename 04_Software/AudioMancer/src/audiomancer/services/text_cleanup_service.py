#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file text_cleanup_service.py
@brief Resumable single-document Cleanup orchestration.
@details Owns deterministic analysis, optional bounded adjudication, atomic
         checkpoints, source-only rendering, publication, and manual edits
         through cleanup.json plus clean_text.txt.
"""

# IMPORTS

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from audiomancer import config
from audiomancer.services import (
    cleanup_ai_adjudication_service,
    cleanup_analysis_service,
    cleanup_metadata_service,
    cleanup_renderer_service,
    cleanup_text_analysis_service,
    project_workspace_service,
    prompt_template_service,
    source_ledger_service,
    token_usage_service,
)
from audiomancer.services.logging_service import get_component_logger
from audiomancer.services.operation_runtime_service import (
    OperationCancelledError,
    raise_if_cancelled,
    reset_operation_data,
)
from audiomancer.services.persistence_service import (
    write_json_atomic,
    write_text_atomic,
)
from audiomancer.services.time_service import utc_now_iso

# CONSTANTS

_CLEANUP_LOGGER = get_component_logger("text_cleanup")
CLEANUP_ROOT_FIELDS = frozenset(
    (
        "status",
        "phase",
        "started_at",
        "updated_at",
        "completed_at",
        "source_hash",
        "ledger_hash",
        "policy_hash",
        "prompt_hash",
        "profile_fingerprint",
        "document_profile",
        "unit_operations",
        "boundaries",
        "paragraphs",
        "progress",
        "warnings",
        "token_usage",
        "quality_report",
        "output_hash",
        "user_modified",
        "structure_source",
    )
)
_STATUSES = frozenset(("running", "paused", "finalizing", "completed", "failed"))
_PHASES = frozenset(("analysis", "adjudication", "rendering", "done"))
_PROGRESS_FIELDS = frozenset(
    (
        "question_count",
        "batch_order",
        "next_batch_index",
        "completed_request_count",
        "estimated_request_count",
        "estimated_input_tokens",
    )
)
_PROGRESS_COUNTER_FIELDS = _PROGRESS_FIELDS - {"batch_order"}
_BLOCKING_QUALITY_FIELDS = (
    "introduced_fusion_count",
    "projection_violation_count",
    "invalid_operation_count",
    "unclassified_boundary_count",
)
_ANALYSIS_COMPLETE_PERCENT = 8
_AI_COMPLETE_PERCENT = 88
_VALIDATION_PERCENT = 94
_PERSISTENCE_PERCENT = 98

# PUBLIC API


class CleanupDocumentError(ValueError):
    """Raised when cleanup.json violates the current strict contract."""


def clean_text(
    project_root: str | Path,
    manifest: dict[str, object],
    ai_profile_payload: dict[str, object] | None = None,
    progress_callback=None,
    cancel_requested=None,
) -> dict[str, object]:
    """Start or resume Cleanup and publish only a validated completed result."""
    root = Path(project_root)
    if not isinstance(manifest.get("source_document"), dict):
        raise ValueError("No imported source is available for Cleanup.")
    ledger = source_ledger_service.load_source_ledger(root)
    canonical_text = (root / config.EXTRACTED_TEXT_FILE_NAME).read_text(
        encoding="utf-8"
    )
    dominant_script = cleanup_text_analysis_service.classify_text_script(
        canonical_text
    )
    if dominant_script == "unsupported":
        raise ValueError(
            "Cleanup supports Latin and Cyrillic source text only; "
            "the document appears to use CJK or Hangul."
        )
    source_hash = source_ledger_service.text_sha256(canonical_text)
    ledger_hash = _json_hash(ledger)
    profile_fingerprint = _profile_fingerprint(ai_profile_payload)
    prompt_hash = _prompt_hash()
    existing = _read_checkpoint(root)

    document: dict[str, object]
    questions: list[dict[str, object]]
    if _can_reuse_analysis(existing, canonical_text, ledger):
        assert existing is not None
        document = existing
        if (
            document["status"] == "finalizing"
            and document["phase"] == "rendering"
        ):
            return _finalize_document(
                root,
                canonical_text,
                ledger,
                document,
                progress_callback,
            )
        if (
            document["status"] == "completed"
            and document["profile_fingerprint"] == profile_fingerprint
            and document["prompt_hash"] == prompt_hash
        ):
            try:
                _validate_completed_output(root, document)
            except CleanupDocumentError as error:
                _CLEANUP_LOGGER.warning(
                    "Rerendering completed Cleanup after output validation failed: %s",
                    error,
                )
                return _finalize_document(
                    root,
                    canonical_text,
                    ledger,
                    document,
                    progress_callback,
                )
            _emit(progress_callback, 1, 1, 100, "Cleanup completed.")
            return document
        if (
            document["profile_fingerprint"] != profile_fingerprint
            or document["prompt_hash"] != prompt_hash
        ):
            _reset_ai_adjudication(
                document,
                profile_fingerprint,
                prompt_hash,
                questions=cleanup_analysis_service.questions_from_boundaries(
                    canonical_text,
                    ledger,
                    list(document["boundaries"]),
                ),
            )
        else:
            document["status"] = "running"
            document["phase"] = "adjudication"
            document["completed_at"] = None
            document["output_hash"] = None
            document["paragraphs"] = []
        questions = cleanup_analysis_service.questions_from_boundaries(
            canonical_text,
            ledger,
            list(document["boundaries"]),
        )
        resumed_current = int(
            document["progress"]["completed_request_count"]
        )
        resumed_total = max(
            resumed_current,
            int(document["progress"]["estimated_request_count"]),
        )
        if resumed_total != document["progress"]["estimated_request_count"]:
            document["progress"]["estimated_request_count"] = resumed_total
            document["updated_at"] = utc_now_iso()
            _write_checkpoint(root, document)
        _emit(
            progress_callback,
            resumed_current,
            max(1, resumed_total),
            _ai_progress_percent(
                resumed_current,
                resumed_total,
            ),
            (
                "Cleanup resumed from batch "
                f"{int(document['progress']['next_batch_index']) + 1}/"
                f"{max(1, len(document['progress']['batch_order']))}."
            ),
        )
    else:
        raise_if_cancelled(cancel_requested)
        _emit(
            progress_callback,
            0,
            1,
            0,
            "Analyzing structural cleanup evidence...",
        )
        analysis = cleanup_analysis_service.analyze_cleanup(
            canonical_text,
            ledger,
        )
        questions = list(analysis["questions"])
        now = utc_now_iso()
        batch_order = _batch_order(questions, ai_profile_payload)
        document = {
            "status": "running",
            "phase": "analysis",
            "started_at": now,
            "updated_at": now,
            "completed_at": None,
            "source_hash": source_hash,
            "ledger_hash": ledger_hash,
            "policy_hash": _policy_hash(
                list(analysis["unit_operations"]),
                list(analysis["boundaries"]),
            ),
            "prompt_hash": prompt_hash,
            "profile_fingerprint": profile_fingerprint,
            "document_profile": dict(analysis["document_profile"]),
            "unit_operations": list(analysis["unit_operations"]),
            "boundaries": list(analysis["boundaries"]),
            "paragraphs": [],
            "progress": {
                "question_count": len(questions),
                "batch_order": batch_order,
                "next_batch_index": 0,
                "completed_request_count": 0,
                "estimated_request_count": len(batch_order) * 2,
                "estimated_input_tokens": _estimated_input_tokens(questions),
            },
            "warnings": list(analysis["warnings"]),
            "token_usage": token_usage_service.empty_token_usage(),
            "quality_report": _empty_quality_report(),
            "output_hash": None,
            "user_modified": False,
            "structure_source": "cleanup_roles",
        }
        _write_checkpoint(root, document)
        document["phase"] = "adjudication"
        document["updated_at"] = utc_now_iso()
        _write_checkpoint(root, document)
        _emit(
            progress_callback,
            0,
            max(1, len(batch_order)),
            _ANALYSIS_COMPLETE_PERCENT,
            (
                f"Cleanup analysis: {len(questions)} ambiguous boundaries; "
                f"estimated {len(batch_order) * 2} AI requests and "
                f"{document['progress']['estimated_input_tokens']} input tokens."
            ),
        )

    resume_answers = _resume_answers(questions, list(document["boundaries"]))
    boundary_by_id = {
        str(item["boundary_id"]): item
        for item in document["boundaries"]
    }

    def _checkpoint_submission(
        _pass_name: str,
        _batch_id: str,
        batch: list[dict[str, object]],
    ) -> None:
        if not isinstance(ai_profile_payload, dict) or not _is_online_backend(
            str(ai_profile_payload.get("backend_kind") or "")
        ):
            return
        quality_report = document["quality_report"]
        quality_report["online_fragment_count"] = int(
            quality_report.get("online_fragment_count", 0)
        ) + len(batch)
        quality_report["online_backend"] = str(
            ai_profile_payload.get("backend_kind")
        )
        document["status"] = "running"
        document["phase"] = "adjudication"
        document["updated_at"] = utc_now_iso()
        _write_checkpoint(root, document)

    def _checkpoint_request(
        pass_name: str,
        _batch_id: str,
        batch: list[dict[str, object]],
        answers: list[dict[str, str]],
        request_usage: dict[str, object],
    ) -> None:
        answer_by_id = {
            str(item["question_id"]): str(item["choice"])
            for item in answers
        }
        for question in batch:
            question_id = str(question["question_id"])
            decision = boundary_by_id[str(question["target_id"])]
            if pass_name == "primary":
                decision["adjudication"]["primary_choice"] = answer_by_id[
                    question_id
                ]
            else:
                decision["adjudication"]["verifier_choice"] = answer_by_id[
                    question_id
                ]
        document["progress"]["completed_request_count"] = (
            int(document["progress"]["completed_request_count"]) + 1
        )
        document["progress"]["next_batch_index"] = _next_batch_index(
            document["progress"],
            batch,
        )
        document["token_usage"] = token_usage_service.merge_token_usage(
            document["token_usage"],
            request_usage,
        )
        document["status"] = "running"
        document["phase"] = "adjudication"
        document["updated_at"] = utc_now_iso()
        _write_checkpoint(root, document)

    def _ai_progress(current: int, total: int, message: str) -> None:
        bounded_current = max(0, int(current))
        bounded_total = max(1, int(total), bounded_current)
        if bounded_total > int(
            document["progress"]["estimated_request_count"]
        ):
            document["progress"]["estimated_request_count"] = bounded_total
            document["updated_at"] = utc_now_iso()
            _write_checkpoint(root, document)
        _emit(
            progress_callback,
            bounded_current,
            bounded_total,
            _ai_progress_percent(bounded_current, bounded_total),
            message,
        )

    log_path = root / (
        f"{config.AI_TRANSACTION_LOG_FILE_PREFIX}"
        f"cleanup_{_timestamp_token()}.log"
    )
    try:
        ai_result = cleanup_ai_adjudication_service.adjudicate_questions(
            questions,
            ai_profile_payload,
            log_path=log_path,
            progress_callback=_ai_progress,
            cancel_requested=cancel_requested,
            resume_answers=resume_answers,
            completed_request_count=int(
                document["progress"]["completed_request_count"]
            ),
            request_callback=_checkpoint_request,
            submission_callback=_checkpoint_submission,
        )
    except OperationCancelledError:
        document["status"] = "paused"
        document["phase"] = "adjudication"
        document["updated_at"] = utc_now_iso()
        _write_checkpoint(root, document)
        project_workspace_service.sync_manifest_operation_summary(
            root,
            "cleanup",
            _manifest_summary(document),
            current_stage="text_cleanup_ready",
        )
        raise

    _emit(
        progress_callback,
        int(document["progress"]["completed_request_count"]),
        max(1, int(document["progress"]["estimated_request_count"])),
        _AI_COMPLETE_PERCENT,
        "AI Cleanup adjudication completed.",
    )
    _apply_ai_result(
        document,
        questions,
        dict(ai_result),
    )
    document["status"] = "finalizing"
    document["phase"] = "rendering"
    document["updated_at"] = utc_now_iso()
    _write_checkpoint(root, document)
    raise_if_cancelled(cancel_requested)
    return _finalize_document(
        root,
        canonical_text,
        ledger,
        document,
        progress_callback,
    )


def load_cleanup_document(
    project_root: str | Path,
) -> dict[str, object] | None:
    """Load and strictly validate the current cleanup.json contract."""
    root = Path(project_root)
    path = root / config.CLEANUP_DOCUMENT_FILE_NAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CleanupDocumentError(
            "cleanup.json is unreadable or malformed."
        ) from error
    ledger = source_ledger_service.load_source_ledger(root)
    canonical_text = (root / config.EXTRACTED_TEXT_FILE_NAME).read_text(
        encoding="utf-8"
    )
    validate_cleanup_document(
        payload,
        canonical_text=canonical_text,
        ledger=ledger,
    )
    if payload["status"] == "completed":
        _validate_completed_output(root, payload)
    return payload


def save_user_cleaned_text(
    project_root: str | Path,
    cleaned_text: str,
) -> dict[str, object]:
    """
    @brief      Persist an operator edit with truthful structure and downstream reset.
    @param[in]  project_root Active project root folder.
    @param[in]  cleaned_text Operator-edited canonical Cleanup text.
    @return     Updated completed Cleanup document.
    @exception  ValueError Raised when the edited text is empty.
    @exception  CleanupDocumentError Raised when completed Cleanup is unavailable.
    """
    root = Path(project_root)
    edited_text = str(cleaned_text).replace("\r\n", "\n").replace("\r", "\n")
    if not edited_text.strip():
        raise ValueError("Cleaned text cannot be empty.")
    document = load_cleanup_document(root)
    if document is None or document["status"] != "completed":
        raise CleanupDocumentError("Run Cleanup before editing clean text.")
    current_path = root / config.CLEANED_TEXT_FILE_NAME
    current_text = current_path.read_text(encoding="utf-8")
    whitespace_only = _lexical_projection(current_text) == _lexical_projection(
        edited_text
    )
    if whitespace_only:
        previous_records = (
            cleanup_metadata_service.load_completed_paragraph_records(
                root,
                current_text,
            )
        )
        _realign_whitespace_boundaries(
            root,
            document,
            edited_text,
        )
        runtime_records = cleanup_metadata_service.build_paragraph_records_from_text(
            edited_text
        )
        _realign_whitespace_roles(previous_records, runtime_records)
        document["paragraphs"] = (
            cleanup_metadata_service.persisted_paragraph_records(runtime_records)
        )
        document["structure_source"] = "cleanup_roles"
    else:
        runtime_records = cleanup_metadata_service.build_paragraph_records_from_text(
            edited_text
        )
        document["paragraphs"] = (
            cleanup_metadata_service.persisted_paragraph_records(runtime_records)
        )
        document["structure_source"] = "user_edited"
    document["user_modified"] = True
    document["status"] = "completed"
    document["phase"] = "done"
    document["updated_at"] = utc_now_iso()
    document["completed_at"] = document["updated_at"]
    document["output_hash"] = source_ledger_service.text_sha256(edited_text)
    canonical_text = (root / config.EXTRACTED_TEXT_FILE_NAME).read_text(
        encoding="utf-8"
    )
    ledger = source_ledger_service.load_source_ledger(root)
    validate_cleanup_document(
        document,
        canonical_text=canonical_text,
        ledger=ledger,
    )
    _publish_completed_cleanup(root, edited_text, document)
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
    """Validate the strict unversioned Cleanup document."""
    if not isinstance(payload, dict):
        raise CleanupDocumentError("Cleanup document must be one JSON object.")
    if set(payload) != CLEANUP_ROOT_FIELDS:
        raise CleanupDocumentError(
            "cleanup.json fields do not match the current contract."
        )
    if payload.get("status") not in _STATUSES:
        raise CleanupDocumentError("Cleanup status is invalid.")
    if payload.get("phase") not in _PHASES:
        raise CleanupDocumentError("Cleanup phase is invalid.")
    if payload.get("source_hash") != source_ledger_service.text_sha256(
        canonical_text
    ):
        raise CleanupDocumentError(
            "Cleanup source hash no longer matches Extraction."
        )
    if payload.get("ledger_hash") != _json_hash(ledger):
        raise CleanupDocumentError(
            "Cleanup ledger hash no longer matches Extraction."
        )
    if payload.get("structure_source") not in {
        "cleanup_roles",
        "user_edited",
    }:
        raise CleanupDocumentError("Cleanup structure source is invalid.")
    if type(payload.get("user_modified")) is not bool:
        raise CleanupDocumentError("Cleanup user-modified flag is invalid.")
    for list_field in (
        "unit_operations",
        "boundaries",
        "paragraphs",
        "warnings",
    ):
        if not isinstance(payload.get(list_field), list):
            raise CleanupDocumentError(
                f"Cleanup {list_field} must be a list."
            )
    progress = payload.get("progress")
    if not isinstance(progress, dict):
        raise CleanupDocumentError("Cleanup progress is invalid.")
    _validate_progress(progress)
    quality_report = payload.get("quality_report")
    if not isinstance(quality_report, dict):
        raise CleanupDocumentError("Cleanup quality report is invalid.")
    if not isinstance(payload.get("document_profile"), dict):
        raise CleanupDocumentError("Cleanup document profile is invalid.")
    if payload.get("profile_fingerprint") is not None and not isinstance(
        payload.get("profile_fingerprint"),
        dict,
    ):
        raise CleanupDocumentError("Cleanup profile fingerprint is invalid.")
    if not isinstance(payload.get("token_usage"), dict):
        raise CleanupDocumentError("Cleanup token usage is invalid.")
    try:
        cleanup_analysis_service.validate_persisted_boundaries(
            payload["boundaries"]
        )
        cleanup_renderer_service.validate_operations(
            canonical_text,
            ledger,
            payload["unit_operations"],
            payload["boundaries"],
        )
        _validate_checkpoint_plan(payload, canonical_text, ledger)
    except (
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        AssertionError,
    ) as error:
        raise CleanupDocumentError(
            "Cleanup deterministic analysis is invalid."
        ) from error
    if payload["status"] == "completed":
        if payload.get("phase") != "done" or payload.get("output_hash") is None:
            raise CleanupDocumentError(
                "Completed Cleanup metadata is incomplete."
            )
        _validate_blocking_quality_metrics(quality_report)


def _validate_progress(progress: dict[str, object]) -> None:
    """Validate the exact persisted Cleanup progress contract."""
    if set(progress) != _PROGRESS_FIELDS:
        raise CleanupDocumentError(
            "Cleanup progress fields do not match the current contract."
        )
    for field in _PROGRESS_COUNTER_FIELDS:
        value = progress[field]
        if type(value) is not int or value < 0:
            raise CleanupDocumentError(
                f"Cleanup progress counter is invalid: {field}."
            )
    batch_order = progress["batch_order"]
    if not isinstance(batch_order, list) or any(
        not isinstance(batch, list)
        or any(not isinstance(boundary_id, str) for boundary_id in batch)
        for batch in batch_order
    ):
        raise CleanupDocumentError("Cleanup progress batch order is invalid.")
    if progress["next_batch_index"] > len(batch_order):
        raise CleanupDocumentError(
            "Cleanup progress next batch index is out of range."
        )


def _validate_blocking_quality_metrics(
    quality_report: dict[str, object],
) -> None:
    """Require completed Cleanup blocking metrics to be integer zeroes."""
    for field in _BLOCKING_QUALITY_FIELDS:
        value = quality_report.get(field)
        if type(value) is not int:
            raise CleanupDocumentError(
                f"Cleanup blocking quality metric is invalid: {field}."
            )
        if value != 0:
            raise CleanupDocumentError(
                f"Cleanup blocking quality metric failed: {field}."
            )


def _finalize_document(
    root: Path,
    canonical_text: str,
    ledger: dict[str, object],
    document: dict[str, object],
    progress_callback,
) -> dict[str, object]:
    """Render and atomically publish one finalizing Cleanup document."""
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
        list(document["unit_operations"]),
        list(document["boundaries"]),
    )
    quality_report = dict(render_metadata["quality_report"])
    previous_quality = dict(document.get("quality_report") or {})
    quality_report["failed_batch_count"] = int(
        previous_quality.get("failed_batch_count", 0)
    )
    quality_report["online_fragment_count"] = int(
        previous_quality.get("online_fragment_count", 0)
    )
    quality_report["online_backend"] = previous_quality.get("online_backend")
    document["paragraphs"] = list(render_metadata["paragraphs"])
    document["quality_report"] = quality_report
    document["output_hash"] = source_ledger_service.text_sha256(cleaned_text)
    document["updated_at"] = utc_now_iso()
    _emit(
        progress_callback,
        1,
        1,
        _PERSISTENCE_PERCENT,
        "Persisting Cleanup results...",
    )
    document["status"] = "completed"
    document["phase"] = "done"
    document["completed_at"] = utc_now_iso()
    document["updated_at"] = document["completed_at"]
    validate_cleanup_document(
        document,
        canonical_text=canonical_text,
        ledger=ledger,
    )
    _publish_completed_cleanup(root, cleaned_text, document)
    _emit(
        progress_callback,
        1,
        1,
        100,
        (
            "Cleanup completed with "
            f"{quality_report['low_confidence_count']} "
            "low-confidence boundaries."
        ),
    )
    return document


def _publish_completed_cleanup(
    root: Path,
    cleaned_text: str,
    document: dict[str, object],
) -> None:
    """
    @brief      Publish canonical Cleanup artifacts and synchronized downstream reset state.
    @param[in]  root Active project root folder.
    @param[in]  cleaned_text Validated canonical cleaned text.
    @param[in]  document Validated completed Cleanup document.
    @return     None.
    @exception  OSError Raised when artifact or manifest persistence fails.
    """
    reset_operation_data(root, "chunking", include_current=True)
    write_text_atomic(root / config.CLEANED_TEXT_FILE_NAME, cleaned_text)
    _write_checkpoint(root, document)

    manifest = project_workspace_service.load_manifest(root)
    updated_manifest = (
        project_workspace_service.build_manifest_after_operation_reset(
            manifest,
            "chunking",
        )
    )
    operations = dict(updated_manifest["operations"])
    operations["cleanup"] = (
        project_workspace_service.project_manifest_operation_summary(
            "cleanup",
            _manifest_summary(document),
        )
    )
    updated_manifest["operations"] = operations
    updated_manifest["original_language"] = document["document_profile"].get(
        "language"
    )
    project_workspace_service.save_manifest(updated_manifest, root)


def _apply_ai_result(
    document: dict[str, object],
    questions: list[dict[str, object]],
    result: dict[str, object],
) -> None:
    """Project adjudication answers onto persisted boundary decisions."""
    boundary_by_id = {
        str(item["boundary_id"]): item
        for item in document["boundaries"]
    }
    question_by_id = {
        str(item["question_id"]): item
        for item in questions
    }
    for record in result["answers"]:
        question = question_by_id[str(record["question_id"])]
        decision = boundary_by_id[str(question["target_id"])]
        fallback = record.get("state") == "fallback"
        decision["adjudication"] = {
            "state": "fallback" if fallback else "completed",
            "primary_choice": record.get("primary_choice"),
            "verifier_choice": record.get("verifier_choice"),
            "accepted": bool(record.get("accepted", False)),
        }
        final_choice = str(
            record.get("final_choice") or decision["prior"]["choice"]
        )
        decision["final"] = {
            "choice": final_choice,
            "origin": (
                "fallback"
                if fallback
                else "llm"
                if bool(record.get("accepted", False))
                else "deterministic"
            ),
            "confidence": str(decision["prior"]["confidence"]),
            "reason_codes": (
                ["llm_verified_override"]
                if bool(record.get("accepted", False))
                else ["deterministic_fallback"]
                if fallback
                else list(decision["prior"]["reason_codes"])
            ),
        }
    document["warnings"] = list(
        dict.fromkeys(
            [
                *[str(item) for item in document["warnings"]],
                *[str(item) for item in result["warnings"]],
            ]
        )
    )
    result_batch_order = list(result.get("batch_order") or [])
    if result_batch_order != document["progress"]["batch_order"]:
        raise CleanupDocumentError(
            "Cleanup runtime batch plan differs from its checkpoint plan."
        )
    document["progress"]["next_batch_index"] = len(
        document["progress"]["batch_order"]
    )
    document["quality_report"]["failed_batch_count"] = int(
        result.get("failed_batch_count", 0)
    )


def _can_reuse_analysis(
    document: dict[str, object] | None,
    canonical_text: str,
    ledger: dict[str, object],
) -> bool:
    """Return whether a checkpoint's deterministic layer remains compatible."""
    try:
        validate_cleanup_document(
            document,
            canonical_text=canonical_text,
            ledger=ledger,
        )
    except CleanupDocumentError:
        return False
    assert document is not None
    try:
        expected_policy_hash = _policy_hash(
            list(document["unit_operations"]),
            list(document["boundaries"]),
        )
    except (KeyError, TypeError, ValueError):
        return False
    return document.get("policy_hash") == expected_policy_hash


def _validate_checkpoint_plan(
    document: dict[str, object],
    canonical_text: str,
    ledger: dict[str, object],
) -> None:
    """Require checkpoint question counts and batches to match the shared plan."""
    if document["user_modified"]:
        return
    questions = cleanup_analysis_service.questions_from_boundaries(
        canonical_text,
        ledger,
        document["boundaries"],
    )
    progress = document["progress"]
    expected_order = _batch_order(
        questions,
        document["profile_fingerprint"],
    )
    if progress["question_count"] != len(questions):
        raise CleanupDocumentError(
            "Cleanup checkpoint question count is invalid."
        )
    if progress["batch_order"] != expected_order:
        raise CleanupDocumentError(
            "Cleanup checkpoint batch plan is invalid."
        )
    planned_estimate = len(expected_order) * 2
    estimated_requests = progress["estimated_request_count"]
    if (
        estimated_requests < planned_estimate
        or (not expected_order and estimated_requests != 0)
    ):
        raise CleanupDocumentError(
            "Cleanup checkpoint request estimate is invalid."
        )


def _reset_ai_adjudication(
    document: dict[str, object],
    profile_fingerprint: dict[str, object] | None,
    prompt_hash: str,
    *,
    questions: list[dict[str, object]],
) -> None:
    """Preserve deterministic analysis and clear all mutable AI state."""
    for decision in document["boundaries"]:
        prior = dict(decision["prior"])
        decision["adjudication"] = {
            "state": (
                "not_required"
                if prior["confidence"] == "strong"
                else "pending"
            ),
            "primary_choice": None,
            "verifier_choice": None,
            "accepted": False,
        }
        decision["final"] = {
            "choice": prior["choice"],
            "origin": (
                "native"
                if str(decision.get("kind")) in {
                    "native_paragraph",
                    "native_line_break",
                }
                else "deterministic"
            ),
            "confidence": prior["confidence"],
            "reason_codes": list(prior["reason_codes"]),
        }
    batch_order = _batch_order(questions, profile_fingerprint)
    document["user_modified"] = False
    document["structure_source"] = "cleanup_roles"
    document["profile_fingerprint"] = profile_fingerprint
    document["prompt_hash"] = prompt_hash
    document["status"] = "running"
    document["phase"] = "adjudication"
    document["completed_at"] = None
    document["paragraphs"] = []
    document["output_hash"] = None
    document["token_usage"] = token_usage_service.empty_token_usage()
    document["progress"]["question_count"] = len(questions)
    document["progress"]["batch_order"] = batch_order
    document["progress"]["next_batch_index"] = 0
    document["progress"]["completed_request_count"] = 0
    document["progress"]["estimated_request_count"] = len(batch_order) * 2
    document["progress"]["estimated_input_tokens"] = _estimated_input_tokens(
        questions
    )
    document["quality_report"] = _empty_quality_report()
    document["updated_at"] = utc_now_iso()


def _resume_answers(
    questions: list[dict[str, object]],
    boundaries: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Map persisted partial AI choices back to stable question identifiers."""
    boundary_by_id = {
        str(item["boundary_id"]): item
        for item in boundaries
    }
    return {
        str(question["question_id"]): {
            "primary_choice": boundary_by_id[
                str(question["target_id"])
            ]["adjudication"].get("primary_choice"),
            "verifier_choice": boundary_by_id[
                str(question["target_id"])
            ]["adjudication"].get("verifier_choice"),
        }
        for question in questions
    }


def _realign_whitespace_roles(
    previous_records: list[dict[str, object]],
    current_records: list[dict[str, object]],
) -> None:
    """
    @brief      Carry prior Cleanup metadata across unambiguous content matches.
    @param[in]  previous_records Prior runtime paragraph records with text.
    @param[out] current_records Rebuilt runtime records receiving safe metadata.
    @return     None.
    @exception  None
    """
    previous_by_text: dict[str, list[dict[str, object]]] = {}
    for record in previous_records:
        comparison_key = cleanup_text_analysis_service.normalized_compare_key(
            str(record.get("text") or "")
        )
        if comparison_key:
            previous_by_text.setdefault(comparison_key, []).append(record)

    current_by_text: dict[str, list[dict[str, object]]] = {}
    for record in current_records:
        comparison_key = cleanup_text_analysis_service.normalized_compare_key(
            str(record.get("text") or "")
        )
        if comparison_key:
            current_by_text.setdefault(comparison_key, []).append(record)

    for record in current_records:
        classified_role = str(record.get("role") or "body")
        record["role"] = classified_role
        record["reason_codes"] = _reason_codes_with_whitespace_realign(
            record.get("reason_codes")
        )
        comparison_key = cleanup_text_analysis_service.normalized_compare_key(
            str(record.get("text") or "")
        )
        prior_matches = previous_by_text.get(comparison_key, [])
        current_matches = current_by_text.get(comparison_key, [])
        if len(prior_matches) != 1 or len(current_matches) != 1:
            continue

        prior = prior_matches[0]
        prior_role = str(prior.get("role") or "body")
        if classified_role != "scene_separator" and prior_role != "scene_separator":
            record["role"] = prior_role
        record["confidence"] = str(prior.get("confidence") or "strong")
        record["reason_codes"] = _reason_codes_with_whitespace_realign(
            prior.get("reason_codes")
        )

        raw_source_ids = prior.get("source_unit_ids")
        source_ids = (
            list(
                dict.fromkeys(
                    str(unit_id)
                    for unit_id in raw_source_ids
                    if str(unit_id)
                )
            )
            if isinstance(raw_source_ids, list)
            else []
        )
        if prior.get("provenance_available") is not True or not source_ids:
            continue
        record["source_unit_ids"] = source_ids
        record["provenance_available"] = True
        record["source_page_start"] = prior.get("source_page_start")
        record["source_page_end"] = prior.get("source_page_end")
        record["starts_after_page_transition"] = bool(
            prior.get("starts_after_page_transition", False)
        )
        record["crosses_page_transition"] = bool(
            prior.get("crosses_page_transition", False)
        )


def _reason_codes_with_whitespace_realign(value: object) -> list[str]:
    """Return ordered unique reason codes with the realignment marker."""
    existing = (
        [str(item) for item in value]
        if isinstance(value, list)
        else []
    )
    return list(dict.fromkeys([*existing, "user_whitespace_realign"]))


def _realign_whitespace_boundaries(
    root: Path,
    document: dict[str, object],
    edited_text: str,
) -> None:
    """Update resolvable typed choices to match one whitespace-only edit."""
    ledger = source_ledger_service.load_source_ledger(root)
    canonical_text = (root / config.EXTRACTED_TEXT_FILE_NAME).read_text(
        encoding="utf-8"
    )
    drops = {
        str(item["target_id"])
        for item in document["unit_operations"]
        if item["action"] == "drop_page_artifact"
    }
    cursor = 0
    located: dict[str, tuple[int, int]] = {}
    for unit in ledger["units"]:
        unit_id = str(unit["unit_id"])
        if unit_id in drops:
            continue
        text = source_ledger_service.unit_text(canonical_text, unit)
        candidate = text
        decision = next(
            (
                item
                for item in document["boundaries"]
                if item.get("left_unit_id") == unit_id
            ),
            None,
        )
        if (
            isinstance(decision, dict)
            and decision["final"]["choice"] == "dehyphenate"
            and candidate.endswith(("-", "\u00ad"))
        ):
            candidate = candidate[:-1]
        start = edited_text.find(candidate, cursor)
        if start < 0:
            warning_code = "user_whitespace_realign_incomplete"
            _CLEANUP_LOGGER.warning(
                "Whitespace-only edit could not realign Cleanup boundaries because source unit %s was not found.",
                unit_id,
            )
            document["warnings"] = list(
                dict.fromkeys(
                    [
                        *[str(item) for item in document["warnings"]],
                        warning_code,
                    ]
                )
            )
            return
        located[unit_id] = (start, start + len(candidate))
        cursor = start + len(candidate)
    for decision in document["boundaries"]:
        left_id = decision.get("left_unit_id")
        right_id = decision.get("right_unit_id")
        if right_id is None:
            continue
        if str(left_id) not in located or str(right_id) not in located:
            continue
        gap = edited_text[
            located[str(left_id)][1] : located[str(right_id)][0]
        ]
        if "\n\n" in gap:
            choice = "set_paragraph_break"
        elif "\n" in gap:
            choice = "set_semantic_line_break"
        elif gap:
            choice = "join_with_space"
        else:
            choice = str(decision["final"]["choice"])
        decision["adjudication"] = {
            "state": "completed",
            "primary_choice": None,
            "verifier_choice": None,
            "accepted": False,
        }
        decision["final"] = {
            "choice": choice,
            "origin": "user",
            "confidence": "strong",
            "reason_codes": ["user_whitespace_realign"],
        }


def _validate_completed_output(
    root: Path,
    document: dict[str, object],
) -> None:
    """Require the completed Cleanup text artifact to exist and match its hash."""
    cleaned_path = root / config.CLEANED_TEXT_FILE_NAME
    if not cleaned_path.is_file():
        raise CleanupDocumentError("Completed Cleanup requires clean_text.txt.")
    cleaned_text = cleaned_path.read_text(encoding="utf-8")
    if source_ledger_service.text_sha256(cleaned_text) != document["output_hash"]:
        raise CleanupDocumentError("clean_text.txt does not match cleanup.json.")


def _read_checkpoint(root: Path) -> dict[str, object] | None:
    """Read cleanup.json without requiring a completed output artifact."""
    path = root / config.CLEANUP_DOCUMENT_FILE_NAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, dict) else None


def _write_checkpoint(root: Path, document: dict[str, object]) -> None:
    """Atomically persist the sole Cleanup metadata/checkpoint document."""
    write_json_atomic(root / config.CLEANUP_DOCUMENT_FILE_NAME, document)


def _policy_hash(
    unit_operations: list[dict[str, object]],
    boundaries: list[dict[str, object]],
) -> str:
    """Hash deterministic roles/priors together with the active policy token."""
    payload = {
        "policy": cleanup_analysis_service.ANALYSIS_POLICY_ID,
        "unit_operations": unit_operations,
        "boundaries": [
            {
                "boundary_id": item["boundary_id"],
                "left_unit_id": item["left_unit_id"],
                "right_unit_id": item["right_unit_id"],
                "kind": item["kind"],
                "page_transition": item["page_transition"],
                "left_role": item["left_role"],
                "right_role": item["right_role"],
                "prior": item["prior"],
            }
            for item in boundaries
        ],
    }
    return _json_hash(payload)


def _prompt_hash() -> str:
    """Hash exact prompt templates and the response-contract identifier."""
    payload = {
        "contract": cleanup_ai_adjudication_service.PROMPT_CONTRACT_ID,
        "primary": prompt_template_service.load_prompt(
            "text_cleanup_adjudication_primary_system"
        ),
        "verifier": prompt_template_service.load_prompt(
            "text_cleanup_adjudication_verifier_system"
        ),
    }
    return _json_hash(payload)


def _profile_fingerprint(
    profile: dict[str, object] | None,
) -> dict[str, object] | None:
    """Project non-secret model and request policy into the resume fingerprint."""
    if profile is None:
        return None
    return {
        "id": str(profile.get("id") or ""),
        "backend_kind": str(profile.get("backend_kind") or ""),
        "model_name": str(profile.get("model_name") or ""),
        "context_window": int(profile.get("context_window", 0) or 0),
        "supports_structured_output": bool(
            profile.get("supports_structured_output", False)
        ),
        "request_timeout_seconds": int(
            profile.get("request_timeout_seconds", 0) or 0
        ),
        "temperature": float(profile.get("temperature", 0.0) or 0.0),
        "max_output_tokens": int(
            profile.get("max_output_tokens", 0) or 0
        ),
    }


def _batch_order(
    questions: list[dict[str, object]],
    profile: dict[str, object] | None,
) -> list[list[str]]:
    """Project the authoritative runtime plan into durable target IDs."""
    return [
        [str(item["target_id"]) for item in batch]
        for batch in cleanup_ai_adjudication_service.plan_question_batches(
            questions,
            profile,
        )
    ]


def _next_batch_index(
    progress: dict[str, object],
    batch: list[dict[str, object]],
) -> int:
    """Return the first estimated batch that still follows the completed request."""
    batch_targets = {
        str(item["target_id"])
        for item in batch
    }
    for index, target_ids in enumerate(progress["batch_order"]):
        if batch_targets & set(target_ids):
            return min(index + 1, len(progress["batch_order"]))
    return int(progress["next_batch_index"])


def _estimated_input_tokens(
    questions: list[dict[str, object]],
) -> int:
    """Estimate question context using a conservative four-codepoint ratio."""
    characters = sum(
        len(str(item.get("left_text") or ""))
        + len(str(item.get("right_text") or ""))
        for item in questions
    )
    return max(0, characters // 4)


def _empty_quality_report() -> dict[str, object]:
    """Return runtime quality counters before final rendering."""
    return {
        "introduced_fusion_count": 0,
        "projection_violation_count": 0,
        "invalid_operation_count": 0,
        "unclassified_boundary_count": 0,
        "low_confidence_count": 0,
        "page_transition_count": 0,
        "artifact_removal_count": 0,
        "deterministic_count": 0,
        "llm_count": 0,
        "fallback_count": 0,
        "override_count": 0,
        "override_rate": 0.0,
        "failed_batch_count": 0,
        "online_fragment_count": 0,
        "online_backend": None,
    }


def _manifest_summary(document: dict[str, object]) -> dict[str, object]:
    """Project the Cleanup document into the compact project manifest."""
    progress = document["progress"]
    total = max(1, len(progress["batch_order"]))
    return {
        "status": str(document["status"]),
        "progress_current": (
            total
            if document["status"] == "completed"
            else min(int(progress["next_batch_index"]), total)
        ),
        "progress_total": total,
        "warning_count": len(document["warnings"]),
        "mode": "hybrid",
    }


def _is_online_backend(backend_kind: str) -> bool:
    """Return whether a profile backend represents a remote hosted provider."""
    return backend_kind.casefold() == config.ONLINE_AI_BACKEND_KIND.casefold()


def _lexical_projection(text: str) -> str:
    """Remove Unicode whitespace for whitespace-only edit classification."""
    return re.sub(r"\s+", "", str(text))


def _json_hash(payload: object) -> str:
    """Return a stable SHA-256 for canonical JSON."""
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _timestamp_token() -> str:
    """Return a filename-safe UTC timestamp."""
    return utc_now_iso().replace(":", "").replace("-", "").replace("+", "_")


def _emit(
    callback,
    current: int,
    total: int,
    percent: int,
    message: str,
) -> None:
    """Emit one bounded Cleanup progress update."""
    if callable(callback):
        callback(
            current,
            total,
            max(0, min(int(percent), 100)),
            message,
        )


def _ai_progress_percent(current: int, total: int) -> int:
    """
    @brief      Map persisted AI request progress into the Cleanup progress band.
    @param[in]  current Number of completed AI requests.
    @param[in]  total Estimated total number of AI requests.
    @return     Bounded progress percentage between analysis and AI completion.
    @exception  None.
    """
    bounded_total = max(1, int(total))
    bounded_current = max(0, min(int(current), bounded_total))
    span = _AI_COMPLETE_PERCENT - _ANALYSIS_COMPLETE_PERCENT
    return _ANALYSIS_COMPLETE_PERCENT + (
        span * bounded_current // bounded_total
    )


# END OF FILE
