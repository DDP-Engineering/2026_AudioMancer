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

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

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


def test_same_content_refresh_preserves_editor_state_and_continued_typing(qtbot) -> None:
    """Verify a persisted edit round-trip preserves both editor documents and character order."""
    page = _build_page(qtbot)
    page.resize(640, 420)
    page.show()
    source_text = "\n".join(f"Source {index:02d} " + ("s" * 160) for index in range(30))
    translated_text = "\n".join(f"Translation {index:02d} " + ("t" * 160) for index in range(30))
    source_chunks = [
        {"chunk_id": "chunk-0001", "sequence_index": 1, "text": source_text},
        {"chunk_id": "chunk-0002", "sequence_index": 2, "text": "Original two"},
    ]
    translated_chunks = [
        {"chunk_id": "chunk-0001", "translated_text": translated_text, "approved": False},
        {"chunk_id": "chunk-0002", "translated_text": "Translated two", "approved": False},
    ]
    page.set_translation_state(
        source_chunks=source_chunks,
        translated_chunks=translated_chunks,
        notes=["review"],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
        translated_count=2,
        approved_count=0,
        total_count=2,
    )
    page._source_text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    page._translated_text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    qtbot.wait(20)

    source_cursor = page._source_text_edit.textCursor()
    source_cursor.setPosition(12)
    source_cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 9)
    page._source_text_edit.setTextCursor(source_cursor)
    translated_cursor = page._translated_text_edit.textCursor()
    insertion_position = translated_text.index("Translation 15") + len("Translation 15")
    translated_cursor.setPosition(insertion_position)
    page._translated_text_edit.setTextCursor(translated_cursor)
    page._translated_text_edit.insertPlainText("X")
    expected_after_first_edit = translated_text[:insertion_position] + "X" + translated_text[insertion_position:]
    assert page._translated_text_edit.document().isUndoAvailable() is True

    editors = (page._source_text_edit, page._translated_text_edit)
    for editor in editors:
        editor.horizontalScrollBar().setValue(max(1, editor.horizontalScrollBar().maximum() // 2))
        editor.verticalScrollBar().setValue(max(1, editor.verticalScrollBar().maximum() // 2))
    source_state = (
        page._source_text_edit.textCursor().position(),
        page._source_text_edit.textCursor().anchor(),
        page._source_text_edit.horizontalScrollBar().value(),
        page._source_text_edit.verticalScrollBar().value(),
    )
    translated_state = (
        page._translated_text_edit.textCursor().position(),
        page._translated_text_edit.textCursor().anchor(),
        page._translated_text_edit.horizontalScrollBar().value(),
        page._translated_text_edit.verticalScrollBar().value(),
    )
    persisted = []

    def persist_and_refresh(chunk_id: str, text: str) -> None:
        """Record one edit and synchronously rebuild controller-driven page state."""
        persisted.append((chunk_id, text))
        translated_chunks[0]["translated_text"] = text
        page.set_translation_state(
            source_chunks=source_chunks,
            translated_chunks=translated_chunks,
            notes=["review"],
            original_language="English",
            target_language="ro",
            selected_profile_id="profile-1",
            stage_status=ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
            translated_count=2,
            approved_count=0,
            total_count=2,
        )

    page.translated_text_changed.connect(persist_and_refresh)
    page.flush_pending_translation_edit()

    assert persisted == [("chunk-0001", expected_after_first_edit)]
    assert (
        page._source_text_edit.textCursor().position(),
        page._source_text_edit.textCursor().anchor(),
        page._source_text_edit.horizontalScrollBar().value(),
        page._source_text_edit.verticalScrollBar().value(),
    ) == source_state
    assert (
        page._translated_text_edit.textCursor().position(),
        page._translated_text_edit.textCursor().anchor(),
        page._translated_text_edit.horizontalScrollBar().value(),
        page._translated_text_edit.verticalScrollBar().value(),
    ) == translated_state
    assert page._translated_text_edit.document().isUndoAvailable() is True

    page._translated_text_edit.insertPlainText("Y")
    page.flush_pending_translation_edit()
    expected_final = (
        expected_after_first_edit[: insertion_position + 1]
        + "Y"
        + expected_after_first_edit[insertion_position + 1 :]
    )
    assert persisted[-1] == ("chunk-0001", expected_final)
    assert page._translated_text_edit.toPlainText() == expected_final


def test_authoritative_content_change_updates_editors_without_manual_edit_signal(qtbot) -> None:
    """Verify genuinely changed source and translation values replace stale editor content under the guard."""
    page = _build_page(qtbot)
    emitted = []
    page.translated_text_changed.connect(lambda chunk_id, text: emitted.append((chunk_id, text)))

    page.set_translation_state(
        source_chunks=[
            {"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Externally changed source"},
            {"chunk_id": "chunk-0002", "sequence_index": 2, "text": "Original two"},
        ],
        translated_chunks=[
            {"chunk_id": "chunk-0001", "translated_text": "Authoritative translation", "approved": False},
            {"chunk_id": "chunk-0002", "translated_text": "Translated two", "approved": False},
        ],
        notes=["external refresh"],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
        translated_count=2,
        approved_count=0,
        total_count=2,
    )

    assert page._source_text_edit.toPlainText() == "Externally changed source"
    assert page._translated_text_edit.toPlainText() == "Authoritative translation"
    assert page._loading_translation_text is False
    assert page._pending_edit is None
    assert page._edit_timer.isActive() is False
    assert emitted == []


def test_translation_state_rebuild_preserves_selected_chunk_by_id(qtbot) -> None:
    """Verify list reordering retains the selected stable chunk identifier."""
    page = _build_page(qtbot)
    page._chunk_list.setCurrentRow(1)
    assert page.selected_chunk_id() == "chunk-0002"

    page.set_translation_state(
        source_chunks=[
            {"chunk_id": "chunk-0001", "sequence_index": 2, "text": "Original one"},
            {"chunk_id": "chunk-0002", "sequence_index": 1, "text": "Original two"},
        ],
        translated_chunks=[
            {"chunk_id": "chunk-0001", "translated_text": "Translated one", "approved": False},
            {"chunk_id": "chunk-0002", "translated_text": "Translated two", "approved": False},
        ],
        notes=["reordered"],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STATUS_REVIEW_PENDING,
        translated_count=2,
        approved_count=0,
        total_count=2,
    )

    assert page.selected_chunk_id() == "chunk-0002"
    assert page._chunk_list.currentRow() == 0
    assert page._source_text_edit.toPlainText() == "Original two"
    assert page._translated_text_edit.toPlainText() == "Translated two"


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


def test_retranslate_selected_requires_started_idle_translation_state(qtbot) -> None:
    """Verify retranslation is inert before start, available when started, and disabled while busy or reset."""
    page = _build_page(qtbot)
    requests = []
    page.retranslate_selected_requested.connect(
        lambda profile_id, chunk_id: requests.append((profile_id, chunk_id))
    )
    untranslated_chunks = [
        {"chunk_id": "chunk-0001", "translated_text": "", "approved": False},
        {"chunk_id": "chunk-0002", "translated_text": "", "approved": False},
    ]

    page.set_translation_state(
        source_chunks=_source_chunks(),
        translated_chunks=untranslated_chunks,
        notes=["not started"],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STATUS_NOT_STARTED,
        translated_count=0,
        approved_count=0,
        total_count=2,
    )
    assert page._retranslate_button.isEnabled() is False
    page._emit_retranslate_selected()
    assert requests == []

    page.set_translation_state(
        source_chunks=_source_chunks(),
        translated_chunks=untranslated_chunks,
        notes=["started"],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STATUS_IN_PROGRESS,
        translated_count=0,
        approved_count=0,
        total_count=2,
    )
    assert page._retranslate_button.isEnabled() is True
    page.set_busy(True)
    assert page._retranslate_button.isEnabled() is False
    page.set_busy(False)
    assert page._retranslate_button.isEnabled() is True

    page.set_translation_state(
        source_chunks=_source_chunks(),
        translated_chunks=untranslated_chunks,
        notes=["reset"],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STATUS_NOT_STARTED,
        translated_count=0,
        approved_count=0,
        total_count=2,
    )
    assert page._retranslate_button.isEnabled() is False
    page._emit_retranslate_selected()
    assert requests == []


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


def test_start_translation_flushes_pending_edit_before_signal_and_stops_timer(qtbot) -> None:
    """Verify worker intent follows edit persistence and busy state prevents a delayed callback."""
    page = _build_page(qtbot)
    events = []
    page.translated_text_changed.connect(lambda chunk_id, text: events.append(("edit", chunk_id, text)))
    page.start_translation_requested.connect(lambda profile_id: events.append(("start", profile_id)))

    page._translated_text_edit.setPlainText("Latest before worker")
    assert page._edit_timer.isActive() is True
    page._emit_start_translation()

    assert events == [
        ("edit", "chunk-0001", "Latest before worker"),
        ("start", "profile-1"),
    ]
    assert page._edit_timer.isActive() is False
    page.flush_pending_translation_edit()
    assert [event for event in events if event[0] == "edit"] == [
        ("edit", "chunk-0001", "Latest before worker")
    ]

    page._translated_text_edit.setPlainText("Defensive busy stop")
    assert page._edit_timer.isActive() is True
    page.set_busy(True)
    assert page._edit_timer.isActive() is False
    qtbot.wait(800)
    assert [event for event in events if event[0] == "edit"] == [
        ("edit", "chunk-0001", "Latest before worker")
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
