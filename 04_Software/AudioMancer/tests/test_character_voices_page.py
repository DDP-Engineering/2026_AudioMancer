#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_character_voices_page.py
@brief Character Voices page tests for AudioMancer.
@details Verifies preview-only Narator Voice behavior, explicit edit mode, and
         bottom status rendering for the Character Voices page.
"""

# IMPORTS

from PySide6.QtCore import Qt

from audiomancer.services import ui_state_service
from audiomancer.ui.pages.character_voices_page import CharacterVoicesPage


def test_character_voices_page_narrator_target_is_preview_only(qtbot) -> None:
    """
    @brief      Verify the Narator Voice row is preview-only when a sample exists.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    page.apply_language("en")
    page.set_project_active(True)
    page.set_character_voices_state(
        targets=[
            {
                "target_id": "narrator",
                "target_kind": "narrator",
                "display_name": "Narator Voice",
                "sample_status_label": "Sample present",
                "has_sample": True,
            }
        ],
        notes=["Ready."],
        current_target_id="narrator",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="English",
        translated_language="Not translated",
        assignment_mode_label="Narrator + character voices",
        target_name="Narator Voice",
        target_kind_label="Narator Voice",
        prompt_text="",
        preview_text="Narator Voice preview text.",
        is_editable=False,
        can_import_sample=False,
        can_edit_prompt=False,
        can_generate_sample=False,
        preview_available=True,
        status_lines=["Total targets: 1"],
        missing_narrator_sample=False,
    )

    assert page._import_sample_button.isEnabled() is False
    assert page._edit_prompt_button.isEnabled() is False
    assert page._generate_sample_button.isEnabled() is False
    assert page._import_sample_button.text() == "Import Sample"
    assert page._import_sample_button.isEnabled() is False
    assert page._preview_toggle_button.isEnabled() is True


def test_character_voices_page_edit_mode_disables_list_and_enables_save_after_changes(qtbot) -> None:
    """
    @brief      Verify edit mode disables the target list and enables Save after prompt changes.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_character_voices_state(
        targets=[
            {
                "target_id": "character_alice",
                "target_kind": "character",
                "display_name": "Alice",
                "sample_status_label": "Sample missing",
                "has_sample": False,
            }
        ],
        notes=["Ready."],
        current_target_id="character_alice",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="English",
        translated_language="Not translated",
        assignment_mode_label="Narrator + character voices",
        target_name="Alice",
        target_kind_label="Character",
        prompt_text="Original prompt.",
        preview_text="Line one.\nLine two.",
        is_editable=True,
        can_import_sample=True,
        can_edit_prompt=True,
        can_generate_sample=True,
        preview_available=False,
        status_lines=["Total targets: 1"],
        missing_narrator_sample=False,
    )

    page.begin_edit_mode()
    page._prompt_edit.setPlainText("Changed prompt.")

    assert page.is_edit_mode() is True
    assert page._target_list.isEnabled() is False
    assert page._prompt_edit.isReadOnly() is False
    assert page._preview_text_edit.isReadOnly() is False
    assert page._save_prompt_button.isEnabled() is True


def test_character_voices_page_unchanged_valid_edit_can_save_current_payload(qtbot) -> None:
    """
    @brief      Verify unchanged valid prompt edit mode can exit through the established Save signal.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_character_voices_state(
        targets=[
            {
                "target_id": "character_alice",
                "target_kind": "character",
                "display_name": "Alice",
                "sample_status_label": "Sample missing",
                "has_sample": False,
            }
        ],
        notes=["Ready."],
        current_target_id="character_alice",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="English",
        translated_language="Not translated",
        assignment_mode_label="Narrator + character voices",
        target_name="Alice",
        target_kind_label="Character",
        prompt_text="Original prompt.",
        preview_text="Line one.\nLine two.",
        is_editable=True,
        can_import_sample=True,
        can_edit_prompt=True,
        can_generate_sample=True,
        preview_available=False,
        status_lines=["Total targets: 1"],
        missing_narrator_sample=False,
    )
    emitted_payloads: list[dict[str, object]] = []
    page.save_prompt_requested.connect(emitted_payloads.append)

    page.begin_edit_mode()

    assert page.is_edit_mode() is True
    assert page.is_dirty() is False
    assert page._save_prompt_button.isEnabled() is True

    page._save_prompt_button.click()

    assert len(emitted_payloads) == 1
    assert emitted_payloads[0]["target_id"] == "character_alice"
    assert emitted_payloads[0]["prompt_text"] == "Original prompt."
    assert emitted_payloads[0]["preview_text"] == "Line one.\nLine two."


