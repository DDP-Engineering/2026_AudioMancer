#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_text_chunking_state_service.py
@brief Text Chunking state-service tests for AudioMancer.
@details Verifies chunking-page notes reflect running and resumable AI chunking
         states correctly.
@author Eng. Dan Dumitru Pasare
@date 2026-04-07
@version 0.1.0
"""

# IMPORTS

from audiomancer.services import text_chunking_state_service


def test_build_text_chunking_notes_shows_in_progress_note_for_running_ai_chunking() -> None:
    """
    @brief      Verify running AI chunking shows only the in-progress note instead of the ready note.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    notes = text_chunking_state_service.build_text_chunking_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        cleaned_text="Cleaned text",
        chunking_report_payload=None,
        chunking_operation_state={
            "status": "running",
            "mode": "ai_assisted",
            "progress_current": 1,
            "progress_total": 29,
            "metadata": {"semantic_strategy": "scene"},
        },
        has_ai_profiles=True,
        language="en",
    )

    assert any("in progress at 1/29" in note for note in notes)
    assert not any("is ready for the current cleaned text" in note for note in notes)


def test_build_text_chunking_notes_shows_resume_note_for_failed_ai_chunking() -> None:
    """
    @brief      Verify failed AI chunking shows the resume note instead of the in-progress note.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-07
    @version    0.1.0
    """
    notes = text_chunking_state_service.build_text_chunking_notes(
        manifest={"source_document": {"original_name": "story.txt"}},
        cleaned_text="Cleaned text",
        chunking_report_payload=None,
        chunking_operation_state={
            "status": "failed",
            "mode": "ai_assisted",
            "progress_current": 1,
            "progress_total": 29,
            "metadata": {"semantic_strategy": "scene"},
        },
        has_ai_profiles=True,
        language="en",
    )

    assert any("was not finalized" in note for note in notes)
    assert not any("in progress at 1/29" in note for note in notes)


# END OF FILE
