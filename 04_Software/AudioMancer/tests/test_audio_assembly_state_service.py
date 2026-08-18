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
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import (
    audio_assembly_service,
    audio_assembly_state_service,
    audio_blocks_service,
    operation_runtime_service,
    project_workspace_service,
    speech_blocks_service,
)


def test_build_audio_assembly_state_keeps_reset_disabled_for_default_metadata(tmp_path) -> None:
    """
    @brief      Verify first-access default Audio Assembly state does not enable reset.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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


def test_build_audio_assembly_state_ignores_scene_ambience_when_excluded(tmp_path) -> None:
    """
    @brief      Verify excluded Scene Ambience blocks do not block Audio Assembly readiness.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("AudioAssemblySceneAmbienceState", tmp_path)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "include_scene_ambience": False,
    }
    project_workspace_service.save_manifest(manifest, project_root)
    _write_audio_blocks(
        project_root,
        extra_blocks=[
            {
                "speech_block_id": "0001-000002-ambience",
                "sequence_index": 2,
                "chunk_id": "chunk-0001",
                "speaker_id": "scene_ambience",
                "speaker_display_name": "Scene Ambience",
                "normalized_speaker_name": "scene_ambience",
                "content_kind": "scene_ambience",
                "text": "Rain in distant trenches.",
                "voice_target_id": "narrator",
                "generated": True,
                "approved": False,
            }
        ],
    )

    state = audio_assembly_state_service.build_audio_assembly_state(project_root, manifest, "en")

    assert state["can_generate"] is True
    assert any("Approved audio blocks: 1/1" in status_line for status_line in state["status_lines"])


def test_build_audio_assembly_state_returns_empty_state_without_project() -> None:
    """
    @brief      Verify no-project Audio Assembly state disables all page actions.
    @return     None.
    @exception  None
    """
    state = audio_assembly_state_service.build_audio_assembly_state(None, None, "en")

    assert state["outputs"] == []
    assert state["current_output_key"] is None
    assert state["can_generate"] is False
    assert state["can_reset"] is False
    assert state["can_play_selected"] is False


def test_build_audio_assembly_state_loads_audio_blocks_once(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify one page-state build reads the Audio Blocks document a single time.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("AudioAssemblySingleLoad", tmp_path)
    _write_audio_blocks(
        project_root,
        extra_blocks=[
            {
                "speech_block_id": "0001-000002-ambience",
                "sequence_index": 2,
                "chunk_id": "chunk-0001",
                "speaker_id": "scene_ambience",
                "speaker_display_name": "Scene Ambience",
                "normalized_speaker_name": "scene_ambience",
                "content_kind": "scene_ambience",
                "text": "Rain in distant trenches.",
                "voice_target_id": "narrator",
                "generated": True,
                "approved": True,
            }
        ],
    )
    load_count = 0
    real_load_audio_blocks = audio_blocks_service.load_audio_blocks

    def counting_load_audio_blocks(*args, **kwargs):
        """
        @brief      Count Audio Blocks loads and delegate to the real loader.
        @param[in]  args Positional arguments forwarded to the real loader.
        @param[in]  kwargs Keyword arguments forwarded to the real loader.
        @return     Loaded Audio Blocks payload list.
        @exception  None
        """
        nonlocal load_count
        load_count += 1
        return real_load_audio_blocks(*args, **kwargs)

    monkeypatch.setattr(audio_blocks_service, "load_audio_blocks", counting_load_audio_blocks)

    state = audio_assembly_state_service.build_audio_assembly_state(project_root, manifest, "en")

    assert load_count == 1
    assert any("Approved audio blocks: 2/2" in status_line for status_line in state["status_lines"])


def _write_audio_blocks(project_root, extra_blocks=()) -> None:
    """
    @brief      Write the Speech Blocks and Audio Blocks documents for state tests.
    @details    Audio Blocks persists only its own contract fields and reads
                identity and text back from Speech Blocks, so both documents
                must be written together.
    @param[in]  project_root Active project root.
    @param[in]  extra_blocks Additional rich fixture blocks appended after the narrator block.
    @return     None.
    @exception  None
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
            "text": "Line one.",
            "voice_target_id": "narrator",
            "generated": True,
            "approved": True,
        },
        *extra_blocks,
    ]
    speech_blocks_service.write_speech_blocks_document(
        project_root,
        {
            "status": "completed",
            "source": {"kind": "original", "language": "en", "fingerprint": "state-fixture"},
            "ai_profile_id": "profile-1",
            "instructions": "",
            "scene_ambience": {"enabled": True},
            "response_contract": "direct_blocks",
            "token_usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "usage_available": False,
            },
            "budget_metadata": {},
            "checkpoint": None,
            "failure": None,
            "blocks": [
                {key: value for key, value in block.items() if key != "generated"} for block in blocks
            ],
        },
    )
    audio_blocks_service.write_audio_blocks_document(
        project_root,
        {
            "status": "completed",
            "voice_language": "en",
            "input_fingerprint": "state-fixture",
            "checkpoint": None,
            "blocks": [
                {
                    "speech_block_id": str(block["speech_block_id"]),
                    "voice_target_id": str(block.get("voice_target_id", "") or ""),
                    "generated": bool(block.get("generated", True)),
                    "approved": bool(block.get("approved", False)),
                    "audio_can_play": bool(block.get("generated", True)),
                    "audio_duration_seconds": None,
                    "generation_fingerprint": None,
                }
                for block in blocks
            ],
        },
    )


def _write_audio_assembly_report(project_root) -> None:
    """
    @brief      Write one completed Audio Assembly report for state tests.
    @param[in]  project_root Active project root.
    @return     None.
    @exception  None
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
