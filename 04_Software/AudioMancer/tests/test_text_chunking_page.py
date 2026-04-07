#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_chunking_page.py
@brief Focused Qt tests for the AudioMancer text-chunking page.
@details Verifies chunking-page button enablement, chunk list rendering, and
         selected chunk preview behavior for deterministic chunking.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.2.0
"""

# IMPORTS

from audiomancer.ui.pages.text_chunking_page import TextChunkingPage


def test_text_chunking_page_renders_chunks_and_selected_preview(qtbot) -> None:
    """
    @brief      Verify chunking-page state renders chunk lists and selected preview text.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    page = TextChunkingPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_processing_state(
        cleaned_text="clean text",
        chunks=[{
            "chunk_id": "chunk-0001",
            "sequence_index": 1,
            "chapter_label": None,
            "text": "Paragraph text",
            "source_start_line": 1,
            "source_end_line": 1,
            "chunking_mode": "deterministic",
            "semantic_strategy": None,
            "scene_note": None,
        }],
        notes=["Chunk artifact contains 1 chunks."],
        can_chunk=True,
    )

    assert page._chunk_button.isEnabled() is True
    assert page._chunk_list.count() == 1
    assert page._chunk_text_edit.toPlainText() == "Paragraph text"
    assert "Chunk artifact contains 1 chunks." in page._notes_edit.toPlainText()
    assert page.current_ai_strategy() == "paragraph"


def test_text_chunking_page_keeps_selectors_readable_while_busy(qtbot) -> None:
    """
    @brief      Verify AI selectors stay readable while chunking actions are busy.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    page = TextChunkingPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_processing_state(
        cleaned_text="clean text",
        chunks=[],
        notes=["busy"],
        can_chunk=True,
    )

    page.set_busy(True)

    assert page._chunk_button.isEnabled() is False
    assert page._ai_chunk_button.isEnabled() is False
    assert page._profile_combo.isEnabled() is True
    assert page._strategy_combo.isEnabled() is True


def test_text_chunking_page_enables_ai_button_when_profiles_exist(qtbot) -> None:
    """
    @brief      Verify AI-assisted chunking is enabled only when a profile is selected and AI chunking is allowed.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    page = TextChunkingPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_processing_state(
        cleaned_text="clean text",
        chunks=[],
        notes=["ready"],
        can_chunk=True,
        can_ai_chunk=True,
    )

    assert page._chunk_button.isEnabled() is True
    assert page._ai_chunk_button.isEnabled() is True


# END OF FILE
