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
@version 0.8.8
"""

# IMPORTS

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QSizePolicy

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
    @version    0.4.0
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
            (speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE, "Scene Ambience"),
            (speech_blocks_service.CONTENT_KIND_PAUSE, "Pause"),
        ],
        can_reset=True,
        selected_text_character_limit=180,
    )

    assert page._generate_button.isEnabled() is False
    assert page._reset_generation_button.isEnabled() is True
    assert page._chunk_list.count() == 1
    assert page._chunk_list.textElideMode() == Qt.TextElideMode.ElideRight
    assert page._speech_block_list.count() == 1
    assert page._source_text_edit.toPlainText() == 'Narration. "Hello there."'
    assert page._source_text_edit.isReadOnly() is True
    assert page._speech_block_text_edit.isReadOnly() is True
    assert page.selected_chunk_id() == "chunk-0001"
    assert page.selected_block_id() == "0001-000001"
    assert page._speaker_combo.currentData() == "alice"
    assert page._speech_block_text_edit.toPlainText() == "Hello there."
    assert page._character_count_edit.isReadOnly() is True
    assert page._character_count_edit.text() == "12 / 180"


def test_speech_blocks_page_chunk_list_uses_one_line_full_preview(qtbot) -> None:
    """
    @brief      Verify chunk-list rows keep the full flattened preview and let the view elide it.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-23
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    long_preview = "First sentence.\nSecond sentence with enough words to exceed the old fixed preview limit."

    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": long_preview}],
        speech_blocks=[],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="not_started",
        selected_source_language="en",
        processed_chunk_count=0,
        total_chunk_count=1,
    )

    row_text = page._chunk_list.item(0).text()

    assert "\n" not in row_text
    assert "Second sentence with enough words to exceed the old fixed preview limit." in row_text


