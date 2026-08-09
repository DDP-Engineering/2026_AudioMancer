#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_blocks_page.py
@brief Focused Qt tests for the AudioMancer Audio Blocks page.
@details Verifies Audio Blocks rendering, translated labels, progress display,
         bounded approval navigation, and selected-row action enablement.
"""

# IMPORTS

import pytest

from audiomancer.services import ui_state_service
from audiomancer.ui.pages.audio_blocks_page import AudioBlocksPage


def test_audio_blocks_page_renders_source_list_markers_and_selected_details(qtbot) -> None:
    """
    @brief      Verify the page renders source text, speech-block markers, selected details, and progress.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_audio_blocks_state(
        full_source_text='Narration one.\n\n"Alice spoke."',
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "speaker_display_name": "Narrator",
                "text": "Narration one.",
                "generated": True,
                "approved": True,
                "audio_file_name": "000001_narrator.wav",
                "audio_duration_seconds": 1.25,
                "can_play": True,
                "is_current": False,
            },
            {
                "speech_block_id": "0001-000002",
                "sequence_index": 2,
                "speaker_display_name": "Alice",
                "text": "Hello there.",
                "generated": True,
                "approved": False,
                "audio_file_name": "000002_alice.wav",
                "audio_duration_seconds": 2.5,
                "can_play": True,
                "is_current": True,
            },
            {
                "speech_block_id": "0001-000003",
                "sequence_index": 3,
                "speaker_display_name": "Bob",
                "text": "Still waiting.",
                "generated": False,
                "approved": False,
                "audio_file_name": "",
                "audio_duration_seconds": None,
                "can_play": False,
                "is_current": False,
            },
        ],
        current_block_id="0001-000002",
        current_block_speaker="Alice",
        current_block_text="Hello there.",
        notes=["Ready."],
        status_lines=["Generated audio: 2/2"],
        progress_current=1,
        progress_total=2,
        progress_percent=50,
        stage_status="in_progress",
        can_start_or_continue=True,
        can_reset=True,
        can_approve_all=True,
        can_regenerate_selected=True,
        can_approve_selected=True,
        selected_text_character_limit=180,
    )

    assert page._source_text_edit.toPlainText() == 'Narration one.\n\n"Alice spoke."'
    assert page._source_text_edit.isReadOnly() is True
    assert page._speech_block_list.count() == 3
    assert "[approved] 1.2s | 000001_narrator.wav" in page._speech_block_list.item(0).text()
    assert "[pending] 2.5s | 000002_alice.wav" in page._speech_block_list.item(1).text()
    assert "[pending] --.-s | Bob" in page._speech_block_list.item(2).text()
    assert page.selected_block_id() == "0001-000002"
    assert page._speaker_label.text() == "Speaker: Alice"
    assert page._approval_status_label.text() == "Status: Pending"
    assert page._block_text_edit.toPlainText() == "Hello there."
    assert page._progress_bar.value() == 50
    expected_status_height = ui_state_service.operator_status_pane_height(page._status_edit)
    assert page._status_group.minimumHeight() == expected_status_height
    assert page._status_group.maximumHeight() == expected_status_height
    assert page._approve_button.isEnabled() is True
    assert page._approve_button.text() == "Approve"
    assert page._approve_all_button.text() == "Approve All"
    assert page._character_count_edit.text() == "12 / 180"
    assert page._selected_playback_button.isEnabled() is True
    assert page._audiobook_playback_button.isEnabled() is True


