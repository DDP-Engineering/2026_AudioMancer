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
@version 0.6.2
"""

# IMPORTS

import json
import wave

import pytest

from audiomancer import config
from audiomancer.services import (
    audio_assembly_service,
    audio_blocks_service,
    project_workspace_service,
    speech_blocks_service,
)


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
    blocks = _load_block_fixtures(project_root)
    blocks[1]["sequence_index"] = 3
    blocks.insert(1, _pause_block_fixture("Pause 500 ms."))
    _persist_block_fixtures(project_root, blocks)
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
    blocks = _load_block_fixtures(project_root)
    _write_wav(
        project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "0001-000002-ambience.wav",
        2400,
    )
    blocks.insert(
        1,
        {
            **blocks[0],
            "speech_block_id": "0001-000002-ambience",
            "sequence_index": 2,
            "speaker_id": "scene_ambience",
            "speaker_display_name": "Scene Ambience",
            "normalized_speaker_name": "scene_ambience",
            "content_kind": "scene_ambience",
            "text": "Rain in distant trenches.",
        },
    )
    blocks[2]["sequence_index"] = 3
    _persist_block_fixtures(project_root, blocks)
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


def test_audio_assembly_service_lists_and_generates_scene_mix_preview(tmp_path) -> None:
    """
    @brief      Verify Scene Ambience groups can be preview-mixed on demand.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-25
    @version    0.1.0
    """
    project_root, _manifest = _create_project_with_audio_blocks(tmp_path)
    _insert_scene_ambience_blocks(project_root, approved=True, with_audio=True)
    progress_events: list[tuple[int, int, int, str]] = []

    groups = audio_assembly_service.list_scene_mix_groups(project_root)
    preview_group = audio_assembly_service.generate_scene_mix_preview(
        project_root,
        groups[0]["group_key"],
        progress_callback=lambda current, total, percent, message: progress_events.append(
            (current, total, percent, message)
        ),
    )
    refreshed_groups = audio_assembly_service.list_scene_mix_groups(project_root)

    assert len(groups) == 1
    assert groups[0]["block_count"] == 2
    assert groups[0]["can_generate_preview"] is True
    assert preview_group["can_play_preview"] is True
    preview_path = project_root / str(preview_group["audio_relative_path"])
    assert preview_path.is_file()
    assert refreshed_groups[0]["can_play_preview"] is True
    assert progress_events[0][:3] == (0, 3, 0)
    assert progress_events[-1][:3] == (3, 3, 100)
    with wave.open(str(preview_path), "rb") as wav_file:
        assert wav_file.getnframes() == 2400


def test_audio_assembly_service_scene_mix_group_not_ready_without_approved_audio(tmp_path) -> None:
    """
    @brief      Verify incomplete Scene Ambience groups are listed but not previewable.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-25
    @version    0.1.0
    """
    project_root, _manifest = _create_project_with_audio_blocks(tmp_path)
    _insert_scene_ambience_blocks(project_root, approved=False, with_audio=False)

    groups = audio_assembly_service.list_scene_mix_groups(project_root)

    assert len(groups) == 1
    assert groups[0]["can_generate_preview"] is False
    assert groups[0]["can_play_preview"] is False
    with pytest.raises(ValueError, match="Generate and approve every source"):
        audio_assembly_service.generate_scene_mix_preview(project_root, groups[0]["group_key"])


def test_audio_assembly_service_final_assembly_uses_mixed_scene_ambience_group(tmp_path) -> None:
    """
    @brief      Verify final assembly inserts one mixed Scene Ambience segment per group.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-25
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    _insert_scene_ambience_blocks(project_root, approved=True, with_audio=True)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK,
        "inter_block_silence_ms": 0,
        "inter_chunk_silence_ms": 0,
        "include_scene_ambience": True,
    }

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    output_path = project_root / str(report["outputs"][0]["audio_relative_path"])
    with wave.open(str(output_path), "rb") as wav_file:
        assert wav_file.getnframes() == 2400 * 4
    assert report["outputs"][0]["block_count"] == 5


