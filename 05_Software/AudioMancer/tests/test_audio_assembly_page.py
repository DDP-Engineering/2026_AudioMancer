#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_assembly_page.py
@brief Audio Assembly page tests for AudioMancer.
@details Verifies output-mode controls, generated-output rendering, progress,
         and playback button state on the Audio Assembly page.
"""

# IMPORTS

from PySide6.QtCore import Qt

from audiomancer.services import audio_assembly_service
from audiomancer.ui.pages.audio_assembly_page import AudioAssemblyPage


def test_audio_assembly_page_time_limit_enables_duration_control(qtbot) -> None:
    """
    @brief      Verify the max-duration input is enabled only for time-limit mode.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioAssemblyPage()
    qtbot.addWidget(page)
    page.set_project_active(True)

    page._output_mode_combo.setCurrentIndex(
        page._output_mode_combo.findData(audio_assembly_service.OUTPUT_MODE_TIME_LIMIT)
    )
    assert page._max_duration_spin.isEnabled() is True
    page._output_mode_combo.setCurrentIndex(
        page._output_mode_combo.findData(audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK)
    )
    assert page._max_duration_spin.isEnabled() is False


def test_audio_assembly_page_uses_two_column_settings_and_scene_ambience_option(qtbot) -> None:
    """
    @brief      Verify settings render in two columns and emit the Scene Ambience inclusion setting.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioAssemblyPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_audio_assembly_state(
        settings={
            **audio_assembly_service.default_audio_assembly_settings(),
            "include_scene_ambience": False,
        },
        outputs=[],
        current_output_key=None,
        notes=["Ready."],
        status_lines=[],
        progress_current=0,
        progress_total=0,
        progress_percent=0,
        stage_status=audio_assembly_service.AUDIO_ASSEMBLY_STAGE_NOT_STARTED,
        can_generate=True,
        can_reset=False,
        can_play_selected=False,
    )

    assert page._include_scene_ambience_checkbox.isChecked() is False
    assert page.current_settings_payload()["include_scene_ambience"] is False
    assert page._settings_group.layout().itemAtPosition(0, 0).widget() is page._output_mode_label
    assert page._settings_group.layout().itemAtPosition(0, 2).widget() is page._inter_block_gap_label

    page._include_scene_ambience_checkbox.setChecked(True)

    assert page.current_settings_payload()["include_scene_ambience"] is True


def test_audio_assembly_page_renders_outputs_progress_and_playback_state(qtbot) -> None:
    """
    @brief      Verify generated outputs and playback controls render from page state.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioAssemblyPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_audio_assembly_state(
        settings=audio_assembly_service.default_audio_assembly_settings(),
        outputs=[
            {
                "output_key": "audiobook",
                "file_name": "audiobook.wav",
                "audio_relative_path": "audiobook/audiobook.wav",
                "block_count": 3,
                "chunk_ids": ["chunk-0001"],
                "duration_seconds": 75.0,
                "generated": True,
                "generated_at": "2026-04-25T00:00:00+00:00",
                "output_format": "wav",
            }
        ],
        current_output_key="audiobook",
        notes=["Ready."],
        status_lines=["Generated output files: 1/1"],
        progress_current=1,
        progress_total=1,
        progress_percent=100,
        stage_status=audio_assembly_service.AUDIO_ASSEMBLY_STAGE_COMPLETED,
        can_generate=True,
        can_reset=True,
        can_play_selected=True,
    )

    assert page._progress_bar.value() == 100
    assert page._output_list.count() == 1
    assert page._playback_button.isEnabled() is True
    assert page._playback_slider.maximum() == 75_000
    assert page._playback_duration_label.text() == "01:15"
    page.set_playback_active(True)
    assert page._playback_button.text() == "Stop Playing"