def test_audio_blocks_page_advances_to_next_pending_generated_scene_ambience_row(qtbot) -> None:
    """
    @brief      Verify approval navigation prefers the next generated pending row, including Scene Ambience.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_audio_blocks_state(
        full_source_text="Narration.\n\nScene change.\n\nMore narration.",
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "speaker_display_name": "Narrator",
                "text": "Narration.",
                "generated": True,
                "approved": False,
                "audio_file_name": "000001_narrator.wav",
                "audio_duration_seconds": 1.0,
                "can_play": True,
                "is_current": True,
            },
            {
                "speech_block_id": "0001-000002",
                "sequence_index": 2,
                "speaker_display_name": "Alice",
                "text": "Already checked.",
                "generated": True,
                "approved": True,
                "audio_file_name": "000002_alice.wav",
                "audio_duration_seconds": 1.0,
                "can_play": True,
                "is_current": False,
            },
            {
                "speech_block_id": "0001-000003",
                "sequence_index": 3,
                "speaker_display_name": "Scene Ambience",
                "text": "distant muffled sound of a single book being closed",
                "content_kind": "scene_ambience",
                "generated": True,
                "approved": False,
                "audio_file_name": "000003_scene_ambience.wav",
                "audio_duration_seconds": 1.5,
                "can_play": True,
                "is_current": False,
            },
        ],
        current_block_id="0001-000001",
        current_block_speaker="Narrator",
        current_block_text="Narration.",
        notes=["Ready."],
        status_lines=["Generated audio: 3/3"],
        progress_current=3,
        progress_total=3,
        progress_percent=100,
        stage_status="in_progress",
        can_start_or_continue=True,
        can_reset=True,
        can_approve_all=True,
        can_regenerate_selected=True,
        can_approve_selected=True,
    )

    page.advance_to_next_block()

    assert page.selected_block_id() == "0001-000003"


def test_audio_blocks_page_places_scene_ambience_selector_on_progress_row(qtbot) -> None:
    """
    @brief      Verify the Scene Ambience Audio selector anchors right and the progress indicator expands.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioBlocksPage()
    qtbot.addWidget(page)
    page.resize(1100, 720)
    page.show()
    page.set_project_active(True)
    page.set_audio_blocks_state(
        full_source_text="Narration.",
        speech_blocks=[],
        current_block_id=None,
        current_block_speaker="",
        current_block_text="",
        notes=["Ready."],
        status_lines=["Generated audio: 0/0"],
        progress_current=0,
        progress_total=0,
        progress_percent=0,
        stage_status="not_started",
        can_start_or_continue=False,
        can_reset=False,
        can_approve_all=False,
        can_regenerate_selected=False,
        can_approve_selected=False,
        scene_ambience_audio_enabled=True,
    )
    page.layout().activate()
    qtbot.wait(0)

    assert page._progress_bar.minimumWidth() >= 520
    assert page._scene_ambience_audio_combo.minimumWidth() >= 230
    assert (
        abs(page._scene_ambience_audio_combo.geometry().center().y() - page._progress_bar.geometry().center().y()) <= 1
    )
    assert page._scene_ambience_audio_combo.geometry().left() > page._progress_bar.geometry().right()
    assert page._scene_ambience_audio_combo.geometry().left() - page._progress_bar.geometry().right() <= 12
    assert page._scene_ambience_audio_combo.geometry().right() >= page.width() - 24
    assert page._scene_ambience_audio_combo.geometry().top() > page._start_button.geometry().bottom()
    assert page.scene_ambience_audio_enabled() is True


