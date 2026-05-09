#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_home_presenter_service.py
@brief Home presenter-service tests for AudioMancer.
@details Verifies that the Home-page presenter service derives workflow status
         from manifest data without Qt dependencies.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.5.0
"""

# IMPORTS

from audiomancer.services import home_presenter_service

# PUBLIC API


def test_build_stage_statuses_marks_cleanup_as_in_progress() -> None:
    """
    @brief      Verify cleanup-running projects show text cleanup as in progress.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    manifest = {
        "current_stage": "source_selected",
        "source_document": {"original_name": "story.txt"},
        "operations": {
            "cleanup": {"status": "running"},
            "extraction": {"status": "completed"},
        },
    }

    statuses = home_presenter_service.build_stage_statuses(manifest, "en")

    assert statuses[0]["label"] == "Text Cleanup"
    assert statuses[0]["status"] == "in_progress"


def test_build_stage_statuses_keeps_chunking_not_started_after_cleanup_completion() -> None:
    """
    @brief      Verify cleanup completion marks Text Cleanup finished but leaves Text Chunking not started.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.2.0
    """
    manifest = {
        "current_stage": "text_chunking_ready",
        "source_document": {"original_name": "story.txt"},
        "operations": {
            "cleanup": {"status": "completed"},
            "extraction": {"status": "completed"},
        },
    }

    statuses = home_presenter_service.build_stage_statuses(manifest, "en")

    assert statuses[0]["status"] == "finished"
    assert statuses[1]["status"] == "not_started"


def test_build_stage_statuses_marks_chunking_finished_after_chunking_completion() -> None:
    """
    @brief      Verify Text Chunking is finished after the workflow reaches translation readiness.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    manifest = {
        "current_stage": "translation_ready",
        "source_document": {"original_name": "story.txt"},
        "operations": {
            "cleanup": {"status": "completed"},
            "chunking": {"status": "completed"},
        },
    }

    statuses = home_presenter_service.build_stage_statuses(manifest, "en")

    assert statuses[1]["label"] == "Text Chunking"
    assert statuses[1]["status"] == "finished"
    assert statuses[2]["status"] == "not_started"


def test_apply_active_operation_status_marks_chunking_in_progress() -> None:
    """
    @brief      Verify active chunking runs update the Home progress row before manifest completion.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    manifest = {
        "current_stage": "text_chunking_ready",
        "source_document": {"original_name": "story.txt"},
        "operations": {
            "cleanup": {"status": "completed"},
            "chunking": {"status": "not_started"},
        },
    }
    statuses = home_presenter_service.build_stage_statuses(manifest, "en")

    home_presenter_service.apply_active_operation_status(statuses, "chunking")

    assert statuses[1]["status"] == "in_progress"


def test_build_stage_statuses_marks_character_voices_ready_as_finished() -> None:
    """
    @brief      Verify Character Voices is finished when its operation summary is completed.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.3.0
    """
    manifest = {
        "current_stage": "character_voices_ready",
        "source_document": {"original_name": "story.txt"},
        "operations": {
            "narrator_definition": {"status": "completed"},
            "character_voices": {"status": "completed"},
        },
    }

    statuses = home_presenter_service.build_stage_statuses(manifest, "en")

    assert statuses[4]["status"] == "finished"
    assert statuses[5]["status"] == "finished"


def test_build_stage_statuses_trusts_not_started_operation_over_advanced_stage() -> None:
    """
    @brief      Verify advanced current_stage values do not mark explicit not-started operations as finished.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    0.1.0
    """
    manifest = {
        "current_stage": "character_voices_ready",
        "source_document": {"original_name": "story.txt"},
        "operations": {
            "cleanup": {"status": "completed"},
            "chunking": {"status": "completed"},
            "translation": {"status": "not_started"},
            "character_discovery": {"status": "not_started"},
            "narrator_definition": {"status": "completed"},
            "character_voices": {"status": "not_started"},
        },
    }

    statuses = home_presenter_service.build_stage_statuses(manifest, "en")

    assert statuses[0]["status"] == "finished"
    assert statuses[1]["status"] == "finished"
    assert statuses[2]["status"] == "not_started"
    assert statuses[3]["status"] == "not_started"
    assert statuses[4]["status"] == "finished"
    assert statuses[5]["status"] == "not_started"


def test_build_stage_statuses_marks_downstream_operation_status_as_in_progress() -> None:
    """
    @brief      Verify generated but unfinished downstream work appears in progress.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    manifest = {
        "current_stage": "character_voices_ready",
        "source_document": {"original_name": "story.txt"},
        "operations": {
            "speech_blocks": {"status": "review_pending"},
            "audio_blocks": {"status": "cancelled"},
        },
    }

    statuses = home_presenter_service.build_stage_statuses(manifest, "en")

    assert statuses[6]["status"] == "in_progress"
    assert statuses[7]["status"] == "in_progress"


# END OF FILE
