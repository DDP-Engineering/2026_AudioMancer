#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_translation_page.py
@brief Focused Qt tests for monofile AI Translation review behavior.
@details Verifies debounced edits, flush ordering, and status-driven controls.
"""

# IMPORTS

from audiomancer.services import ai_translation_service
from audiomancer.ui.pages.ai_translation_page import AiTranslationPage

# PUBLIC API


def test_translation_edit_debounce_and_flush(qtbot) -> None:
    """Verify REQ-UX-002 rapid edits emit one save and selection changes flush immediately."""
    page = _build_page(qtbot)
    emitted = []
    page.translated_text_changed.connect(lambda chunk_id, text: emitted.append((chunk_id, text)))

    page._translated_text_edit.setPlainText("Edit one")
    page._translated_text_edit.setPlainText("Edit two")
    page._translated_text_edit.setPlainText("Final edit")
    qtbot.wait(800)
    assert emitted == [("chunk-0001", "Final edit")]

    page._translated_text_edit.setPlainText("Flush before selection")
    page._chunk_list.setCurrentRow(1)
    assert emitted[-1] == ("chunk-0001", "Flush before selection")


def test_translation_page_control_state_uses_review_pending_and_completed(qtbot) -> None:
    """Verify REQ-UX-002 Start is disabled after generation and reenabled for empty text."""
    page = _build_page(qtbot)
    assert page._start_button.isEnabled() is False
    assert page._reset_button.isEnabled() is True

    page.set_translation_state(
        source_chunks=_source_chunks(),
        translated_chunks=[
            {"chunk_id": "chunk-0001", "translated_text": "Traducere", "approved": True},
            {"chunk_id": "chunk-0002", "translated_text": "", "approved": False},
        ],
        notes=["resume"],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STATUS_IN_PROGRESS,
        translated_count=1,
        approved_count=1,
        total_count=2,
    )
    assert page._start_button.isEnabled() is True

    page.set_translation_state(
        source_chunks=_source_chunks(),
        translated_chunks=[
            {"chunk_id": "chunk-0001", "translated_text": "Traducere", "approved": True},
            {"chunk_id": "chunk-0002", "translated_text": "Alta traducere", "approved": True},
        ],
        notes=["complete"],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STATUS_COMPLETED,
        translated_count=2,
        approved_count=2,
        total_count=2,
    )
    assert page._start_button.isEnabled() is False


def test_approve_selected_flushes_pending_edit_before_signal(qtbot) -> None:
    """Verify REQ-UX-002 approval observes the latest local edit."""
    page = _build_page(qtbot)
    events = []
    page.translated_text_changed.connect(lambda chunk_id, text: events.append(("edit", chunk_id, text)))
    page.approve_selected_requested.connect(lambda chunk_id: events.append(("approve", chunk_id)))

    page._translated_text_edit.setPlainText("Latest translation")
    page._emit_approve_selected()

    assert events == [
        ("edit", "chunk-0001", "Latest translation"),
        ("approve", "chunk-0001"),
    ]


def test_translation_page_displays_locked_language_and_chunk_preview(qtbot) -> None:
    """Verify locked language indicators and canonical source preview remain visible."""
    page = _build_page(qtbot)
    assert page._original_language_value_label.text() == "English"
    assert page._target_language_value_label.text() == "Romanian"
    assert page._source_text_edit.toPlainText() == "Original one"
    assert page._chunk_list.item(0).text() == "[Translated] chunk-0001 | Original one"


# TEST HELPERS


def _build_page(qtbot) -> AiTranslationPage:
    """Build one active translation page with two review-pending chunks."""
    page = AiTranslationPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_translation_state(
        source_chunks=_source_chunks(),
        translated_chunks=[
            {"chunk_id": "chunk-0001", "translated_text": "Translated one", "approved": False},
            {"chunk_id": "chunk-0002", "translated_text": "Translated two", "approved": False},
        ],
        notes=["review"],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
        translated_count=2,
        approved_count=0,
        total_count=2,
    )
    return page


def _source_chunks() -> list[dict[str, object]]:
    """Return canonical source chunks for page-state tests."""
    return [
        {"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Original one"},
        {"chunk_id": "chunk-0002", "sequence_index": 2, "text": "Original two"},
    ]


# END OF FILE