def test_speech_blocks_page_header_uses_compact_buttons_and_wider_profile(qtbot) -> None:
    """
    @brief      Verify compact Speech Blocks header labels leave room for the AI profile selector.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-20
    @version    0.1.1
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.apply_language("en")

    assert page._generate_button.text() == "Generate All"
    assert page._reset_generation_button.text() == "Reset"
    assert page._approve_all_button.text() == "Approve All"
    assert page._profile_combo.minimumWidth() >= 260
    assert page._generate_button.minimumWidth() >= 140
    assert page._reset_generation_button.minimumWidth() >= 96
    assert page._approve_all_button.minimumWidth() >= 132


def test_speech_blocks_page_selected_audio_controls_emit_and_track_playback(qtbot) -> None:
    """
    @brief      Verify selected Speech Block audio controls mirror Audio Blocks selected actions.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.2.4
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Narration."}],
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "source_language": "en",
                "speaker_kind": "narrator",
                "speaker_id": "narrator",
                "speaker_display_name": "Narrator",
                "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                "text": "Narration.",
                "warning_flags": [],
                "approved": True,
                "audio_can_play": True,
                "audio_metadata_only": False,
            }
        ],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="completed",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
        speaker_catalog=[{"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}],
        content_kind_options=[(speech_blocks_service.CONTENT_KIND_NARRATION, "Narration")],
        can_reset=True,
    )

    assert page._generate_audio_button.isEnabled() is True
    assert page._generate_audio_button.text() == "Generate Audio"
    assert page._selected_audio_playback_button.isEnabled() is True
    assert page._selected_audio_playback_button.text() == "Play"
    generate_row = page._chunk_actions_grid_layout.getItemPosition(
        page._chunk_actions_grid_layout.indexOf(page._generate_audio_button)
    )[0]
    play_row = page._chunk_actions_grid_layout.getItemPosition(
        page._chunk_actions_grid_layout.indexOf(page._selected_audio_playback_button)
    )[0]
    assert generate_row == play_row
    assert page._chunk_actions_column_layout.contentsMargins().top() == 2
    # The Chunk List frame caps at the action-button column height so their bottoms align.
    assert page._chunk_group.maximumHeight() == page._chunk_actions_column.sizeHint().height()

    with qtbot.waitSignal(page.generate_audio_selected_requested) as generation_signal:
        page._generate_audio_button.click()
    with qtbot.waitSignal(page.selected_audio_playback_toggle_requested) as playback_signal:
        page._selected_audio_playback_button.click()

    assert generation_signal.args == ["0001-000001"]
    assert playback_signal.args == ["0001-000001"]

    page.set_selected_audio_playback_active(True)

    assert page._selected_audio_playback_button.text() == "Stop"

    page.set_selected_audio_playback_active(False)

    assert page._selected_audio_playback_button.text() == "Play"


def test_speech_blocks_page_enables_selected_audio_controls_for_scene_ambience(qtbot) -> None:
    """
    @brief      Verify Scene Ambience blocks expose the same selected audio actions as spoken blocks.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-20
    @version    0.1.1
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "A quiet room."}],
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "source_language": "en",
                "speaker_kind": speech_blocks_service.SPEAKER_KIND_OPERATION,
                "speaker_id": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
                "speaker_display_name": "Scene Ambience",
                "content_kind": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
                "text": "Quiet room tone with sparse interface clicks.",
                "warning_flags": [],
                "approved": True,
                "audio_can_play": True,
                "audio_metadata_only": False,
            }
        ],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="completed",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
        speaker_catalog=[{"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}],
        content_kind_options=[(speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE, "Scene Ambience")],
        can_reset=True,
    )

    assert page._generate_audio_button.isEnabled() is True
    assert page._selected_audio_playback_button.isEnabled() is True


def test_speech_blocks_page_selected_chunk_actions_fill_row_evenly(qtbot) -> None:
    """
    @brief      Verify selected-chunk action controls align under the chunk editor.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-20
    @version    0.3.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.resize(1000, 720)
    page.show()
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
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
    qtbot.wait(0)

    assert page._resplit_button.minimumWidth() >= 180
    assert page._resplit_button.geometry().left() == page._source_text_edit.geometry().left()
    assert abs(page._resplit_button.geometry().right() - page._source_text_edit.geometry().right()) <= 2
    assert hasattr(page, "_scene_ambience_combo") is False


def test_speech_blocks_page_selected_chunk_pane_keeps_minimum_width(qtbot) -> None:
    """
    @brief      Verify the lower splitter keeps a usable minimum width for the selected chunk pane.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-23
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.resize(1400, 780)
    page.show()
    qtbot.wait(0)

    assert page._source_group.minimumWidth() >= 480


def test_speech_blocks_page_restores_selected_chunk_text_selection(qtbot) -> None:
    """
    @brief      Verify selected-chunk text selection and scroll can be restored after UI refreshes.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-25
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.resize(1000, 720)
    page.show()
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    source_text = "\n".join(f"Line {index:03d} with enough words for scrolling." for index in range(80))
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": source_text}],
        speech_blocks=[],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="not_started",
        selected_source_language="en",
        processed_chunk_count=0,
        total_chunk_count=1,
    )
    qtbot.wait(0)
    cursor = page._source_text_edit.textCursor()
    cursor.setPosition(10)
    cursor.setPosition(35, QTextCursor.MoveMode.KeepAnchor)
    page._source_text_edit.setTextCursor(cursor)
    page._source_text_edit.verticalScrollBar().setValue(12)
    text_position = page.source_text_position()

    page._source_text_edit.moveCursor(QTextCursor.MoveOperation.Start)
    page._source_text_edit.verticalScrollBar().setValue(0)
    page.restore_source_text_position(text_position)
    qtbot.wait(0)
    restored_cursor = page._source_text_edit.textCursor()

    assert restored_cursor.anchor() == 10
    assert restored_cursor.position() == 35
    assert page._source_text_edit.verticalScrollBar().value() == 12


