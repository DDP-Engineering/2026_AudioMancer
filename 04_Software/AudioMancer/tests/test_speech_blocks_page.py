#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_speech_blocks_page.py
@brief Focused Qt tests for the AudioMancer Speech Blocks page.
@details Verifies Speech Blocks rendering, editable selected-block behavior,
         approval controls, bounded approval navigation, refresh-state
         preservation, translated labels, and generation button enablement.
@author Eng. Dan Dumitru Pasare
@date 2026-04-24
@version 0.4.0
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
    @version    0.2.0
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
                "speech_block_id": "0001-000001",
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
        speaker_catalog=[
            {"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"},
            {"speaker_id": "alice", "display_name": "Alice", "speaker_kind": "character"},
        ],
        content_kind_options=[
            (speech_blocks_service.CONTENT_KIND_NARRATION, "Narration"),
            (speech_blocks_service.CONTENT_KIND_DIALOGUE, "Dialogue"),
            (speech_blocks_service.CONTENT_KIND_BACKGROUND_NOISE, "Background Noise"),
            (speech_blocks_service.CONTENT_KIND_PAUSE, "Pause"),
        ],
    )

    assert page._generate_button.isEnabled() is True
    assert page._chunk_list.count() == 1
    assert page._speech_block_list.count() == 1
    assert page._source_text_edit.toPlainText() == 'Narration. "Hello there."'
    assert page._source_text_edit.isReadOnly() is True
    assert page._speech_block_text_edit.isReadOnly() is True
    assert page.selected_chunk_id() == "chunk-0001"
    assert page.selected_block_id() == "0001-000001"
    assert page._speaker_combo.currentData() == "alice"
    assert page._speech_block_text_edit.toPlainText() == "Hello there."


