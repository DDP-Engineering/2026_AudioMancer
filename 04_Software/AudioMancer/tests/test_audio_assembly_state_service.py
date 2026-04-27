#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_assembly_state_service.py
@brief Audio Assembly state-service tests for AudioMancer.
@details Verifies reset eligibility, generated-output state shaping, and
         project-less state defaults for the Audio Assembly page.
@author Eng. Dan Dumitru Pasare
@date 2026-04-27
@version 0.1.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import (
    audio_assembly_service,
    audio_assembly_state_service,
    operation_runtime_service,
    project_workspace_service,
)


def test_build_audio_assembly_state_keeps_reset_disabled_for_default_metadata(tmp_path) -> None:
    """
    @brief      Verify first-access default Audio Assembly state does not enable reset.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("AudioAssemblyDefaultState", tmp_path)
    operation_runtime_service.ensure_default_operation_state(project_root, "audio_assembly")

    state = audio_assembly_state_service.build_audio_assembly_state(project_root, manifest, "en")

    assert state["stage_status"] == audio_assembly_service.AUDIO_ASSEMBLY_STAGE_NOT_STARTED
    assert state["can_reset"] is False
    assert state["progress_current"] == 0
    assert state["progress_total"] == 0


def test_build_audio_assembly_state_reports_completed_outputs(tmp_path) -> None:
    """
    @brief      Verify completed report data is exposed to the Audio Assembly page.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("AudioAssemblyCompletedState", tmp_path)
    _write_audio_blocks(project_root)
    _write_audio_assembly_report(project_root)

    state = audio_assembly_state_service.build_audio_assembly_state(project_root, manifest, "en")

    assert state["stage_status"] == audio_assembly_service.AUDIO_ASSEMBLY_STAGE_COMPLETED
    assert state["current_output_key"] == "audiobook"
    assert state["progress_current"] == 1
    assert state["progress_total"] == 1
    assert state["progress_percent"] == 100
    assert state["can_generate"] is True
    assert state["can_reset"] is True
    assert state["can_play_selected"] is True


def test_build_audio_assembly_state_returns_empty_state_without_project() -> None:
    """
    @brief      Verify no-project Audio Assembly state disables all page actions.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    state = audio_assembly_state_service.build_audio_assembly_state(None, None, "en")

    assert state["outputs"] == []
    assert state["current_output_key"] is None
    assert state["can_generate"] is False
    assert state["can_reset"] is False
    assert state["can_play_selected"] is False


def _write_audio_blocks(project_root) -> None:
    """
    @brief      Write one approved Audio Blocks payload for state tests.
    @param[in]  project_root Active project root.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    blocks = [
        {
            "speech_block_id": "0001-000001",
            "sequence_index": 1,
            "chunk_id": "chunk-0001",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "normalized_speaker_name": "narrator",
            "content_kind": "narration",
            "metadata_only": False,
            "text": "Line one.",
            "voice_target_id": "narrator",
            "voice_source_kind": "sample",
            "audio_relative_path": "audio_blocks/0001_000001_narrator.wav",
            "metadata_relative_path": None,
            "generated": True,
            "approved": True,
            "approved_at": "2026-04-27T00:00:00+00:00",
            "generated_at": "2026-04-27T00:00:00+00:00",
            "runtime_result_summary": "",
            "split_part_count": 1,
            "split_strategy": "single",
            "model_token_budget": 1024,
            "model_audio_seconds_budget": 60.0,
            "generated_part_relative_paths": [],
            "warning_flags": [],
        }
    ]
    (project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(blocks, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_audio_assembly_report(project_root) -> None:
    """
    @brief      Write one completed Audio Assembly report for state tests.
    @param[in]  project_root Active project root.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    report = {
        "audio_assembly_stage_status": audio_assembly_service.AUDIO_ASSEMBLY_STAGE_COMPLETED,
        "operation_status": "completed",
        "settings": audio_assembly_service.default_audio_assembly_settings(),
        "input_fingerprint": "fingerprint",
        "total_audio_block_count": 1,
        "composed_audio_block_count": 1,
        "planned_output_count": 1,
        "generated_output_count": 1,
        "total_duration_seconds": 2.0,
        "outputs": [
            {
                "output_key": "audiobook",
                "file_name": "audiobook.wav",
                "audio_relative_path": "audiobook/audiobook.wav",
                "block_count": 1,
                "chunk_ids": ["chunk-0001"],
                "duration_seconds": 2.0,
                "generated": True,
                "generated_at": "2026-04-27T00:00:00+00:00",
                "output_format": "wav",
            }
        ],
        "warning_count": 0,
        "warnings": [],
        "started_at": "2026-04-27T00:00:00+00:00",
        "completed_at": "2026-04-27T00:00:02+00:00",
        "updated_at": "2026-04-27T00:00:02+00:00",
    }
    (project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME).write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )


# END OF FILE