def test_character_voices_page_import_button_emits_for_character_targets(qtbot) -> None:
    """
    @brief      Verify Import Sample is available for editable character targets.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    page.apply_language("en")
    page.set_project_active(True)
    page.set_character_voices_state(
        targets=[
            {
                "target_id": "character_alice",
                "target_kind": "character",
                "display_name": "Alice",
                "sample_status_label": "Sample missing",
                "has_sample": False,
                "can_import_sample": True,
            }
        ],
        notes=["Ready."],
        current_target_id="character_alice",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="English",
        translated_language="Not translated",
        assignment_mode_label="Narrator + character voices",
        target_name="Alice",
        target_kind_label="Character",
        prompt_text="Original prompt.",
        preview_text="Line one.",
        is_editable=True,
        can_import_sample=True,
        can_edit_prompt=True,
        can_generate_sample=True,
        preview_available=False,
        status_lines=["Total targets: 1"],
        missing_narrator_sample=False,
    )
    emitted: list[str] = []
    page.import_sample_requested.connect(lambda target_id: emitted.append(target_id))

    assert page._import_sample_button.isEnabled() is True

    page._import_sample_button.click()

    assert emitted == ["character_alice"]


def test_character_voices_page_batch_button_enables_for_current_character_targets(qtbot) -> None:
    """
    @brief      Verify the batch generation button enables when current character targets can generate.
    @details    Covers SPEC-CV-AI-SELECTOR-REMOVAL and REQ-UX-009.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    page.apply_language("en")
    page.set_project_active(True)
    page.set_character_voices_state(
        targets=[
            {
                "target_id": "character_alice",
                "target_kind": "character",
                "display_name": "Alice",
                "sample_status_label": "Sample missing",
                "has_sample": False,
                "can_generate_sample": True,
            },
            {
                "target_id": "character_bob",
                "target_kind": "character",
                "display_name": "Bob",
                "sample_status_label": "Sample present",
                "has_sample": True,
                "can_generate_sample": False,
            },
        ],
        notes=["Ready."],
        current_target_id="character_alice",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="English",
        translated_language="Not translated",
        assignment_mode_label="Narrator + character voices",
        target_name="Alice",
        target_kind_label="Character",
        prompt_text="Original prompt.",
        preview_text="Line one.",
        is_editable=True,
        can_import_sample=True,
        can_edit_prompt=True,
        can_generate_sample=True,
        preview_available=False,
        status_lines=["Total targets: 2"],
        missing_narrator_sample=False,
    )
    emitted: list[bool] = []
    page.generate_missing_samples_requested.connect(lambda: emitted.append(True))

    assert page._generate_missing_samples_button.text() == "Generate Character Samples"
    assert page._generate_missing_samples_button.isEnabled() is True

    page._generate_missing_samples_button.click()

    assert emitted == [True]