def test_audio_blocks_page_applies_translated_labels_and_tracks_selected_row_actions(qtbot) -> None:
    """
    @brief      Verify translated labels render and the selected-row buttons follow the current list selection.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioBlocksPage()
    qtbot.addWidget(page)
    page.apply_language("ro")
    page.set_project_active(True)
    page.set_audio_blocks_state(
        full_source_text="Text sursa.",
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "speaker_display_name": "Narator",
                "text": "Textul unu.",
                "generated": True,
                "approved": True,
                "audio_file_name": "000001_narator.wav",
                "audio_duration_seconds": 1.0,
                "can_play": True,
                "is_current": True,
            },
            {
                "speech_block_id": "0001-000002",
                "sequence_index": 2,
                "speaker_display_name": "Alice",
                "text": "Textul doi.",
                "generated": True,
                "approved": False,
                "audio_file_name": "000002_alice.wav",
                "audio_duration_seconds": 1.5,
                "can_play": True,
                "is_current": False,
            },
        ],
        current_block_id="0001-000001",
        current_block_speaker="Narator",
        current_block_text="Textul unu.",
        notes=["Pregatit."],
        status_lines=["Audio generat: 2/2"],
        progress_current=2,
        progress_total=2,
        progress_percent=100,
        stage_status="in_progress",
        can_start_or_continue=True,
        can_reset=True,
        can_approve_all=True,
        can_regenerate_selected=True,
        can_approve_selected=False,
        selected_text_character_limit=120,
    )

    assert "Blocuri Audio" in page._title_label.text()
    assert page._start_button.text() == "Porneste Generarea Audio"
    assert page._approve_all_button.text() == "Aproba Tot"
    assert page._audiobook_playback_button.text() == "Reda Audiobook"
    assert page._blocks_group.title() == "Blocuri Vorbire"
    assert page._approve_button.text() == "Dezaproba"
    assert page._approve_button.isEnabled() is True
    assert page._character_count_edit.text() == "11 / 120"

    page._speech_block_list.setCurrentRow(1)

    assert page.selected_block_id() == "0001-000002"
    assert page._approve_button.text() == "Aproba"
    assert page._approve_button.isEnabled() is True
    assert page._regenerate_button.isEnabled() is True
    assert page._approval_status_label.text() == "Stare: In asteptare"
    assert page._character_count_edit.text() == "11 / 120"

    page.set_busy(True)

    assert page._start_button.isEnabled() is False
    assert page._approve_button.isEnabled() is False
    assert page._speech_block_list.isEnabled() is False


def test_audio_blocks_page_tracks_play_and_regenerate_eligibility_per_selected_row(qtbot) -> None:
    """
    @brief      Verify selected Play and Re-Generate buttons follow row-level capability state.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None.
    """
    page = AudioBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    rows = [
        {
            "speech_block_id": "0001-000001",
            "sequence_index": 1,
            "speaker_display_name": "Pause",
            "content_kind": "pause",
            "text": "Pause for 900 ms.",
            "generated": True,
            "approved": True,
            "can_play": True,
            "can_regenerate": False,
            "is_current": True,
        },
        {
            "speech_block_id": "0001-000002",
            "sequence_index": 2,
            "speaker_display_name": "Indication",
            "content_kind": "indication",
            "text": "Chapter heading.",
            "generated": True,
            "approved": True,
            "can_play": False,
            "can_regenerate": False,
            "is_current": False,
        },
        {
            "speech_block_id": "0001-000003",
            "sequence_index": 3,
            "speaker_display_name": "Scene Ambience",
            "content_kind": "scene_ambience",
            "text": "Metadata ambience.",
            "generated": True,
            "approved": True,
            "can_play": False,
            "can_regenerate": True,
            "is_current": False,
        },
        {
            "speech_block_id": "0001-000004",
            "sequence_index": 4,
            "speaker_display_name": "Scene Ambience",
            "content_kind": "scene_ambience",
            "text": "Generated ambience.",
            "generated": True,
            "approved": True,
            "can_play": True,
            "can_regenerate": True,
            "is_current": False,
        },
        {
            "speech_block_id": "0001-000005",
            "sequence_index": 5,
            "speaker_display_name": "Narrator",
            "content_kind": "narration",
            "text": "Spoken narration.",
            "generated": True,
            "approved": True,
            "can_play": True,
            "can_regenerate": True,
            "is_current": False,
        },
    ]
    page.set_audio_blocks_state(
        full_source_text="Pause. Heading. Ambience. Narration.",
        speech_blocks=rows,
        current_block_id="0001-000001",
        current_block_speaker="Pause",
        current_block_text="Pause for 900 ms.",
        notes=["Ready."],
        status_lines=["Generated audio: 5/5"],
        progress_current=5,
        progress_total=5,
        progress_percent=100,
        stage_status="completed",
        can_start_or_continue=False,
        can_reset=True,
        can_approve_all=False,
        can_regenerate_selected=False,
        can_approve_selected=True,
    )

    expected_controls = [
        (True, False),
        (False, False),
        (False, True),
        (True, True),
        (True, True),
    ]
    for row_index, (can_play, can_regenerate) in enumerate(expected_controls):
        page._speech_block_list.setCurrentRow(row_index)
        assert page._selected_playback_button.isEnabled() is can_play
        assert page._regenerate_button.isEnabled() is can_regenerate


def test_audio_blocks_page_advances_block_selection_with_limit(qtbot) -> None:
    """
    @brief      Verify approval navigation advances through Audio Blocks rows without crossing the end.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_audio_blocks_state(
        full_source_text="Text source.",
        speech_blocks=[
            {
                "speech_block_id": "0001-000001",
                "sequence_index": 1,
                "speaker_display_name": "Narrator",
                "text": "First.",
                "generated": True,
                "approved": False,
                "audio_file_name": "000001_narrator.wav",
                "audio_duration_seconds": 1.0,
                "can_play": True,
                "is_current": True,
            },
            {
                "speech_block_id": "0001-000002",
                "sequence_index": 2,
                "speaker_display_name": "Alice",
                "text": "Second.",
                "generated": True,
                "approved": False,
                "audio_file_name": "000002_alice.wav",
                "audio_duration_seconds": 1.5,
                "can_play": True,
                "is_current": False,
            },
        ],
        current_block_id="0001-000001",
        current_block_speaker="Narrator",
        current_block_text="First.",
        notes=["Ready."],
        status_lines=["Generated audio: 2/2"],
        progress_current=2,
        progress_total=2,
        progress_percent=100,
        stage_status="in_progress",
        can_start_or_continue=True,
        can_reset=True,
        can_approve_all=True,
        can_regenerate_selected=True,
        can_approve_selected=True,
    )

    page.advance_to_next_block()

    assert page.selected_block_id() == "0001-000002"
    assert page._speech_block_list.currentRow() == 1

    page.advance_to_next_block()

    assert page.selected_block_id() == "0001-000002"
    assert page._speech_block_list.currentRow() == 1


