#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_assembly_service.py
@brief Audio Assembly service tests for AudioMancer.
@details Verifies WAV audiobook composition, project settings normalization,
         stale-input protection, and generated-output reset behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-25
@version 0.3.1
"""

# IMPORTS

import json
import wave

import pytest

from audiomancer import config
from audiomancer.services import audio_assembly_service, project_workspace_service


def test_audio_assembly_service_composes_per_chunk_outputs(tmp_path) -> None:
    """
    @brief      Verify per-chunk composition creates one WAV output per chunk.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_PER_CHUNK,
    }

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    assert report["audio_assembly_stage_status"] == audio_assembly_service.AUDIO_ASSEMBLY_STAGE_COMPLETED
    assert [output["file_name"] for output in report["outputs"]] == ["chunk-0001.wav", "chunk-0002.wav"]
    assert (project_root / "audiobook" / "chunk-0001.wav").is_file()
    assert (project_root / "audiobook" / "chunk-0002.wav").is_file()
    assert audio_assembly_service.load_operation_state(project_root)["status"] == "completed"


def test_audio_assembly_service_writes_pause_blocks_as_silence(tmp_path) -> None:
    """
    @brief      Verify explicit pause blocks contribute silence without adjacent automatic gaps.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    payload_path = project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload[1]["sequence_index"] = 3
    payload.insert(
        1,
        {
            "speech_block_id": "0001-000002-pause",
            "sequence_index": 2,
            "chunk_id": "chunk-0001",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "normalized_speaker_name": "narrator",
            "content_kind": "pause",
            "metadata_only": True,
            "pause_duration_ms": 500,
            "text": "Pause 500 ms.",
            "voice_target_id": "narrator",
            "voice_source_kind": "metadata",
            "audio_relative_path": None,
            "metadata_relative_path": None,
            "generated": True,
            "approved": True,
            "approved_at": "2026-04-25T00:00:00+00:00",
            "generated_at": None,
            "runtime_result_summary": "Metadata-only block; no speech audio generated.",
            "split_part_count": 1,
            "split_strategy": "single",
            "model_token_budget": None,
            "model_audio_seconds_budget": None,
            "generated_part_relative_paths": [],
            "warning_flags": [],
        },
    )
    payload_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK,
        "inter_block_silence_ms": 1000,
        "inter_chunk_silence_ms": 0,
    }

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    output_path = project_root / str(report["outputs"][0]["audio_relative_path"])
    with wave.open(str(output_path), "rb") as wav_file:
        assert wav_file.getnframes() == (2400 * 3) + 12_000
    assert report["outputs"][0]["block_count"] == 4


def test_audio_assembly_service_composes_time_limited_outputs(tmp_path) -> None:
    """
    @brief      Verify time-limited composition splits sequential outputs by duration.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path, frame_count=48_000)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_TIME_LIMIT,
        "max_duration_minutes": 1,
    }

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    assert [output["file_name"] for output in report["outputs"]] == ["part-0001.wav"]
    assert report["outputs"][0]["block_count"] == 3


def test_audio_assembly_service_rejects_unapproved_audio_blocks(tmp_path) -> None:
    """
    @brief      Verify composition refuses incomplete Audio Blocks approval state.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    payload_path = project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload[0]["approved"] = False
    payload_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Approve every generated Audio Block"):
        audio_assembly_service.start_or_continue_composition(project_root, manifest)


def test_audio_assembly_service_requires_reset_when_settings_change(tmp_path) -> None:
    """
    @brief      Verify stale persisted assembly data cannot resume after settings changes.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    audio_assembly_service.start_or_continue_composition(project_root, manifest)
    changed_manifest = dict(manifest)
    changed_manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_PER_CHUNK,
    }

    with pytest.raises(ValueError, match="Reset Audio Assembly"):
        audio_assembly_service.start_or_continue_composition(project_root, changed_manifest)


