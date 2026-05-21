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
@version 0.5.2
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
    @version    0.2.0
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
    state = audio_assembly_service.load_operation_state(project_root)
    assert state["status"] == "completed"
    assert state["resume_checkpoint"] is None
    assert "completed_output_keys" not in state["metadata"]


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


def test_audio_assembly_service_can_skip_scene_ambience_blocks(tmp_path) -> None:
    """
    @brief      Verify Audio Assembly excludes generated Scene Ambience blocks when configured.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-20
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    payload_path = project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    ambience_audio_path = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "0001_000002_ambience.wav"
    _write_wav(ambience_audio_path, 2400)
    payload.insert(
        1,
        {
            **payload[0],
            "speech_block_id": "0001-000002-ambience",
            "sequence_index": 2,
            "speaker_id": "scene_ambience",
            "speaker_display_name": "Scene Ambience",
            "normalized_speaker_name": "scene_ambience",
            "content_kind": "scene_ambience",
            "text": "Rain in distant trenches.",
            "audio_relative_path": ambience_audio_path.relative_to(project_root).as_posix(),
        },
    )
    payload[2]["sequence_index"] = 3
    payload_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK,
        "inter_block_silence_ms": 0,
        "inter_chunk_silence_ms": 0,
        "include_scene_ambience": False,
    }

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    assert report["settings"]["include_scene_ambience"] is False
    assert report["outputs"][0]["block_count"] == 3
    output_path = project_root / str(report["outputs"][0]["audio_relative_path"])
    with wave.open(str(output_path), "rb") as wav_file:
        assert wav_file.getnframes() == 2400 * 3


def test_audio_assembly_service_missing_pause_duration_uses_default(tmp_path) -> None:
    """
    @brief      Verify pause duration no longer falls back to parsing older pause text.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
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
            "pause_duration_ms": None,
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
        "inter_block_silence_ms": 0,
        "inter_chunk_silence_ms": 0,
    }

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    output_path = project_root / str(report["outputs"][0]["audio_relative_path"])
    with wave.open(str(output_path), "rb") as wav_file:
        assert wav_file.getnframes() == (2400 * 3) + 24_000


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


def test_audio_assembly_service_time_limit_counts_inserted_silence(tmp_path) -> None:
    """
    @brief      Verify time-limit planning accounts for automatic silence gaps.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path, frame_count=24_000 * 20)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_TIME_LIMIT,
        "max_duration_minutes": 1,
        "inter_block_silence_ms": 1000,
        "inter_chunk_silence_ms": 1000,
    }

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    assert [output["file_name"] for output in report["outputs"]] == ["part-0001.wav", "part-0002.wav"]
    assert all(float(output["duration_seconds"]) <= 60.0 for output in report["outputs"])


def test_audio_assembly_service_resume_preserves_time_limit_warnings(tmp_path) -> None:
    """
    @brief      Verify resumed completed-output runs keep deterministic warnings.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path, frame_count=24_000 * 61)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_TIME_LIMIT,
        "max_duration_minutes": 1,
    }

    first_report = audio_assembly_service.start_or_continue_composition(project_root, manifest)
    resumed_report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    assert first_report["warning_count"] == 3
    assert resumed_report["warning_count"] == 3
    assert [warning["output_key"] for warning in resumed_report["warnings"]] == [
        "part-0001",
        "part-0002",
        "part-0003",
    ]


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