def test_audio_assembly_page_renders_scene_mix_previews(qtbot) -> None:
    """
    @brief      Verify Scene Ambience mix preview rows and buttons render from page state.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioAssemblyPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_audio_assembly_state(
        settings=audio_assembly_service.default_audio_assembly_settings(),
        outputs=[],
        current_output_key=None,
        notes=["Ready."],
        status_lines=[],
        progress_current=0,
        progress_total=0,
        progress_percent=0,
        stage_status=audio_assembly_service.AUDIO_ASSEMBLY_STAGE_NOT_STARTED,
        can_generate=True,
        can_reset=True,
        can_play_selected=False,
        scene_mix_groups=[
            {
                "group_key": "scene_mix:chunk-0001:opener:",
                "label": "chunk-0001 opener scene mix",
                "block_count": 2,
                "duration_seconds": 10.0,
                "can_generate_preview": True,
                "can_play_preview": True,
            }
        ],
        current_scene_mix_key="scene_mix:chunk-0001:opener:",
        can_generate_scene_mix=True,
        can_play_scene_mix=True,
    )
    generated: list[str] = []
    played: list[str] = []
    page.scene_mix_generate_requested.connect(generated.append)
    page.scene_mix_playback_toggle_requested.connect(played.append)

    assert page._scene_mix_list.count() == 1
    assert page._scene_mix_generate_button.isEnabled() is True
    assert page._scene_mix_playback_button.isEnabled() is True
    assert page._playback_slider.maximum() == 10_000
    page._scene_mix_generate_button.click()
    page._scene_mix_playback_button.click()

    assert generated == ["scene_mix:chunk-0001:opener:"]
    assert played == ["scene_mix:chunk-0001:opener:"]


def test_audio_assembly_page_updates_and_emits_playback_progress(qtbot) -> None:
    """
    @brief      Verify playback progress controls display and emit seek requests.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioAssemblyPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_audio_assembly_state(
        settings=audio_assembly_service.default_audio_assembly_settings(),
        outputs=[
            {
                "output_key": "audiobook",
                "file_name": "audiobook.wav",
                "audio_relative_path": "audiobook/audiobook.wav",
                "block_count": 3,
                "chunk_ids": ["chunk-0001"],
                "duration_seconds": 3661.0,
                "generated": True,
                "generated_at": "2026-04-25T00:00:00+00:00",
                "output_format": "wav",
            }
        ],
        current_output_key="audiobook",
        notes=["Ready."],
        status_lines=["Generated output files: 1/1"],
        progress_current=1,
        progress_total=1,
        progress_percent=100,
        stage_status=audio_assembly_service.AUDIO_ASSEMBLY_STAGE_COMPLETED,
        can_generate=True,
        can_reset=True,
        can_play_selected=True,
    )
    seeks: list[int] = []
    skips: list[int] = []
    page.playback_seek_requested.connect(seeks.append)
    page.playback_skip_requested.connect(skips.append)

    page.set_playback_progress(12_345, 3_661_000)
    page.set_playback_active(True)
    page._playback_slider.setValue(40_000)
    page._emit_playback_slider_release()
    page._rewind_button.click()
    page._forward_button.click()

    assert page._playback_position_label.text() == "00:12"
    assert page._playback_duration_label.text() == "01:01:01"
    assert page._playback_slider.value() == 40_000
    assert seeks == [40_000]
    assert skips == [-10_000, 10_000]


