#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""Build the localized Book Analysis page state without mutating project data."""

from pathlib import Path

from audiomancer import config
from audiomancer.services import (
    ai_state_note_service,
    book_analysis_document_service,
    chunking_document_service,
    ui_state_service,
)


def build_book_analysis_profile_state(
    settings: dict[str, object] | None,
    selected_profile_id: str | None = None,
) -> dict[str, object]:
    """Return enabled profile entries and the Book Analysis selection."""
    return ai_state_note_service.build_llm_profile_selector_state(
        settings,
        "default_book_analysis_profile_id",
        selected_profile_id,
    )


def build_book_analysis_state(
    project_root: str | Path | None,
    manifest: dict[str, object] | None,
    language: str,
    settings: dict[str, object] | None,
    selected_profile_id: str | None,
    operation_is_active: bool = False,
) -> dict[str, object]:
    """Project canonical chunks and the durable report document into page state."""
    profile_state = build_book_analysis_profile_state(settings, selected_profile_id)
    selected_id = profile_state["selected_profile_id"]
    base = {
        "profiles": profile_state["entries"],
        "selected_profile_id": selected_id,
        "state": "unavailable",
        "notes": [],
        "report": None,
        "report_stale": False,
        "can_analyze": False,
        "can_reset": False,
    }
    if project_root is None or not isinstance(manifest, dict):
        base["notes"] = [_text("book_analysis.note_no_project", language)]
        return base

    chunking_document = chunking_document_service.load_chunking_document(project_root)
    if not isinstance(chunking_document, dict) or chunking_document.get("status") != "completed":
        base["notes"] = [_text("book_analysis.note_chunks_required", language)]
        return base
    chunks = chunking_document_service.load_chunks(project_root)
    if not chunks:
        base["notes"] = [_text("book_analysis.note_chunks_required", language)]
        return base

    target_language = str(manifest.get("target_language", "")).strip()
    operations = manifest.get("operations")
    analysis_summary = (
        operations.get("book_analysis") if isinstance(operations, dict) else None
    )
    declared_running = bool(
        operation_is_active
        and isinstance(analysis_summary, dict)
        and analysis_summary.get("status") == "running"
    )
    selected_profile = _selected_profile(settings, selected_id)
    profile_compatible = bool(
        selected_profile is not None
        and int(selected_profile.get("context_window", 0))
        >= config.BOOK_ANALYSIS_MIN_CONTEXT_TOKENS
    )
    try:
        document = book_analysis_document_service.load_document(project_root)
    except book_analysis_document_service.BookAnalysisDocumentError as error_object:
        base.update(
            {
                "state": "invalid",
                "notes": [str(error_object), _text("book_analysis.note_reset_recovery", language)],
                "can_reset": True,
            }
        )
        return base

    if document is None:
        if declared_running:
            base.update(
                {
                    "state": "running",
                    "notes": [_text("book_analysis.note_running", language)],
                    "can_reset": True,
                }
            )
            return base
        base.update(
            {
                "state": "ready",
                "notes": [_ready_note(profile_compatible, language)],
                "can_analyze": profile_compatible and bool(target_language),
            }
        )
        return base

    completed = document.get("completed_report")
    candidate = document.get("candidate_run")
    has_started = isinstance(completed, dict) or isinstance(candidate, dict)
    source = book_analysis_document_service.canonical_source_descriptor(chunks)
    report_stale = bool(
        isinstance(completed, dict)
        and book_analysis_document_service.completed_report_is_stale(
            completed,
            source,
            target_language,
        )
    )
    report = completed.get("report") if isinstance(completed, dict) else None

    if declared_running and isinstance(candidate, dict) and candidate.get("status") == "running":
        base.update(
            {
                "state": "running",
                "notes": [_text("book_analysis.note_running", language)],
                "report": report,
                "report_stale": report_stale,
                "can_reset": has_started,
            }
        )
        return base

    if isinstance(completed, dict) and not report_stale:
        base.update(
            {
                "state": "fresh_completed",
                "notes": [_text("book_analysis.note_completed", language)],
                "report": report,
                "can_reset": True,
            }
        )
        return base

    candidate_matches = bool(
        selected_profile is not None
        and isinstance(candidate, dict)
        and book_analysis_document_service.candidate_resume_matches(
            candidate,
            source=source,
            target_language=target_language,
            profile_id=str(selected_id),
            profile_fingerprint=book_analysis_document_service.safe_profile_fingerprint(
                selected_profile
            ),
        )
    )
    if report_stale:
        state_name = "stale_completed"
        note = _text("book_analysis.note_stale", language)
    elif candidate_matches and candidate.get("status") == "running":
        state_name = "interrupted"
        note = _text("book_analysis.note_interrupted", language)
    elif candidate_matches and candidate.get("status") == "failed":
        state_name = "failed"
        note = _text("book_analysis.note_failed", language)
    elif candidate_matches and candidate.get("status") == "cancelled":
        state_name = "cancelled"
        note = _text("book_analysis.note_cancelled", language)
    else:
        state_name = "ready"
        note = (
            _text("book_analysis.note_new_candidate", language)
            if isinstance(candidate, dict)
            else _ready_note(profile_compatible, language)
        )
    base.update(
        {
            "state": state_name,
            "notes": [note],
            "report": report,
            "report_stale": report_stale,
            "can_analyze": profile_compatible and bool(target_language),
            "can_reset": has_started,
        }
    )
    return base


def _selected_profile(
    settings: dict[str, object] | None,
    profile_id: object,
) -> dict[str, object] | None:
    if not isinstance(settings, dict):
        return None
    profiles = settings.get("llm_profiles")
    if not isinstance(profiles, list):
        return None
    return next(
        (
            profile
            for profile in profiles
            if isinstance(profile, dict)
            and bool(profile.get("enabled", True))
            and str(profile.get("id", "")) == str(profile_id or "")
        ),
        None,
    )


def _ready_note(profile_compatible: bool, language: str) -> str:
    key = "book_analysis.note_ready" if profile_compatible else "book_analysis.note_profile_required"
    return _text(key, language)


def _text(key: str, language: str) -> str:
    return ui_state_service.translate(key, language)


# END OF FILE