def test_audio_assembly_service_final_assembly_converts_scene_mix_wav_params(tmp_path) -> None:
    """
    @brief      Verify final assembly accepts Scene Ambience mixes with different WAV parameters.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-27
    @version    0.1.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    _insert_scene_ambience_blocks(
        project_root,
        approved=True,
        with_audio=True,
        wav_channels=2,
        wav_frame_rate=44_100,
        wav_frame_count=4410,
    )
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK,
        "inter_block_silence_ms": 0,
        "inter_chunk_silence_ms": 0,
        "include_scene_ambience": True,
    }

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    output_path = project_root / str(report["outputs"][0]["audio_relative_path"])
    with wave.open(str(output_path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 24_000
        assert wav_file.getnframes() == 2400 * 4
    assert report["outputs"][0]["block_count"] == 5


def test_audio_assembly_service_final_assembly_prefers_speech_params_when_scene_ambience_leads(tmp_path) -> None:
    """
    @brief      Verify leading Scene Ambience does not upsample the final audiobook.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-08
    @version    0.1.0
    """
    # REQ-FUNC-057: final output params must prefer speech over leading ambience.
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    _insert_scene_ambience_blocks(
        project_root,
        approved=True,
        with_audio=True,
        wav_channels=2,
        wav_frame_rate=44_100,
        wav_frame_count=4410,
    )
    blocks = _load_block_fixtures(project_root)
    for block in blocks:
        if block["speaker_id"] == "scene_ambience":
            block["sequence_index"] = 0
    _persist_block_fixtures(project_root, blocks)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK,
        "inter_block_silence_ms": 0,
        "inter_chunk_silence_ms": 0,
        "include_scene_ambience": True,
    }

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    output_path = project_root / str(report["outputs"][0]["audio_relative_path"])
    with wave.open(str(output_path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 24_000
    assert report["outputs"][0]["block_count"] == 5


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
    blocks = _load_block_fixtures(project_root)
    blocks[1]["sequence_index"] = 3
    blocks.insert(1, _pause_block_fixture("Pause for a while."))
    _persist_block_fixtures(project_root, blocks)
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
    blocks = _load_block_fixtures(project_root)
    blocks[0]["approved"] = False
    _persist_block_fixtures(project_root, blocks)

    with pytest.raises(ValueError, match="Approve every generated Audio Block"):
        audio_assembly_service.start_or_continue_composition(project_root, manifest)


@pytest.mark.parametrize("path_kind", ["parent_traversal", "absolute", "unc_like"])
def test_audio_assembly_service_rejects_escaping_audio_block_path(tmp_path, monkeypatch, path_kind: str) -> None:
    """
    @brief      Verify composition refuses Audio Block paths resolving outside the project root.
    @details    The persisted document no longer stores a path, so the escaping
                path is injected at the load seam to keep the composition-level
                containment guard covered.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  path_kind Escaping path form under test.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.2.0
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    outside_path = tmp_path / "outside.wav"
    _write_wav(outside_path, 2400)
    escaping_path = _escaping_artifact_path(path_kind, "outside.wav", outside_path)
    loaded_blocks = audio_blocks_service.load_audio_blocks(project_root)
    loaded_blocks[0]["audio_relative_path"] = escaping_path
    monkeypatch.setattr(audio_blocks_service, "load_audio_blocks", lambda _project_root: loaded_blocks)

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
        audio_path = audio_root / f"{speech_block_id}.wav"
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
    _persist_block_fixtures(project_root, blocks)
    return project_root, project_workspace_service.load_manifest(project_root)


def _insert_scene_ambience_blocks(
    project_root,
    approved: bool,
    with_audio: bool,
    wav_channels: int = 1,
    wav_frame_rate: int = 24_000,
    wav_frame_count: int = 2400,
) -> None:
    """
    @brief      Insert two Scene Ambience Audio Blocks into the first chunk.
    @param[in]  project_root Active project root.
    @param[in]  approved Whether the inserted blocks are approved.
    @param[in]  with_audio Whether the inserted blocks reference generated WAV files.
    @param[in]  wav_channels Generated source WAV channel count.
    @param[in]  wav_frame_rate Generated source WAV frame rate.
    @param[in]  wav_frame_count Generated source WAV frame count.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-25
    @version    0.1.0
    """
    blocks = _load_block_fixtures(project_root)
    ambience_audio_root = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    ambience_blocks = []
    for offset, prompt in enumerate(("quiet library room tone", "intermittent page turns"), start=1):
        speech_block_id = f"0001-00000{offset + 1}-ambience"
        if with_audio:
            _write_wav(
                ambience_audio_root / f"{speech_block_id}.wav",
                wav_frame_count,
                channels=wav_channels,
                frame_rate=wav_frame_rate,
            )
        ambience_blocks.append(
            {
                **blocks[0],
                "speech_block_id": speech_block_id,
                "sequence_index": offset + 1,
                "speaker_id": "scene_ambience",
                "speaker_display_name": "Scene Ambience",
                "normalized_speaker_name": "scene_ambience",
                "content_kind": "scene_ambience",
                "text": prompt,
                "sound_prompt": prompt,
                "negative_prompt": "speech, music",
                "duration_seconds": 0.1,
                "ambience_position": "opener",
                "after_speech_block_id": "",
                "audio_duration_seconds": 0.1 if with_audio else None,
                "approved": approved,
                "generated": with_audio,
            }
        )
    blocks[1]["sequence_index"] = 4
    blocks[2]["sequence_index"] = 1
    blocks[1:1] = ambience_blocks
    _persist_block_fixtures(project_root, blocks)


