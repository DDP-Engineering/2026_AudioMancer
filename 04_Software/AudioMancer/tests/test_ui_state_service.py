#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ui_state_service.py
@brief Focused tests for the runtime UI-state service.
@details Verifies translated string lookup and application-wide text-scale
         changes used by the settings-backed runtime UI behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.2.0
"""

# IMPORTS

from PySide6.QtWidgets import QApplication

from audiomancer.services import ui_state_service


def test_translate_returns_expected_english_and_romanian_strings() -> None:
    """
    @brief      Verify the UI string catalog resolves EN and RO labels.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    assert ui_state_service.translate("toolbar.settings", "en") == "Settings"
    assert ui_state_service.translate("toolbar.settings", "ro") == "Setari"
    assert ui_state_service.translate("sidebar.text_chunking", "ro") == "Segmentare Text"


def test_v2_selective_impact_strings_cover_supported_languages() -> None:
    """
    @brief      Verify v2 selective-impact labels and confirmations exist in EN and RO.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    required_keys = (
        "dialog.confirm_chunk_insert_title",
        "dialog.confirm_chunk_delete_title",
        "project.confirm_chunk_edit",
        "project.confirm_chunk_insert",
        "project.confirm_chunk_delete",
        "dialog.character_add_confirm_title",
        "dialog.character_add_confirm_message",
        "dialog.character_edit_title",
        "dialog.character_edit_message",
        "dialog.character_delete_title",
        "dialog.character_delete_message",
        "project.confirm_speech_block_audio_reset",
        "project.confirm_speech_block_sequence_change",
        "audio_blocks.unapprove_selected",
        "audio_blocks.reset_selected",
        "project.confirm_audio_block_regeneration",
        "project.confirm_audio_block_reset",
        "project.confirm_audio_block_approval_change",
        "project.confirm_single_voice_target_invalidation",
        "project.confirm_narrator_voice_invalidation",
        "project.confirm_global_voice_settings_invalidation",
        "project.confirm_audio_assembly_settings_change",
        "status.audio_assembly_settings_saved_reset",
    )

    for language in ("en", "ro"):
        for key in required_keys:
            assert ui_state_service.translate(key, language) != key


def test_apply_text_scale_updates_application_font(qtbot) -> None:
    """
    @brief      Verify one UI text-scale preset updates the application font.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    application = QApplication.instance()
    ui_state_service.apply_text_scale(application, "normal")
    normal_size = application.font().pointSizeF()

    ui_state_service.apply_text_scale(application, "very_large")
    large_size = application.font().pointSizeF()

    assert large_size > normal_size


# END OF FILE
