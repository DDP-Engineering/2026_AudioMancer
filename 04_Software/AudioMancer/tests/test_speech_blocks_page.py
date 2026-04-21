#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_speech_blocks_page.py
@brief Focused Qt tests for the AudioMancer Speech Blocks page.
@details Verifies Speech Blocks rendering, review-only behavior, translated
         labels, and generation button enablement.
@author Eng. Dan Dumitru Pasare
@date 2026-04-21
@version 0.1.0
"""

# IMPORTS

from audiomancer.services import speech_blocks_service
from audiomancer.ui.pages.speech_blocks_page import SpeechBlocksPage


def test_speech_blocks_page_renders_chunks_and_read_only_block_details(qtbot) -> None:
    """
    @brief      Verify the page renders chunk lists, block lists, and read-only selected block details.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_speech_blocks_state(
        source_chunks=[
            {"chunk_id": "chunk-0001", "sequence_index": 1, "text": 'Narration. "Hello there."'},
        ],
        speech_blocks=[
            {
                "speech_block_id": "speech-block-0001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "chunk_sequence_index": 1,
                "source_language": "en",
                "speaker_kind": "character",
                "speaker_id": "alice",
                "speaker_display_name": "Alice",
                "content_kind": speech_blocks_service.CONTENT_KIND_DIALOGUE,
                "text": "Hello there.",
                "warning_flags": [],
            }
        ],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="completed",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
    )

    assert page._generate_button.isEnabled() is True
    assert page._chunk_list.count() == 1
    assert page._speech_block_list.count() == 1
    assert page._source_text_edit.toPlainText() == 'Narration. "Hello there."'
    assert page._source_text_edit.isReadOnly() is True
    assert page._speech_block_details.isReadOnly() is True
    assert page.selected_chunk_id() == "chunk-0001"
    assert page.selected_block_id() == "speech-block-0001"
    assert "Speaker: Alice" in page._speech_block_details.toPlainText()
    assert "Hello there." in page._speech_block_details.toPlainText()


def test_speech_blocks_page_disables_generate_without_source_and_while_busy(qtbot) -> None:
    """
    @brief      Verify generation stays disabled without source chunks and while a run is busy.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")

    assert page._generate_button.isEnabled() is False

    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Narration."}],
        speech_blocks=[],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="not_started",
        selected_source_language="en",
        processed_chunk_count=0,
        total_chunk_count=1,
    )
    page.set_busy(True)

    assert page._generate_button.isEnabled() is False
    assert page._profile_combo.isEnabled() is False


def test_speech_blocks_page_applies_translated_labels(qtbot) -> None:
    """
    @brief      Verify Speech Blocks labels are translated through the runtime UI catalog.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.apply_language("ro")

    assert "Blocuri Vorbire" in page._title_label.text()
    assert page._profile_label.text() == "Profil AI"
    assert page._generate_button.text() == "Genereaza Blocuri Vorbire"
    assert page._chunk_group.title() == "Lista Segmentelor"
    assert page._notes_group.title() == "Note Blocuri Vorbire"


# END OF FILE