def test_speech_blocks_page_edit_enables_fields_and_save_returns_to_indicators(qtbot) -> None:
    """
    @brief      Verify Edit enables selected-block inputs and Save disables them after emitting changes.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
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
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "chunk_sequence_index": 1,
                "source_language": "en",
                "speaker_kind": "character",
                "speaker_id": "alice",
                "speaker_display_name": "Alice",
                "content_kind": speech_blocks_service.CONTENT_KIND_DIALOGUE,
                "text": "Hello there.",
                "warning_flags": ["ambiguous_speaker"],
            }
        ],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="in_progress",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
        speaker_catalog=[
            {"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"},
            {"speaker_id": "alice", "display_name": "Alice", "speaker_kind": "character"},
        ],
        content_kind_options=[
            (speech_blocks_service.CONTENT_KIND_NARRATION, "Narration"),
            (speech_blocks_service.CONTENT_KIND_DIALOGUE, "Dialogue"),
            (speech_blocks_service.CONTENT_KIND_BACKGROUND_NOISE, "Background Noise"),
            (speech_blocks_service.CONTENT_KIND_PAUSE, "Pause"),
        ],
    )
    saved_payloads: list[tuple[str, str, str, str]] = []
    page.save_block_requested.connect(lambda *payload: saved_payloads.append(tuple(str(value) for value in payload)))

    page._edit_button.click()

    assert page._speaker_combo.isEnabled() is True
    assert page._content_kind_combo.isEnabled() is True
    assert page._speech_block_text_edit.isReadOnly() is False
    assert page._save_button.isEnabled() is True
    assert page._warning_label.text() == ""

    page._speaker_combo.setCurrentIndex(page._speaker_combo.findData("narrator"))
    page._content_kind_combo.setCurrentIndex(
        page._content_kind_combo.findData(speech_blocks_service.CONTENT_KIND_NARRATION)
    )
    page._speech_block_text_edit.setPlainText("Updated narration.")
    page._save_button.click()

    assert saved_payloads == [
        ("0001-000001", "narrator", speech_blocks_service.CONTENT_KIND_NARRATION, "Updated narration.")
    ]
    assert page._speaker_combo.isEnabled() is False
    assert page._content_kind_combo.isEnabled() is False
    assert page._speech_block_text_edit.isReadOnly() is True
    assert page._save_button.isEnabled() is False


def test_speech_blocks_page_approve_selected_emits_only_selected_block(qtbot) -> None:
    """
    @brief      Verify the selected-block approval button emits the selected Speech Block id.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_speech_blocks_state(
        source_chunks=[
            {"chunk_id": "chunk-0001", "sequence_index": 1, "text": "First chunk."},
        ],
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "chunk_sequence_index": 1,
                "source_language": "en",
                "speaker_kind": "narrator",
                "speaker_id": "narrator",
                "speaker_display_name": "Narrator",
                "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                "text": "First block.",
                "warning_flags": [],
                "approved": False,
            },
            {
                "speech_block_id": "0001-000002",
                "sequence_index": 2,
                "chunk_id": "chunk-0001",
                "chunk_sequence_index": 1,
                "source_language": "en",
                "speaker_kind": "narrator",
                "speaker_id": "narrator",
                "speaker_display_name": "Narrator",
                "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                "text": "Second block.",
                "warning_flags": [],
                "approved": False,
            },
        ],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="in_progress",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
        speaker_catalog=[{"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}],
        content_kind_options=[(speech_blocks_service.CONTENT_KIND_NARRATION, "Narration")],
    )
    approved_block_ids: list[str] = []
    page.approve_block_requested.connect(approved_block_ids.append)

    page._speech_block_list.setCurrentRow(1)
    page._approve_block_button.click()

    assert approved_block_ids == ["0001-000002"]


def test_speech_blocks_page_advances_visible_block_selection_with_limit(qtbot) -> None:
    """
    @brief      Verify approval navigation moves within the visible Speech Blocks list only.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "First chunk."}],
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "chunk_sequence_index": 1,
                "source_language": "en",
                "speaker_kind": "narrator",
                "speaker_id": "narrator",
                "speaker_display_name": "Narrator",
                "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                "text": "First block.",
                "warning_flags": [],
                "approved": False,
            },
            {
                "speech_block_id": "0001-000002",
                "sequence_index": 2,
                "chunk_id": "chunk-0001",
                "chunk_sequence_index": 2,
                "source_language": "en",
                "speaker_kind": "narrator",
                "speaker_id": "narrator",
                "speaker_display_name": "Narrator",
                "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                "text": "Second block.",
                "warning_flags": [],
                "approved": False,
            },
        ],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="in_progress",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
        speaker_catalog=[{"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}],
        content_kind_options=[(speech_blocks_service.CONTENT_KIND_NARRATION, "Narration")],
    )

    page.advance_to_next_block()

    assert page.selected_block_id() == "0001-000002"
    assert page._speech_block_list.currentRow() == 1

    page.advance_to_next_block()

    assert page.selected_block_id() == "0001-000002"
    assert page._speech_block_list.currentRow() == 1


def test_speech_blocks_page_refresh_preserves_block_selection_and_source_scroll(qtbot) -> None:
    """
    @brief      Verify state refresh keeps selected Speech Block and selected-chunk scroll position.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.resize(900, 700)
    page.show()
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    source_text = "\n".join(f"Line {line_number}" for line_number in range(80))
    speech_blocks = [
        {
            "speech_block_id": "0001-000001",
            "sequence_index": 1,
            "chunk_id": "chunk-0001",
            "chunk_sequence_index": 1,
            "source_language": "en",
            "speaker_kind": "narrator",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            "text": "First block.",
            "warning_flags": [],
            "approved": False,
        },
        {
            "speech_block_id": "0001-000002",
            "sequence_index": 2,
            "chunk_id": "chunk-0001",
            "chunk_sequence_index": 1,
            "source_language": "en",
            "speaker_kind": "narrator",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            "text": "Second block.",
            "warning_flags": [],
            "approved": False,
        },
    ]
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": source_text}],
        speech_blocks=speech_blocks,
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="in_progress",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
        speaker_catalog=[{"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}],
        content_kind_options=[(speech_blocks_service.CONTENT_KIND_NARRATION, "Narration")],
    )
    page._speech_block_list.setCurrentRow(1)
    source_scroll_bar = page._source_text_edit.verticalScrollBar()
    source_scroll_bar.setValue(source_scroll_bar.maximum())
    saved_scroll_position = source_scroll_bar.value()

    refreshed_blocks = [dict(block) for block in speech_blocks]
    refreshed_blocks[1]["text"] = "Edited second block."
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": source_text}],
        speech_blocks=refreshed_blocks,
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="in_progress",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
        speaker_catalog=[{"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}],
        content_kind_options=[(speech_blocks_service.CONTENT_KIND_NARRATION, "Narration")],
    )
    qtbot.wait(0)

    assert page.selected_block_id() == "0001-000002"
    assert page._speech_block_list.currentRow() == 1
    assert source_scroll_bar.value() == saved_scroll_position


def test_speech_blocks_page_disables_generate_without_source_and_while_busy(qtbot) -> None:
    """
    @brief      Verify generation stays disabled without source chunks and while a run is busy.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
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
    assert page._reset_generation_button.text() == "Reseteaza Blocurile de Vorbire"
    assert page._approve_block_button.text() == "Aproba"
    assert page._chunk_group.title() == "Lista Segmentelor"
    assert page._notes_group.title() == "Note Blocuri Vorbire"


# END OF FILE
