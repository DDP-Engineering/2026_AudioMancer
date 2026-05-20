#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ai_translation_page.py
@brief Focused Qt tests for the AudioMancer AI translation page.
@details Verifies translation-page enablement, chunk rendering, review
         controls, and bounded approval navigation for the AI Translation
         workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.4.3
"""

# IMPORTS

from audiomancer.services import ai_translation_service
from audiomancer.ui.pages.ai_translation_page import AiTranslationPage

# PUBLIC API


def test_ai_translation_page_displays_locked_language_indicators(qtbot) -> None:
    """
    @brief      Verify locked original and target language indicators are shown without a selector.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    page = AiTranslationPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_translation_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Original"}],
        translated_chunks=[
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "source_text": "Original",
                "translated_text": "Translated",
                "approved": False,
                "translation_profile_id": "profile-1",
                "target_language": "ro",
                "status": ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED,
            }
        ],
        notes=["Translated chunks: 1/1."],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STAGE_TRANSLATED,
        translated_count=1,
        approved_count=0,
        total_count=1,
    )

    assert hasattr(page, "_language_combo") is False
    assert page._original_language_value_label.text() == "English"
    assert page._target_language_value_label.text() == "Romanian"
    assert page._start_button.isEnabled() is False
    assert page._reset_button.isEnabled() is True


def test_ai_translation_page_renders_selected_chunk_and_review_actions(qtbot) -> None:
    """
    @brief      Verify selected translation chunks render with enabled review actions.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    page = AiTranslationPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_translation_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Original text"}],
        translated_chunks=[
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "source_text": "Original text",
                "translated_text": "Translated text",
                "approved": False,
                "translation_profile_id": "profile-1",
                "target_language": "ro",
                "status": ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED,
            }
        ],
        notes=["Translated chunks: 1/1."],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STAGE_IN_PROGRESS,
        translated_count=1,
        approved_count=0,
        total_count=1,
    )

    assert page._chunk_list.count() == 1
    assert page._chunk_list_group.maximumHeight() == 176
    assert page._chunk_list_group.layout().indexOf(page._translation_actions_widget) >= 0
    assert page._start_button.parentWidget() == page._translation_actions_widget
    assert page._source_text_edit.toPlainText() == "Original text"
    assert page._translated_text_edit.toPlainText() == "Translated text"
    assert page._approve_all_button.isEnabled() is True
    assert page._approve_selected_button.isEnabled() is True


def test_ai_translation_page_edit_marks_selected_chunk_unapproved(qtbot) -> None:
    """
    @brief      Verify editing selected translated text emits a review-state update.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    page = AiTranslationPage()
    qtbot.addWidget(page)
    emitted = []
    page.translated_text_changed.connect(lambda chunk_id, translated_text: emitted.append((chunk_id, translated_text)))
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_translation_state(
        source_chunks=[{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Original text"}],
        translated_chunks=[
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "source_text": "Original text",
                "translated_text": "Translated text",
                "approved": True,
                "translation_profile_id": "profile-1",
                "target_language": "ro",
                "status": ai_translation_service.TRANSLATED_CHUNK_STATUS_APPROVED,
            }
        ],
        notes=["Translated chunks: 1/1."],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STAGE_IN_PROGRESS,
        translated_count=1,
        approved_count=1,
        total_count=1,
    )

    page._translated_text_edit.setPlainText("Edited translation")

    assert emitted == [("chunk-0001", "Edited translation")]
    assert page._approve_selected_button.isEnabled() is True


def test_ai_translation_page_advances_to_next_chunk_with_limit(qtbot) -> None:
    """
    @brief      Verify approval navigation advances to the next chunk without crossing the end.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    page = AiTranslationPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_ai_profiles([("Profile One", "profile-1")], "profile-1")
    page.set_translation_state(
        source_chunks=[
            {"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Original one"},
            {"chunk_id": "chunk-0002", "sequence_index": 2, "text": "Original two"},
        ],
        translated_chunks=[
            {
                "chunk_id": "chunk-0001",
                "sequence_index": 1,
                "source_text": "Original one",
                "translated_text": "Translated one",
                "approved": False,
                "translation_profile_id": "profile-1",
                "target_language": "ro",
                "status": ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED,
            },
            {
                "chunk_id": "chunk-0002",
                "sequence_index": 2,
                "source_text": "Original two",
                "translated_text": "Translated two",
                "approved": False,
                "translation_profile_id": "profile-1",
                "target_language": "ro",
                "status": ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED,
            },
        ],
        notes=["Translated chunks: 2/2."],
        original_language="English",
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STAGE_IN_PROGRESS,
        translated_count=2,
        approved_count=0,
        total_count=2,
    )

    page.advance_to_next_chunk()

    assert page.selected_chunk_id() == "chunk-0002"
    assert page._chunk_list.currentRow() == 1

    page.advance_to_next_chunk()

    assert page.selected_chunk_id() == "chunk-0002"
    assert page._chunk_list.currentRow() == 1


# END OF FILE