def test_audio_assembly_service_reset_deletes_report_state_and_audiobook_folder(tmp_path) -> None:
    """
    @brief      Verify reset clears Audio Assembly runtime artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    audio_assembly_service.start_or_continue_composition(project_root, manifest)

    audio_assembly_service.reset_audio_assembly(project_root)

    assert not (project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME).exists()
    assert not (project_root / config.AUDIO_ASSEMBLY_STATE_FILE_NAME).exists()
    assert not list((project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME).glob("*.wav"))


def test_project_manifest_normalizes_audio_assembly_settings(tmp_path) -> None:
    """
    @brief      Verify project manifests retain normalized Audio Assembly settings.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    updated_manifest = audio_assembly_service.save_audio_assembly_settings(
        project_root,
        manifest,
        {
            "output_mode": "time_limit",
            "max_duration_minutes": "45",
            "output_format": "wav",
            "inter_block_silence_ms": "400",
            "inter_chunk_silence_ms": "1200",
        },
    )

    assert updated_manifest["audio_assembly_settings"] == {
        "output_mode": "time_limit",
        "max_duration_minutes": 45,
        "output_format": "wav",
        "inter_block_silence_ms": 400,
        "inter_chunk_silence_ms": 1200,
    }


def _create_project_with_audio_blocks(tmp_path, frame_count: int = 2400):
    """
    @brief      Create a temporary project with approved generated Audio Blocks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  frame_count Frame count for each generated WAV file.
    @return     Project root and loaded manifest.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root = tmp_path / "AudioAssemblyProject"
    project_root.mkdir()
    manifest = project_workspace_service.build_project_manifest("AudioAssemblyProject")
    manifest["current_stage"] = "audio_blocks_ready"
    manifest["audio_assembly_settings"] = audio_assembly_service.default_audio_assembly_settings()
    project_workspace_service.save_manifest(manifest, project_root)
    audio_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    audio_root.mkdir()
    blocks = []
    block_specs = (
        ("chunk-0001", 1, "0001-000001", "narrator"),
        ("chunk-0001", 2, "0001-000002", "alice"),
        ("chunk-0002", 1, "0002-000001", "narrator"),
    )
    for index, (chunk_id, sequence_index, speech_block_id, speaker) in enumerate(block_specs, start=1):
        audio_path = audio_root / f"{speech_block_id.replace('-', '_')}_{speaker}.wav"
        _write_wav(audio_path, frame_count)
        blocks.append(
            {
                "speech_block_id": speech_block_id,
                "sequence_index": sequence_index,
                "chunk_id": chunk_id,
                "speaker_id": speaker,
                "speaker_display_name": speaker.title(),
                "normalized_speaker_name": speaker,
                "content_kind": "narration",
                "metadata_only": False,
                "text": f"Line {index}.",
                "voice_target_id": speaker,
                "voice_source_kind": "sample",
                "audio_relative_path": audio_path.relative_to(project_root).as_posix(),
                "metadata_relative_path": None,
                "generated": True,
                "approved": True,
                "approved_at": "2026-04-25T00:00:00+00:00",
                "generated_at": "2026-04-25T00:00:00+00:00",
                "runtime_result_summary": "",
                "split_part_count": 1,
                "split_strategy": "single",
                "model_token_budget": 1024,
                "model_audio_seconds_budget": 60.0,
                "generated_part_relative_paths": [],
                "warning_flags": [],
            }
        )
    (project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(blocks, indent=2) + "\n",
        encoding="utf-8",
    )
    return project_root, project_workspace_service.load_manifest(project_root)


def _write_wav(path, frame_count: int) -> None:
    """
    @brief      Write one small mono PCM WAV test file.
    @param[in]  path Destination WAV path.
    @param[in]  frame_count Number of silent frames to write.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24_000)
        wav_file.writeframes(b"\x00\x00" * frame_count)


# END OF FILE