@pytest.mark.parametrize("path_kind", ["parent_traversal", "absolute", "unc_like"])
def test_audio_assembly_service_rejects_escaping_audio_block_path(tmp_path, path_kind: str) -> None:
    """
    @brief      Verify persisted Audio Block paths cannot make composition read outside the project root.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  path_kind Escaping path form under test.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    outside_path = tmp_path / "outside.wav"
    _write_wav(outside_path, 2400)
    payload_path = project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload[0]["audio_relative_path"] = _escaping_artifact_path(path_kind, "outside.wav", outside_path)
    payload_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Every approved Audio Block"):
        audio_assembly_service.start_or_continue_composition(project_root, manifest)

    assert outside_path.is_file()


@pytest.mark.parametrize("path_kind", ["parent_traversal", "absolute", "unc_like"])
def test_audio_assembly_service_resume_ignores_escaping_output_record(tmp_path, path_kind: str) -> None:
    """
    @brief      Verify resume does not reuse completed output records pointing outside the project root.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  path_kind Escaping path form under test.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    project_root, _manifest = _create_project_with_audio_blocks(tmp_path)
    outside_path = tmp_path / "outside_resume.wav"
    _write_wav(outside_path, 2400)
    escaping_path = _escaping_artifact_path(path_kind, "outside_resume.wav", outside_path)
    report = {
        "outputs": [
            {
                "output_key": "part-0001",
                "file_name": "part-0001.wav",
                "audio_relative_path": escaping_path,
                "block_count": 1,
                "chunk_ids": ["chunk-0001"],
                "duration_seconds": 0.1,
                "generated": True,
                "generated_at": "2026-04-29T00:00:00+00:00",
                "output_format": audio_assembly_service.OUTPUT_FORMAT_WAV,
            }
        ]
    }
    operation_state = {"metadata": {"input_fingerprint": "fingerprint"}}
    audio_assembly_service._persist_state(project_root, report, operation_state)  # noqa: SLF001

    assert (
        audio_assembly_service._completed_records_for_resume(  # noqa: SLF001
            project_root,
            operation_state,
            "fingerprint",
        )
        == []
    )
    assert outside_path.is_file()


@pytest.mark.parametrize("path_kind", ["parent_traversal", "absolute", "unc_like"])
def test_audio_assembly_service_reference_fallback_rejects_escaping_path(tmp_path, path_kind: str) -> None:
    """
    @brief      Verify pause-only fallback WAV lookup cannot read outside the project root.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  path_kind Escaping path form under test.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    project_root, _manifest = _create_project_with_audio_blocks(tmp_path)
    outside_path = tmp_path / "outside_fallback.wav"
    _write_wav(outside_path, 2400)
    escaping_path = _escaping_artifact_path(path_kind, "outside_fallback.wav", outside_path)

    with pytest.raises(RuntimeError, match="without at least one source WAV"):
        audio_assembly_service._reference_wav_params(project_root, [], escaping_path)  # noqa: SLF001

    assert outside_path.is_file()


def _escaping_artifact_path(path_kind: str, traversal_file_name: str, absolute_path) -> str:
    """
    @brief      Build one escaping persisted artifact path for traversal tests.
    @param[in]  path_kind Escaping path form under test.
    @param[in]  traversal_file_name Sibling file name used by parent traversal and UNC-like cases.
    @param[in]  absolute_path Absolute path used by the drive-qualified case.
    @return     Escaping path string.
    @exception  AssertionError Raised when the test path kind is unknown.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    if path_kind == "parent_traversal":
        return f"../{traversal_file_name}"
    if path_kind == "absolute":
        return str(absolute_path.resolve())
    if path_kind == "unc_like":
        return f"//server/share/{traversal_file_name}"
    raise AssertionError(f"Unknown path kind: {path_kind}")


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


def test_audio_assembly_service_requires_reset_for_state_without_fingerprint(tmp_path) -> None:
    """
    @brief      Verify non-default current-version state requires a fingerprint before continuation.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-16
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    (project_root / config.AUDIO_ASSEMBLY_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "status": "running",
                "progress_current": 0,
                "progress_total": 1,
                "metadata": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Reset Audio Assembly"):
        audio_assembly_service.start_or_continue_composition(project_root, manifest)


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
            "include_scene_ambience": False,
        },
    )

    assert updated_manifest["audio_assembly_settings"] == {
        "output_mode": "time_limit",
        "max_duration_minutes": 45,
        "output_format": "wav",
        "inter_block_silence_ms": 400,
        "inter_chunk_silence_ms": 1200,
        "include_scene_ambience": False,
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
