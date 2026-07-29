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
@brief Qt tests for the unified Cleanup V2 page.
@details Verifies the single Cleanup action, optional AI profile, and optional
         operator edit, save, and cancel controls.
@author Eng. Dan Dumitru Pasare
@date 2026-07-27
@version 0.1.0
"""

# IMPORTS

from audiomancer.ui.pages.text_cleanup_page import TextCleanupPage

# PUBLIC API


def test_page_exposes_one_cleanup_action_with_optional_ai_profile(qtbot) -> None:
    """
    @brief      Verify the page exposes one Cleanup action with an optional AI profile.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-27
    @version    0.1.0
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
    assert not hasattr(page, "_ai_clean_button")
    assert not hasattr(page, "_apply_spacing_button")

    page._ai_profile_combo.setCurrentIndex(0)
    page._cleanup_button.click()
    assert requested[-1] is None


def test_page_edit_save_and_cancel_are_optional(qtbot) -> None:
    """
    @brief      Verify optional cleaned-text editing supports save and cancel.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-27
    @version    0.1.0
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_processing_state("source", "clean", [], True, True, True, "passed", 0)
    status_text = page._status_edit.toPlainText()
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


# END OF FILE