def test_speech_blocks_page_metadata_controls_align_to_list_edges(qtbot) -> None:
    """
    @brief      Verify speaker and content-kind controls expand within the speech-block list edges.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-20
    @version    0.1.2
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.resize(1000, 720)
    page.show()
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Narration."}],
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "source_language": "en",
                "speaker_kind": "narrator",
                "speaker_id": "narrator",
                "speaker_display_name": "Narrator",
                "content_kind": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
                "text": "Quiet room tone.",
                "warning_flags": [],
            }
        ],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="completed",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
        speaker_catalog=[{"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}],
        content_kind_options=[
            (speech_blocks_service.CONTENT_KIND_NARRATION, "Narration"),
            (speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE, "Scene Ambience"),
        ],
    )
    qtbot.wait(0)

    assert page._speaker_label.geometry().left() == page._speech_block_list.geometry().left()
    assert page._speaker_label.width() <= 58
    assert page._speaker_combo.minimumWidth() <= 88
    assert page._speaker_combo.maximumWidth() > 104
    assert page._speaker_combo.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert page._speaker_combo.geometry().right() < page._content_kind_label.geometry().left()
    assert page._content_kind_label.width() <= 88
    assert page._content_kind_combo.minimumWidth() <= 126
    assert page._content_kind_combo.maximumWidth() > 150
    assert page._content_kind_combo.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert page._content_kind_combo.currentText() == "Scene Ambience"
    content_kind_right_offset = page._content_kind_combo.geometry().right() - page._speech_block_list.geometry().right()
    assert content_kind_right_offset <= 0
    assert page._source_group.geometry().right() < page._blocks_group.geometry().left()


def test_speech_blocks_page_same_narrator_edit_shows_only_disabled_narrator(qtbot) -> None:
    """
    @brief      Verify same-narrator projects do not expose character speaker choices while editing.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Narration."}],
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "source_language": "en",
                "speaker_kind": "narrator",
                "speaker_id": "narrator",
                "speaker_display_name": "Narrator",
                "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                "text": "Narration.",
                "warning_flags": [],
                "approved": False,
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
        content_kind_options=[(speech_blocks_service.CONTENT_KIND_NARRATION, "Narration")],
        voice_assignment_mode="same_narrator",
    )

    page.begin_editing_selected_block()

    assert page._speaker_combo.count() == 1
    assert page._speaker_combo.itemData(0) == "narrator"
    assert page._speaker_combo.isEnabled() is False
    assert page._content_kind_combo.isEnabled() is True


def test_speech_blocks_page_insert_delete_buttons_emit_selection(qtbot) -> None:
    """
    @brief      Verify Insert/Delete controls sit outside the chunk group and emit selected ids.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.3.1
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Narration."}],
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "speaker_id": "narrator",
                "speaker_display_name": "Narrator",
                "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                "text": "Narration.",
                "warning_flags": [],
            }
        ],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="in_progress",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
        speaker_catalog=[{"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}],
        content_kind_options=[
            (speech_blocks_service.CONTENT_KIND_NARRATION, "Narration"),
            (speech_blocks_service.CONTENT_KIND_INDICATION, "Indication"),
        ],
    )
    insert_payloads: list[tuple[str, str]] = []
    delete_payloads: list[str] = []
    page.insert_block_requested.connect(lambda *payload: insert_payloads.append(tuple(str(value) for value in payload)))
    page.delete_block_requested.connect(lambda speech_block_id: delete_payloads.append(str(speech_block_id)))

    assert page._insert_block_button.isEnabled() is True
    assert page._delete_block_button.isEnabled() is True

    page._insert_block_button.click()
    page._delete_block_button.click()

    assert page._insert_block_button.text() == "Insert"
    assert page._delete_block_button.text() == "Delete"
    assert page._insert_block_button.parentWidget() is page._chunk_actions_column
    assert page._delete_block_button.parentWidget() is page._chunk_actions_column
    assert page._insert_block_button.parentWidget() is not page._chunk_group
    assert page._delete_block_button.parentWidget() is not page._chunk_group
    assert insert_payloads == [("chunk-0001", "0001-000001")]
    assert delete_payloads == ["0001-000001"]
    assert page._content_kind_combo.findData(speech_blocks_service.CONTENT_KIND_INDICATION) >= 0


def test_speech_blocks_page_insert_enabled_for_empty_selected_chunk(qtbot) -> None:
    """
    @brief      Verify Insert stays active when a selected source chunk has no Speech Blocks yet.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Narration."}],
        speech_blocks=[],
        notes=["Generated 0 speech blocks from 0/1 chunks."],
        selected_profile_id="profile-1",
        stage_status="not_started",
        selected_source_language="en",
        processed_chunk_count=0,
        total_chunk_count=1,
        speaker_catalog=[{"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}],
        content_kind_options=[(speech_blocks_service.CONTENT_KIND_NARRATION, "Narration")],
    )
    insert_payloads: list[tuple[str, str]] = []
    page.insert_block_requested.connect(lambda *payload: insert_payloads.append(tuple(str(value) for value in payload)))

    assert page._insert_block_button.isEnabled() is True
    assert page._delete_block_button.isEnabled() is False

    page._insert_block_button.click()

    assert insert_payloads == [("chunk-0001", "")]


def test_speech_blocks_page_list_shows_operation_name_for_metadata_block(qtbot) -> None:
    """
    @brief      Verify metadata-only Speech Blocks display the operation label in the list.
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
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Wind."}],
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "speaker_kind": speech_blocks_service.SPEAKER_KIND_OPERATION,
                "speaker_id": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
                "speaker_display_name": "Scene Ambience",
                "content_kind": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
                "text": "Wind.",
                "warning_flags": [],
            }
        ],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="in_progress",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
        speaker_catalog=[{"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}],
        content_kind_options=[(speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE, "Scene Ambience")],
    )

    assert page._speech_block_list.item(0).text().count("Scene Ambience") == 1


def test_speech_blocks_page_edit_enables_fields_and_save_returns_to_indicators(qtbot) -> None:
    """
    @brief      Verify confirmed Edit enables inputs and Save disables them after emitting changes.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.1
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
            (speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE, "Scene Ambience"),
            (speech_blocks_service.CONTENT_KIND_PAUSE, "Pause"),
        ],
        selected_text_character_limit=120,
    )
    saved_payloads: list[tuple[str, str, str, str]] = []
    edit_requests: list[str] = []
    page.edit_started.connect(lambda block_id: edit_requests.append(str(block_id)))
    page.save_block_requested.connect(lambda *payload: saved_payloads.append(tuple(str(value) for value in payload)))

    page._edit_button.click()

    assert edit_requests == ["0001-000001"]
    assert page._speaker_combo.isEnabled() is False
    assert page._content_kind_combo.isEnabled() is False
    assert page._speech_block_text_edit.isReadOnly() is True
    assert page._save_button.isEnabled() is False

    page.begin_editing_selected_block()

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
    assert page._character_count_edit.text() == "18 / 120"
    page._save_button.click()

    assert saved_payloads == [
        ("0001-000001", "narrator", speech_blocks_service.CONTENT_KIND_NARRATION, "Updated narration.")
    ]
    assert page._speaker_combo.isEnabled() is False
    assert page._content_kind_combo.isEnabled() is False
    assert page._speech_block_text_edit.isReadOnly() is True
    assert page._save_button.isEnabled() is False