def _write_wav(path, frame_count: int, channels: int = 1, frame_rate: int = 24_000) -> None:
    """
    @brief      Write one small mono PCM WAV test file.
    @param[in]  path Destination WAV path.
    @param[in]  frame_count Number of silent frames to write.
    @param[in]  channels Number of channels to write.
    @param[in]  frame_rate WAV frame rate.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count * channels)



def _pause_block_fixture(text: str) -> dict:
    """
    @brief      Build one metadata-only pause fixture block.
    @details    The pause duration is not persisted; it is parsed back from the
                Speech Blocks text on every load, so `text` is what drives it.
    @param[in]  text Pause Speech Block text carrying the duration.
    @return     Rich fixture block payload.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    return {
        "speech_block_id": "0001-000002-pause",
        "sequence_index": 2,
        "chunk_id": "chunk-0001",
        "speaker_id": "narrator",
        "speaker_display_name": "Narrator",
        "normalized_speaker_name": "narrator",
        "content_kind": "pause",
        "metadata_only": True,
        "text": text,
        "voice_target_id": "narrator",
        "generated": True,
        "approved": True,
    }


def _load_block_fixtures(project_root) -> list[dict]:
    """
    @brief      Rebuild the rich fixture block list from the two persisted documents.
    @details    Inverse of `_persist_block_fixtures`: Audio Blocks contract fields
                are merged back over the Speech Blocks entry so a test can mutate
                one flat list and persist it again.
    @param[in]  project_root Active project root folder.
    @return     Ordered rich fixture block payloads.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    document = audio_blocks_service.load_audio_blocks_document(project_root) or {"blocks": []}
    audio_blocks_by_id = {
        str(block.get("speech_block_id", "")).strip(): dict(block) for block in document.get("blocks", [])
    }
    blocks: list[dict] = []
    for speech_block in speech_blocks_service.load_speech_blocks(project_root):
        speech_block_id = str(speech_block.get("speech_block_id", "")).strip()
        blocks.append({**dict(speech_block), **audio_blocks_by_id.get(speech_block_id, {})})
    return blocks


def _persist_block_fixtures(project_root, blocks) -> None:
    """
    @brief      Persist rich fixture blocks as a Speech Blocks document plus an Audio Blocks document.
    @details    Audio Blocks now stores only its own contract fields and reads
                identity, text and prompts back from the Speech Blocks document,
                so fixtures must write both.
    @param[in]  project_root Active project root folder.
    @param[in]  blocks Ordered rich fixture block payloads.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-26
    @version    0.1.0
    """
    audio_only_fields = {
        "audio_relative_path",
        "metadata_relative_path",
        "generated",
        "generated_at",
        "runtime_result_summary",
        "split_part_count",
        "split_strategy",
        "model_token_budget",
        "model_audio_seconds_budget",
        "generated_part_relative_paths",
        "voice_source_kind",
        "audio_can_play",
        "audio_duration_seconds",
        "generation_fingerprint",
    }
    speech_blocks_service.write_speech_blocks_document(
        project_root,
        {
            "status": "completed",
            "source": {"kind": "original", "language": "en", "fingerprint": "assembly-fixture"},
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
                {key: value for key, value in block.items() if key not in audio_only_fields} for block in blocks
            ],
        },
    )
    audio_blocks_service.write_audio_blocks_document(
        project_root,
        {
            "status": "completed",
            "voice_language": "en",
            "input_fingerprint": "assembly-fixture",
            "checkpoint": None,
            "blocks": [
                {
                    "speech_block_id": str(block["speech_block_id"]),
                    "voice_target_id": str(block.get("voice_target_id", "") or ""),
                    "generated": bool(block.get("generated", True)),
                    "approved": bool(block.get("approved", False)),
                    "audio_can_play": bool(
                        block.get(
                            "audio_can_play",
                            bool(block.get("generated", True)) and not bool(block.get("metadata_only", False)),
                        )
                    ),
                    "audio_duration_seconds": block.get("audio_duration_seconds"),
                    "generation_fingerprint": None,
                }
                for block in blocks
            ],
        },
    )

# END OF FILE
