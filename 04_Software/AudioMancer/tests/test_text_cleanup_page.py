#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_cleanup_page.py
@brief Focused Qt tests for the AudioMancer text-cleanup page.
@details Verifies extraction-button enablement and preview state updates for
         the extraction-only cleanup slice.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.1.0
"""

# IMPORTS

from audiomancer.ui.pages.text_cleanup_page import TextCleanupPage


def test_text_cleanup_page_enables_extract_only_with_project_and_source(qtbot) -> None:
    """
    @brief      Verify extraction becomes available only for an active project with source data.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)

    assert page._extract_button.isEnabled() is False

    page.set_project_active(True)
    page.set_processing_state(
        extracted_text=None,
        cleaned_text=None,
        notes=["Ready"],
        can_extract=True,
    )

    assert page._extract_button.isEnabled() is True

    page.set_busy(True)

    assert page._extract_button.isEnabled() is False


def test_text_cleanup_page_updates_previews_and_notes(qtbot) -> None:
    """
    @brief      Verify extraction state updates the previews and notes panes.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    page = TextCleanupPage()
    qtbot.addWidget(page)

    page.set_project_active(True)
    page.set_processing_state(
        extracted_text="Raw paragraph",
        cleaned_text="Clean paragraph",
        notes=["Warning A", "Warning B"],
        can_extract=True,
    )

    assert page._extracted_text_edit.toPlainText() == "Raw paragraph"
    assert page._cleaned_text_edit.toPlainText() == "Clean paragraph"
    assert page._notes_edit.toPlainText() == "Warning A\nWarning B"


# END OF FILE