def test_audio_assembly_page_double_click_emits_restart_for_clicked_output(qtbot) -> None:
    """
    @brief      Verify double-click playback uses the clicked output row.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioAssemblyPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_audio_assembly_state(
        settings=audio_assembly_service.default_audio_assembly_settings(),
        outputs=[
            {
                "output_key": "part-0001",
                "file_name": "part-0001.wav",
                "audio_relative_path": "audiobook/part-0001.wav",
                "block_count": 1,
                "chunk_ids": ["chunk-0001"],
                "duration_seconds": 10.0,
                "generated": True,
                "generated_at": "2026-04-25T00:00:00+00:00",
                "output_format": "wav",
            },
            {
                "output_key": "part-0002",
                "file_name": "part-0002.wav",
                "audio_relative_path": "audiobook/part-0002.wav",
                "block_count": 1,
                "chunk_ids": ["chunk-0002"],
                "duration_seconds": 20.0,
                "generated": True,
                "generated_at": "2026-04-25T00:00:00+00:00",
                "output_format": "wav",
            },
        ],
        current_output_key="part-0001",
        notes=["Ready."],
        status_lines=["Generated output files: 2/2"],
        progress_current=2,
        progress_total=2,
        progress_percent=100,
        stage_status=audio_assembly_service.AUDIO_ASSEMBLY_STAGE_COMPLETED,
        can_generate=True,
        can_reset=True,
        can_play_selected=True,
    )
    restarts: list[str] = []
    page.playback_restart_requested.connect(restarts.append)

    page._emit_playback_restart(page._output_list.item(1))

    assert restarts == ["part-0002"]


def test_audio_assembly_page_localizes_mode_and_output_rows(qtbot) -> None:
    """
    @brief      Verify runtime language refresh covers mode labels and output rows.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioAssemblyPage()
    qtbot.addWidget(page)
    page.apply_language("ro")
    page.set_audio_assembly_state(
        settings=audio_assembly_service.default_audio_assembly_settings(),
        outputs=[
            {
                "output_key": "audiobook",
                "file_name": "audiobook.wav",
                "audio_relative_path": "audiobook/audiobook.wav",
                "block_count": 3,
                "chunk_ids": ["chunk-0001"],
                "duration_seconds": 75.0,
                "generated": True,
                "generated_at": "2026-04-25T00:00:00+00:00",
                "output_format": "wav",
            }
        ],
        current_output_key="audiobook",
        notes=["Gata."],
        status_lines=["Fisiere de iesire generate: 1/1"],
        progress_current=1,
        progress_total=1,
        progress_percent=100,
        stage_status=audio_assembly_service.AUDIO_ASSEMBLY_STAGE_COMPLETED,
        can_generate=True,
        can_reset=True,
        can_play_selected=True,
    )

    assert (
        page._output_mode_combo.itemText(
            page._output_mode_combo.findData(audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK)
        )
        == "Audiobook intreg"
    )
    assert page._include_scene_ambience_checkbox.text() == "Include Ambienta Scena"
    assert "blocuri audio" in page._output_list.item(0).text()


def test_audio_assembly_page_reports_a_numeric_setting_once_its_value_settles(qtbot) -> None:
    """
    @brief      Verify a typed numeric Output Setting is reported once, for its settled value.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioAssemblyPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page._output_mode_combo.setCurrentIndex(
        page._output_mode_combo.findData(audio_assembly_service.OUTPUT_MODE_TIME_LIMIT)
    )
    payloads: list[dict[str, object]] = []
    page.settings_changed.connect(payloads.append)

    for spin_box, typed_value, settings_key in (
        (page._inter_block_gap_spin, "320", "inter_block_silence_ms"),
        (page._inter_chunk_gap_spin, "750", "inter_chunk_silence_ms"),
        (page._max_duration_spin, "45", "max_duration_minutes"),
    ):
        assert spin_box.keyboardTracking() is False
        payloads.clear()
        spin_box.selectAll()
        qtbot.keyClicks(spin_box, typed_value)
        qtbot.keyClick(spin_box, Qt.Key.Key_Return)
        assert len(payloads) == 1
        assert payloads[0][settings_key] == int(typed_value)


def test_audio_assembly_page_generates_with_a_typed_but_unconfirmed_setting(qtbot) -> None:
    """
    @brief      Verify Generate Audio uses a typed numeric setting that was never confirmed.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = AudioAssemblyPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_audio_assembly_state(
        settings=audio_assembly_service.default_audio_assembly_settings(),
        outputs=[],
        current_output_key=None,
        notes=["Ready."],
        status_lines=[],
        progress_current=0,
        progress_total=0,
        progress_percent=0,
        stage_status=audio_assembly_service.AUDIO_ASSEMBLY_STAGE_NOT_STARTED,
        can_generate=True,
        can_reset=False,
        can_play_selected=False,
    )
    requested: list[dict[str, object]] = []
    page.generate_requested.connect(requested.append)

    page._inter_block_gap_spin.selectAll()
    qtbot.keyClicks(page._inter_block_gap_spin, "480")
    page._generate_button.click()

    assert requested[0]["inter_block_silence_ms"] == 480


# END OF FILE