def test_audio_blocks_page_single_item_update_preserves_sibling_items(qtbot) -> None:
    """
    @brief      Verify one Audio Blocks row can refresh without recreating sibling list items.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_audio_blocks_state(
        full_source_text="First.\nSecond.",
        speech_blocks=[
            _audio_block("0001-000001", "Narrator", "First.", generated=True, approved=False),
            _audio_block("0001-000002", "Alice", "Second.", generated=True, approved=False),
        ],
        current_block_id="0001-000001",
        current_block_speaker="Narrator",
        current_block_text="First.",
        notes=["Ready."],
        status_lines=["Generated audio: 2/2"],
        progress_current=2,
        progress_total=2,
        progress_percent=100,
        stage_status="in_progress",
        can_start_or_continue=True,
        can_reset=True,
        can_approve_all=True,
        can_regenerate_selected=True,
        can_approve_selected=True,
    )
    first_item = page._speech_block_list.item(0)
    second_item = page._speech_block_list.item(1)

    page.update_audio_block_item(_audio_block("0001-000002", "Alice", "Second.", generated=True, approved=True))

    assert page._speech_block_list.item(0) is first_item
    assert page._speech_block_list.item(1) is second_item
    assert "[approved]" in second_item.text()
    assert page.selected_block_id() == "0001-000001"
    assert page._block_text_edit.toPlainText() == "First."


@pytest.mark.parametrize(
    ("incoming_id", "incoming_text", "expected_ids", "expected_next_id"),
    [
        ("0001-000001", "Before.", ["0001-000001", "0001-000002", "0001-000004"], "0001-000002"),
        ("0001-000003", "Between.", ["0001-000002", "0001-000003", "0001-000004"], "0001-000004"),
        ("0001-000005", "After.", ["0001-000002", "0001-000004", "0001-000005"], "0001-000005"),
    ],
)
def test_audio_blocks_page_inserts_unseen_item_with_aligned_rows_and_selection(
    qtbot,
    incoming_id: str,
    incoming_text: str,
    expected_ids: list[str],
    expected_next_id: str,
) -> None:
    """
    @brief      Verify unseen incremental rows rebuild sorted model and widget state together.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  incoming_id Unseen Speech Block identifier to insert.
    @param[in]  incoming_text Text attached to the unseen row.
    @param[in]  expected_ids Expected sorted row identifiers.
    @param[in]  expected_next_id Expected selection after advancing from the inserted row.
    @return     None.
    @exception  None
    """
    page = AudioBlocksPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_audio_blocks_state(
        full_source_text="Second.\nFourth.",
        speech_blocks=[
            _audio_block("0001-000002", "Alice", "Second.", generated=True, approved=False),
            _audio_block("0001-000004", "Narrator", "Fourth.", generated=True, approved=False),
        ],
        current_block_id="0001-000004",
        current_block_speaker="Narrator",
        current_block_text="Fourth.",
        notes=["Ready."],
        status_lines=["Generated audio: 2/2"],
        progress_current=2,
        progress_total=2,
        progress_percent=100,
        stage_status="in_progress",
        can_start_or_continue=True,
        can_reset=True,
        can_approve_all=True,
        can_regenerate_selected=True,
        can_approve_selected=True,
    )

    page.update_audio_block_item(
        _audio_block(incoming_id, "Inserted", incoming_text, generated=True, approved=False)
    )

    assert [str(block["speech_block_id"]) for block in page._speech_blocks] == expected_ids
    assert page._speech_block_list.count() == len(expected_ids)
    expected_text_by_id = {
        "0001-000001": "Before.",
        "0001-000002": "Second.",
        "0001-000003": "Between.",
        "0001-000004": "Fourth.",
        "0001-000005": "After.",
    }
    for row, speech_block_id in enumerate(expected_ids):
        assert expected_text_by_id[speech_block_id] in page._speech_block_list.item(row).text()
    assert page.selected_block_id() == "0001-000004"
    assert page._speech_block_list.currentRow() == expected_ids.index("0001-000004")
    assert page._speaker_label.text() == "Speaker: Narrator"
    assert page._block_text_edit.toPlainText() == "Fourth."

    page.select_block_id(incoming_id)

    assert page.selected_block_id() == incoming_id
    assert page._block_text_edit.toPlainText() == incoming_text

    page.advance_to_next_block()

    assert page.selected_block_id() == expected_next_id
    assert page._block_text_edit.toPlainText() == expected_text_by_id[expected_next_id]


def _audio_block(
    speech_block_id: str,
    speaker_display_name: str,
    text: str,
    *,
    generated: bool,
    approved: bool,
) -> dict[str, object]:
    """
    @brief      Build one compact Audio Blocks page test row.
    @param[in]  speech_block_id Speech Block identifier.
    @param[in]  speaker_display_name Display speaker name.
    @param[in]  text Speech Block text.
    @param[in]  generated True when generated audio is available.
    @param[in]  approved True when the audio row is approved.
    @return     Audio Blocks page row payload.
    @exception  None
    """
    sequence_index = int(speech_block_id.rsplit("-", maxsplit=1)[-1])
    return {
        "speech_block_id": speech_block_id,
        "sequence_index": sequence_index,
        "speaker_display_name": speaker_display_name,
        "text": text,
        "generated": generated,
        "approved": approved,
        "audio_file_name": f"{sequence_index:06d}.wav" if generated else "",
        "audio_duration_seconds": 1.0 if generated else 0.0,
        "can_play": generated,
        "is_current": sequence_index == 1,
    }


# END OF FILE
