#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_cleanup_page.py
@brief Qt tests for the unified Cleanup page.
@details Verifies the single Cleanup action, optional AI profile, and optional
         operator edit, save, and cancel controls.
"""

# IMPORTS

from PySide6.QtWidgets import QApplication

from audiomancer.ui.pages.text_cleanup_page import TextCleanupPage

# PUBLIC API


def test_page_exposes_one_cleanup_action_with_optional_ai_profile(qtbot) -> None:
    """
    @brief      Verify the page exposes one Cleanup action with an optional AI profile.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Local Qwen", "qwen")], "qwen")
    page.set_processing_state("source", None, [], True, True)
    requested: list[object] = []
    page.cleanup_requested.connect(requested.append)

    page._cleanup_button.click()
    assert requested == ["qwen"]

    page._ai_profile_combo.setCurrentIndex(0)
    page._cleanup_button.click()
    assert requested[-1] is None


def test_page_edit_save_and_cancel_are_optional(qtbot) -> None:
    """
    @brief      Verify optional cleaned-text editing supports save and cancel.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_processing_state("source", "clean", [], True, True, True, "passed", 0)
    status_text = page.operation_status_text()
    assert "low-confidence boundaries: 0" in status_text
    assert "preserved" not in status_text
    saved: list[str] = []
    page.save_cleaned_text_requested.connect(saved.append)

    page._edit_cleaned_button.click()
    page._cleaned_text_edit.setPlainText("changed")
    page._cancel_edit_button.click()
    assert page._cleaned_text_edit.toPlainText() == "clean"

    page._edit_cleaned_button.click()
    page._cleaned_text_edit.setPlainText("saved")
    page._save_cleaned_button.click()
    assert saved == ["saved"]


def test_active_cleaned_text_edit_survives_refresh_and_blocks_workflow_actions(qtbot) -> None:
    """Verify a same-project refresh cannot discard an active Cleanup draft."""
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Local Qwen", "qwen")], "qwen")
    page.set_processing_state("source", "saved text", [], True, True, True, "passed", 0)
    signals: list[str] = []
    page.extract_requested.connect(lambda: signals.append("extract"))
    page.cleanup_requested.connect(lambda _profile: signals.append("cleanup"))
    page.reset_cleanup_requested.connect(lambda: signals.append("reset"))

    page._edit_cleaned_button.click()
    page._cleaned_text_edit.setPlainText("exact unsaved draft")
    page.set_processing_state("new source", "persisted text", ["refreshed"], True, True, True)

    assert page._editing_cleaned_text is True
    assert page._cleaned_text_edit.toPlainText() == "exact unsaved draft"
    assert page._saved_cleaned_text == "saved text"
    assert page._cleaned_text_edit.isReadOnly() is False
    assert page._extract_button.isEnabled() is False
    assert page._cleanup_button.isEnabled() is False
    assert page._reset_cleanup_button.isEnabled() is False
    assert page._ai_profile_label.isEnabled() is False
    assert page._ai_profile_combo.isEnabled() is False
    assert page._save_cleaned_button.isEnabled() is True
    assert page._cancel_edit_button.isEnabled() is True

    page._extract_button.click()
    page._cleanup_button.click()
    page._reset_cleanup_button.click()
    assert signals == []

    page._cancel_edit_button.click()
    assert page._cleaned_text_edit.toPlainText() == "saved text"
    assert page._editing_cleaned_text is False


def test_busy_transition_keeps_active_cleaned_text_draft(qtbot) -> None:
    """Verify busy-state changes never replace the editable Cleanup buffer."""
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_processing_state("source", "saved", [], True, True, True, "passed", 0)

    page._edit_cleaned_button.click()
    page._cleaned_text_edit.setPlainText("draft while busy")
    page.set_busy(True, "Cleanup")
    page.set_busy(False)

    assert page._editing_cleaned_text is True
    assert page._cleaned_text_edit.toPlainText() == "draft while busy"
    assert page._cleaned_text_edit.isReadOnly() is False


def test_cleanup_previews_share_one_minimum_width(qtbot) -> None:
    """
    @brief      Verify neither preview can be dragged narrower than the other.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.resize(1400, 800)
    page.show()
    QApplication.processEvents()

    shared_minimum = page._cleaned_group.minimumWidth()
    assert page._extracted_group.minimumWidth() == shared_minimum
    # The Cleaned Text preview carries the Edit/Save/Cancel row, so its own
    # content is what sets the width both panes have to respect.
    assert shared_minimum >= page._cleaned_group.minimumSizeHint().width()


def test_cleanup_previews_open_at_equal_width(qtbot) -> None:
    """
    @brief      Verify both previews open equal and stay equal as the page resizes.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.resize(1400, 800)
    page.show()
    QApplication.processEvents()

    opening_sizes = page._preview_splitter.sizes()
    # One pixel of slack: an odd number of pixels cannot split evenly in two.
    assert abs(opening_sizes[0] - opening_sizes[1]) <= 1

    page.resize(1700, 800)
    QApplication.processEvents()

    widened_sizes = page._preview_splitter.sizes()
    assert abs(widened_sizes[0] - widened_sizes[1]) <= 1
    assert widened_sizes[0] > opening_sizes[0]


# END OF FILE
