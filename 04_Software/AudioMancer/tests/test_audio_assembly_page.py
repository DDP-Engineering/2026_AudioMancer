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
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.1.0
"""

# IMPORTS

from audiomancer.services import audio_assembly_service
from audiomancer.ui.pages.audio_assembly_page import AudioAssemblyPage


def test_audio_assembly_page_time_limit_enables_duration_control(qtbot) -> None:
    """
    @brief      Verify the max-duration input is enabled only for time-limit mode.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
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


def test_audio_assembly_page_renders_outputs_progress_and_playback_state(qtbot) -> None:
    """
    @brief      Verify generated outputs and playback controls render from page state.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
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
    page.set_playback_active(True)
    assert page._playback_button.text() == "Stop Playing"


# END OF FILE
