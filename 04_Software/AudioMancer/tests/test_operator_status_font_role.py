#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_operator_status_font_role.py
@brief Focused Qt tests for operator notes/status font roles.
@details Verifies read-only operator notes and status text editors opt out of
         the book-manipulation text font and instead use the UI-control font.
@author Eng. Dan Dumitru Pasare
@date 2026-05-15
@version 0.1.0
"""

# IMPORTS

import pytest

from audiomancer.services import ui_state_service
from audiomancer.ui.pages.ai_translation_page import AiTranslationPage
from audiomancer.ui.pages.audio_assembly_page import AudioAssemblyPage
from audiomancer.ui.pages.audio_blocks_page import AudioBlocksPage
from audiomancer.ui.pages.character_voices_page import CharacterVoicesPage
from audiomancer.ui.pages.narator_voice_page import NaratorVoicePage
from audiomancer.ui.pages.speech_blocks_page import SpeechBlocksPage
from audiomancer.ui.pages.text_chunking_page import TextChunkingPage
from audiomancer.ui.pages.text_cleanup_page import TextCleanupPage


@pytest.mark.parametrize(
    ("page_factory", "editor_name"),
    [
        (TextCleanupPage, "_notes_edit"),
        (TextChunkingPage, "_notes_edit"),
        (AiTranslationPage, "_notes_edit"),
        (SpeechBlocksPage, "_notes_edit"),
        (NaratorVoicePage, "_status_edit"),
        (CharacterVoicesPage, "_status_edit"),
        (AudioBlocksPage, "_status_edit"),
        (AudioAssemblyPage, "_status_edit"),
    ],
)
def test_operator_notes_and_status_editors_use_ui_font_role(qtbot, page_factory, editor_name: str) -> None:
    """
    @brief      Verify operator notes/status editors are marked for the UI-control font.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  page_factory Page constructor under test.
    @param[in]  editor_name Private editor attribute under test.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    page = page_factory()
    qtbot.addWidget(page)
    editor = getattr(page, editor_name)

    assert editor.property(ui_state_service.CONTROL_TEXT_FONT_ROLE_PROPERTY) == (
        ui_state_service.CONTROL_TEXT_FONT_ROLE_VALUE
    )
