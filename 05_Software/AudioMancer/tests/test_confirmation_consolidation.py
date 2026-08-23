#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_confirmation_consolidation.py
@brief Focused preservation tests for consolidated UI confirmations.
@details Verifies every behavior-equivalent confirmation wrapper retains its
         translation keys, parent, button defaults, return value, and existing
         controller-local QMessageBox patch seam.
"""

# IMPORTS

from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox
import pytest

from audiomancer.ui.controllers import (
    audio_assembly_ui_controller,
    audio_blocks_ui_controller,
    characters_ui_controller,
    home_ui_controller,
    misc_ui_controller,
    narator_voice_ui_controller,
    speech_blocks_ui_controller,
    text_chunking_ui_controller,
)

# CONSTANTS

_CONFIRMATION_CASES = (
    (
        audio_assembly_ui_controller,
        "_confirm_audio_assembly",
        "dialog.confirm_audio_assembly_title",
        "project.confirm_audio_assembly",
    ),
    (
        audio_assembly_ui_controller,
        "_confirm_audio_assembly_reset",
        "dialog.confirm_audio_assembly_reset_title",
        "project.confirm_audio_assembly_reset",
    ),
    (
        audio_assembly_ui_controller,
        "_confirm_audio_assembly_settings_change",
        "dialog.confirm_audio_assembly_settings_change_title",
        "project.confirm_audio_assembly_settings_change",
    ),
    (
        audio_blocks_ui_controller,
        "_confirm_generation",
        "dialog.confirm_audio_blocks_title",
        "project.confirm_audio_blocks",
    ),
    (
        audio_blocks_ui_controller,
        "_confirm_scene_ambience_audio_blocks",
        "dialog.confirm_scene_ambience_audio_blocks_title",
        "project.confirm_scene_ambience_audio_blocks",
    ),
    (
        audio_blocks_ui_controller,
        "_confirm_audio_blocks_reset",
        "dialog.confirm_audio_blocks_reset_title",
        "project.confirm_audio_blocks_reset",
    ),
    (
        characters_ui_controller,
        "_confirm_add_character",
        "dialog.character_add_confirm_title",
        "dialog.character_add_confirm_message",
    ),
    (
        characters_ui_controller,
        "_confirm_edit_character",
        "dialog.character_edit_title",
        "dialog.character_edit_message",
    ),
    (
        characters_ui_controller,
        "_confirm_delete_character",
        "dialog.character_delete_title",
        "dialog.character_delete_message",
    ),
    (
        home_ui_controller,
        "_confirm_cleanup_draft_discard",
        "dialog.confirm_cleanup_draft_discard_title",
        "project.confirm_cleanup_draft_discard",
    ),
    (
        narator_voice_ui_controller,
        "_confirm_generate_profiles",
        "dialog.narator_voice_generate_profiles_title",
        "dialog.narator_voice_generate_profiles_message",
    ),
    (
        speech_blocks_ui_controller,
        "_confirm_generation",
        "dialog.confirm_speech_blocks_title",
        "project.confirm_speech_blocks",
    ),
    (
        speech_blocks_ui_controller,
        "_confirm_scene_ambience_speech_blocks",
        "dialog.confirm_scene_ambience_speech_blocks_title",
        "project.confirm_scene_ambience_speech_blocks",
    ),
    (
        speech_blocks_ui_controller,
        "_confirm_speech_blocks_reset",
        "dialog.confirm_speech_blocks_rerun_title",
        "project.confirm_speech_blocks_rerun",
    ),
    (
        speech_blocks_ui_controller,
        "_confirm_speech_block_audio_reset_if_needed",
        "dialog.confirm_speech_block_audio_reset_title",
        "project.confirm_speech_block_audio_reset",
    ),
    (
        speech_blocks_ui_controller,
        "_confirm_speech_block_sequence_change",
        "dialog.confirm_speech_block_sequence_change_title",
        "project.confirm_speech_block_sequence_change",
    ),
    (
        speech_blocks_ui_controller,
        "_confirm_speech_blocks_resplit",
        "dialog.confirm_speech_blocks_resplit_title",
        "project.confirm_speech_blocks_resplit",
    ),
    (
        speech_blocks_ui_controller,
        "_confirm_delete_speech_block",
        "dialog.confirm_delete_speech_block_title",
        "project.confirm_delete_speech_block",
    ),
    (
        text_chunking_ui_controller,
        "confirm_chunking_rerun",
        "dialog.confirm_chunking_rerun_title",
        "project.confirm_chunking_rerun",
    ),
    (
        text_chunking_ui_controller,
        "confirm_ai_chunking_rerun",
        "dialog.confirm_ai_chunking_rerun_title",
        "project.confirm_ai_chunking_rerun",
    ),
    (
        text_chunking_ui_controller,
        "confirm_chunk_insert",
        "dialog.confirm_chunk_insert_title",
        "project.confirm_chunk_insert",
    ),
    (
        text_chunking_ui_controller,
        "confirm_chunk_delete",
        "dialog.confirm_chunk_delete_title",
        "project.confirm_chunk_delete",
    ),
)


@pytest.mark.parametrize(("controller", "function_name", "title_key", "message_key"), _CONFIRMATION_CASES)
def test_confirmation_wrapper_preserves_exact_dialog_contract(
    monkeypatch,
    controller,
    function_name: str,
    title_key: str,
    message_key: str,
) -> None:
    """
    @brief      Verify one consolidated wrapper retains exact dialog arguments and patch seam.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  controller Controller module owning the wrapper.
    @param[in]  function_name Confirmation wrapper name.
    @param[in]  title_key Expected title translation key.
    @param[in]  message_key Expected message translation key.
    @return     None.
    @exception  None
    """
    window = SimpleNamespace()
    questions: list[tuple[object, ...]] = []
    translations: list[tuple[str, str]] = []
    assert controller.QMessageBox is misc_ui_controller.QMessageBox
    assert controller.ui_state_service is misc_ui_controller.ui_state_service
    monkeypatch.setattr(
        controller.ui_state_service,
        "translate",
        lambda key, language: translations.append((key, language)) or key,
    )
    monkeypatch.setattr(
        controller.QMessageBox,
        "question",
        lambda *args: questions.append(args) or QMessageBox.StandardButton.No,
    )

    confirmation = getattr(controller, function_name)
    extra_arguments = ()
    if function_name == "_confirm_cleanup_draft_discard":
        window._text_cleanup_page = SimpleNamespace(has_modified_cleaned_text_draft=lambda: True)
    elif function_name == "_confirm_speech_block_audio_reset_if_needed":
        window._current_project_root = object()
        extra_arguments = ("speech-block-1",)
        monkeypatch.setattr(
            speech_blocks_ui_controller.audio_blocks_service,
            "has_persisted_audio_for_speech_block",
            lambda _root, _speech_block_id: True,
        )
    outcome = confirmation(window, *extra_arguments, "ro")

    assert outcome is False
    assert translations == [(title_key, "ro"), (message_key, "ro")]
    assert questions == [
        (
            window,
            title_key,
            message_key,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
    ]


def test_audio_blocks_conditional_confirmation_preserves_short_circuit_and_dialog(monkeypatch) -> None:
    """
    @brief      Verify persisted-audio confirmation still short-circuits and otherwise uses exact keys.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    window = SimpleNamespace(_current_project_root=None)
    questions: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        audio_blocks_ui_controller.QMessageBox,
        "question",
        lambda *args: questions.append(args) or QMessageBox.StandardButton.Yes,
    )

    assert audio_blocks_ui_controller._confirm_persisted_audio_blocks_invalidation(
        window,
        "en",
        "title.key",
        "message.key",
    )
    assert questions == []

    window._current_project_root = object()
    monkeypatch.setattr(
        audio_blocks_ui_controller.audio_blocks_service, "has_persisted_audio_blocks", lambda _root: True
    )
    monkeypatch.setattr(audio_blocks_ui_controller.ui_state_service, "translate", lambda key, _language: key)

    assert audio_blocks_ui_controller._confirm_persisted_audio_blocks_invalidation(
        window,
        "en",
        "title.key",
        "message.key",
    )
    assert questions == [
        (
            window,
            "title.key",
            "message.key",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
    ]


# END OF FILE