def test_character_voices_page_batch_button_disables_when_character_targets_cannot_generate(qtbot) -> None:
    """
    @brief      Verify same-narrator or unavailable targets do not enable batch voice generation.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    page.apply_language("en")
    page.set_project_active(True)
    page.set_character_voices_state(
        targets=[
            {
                "target_id": "character_alice",
                "target_kind": "character",
                "display_name": "Alice",
                "sample_status_label": "Sample present",
                "has_sample": True,
                "can_generate_sample": False,
            }
        ],
        notes=["Same narrator voice mode."],
        current_target_id="character_alice",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="English",
        translated_language="Not translated",
        assignment_mode_label="Same narrator voice",
        target_name="Alice",
        target_kind_label="Character",
        prompt_text="Original prompt.",
        preview_text="Line one.",
        is_editable=False,
        can_import_sample=False,
        can_edit_prompt=False,
        can_generate_sample=False,
        preview_available=True,
        status_lines=["Total targets: 1"],
        missing_narrator_sample=False,
    )
    emitted: list[bool] = []
    page.generate_missing_samples_requested.connect(lambda: emitted.append(True))

    assert page._generate_missing_samples_button.isEnabled() is False

    page._generate_missing_samples_button.click()

    assert emitted == []


def test_character_voices_page_editor_payload_includes_preview_text(qtbot) -> None:
    """
    @brief      Verify the Character Voices editor payload includes the editable preview text.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_character_voices_state(
        targets=[
            {
                "target_id": "character_alice",
                "target_kind": "character",
                "display_name": "Alice",
                "sample_status_label": "Sample missing",
                "has_sample": False,
            }
        ],
        notes=["Ready."],
        current_target_id="character_alice",
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="English",
        translated_language="Not translated",
        assignment_mode_label="Narrator + character voices",
        target_name="Alice",
        target_kind_label="Character",
        prompt_text="Original prompt.",
        preview_text="Line one.\nLine two.",
        is_editable=True,
        can_import_sample=True,
        can_edit_prompt=True,
        can_generate_sample=True,
        preview_available=False,
        status_lines=["Total targets: 1"],
        missing_narrator_sample=False,
    )

    assert page.current_editor_payload()["preview_text"] == "Line one.\nLine two."


def test_character_voices_page_header_indicators_render_languages_and_assignment_mode(qtbot) -> None:
    """
    @brief      Verify the boxed header indicators render original language, translated language, and assignment mode.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    page.apply_language("en")
    page.set_project_active(True)
    page.set_character_voices_state(
        targets=[],
        notes=["Ready."],
        current_target_id=None,
        selected_voice_language="en",
        language_entries=[("English", "en")],
        original_language="Italian",
        translated_language="Romanian",
        assignment_mode_label="Narrator + character voices",
        target_name="",
        target_kind_label="",
        prompt_text="",
        preview_text="",
        is_editable=False,
        can_import_sample=False,
        can_edit_prompt=False,
        can_generate_sample=False,
        preview_available=False,
        status_lines=["Total targets: 0"],
        missing_narrator_sample=False,
    )

    assert page._original_language_group.title() == "Original language"
    assert page._translated_language_group.title() == "Translated language"
    assert page._assignment_mode_group.title() == "Voice assignment"
    assert page._voice_language_group.title() == "Voice language"
    assert page._original_language_value_label.text() == "Italian"
    assert page._translated_language_value_label.text() == "Romanian"
    assert page._assignment_mode_value_label.text() == "Narrator + character voices"
    assert page._voice_language_value_label.text() == "English"


def test_character_voices_page_matches_translation_notes_and_narrator_editor_sizing(qtbot) -> None:
    """
    @brief      Verify Character Voices uses the shared compact editor and status layout sizing.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = CharacterVoicesPage()
    qtbot.addWidget(page)
    editor_layout = page._prompt_group.parentWidget().layout()

    expected_status_height = ui_state_service.operator_status_pane_height(page._status_edit)
    assert page._status_group.minimumHeight() == expected_status_height
    assert page._status_group.maximumHeight() == expected_status_height
    assert editor_layout.stretch(editor_layout.indexOf(page._prompt_group)) == 1
    assert editor_layout.stretch(editor_layout.indexOf(page._preview_group)) == 1
    assert page._prompt_edit.minimumHeight() == 112
    assert page._preview_text_edit.minimumHeight() == 92
    assert page._prompt_edit.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    assert page._preview_text_edit.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn


# END OF FILE