def test_speech_blocks_page_edits_scene_ambience_fields(qtbot) -> None:
    """
    @brief      Verify Scene Ambience blocks expose dedicated edit fields.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-21
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.show()
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Airport terminal."}],
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "chunk_id": "chunk-0001",
                "source_language": "en",
                "speaker_kind": "operation",
                "speaker_id": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
                "speaker_display_name": "Scene Ambience",
                "content_kind": speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
                "text": "distant aircraft takeoff",
                "sound_prompt": "distant aircraft takeoff",
                "negative_prompt": "speech",
                "duration_seconds": 2.0,
                "warning_flags": [],
            }
        ],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="in_progress",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
        speaker_catalog=[{"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}],
        content_kind_options=[(speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE, "Scene Ambience")],
        selected_text_character_limit=120,
    )
    qtbot.wait(0)
    saved_payloads: list[tuple[object, ...]] = []
    page.save_block_requested.connect(lambda *payload: saved_payloads.append(tuple(payload)))

    assert page._speech_block_text_edit.isVisible() is False
    assert page._ambience_detail_widget.isVisible() is True
    assert page._ambient_prompt_edit.toPlainText() == "distant aircraft takeoff"
    assert page._character_count_edit.text() == "24 / 120"

    page.begin_editing_selected_block()
    page._ambient_prompt_edit.setPlainText("indistinct airport crowd murmur")
    page._ambient_negative_prompt_edit.setPlainText("clear speech, singing")
    page._ambient_duration_spin.setValue(1.5)
    page._save_button.click()

    assert saved_payloads[0][:3] == (
        "0001-000001",
        speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
        speech_blocks_service.CONTENT_KIND_SCENE_AMBIENCE,
    )
    assert saved_payloads[0][3] == {
        "sound_prompt": "indistinct airport crowd murmur",
        "negative_prompt": "clear speech, singing",
        "duration_seconds": 1.5,
    }


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


def test_speech_blocks_page_approval_button_toggles_label_for_approved_block(qtbot) -> None:
    """
    @brief      Verify approved Speech Blocks expose the selected approval action as Unapprove.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-05
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
                "source_language": "en",
                "speaker_kind": "narrator",
                "speaker_id": "narrator",
                "speaker_display_name": "Narrator",
                "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                "text": "First block.",
                "warning_flags": [],
                "approved": True,
            },
        ],
        notes=["Ready."],
        selected_profile_id="profile-1",
        stage_status="completed",
        selected_source_language="en",
        processed_chunk_count=1,
        total_chunk_count=1,
        speaker_catalog=[{"speaker_id": "narrator", "display_name": "Narrator", "speaker_kind": "narrator"}],
        content_kind_options=[(speech_blocks_service.CONTENT_KIND_NARRATION, "Narration")],
    )
    toggled_block_ids: list[str] = []
    page.approve_block_requested.connect(toggled_block_ids.append)

    assert page._approve_block_button.isEnabled() is True
    assert page._approve_block_button.text() == "Unapprove"

    page._approve_block_button.click()

    assert toggled_block_ids == ["0001-000001"]


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
    @brief      Verify state refresh keeps selected Speech Block and selected-chunk text position.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.1
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.resize(900, 700)
    page.show()
    page._source_text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    source_text = (
        ("Opening source line with enough words for horizontal scrolling. " * 8)
        + "\n"
        + "\n".join(f"Line {line_number}" for line_number in range(80))
    )
    speech_blocks = [
        {
            "speech_block_id": "0001-000001",
            "sequence_index": 1,
            "chunk_id": "chunk-0001",
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
    source_cursor = page._source_text_edit.textCursor()
    source_cursor.setPosition(28)
    source_cursor.setPosition(116, QTextCursor.MoveMode.KeepAnchor)
    page._source_text_edit.setTextCursor(source_cursor)
    source_scroll_bar = page._source_text_edit.verticalScrollBar()
    source_scroll_bar.setValue(source_scroll_bar.maximum())
    saved_scroll_position = source_scroll_bar.value()
    source_horizontal_scroll_bar = page._source_text_edit.horizontalScrollBar()
    source_horizontal_scroll_bar.setValue(source_horizontal_scroll_bar.maximum())
    saved_horizontal_scroll_position = source_horizontal_scroll_bar.value()
    saved_cursor_position = page._source_text_edit.textCursor().position()
    saved_anchor_position = page._source_text_edit.textCursor().anchor()

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
    qtbot.wait(35)

    assert page.selected_block_id() == "0001-000002"
    assert page._speech_block_list.currentRow() == 1
    assert source_scroll_bar.value() == saved_scroll_position
    assert source_horizontal_scroll_bar.value() == saved_horizontal_scroll_position
    assert page._source_text_edit.textCursor().position() == saved_cursor_position
    assert page._source_text_edit.textCursor().anchor() == saved_anchor_position


def test_speech_blocks_page_resolves_delete_replacement_from_visible_block_order(qtbot) -> None:
    """
    @brief      Verify delete replacement selection uses next row or current row when deleting the last block.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    speech_blocks = [
        {
            "speech_block_id": "0001-000001",
            "sequence_index": 1,
            "chunk_id": "chunk-0001",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            "text": "First block.",
            "approved": False,
        },
        {
            "speech_block_id": "0001-000002",
            "sequence_index": 2,
            "chunk_id": "chunk-0001",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            "text": "Second block.",
            "approved": False,
        },
        {
            "speech_block_id": "0001-000003",
            "sequence_index": 3,
            "chunk_id": "chunk-0001",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
            "text": "Third block.",
            "approved": False,
        },
    ]
    page.set_speech_blocks_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Chunk text."}],
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

    assert page.replacement_block_id_after_delete("0001-000002") == "0001-000003"
    assert page.replacement_block_id_after_delete("0001-000003") == "0001-000002"


def test_speech_blocks_page_disables_generate_without_source_and_while_busy(qtbot) -> None:
    """
    @brief      Verify generation stays disabled without source chunks and while a run is busy.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.3.0
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

    assert page._generate_button.isEnabled() is True

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
    @version    0.2.0
    """
    page = SpeechBlocksPage()
    qtbot.addWidget(page)
    page.apply_language("ro")

    assert "Blocuri Vorbire" in page._title_label.text()
    assert page._profile_label.text() == "Profil AI"
    assert page._generate_button.text() == "Genereaza Tot"
    assert page._reset_generation_button.text() == "Reset"
    assert page._approve_all_button.text() == "Aproba Tot"
    assert page._approve_block_button.text() == "Aproba"
    assert page._chunk_group.title() == "Lista Segmentelor"


# END OF FILE
