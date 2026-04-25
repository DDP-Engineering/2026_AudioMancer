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
@details Verifies translation-page enablement, chunk rendering, and review
         controls for the AI Translation workflow.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.1.0
"""

# IMPORTS

from audiomancer.services import ai_translation_service
from audiomancer.ui.pages.ai_translation_page import AiTranslationPage


def test_ai_translation_page_locks_language_when_translation_exists(qtbot) -> None:
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
                "approved_at": None,
                "translated_at": "2026-04-07T12:00:00+00:00",
                "translation_profile_id": "profile-1",
                "target_language": "ro",
                "status": ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED,
            }
        ],
        notes=["Translated chunks: 1/1."],
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STAGE_COMPLETED,
        translated_count=1,
        approved_count=0,
        total_count=1,
    )

    assert page._language_combo.isEnabled() is False
    assert page._start_button.isEnabled() is False
    assert page._reset_button.isEnabled() is True


def test_ai_translation_page_renders_selected_chunk_and_review_actions(qtbot) -> None:
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
                "approved_at": None,
                "translated_at": "2026-04-07T12:00:00+00:00",
                "translation_profile_id": "profile-1",
                "target_language": "ro",
                "status": ai_translation_service.TRANSLATED_CHUNK_STATUS_TRANSLATED,
            }
        ],
        notes=["Translated chunks: 1/1."],
        target_language="ro",
        selected_profile_id="profile-1",
        stage_status=ai_translation_service.TRANSLATION_STAGE_IN_PROGRESS,
        translated_count=1,
        approved_count=0,
        total_count=1,
    )

    assert page._chunk_list.count() == 1
    assert page._chunk_list_group.maximumHeight() == 176
    assert page._source_text_edit.toPlainText() == "Original text"
    assert page._translated_text_edit.toPlainText() == "Translated text"
    assert page._approve_all_button.isEnabled() is True
    assert page._approve_selected_button.isEnabled() is True


def test_ai_translation_page_edit_marks_selected_chunk_unapproved(qtbot) -> None:
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
                "approved_at": "2026-04-07T12:01:00+00:00",
                "translated_at": "2026-04-07T12:00:00+00:00",
                "translation_profile_id": "profile-1",
                "target_language": "ro",
                "status": ai_translation_service.TRANSLATED_CHUNK_STATUS_APPROVED,
            }
        ],
        notes=["Translated chunks: 1/1."],
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


# END OF FILE
