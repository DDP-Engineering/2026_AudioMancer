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
"""

# IMPORTS

from datetime import datetime
import json
import os
from pathlib import Path
import wave

import pytest

from audiomancer import config
from audiomancer.services import (
    audio_assembly_service,
    audio_assembly_state_service,
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
    assert state["resume_checkpoint"] == {"run_token": report["started_at"]}
    assert "completed_output_keys" not in state["metadata"]


def test_audio_assembly_service_persists_truthful_run_timestamps(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify fresh completion persists ordered report timestamps and a matching state token.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    clock_values = iter(("2026-08-09T10:00:00+00:00", "2026-08-09T10:00:05+00:00"))
    monkeypatch.setattr(audio_assembly_service, "_utc_now_iso", lambda: next(clock_values))

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)
    persisted_report = audio_assembly_service.load_audio_assembly_report(project_root)
    operation_state = audio_assembly_service.load_operation_state(project_root)

    assert report == persisted_report
    assert report["started_at"] == "2026-08-09T10:00:00+00:00"
    assert report["completed_at"] == "2026-08-09T10:00:05+00:00"
    assert datetime.fromisoformat(report["started_at"]) < datetime.fromisoformat(report["completed_at"])
    assert operation_state["resume_checkpoint"] == {"run_token": report["started_at"]}
    assert operation_state["metadata"]["input_fingerprint"] == report["input_fingerprint"]


def test_audio_assembly_service_cancel_resume_preserves_run_token_and_outputs(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify cancellation and resume keep one start token and reuse completed output work.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_PER_CHUNK,
    }
    monkeypatch.setattr(audio_assembly_service, "_utc_now_iso", lambda: "2026-08-09T11:00:00+00:00")

    def cancel_after_first_output() -> bool:
        """Return cancellation only after the first output has completed."""
        return (project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME / "chunk-0001.wav").is_file()

    with pytest.raises(audio_assembly_service.operation_runtime_service.OperationCancelledError):
        audio_assembly_service.start_or_continue_composition(
            project_root,
            manifest,
            cancel_requested=cancel_after_first_output,
        )

    cancelled_report = audio_assembly_service.load_audio_assembly_report(project_root)
    cancelled_state = audio_assembly_service.load_operation_state(project_root)
    first_output = dict(cancelled_report["outputs"][0])
    assert cancelled_report["started_at"] == "2026-08-09T11:00:00+00:00"
    assert cancelled_report["completed_at"] is None
    assert cancelled_state["resume_checkpoint"] == {"run_token": cancelled_report["started_at"]}
    assert cancelled_state["progress_current"] == 1

    original_compose_output = audio_assembly_service._compose_output_file  # noqa: SLF001
    resumed_output_keys: list[str] = []

    def record_resumed_output(*args, **kwargs):
        """Record each output that resume actually composes."""
        resumed_output_keys.append(str(args[1]["output_key"]))
        return original_compose_output(*args, **kwargs)

    monkeypatch.setattr(audio_assembly_service, "_compose_output_file", record_resumed_output)
    monkeypatch.setattr(audio_assembly_service, "_utc_now_iso", lambda: "2026-08-09T11:05:00+00:00")

    resumed_report = audio_assembly_service.start_or_continue_composition(project_root, manifest)
    resumed_state = audio_assembly_service.load_operation_state(project_root)

    assert resumed_report["started_at"] == cancelled_report["started_at"]
    assert resumed_report["completed_at"] == "2026-08-09T11:05:00+00:00"
    assert resumed_report["outputs"][0] == first_output
    assert resumed_output_keys == ["chunk-0002"]
    assert resumed_state["resume_checkpoint"] == {"run_token": cancelled_report["started_at"]}
    assert resumed_state["progress_current"] == resumed_state["progress_total"] == 2


def test_audio_assembly_service_legacy_state_without_checkpoint_gets_fresh_run_token(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify compatible legacy report and state load and receive one fallback run token.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    settings = audio_assembly_service.normalize_audio_assembly_settings(manifest["audio_assembly_settings"])
    approved_blocks = audio_assembly_service._load_approved_audio_blocks(  # noqa: SLF001
        project_root,
        include_scene_ambience=bool(settings["include_scene_ambience"]),
    )
    input_fingerprint = audio_assembly_service._build_input_fingerprint(  # noqa: SLF001
        project_root,
        approved_blocks,
        settings,
    )
    legacy_report = {
        "operation_status": "cancelled",
        "input_fingerprint": input_fingerprint,
        "outputs": [],
        "warnings": [],
    }
    legacy_state = {
        "status": "cancelled",
        "progress_current": 0,
        "progress_total": 1,
        "mode": "audio_composition",
        "warning_count": 0,
        "metadata": {"input_fingerprint": input_fingerprint},
    }
    audio_assembly_service._persist_state(project_root, legacy_report, legacy_state)  # noqa: SLF001

    loaded_legacy_report = audio_assembly_service.load_audio_assembly_report(project_root)
    loaded_legacy_state = audio_assembly_service.load_operation_state(project_root)
    assert "started_at" not in loaded_legacy_report
    assert "completed_at" not in loaded_legacy_report
    assert "resume_checkpoint" not in loaded_legacy_state

    clock_values = iter(("2026-08-09T12:00:00+00:00", "2026-08-09T12:00:03+00:00"))
    monkeypatch.setattr(audio_assembly_service, "_utc_now_iso", lambda: next(clock_values))

    resumed_report = audio_assembly_service.start_or_continue_composition(project_root, manifest)
    resumed_state = audio_assembly_service.load_operation_state(project_root)

    assert resumed_report["started_at"] == "2026-08-09T12:00:00+00:00"
    assert resumed_report["completed_at"] == "2026-08-09T12:00:03+00:00"
    assert resumed_state["resume_checkpoint"] == {"run_token": resumed_report["started_at"]}


def test_audio_assembly_service_writes_pause_blocks_as_silence(tmp_path) -> None:
    """
    @brief      Verify explicit pause blocks contribute silence without adjacent automatic gaps.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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


@pytest.mark.parametrize("source_kind", ["missing", "unsafe", "directory", "invalid_wav"])
def test_audio_assembly_service_preflights_included_legacy_scene_ambience_source(
    tmp_path,
    monkeypatch,
    source_kind: str,
) -> None:
    """
    @brief      Verify path-carrying metadata-only ambience cannot bypass source preflight.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  source_kind Missing, unsafe, non-file, or invalid-WAV source case.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    source_relative_path = f"audio_blocks/legacy-{source_kind}.wav"
    source_path = project_root / source_relative_path
    if source_kind == "unsafe":
        source_relative_path = "../outside.wav"
        _write_wav(tmp_path / "outside.wav", 2400)
    elif source_kind == "directory":
        source_path.mkdir()
    elif source_kind == "invalid_wav":
        source_path.write_bytes(b"not a WAV file")
    loaded_blocks = _loaded_blocks_with_legacy_scene_ambience(project_root, source_relative_path)
    monkeypatch.setattr(audio_blocks_service, "load_audio_blocks", lambda _project_root: loaded_blocks)

    with pytest.raises(ValueError, match="Every approved Audio Block"):
        audio_assembly_service.start_or_continue_composition(project_root, manifest)

    assert not (project_root / config.AUDIO_ASSEMBLY_STATE_FILE_NAME).exists()
    assert not (project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME).exists()


def test_audio_assembly_service_composes_valid_legacy_scene_ambience_source(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify included path-carrying metadata-only ambience still composes when its WAV is valid.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    source_relative_path = "audio_blocks/legacy-valid-ambience.wav"
    _write_wav(project_root / source_relative_path, 2400)
    loaded_blocks = _loaded_blocks_with_legacy_scene_ambience(project_root, source_relative_path)
    monkeypatch.setattr(audio_blocks_service, "load_audio_blocks", lambda _project_root: loaded_blocks)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK,
        "inter_block_silence_ms": 0,
        "inter_chunk_silence_ms": 0,
        "include_scene_ambience": True,
    }

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    assert report["outputs"][0]["block_count"] == 4
    assert (project_root / str(report["outputs"][0]["audio_relative_path"])).is_file()


def test_audio_assembly_service_ignores_invalid_legacy_scene_ambience_when_disabled(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify disabled ambience is outside both preflight and composition.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    loaded_blocks = _loaded_blocks_with_legacy_scene_ambience(project_root, "audio_blocks/missing-legacy.wav")
    monkeypatch.setattr(audio_blocks_service, "load_audio_blocks", lambda _project_root: loaded_blocks)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK,
        "inter_block_silence_ms": 0,
        "inter_chunk_silence_ms": 0,
        "include_scene_ambience": False,
    }

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    assert report["outputs"][0]["block_count"] == 3


def test_audio_assembly_service_lists_and_generates_scene_mix_preview(tmp_path) -> None:
    """
    @brief      Verify Scene Ambience groups can be preview-mixed on demand.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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
    assert groups[0]["audio_relative_path"] == preview_group["audio_relative_path"]
    preview_path = project_root / str(preview_group["audio_relative_path"])
    assert preview_path.is_file()
    assert refreshed_groups[0]["can_play_preview"] is True
    assert refreshed_groups[0]["audio_relative_path"] == preview_group["audio_relative_path"]
    assert progress_events[0][:3] == (0, 3, 0)
    assert progress_events[-1][:3] == (3, 3, 100)
    with wave.open(str(preview_path), "rb") as wav_file:
        assert wav_file.getnframes() == 2400


def test_audio_assembly_scene_mix_refresh_reuses_unchanged_source_digests(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify repeated list and page-state refreshes hash each unchanged source once.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    _insert_scene_ambience_blocks(project_root, approved=True, with_audio=True)
    source_paths = _scene_ambience_source_paths(project_root)
    audio_assembly_service._clear_file_sha1_cache()  # noqa: SLF001
    read_counts = _count_source_binary_reads(monkeypatch, source_paths)

    first_groups = audio_assembly_service.list_scene_mix_groups(project_root)
    page_state = audio_assembly_state_service.build_audio_assembly_state(project_root, manifest, "en")
    second_groups = audio_assembly_service.list_scene_mix_groups(project_root)

    assert [group["audio_relative_path"] for group in first_groups] == [
        group["audio_relative_path"] for group in second_groups
    ]
    assert page_state["scene_mix_groups"][0]["audio_relative_path"] == first_groups[0]["audio_relative_path"]
    assert read_counts == {source_path.resolve(): 1 for source_path in source_paths}


def test_audio_assembly_scene_mix_shared_source_uses_one_digest(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify multiple Scene Ambience groups sharing one source reuse its digest.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project_with_audio_blocks(tmp_path)
    _insert_scene_ambience_blocks(project_root, approved=True, with_audio=True)
    loaded_blocks = audio_blocks_service.load_audio_blocks(project_root)
    scene_blocks = [block for block in loaded_blocks if block.get("content_kind") == "scene_ambience"]
    scene_blocks[1]["ambience_position"] = "scene_change"
    scene_blocks[1]["after_speech_block_id"] = "0001-000001"
    scene_blocks[1]["audio_relative_path"] = scene_blocks[0]["audio_relative_path"]
    shared_source = project_root / str(scene_blocks[0]["audio_relative_path"])
    monkeypatch.setattr(audio_blocks_service, "load_audio_blocks", lambda _project_root: loaded_blocks)
    audio_assembly_service._clear_file_sha1_cache()  # noqa: SLF001
    read_counts = _count_source_binary_reads(monkeypatch, [shared_source])

    groups = audio_assembly_service.list_scene_mix_groups(project_root)

    assert len(groups) == 2
    assert read_counts == {shared_source.resolve(): 1}


def test_audio_assembly_scene_mix_digest_cache_invalidates_on_stat_change(tmp_path) -> None:
    """
    @brief      Verify mtime or size changes rehash content and change preview identity.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project_with_audio_blocks(tmp_path)
    _insert_scene_ambience_blocks(project_root, approved=True, with_audio=True)
    source_path = _scene_ambience_source_paths(project_root)[0]
    audio_assembly_service._clear_file_sha1_cache()  # noqa: SLF001

    first_preview_path = audio_assembly_service.list_scene_mix_groups(project_root)[0]["audio_relative_path"]
    first_stat = source_path.stat()
    changed_bytes = bytearray(source_path.read_bytes())
    changed_bytes[-1] ^= 1
    source_path.write_bytes(changed_bytes)
    os.utime(
        source_path,
        ns=(first_stat.st_atime_ns, first_stat.st_mtime_ns + 2_000_000_000),
    )
    second_stat = source_path.stat()
    assert second_stat.st_mtime_ns != first_stat.st_mtime_ns

    second_preview_path = audio_assembly_service.list_scene_mix_groups(project_root)[0]["audio_relative_path"]
    source_path.write_bytes(source_path.read_bytes() + b"\x01")
    os.utime(source_path, ns=(second_stat.st_atime_ns, second_stat.st_mtime_ns))
    third_stat = source_path.stat()
    assert third_stat.st_mtime_ns == second_stat.st_mtime_ns
    assert third_stat.st_size != second_stat.st_size

    third_preview_path = audio_assembly_service.list_scene_mix_groups(project_root)[0]["audio_relative_path"]

    assert len({first_preview_path, second_preview_path, third_preview_path}) == 3


def test_audio_assembly_scene_mix_digest_failure_is_not_cached(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify a transient source-hash read failure is retried on the next refresh.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = _create_project_with_audio_blocks(tmp_path)
    _insert_scene_ambience_blocks(project_root, approved=True, with_audio=True)
    source_path = _scene_ambience_source_paths(project_root)[0].resolve()
    audio_assembly_service._clear_file_sha1_cache()  # noqa: SLF001
    original_open = Path.open
    hash_attempts = 0

    def fail_first_hash_open(path, *args, **kwargs):
        """Raise once for the selected source's binary read, then delegate."""
        nonlocal hash_attempts
        mode = str(args[0] if args else kwargs.get("mode", "r"))
        if path.resolve() == source_path and "r" in mode and "b" in mode:
            hash_attempts += 1
            if hash_attempts == 1:
                raise OSError("transient hash read failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_first_hash_open)

    with pytest.raises(OSError, match="transient hash read failure"):
        audio_assembly_service.list_scene_mix_groups(project_root)
    groups = audio_assembly_service.list_scene_mix_groups(project_root)

    assert groups
    assert hash_attempts == 2


def test_audio_assembly_scene_mix_digest_cache_is_bounded_and_clearable(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify the digest cache has a finite bound and a deterministic test reset.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    audio_assembly_service._clear_file_sha1_cache()  # noqa: SLF001
    monkeypatch.setattr(audio_assembly_service, "_hash_file_contents", lambda path: str(path))  # noqa: SLF001
    cache_size = audio_assembly_service._FILE_SHA1_CACHE_MAXSIZE  # noqa: SLF001
    for index in range(cache_size + 5):
        fake_path = str((tmp_path / f"source-{index:04d}.wav").resolve())
        audio_assembly_service._cached_file_sha1(fake_path, index, index)  # noqa: SLF001

    cache_info = audio_assembly_service._cached_file_sha1.cache_info()  # noqa: SLF001
    assert cache_info.maxsize == cache_size
    assert cache_info.currsize == cache_size

    audio_assembly_service._clear_file_sha1_cache()  # noqa: SLF001
    assert audio_assembly_service._cached_file_sha1.cache_info().currsize == 0  # noqa: SLF001


def test_audio_assembly_service_scene_mix_group_not_ready_without_approved_audio(tmp_path) -> None:
    """
    @brief      Verify incomplete Scene Ambience groups are listed but not previewable.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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
    @brief      Verify a missing pause duration uses the configured default.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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


def test_audio_assembly_service_resume_preserves_time_limit_warnings(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify resumed completed-output runs keep deterministic warnings.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path, frame_count=24_000 * 61)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_TIME_LIMIT,
        "max_duration_minutes": 1,
    }
    clock_values = iter(
        (
            "2026-08-09T13:00:00+00:00",
            "2026-08-09T13:01:00+00:00",
            "2026-08-09T13:05:00+00:00",
        )
    )
    monkeypatch.setattr(audio_assembly_service, "_utc_now_iso", lambda: next(clock_values))

    first_report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    def reject_recomposition(*_args, **_kwargs):
        """Fail if a completed output is recomposed during a compatible resume."""
        raise AssertionError("completed output was recomposed")

    monkeypatch.setattr(audio_assembly_service, "_compose_output_file", reject_recomposition)
    resumed_report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    assert first_report["warning_count"] == 3
    assert resumed_report["warning_count"] == 3
    assert resumed_report["started_at"] == first_report["started_at"]
    assert resumed_report["completed_at"] == first_report["completed_at"]
    assert resumed_report["outputs"] == first_report["outputs"]
    assert [warning["output_key"] for warning in resumed_report["warnings"]] == [
        "part-0001",
        "part-0002",
        "part-0003",
    ]


def test_audio_assembly_service_classic_wav_size_boundary_uses_whole_frames() -> None:
    """
    @brief      Verify the exact stdlib RIFF bound permits the last legal whole frame.
    @return     None.
    @exception  None
    """
    params = wave._wave_params(1, 2, 24_000, 0, "NONE", "not compressed")
    assert audio_assembly_service._WAV_MAX_DATA_BYTES == (1 << 32) - 1 - 36  # noqa: SLF001
    assert audio_assembly_service._conservative_resampled_frame_count(1, 24_000, 44_100) == 2  # noqa: SLF001
    assert audio_assembly_service._silence_frame_count(44_100, 1) == 44  # noqa: SLF001
    maximum_frames = audio_assembly_service._WAV_MAX_DATA_BYTES // 2  # noqa: SLF001

    audio_assembly_service._validate_classic_wav_data_size(  # noqa: SLF001
        "legal.wav",
        maximum_frames,
        params,
    )

    with pytest.raises(RuntimeError, match="4 GB classic WAV limit.*Per text chunk or Time limit"):
        audio_assembly_service._validate_classic_wav_data_size(  # noqa: SLF001
            "oversized.wav",
            maximum_frames + 1,
            params,
        )


def test_audio_assembly_service_size_preflight_precedes_output_work_and_persistence(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify overflow rejection performs no output work and preserves report state.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK,
        "inter_block_silence_ms": 0,
        "inter_chunk_silence_ms": 0,
    }
    prior_report = {"sentinel": True, "outputs": []}
    prior_state = {
        "status": "not_started",
        "progress_current": 0,
        "progress_total": 0,
        "mode": "audio_composition",
        "warning_count": 0,
        "metadata": {"sentinel": True},
        "resume_checkpoint": None,
    }
    audio_assembly_service._persist_state(project_root, prior_report, prior_state)  # noqa: SLF001
    report_path = project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME
    state_path = project_root / config.AUDIO_ASSEMBLY_STATE_FILE_NAME
    original_report_bytes = report_path.read_bytes()
    original_state_bytes = state_path.read_bytes()
    monkeypatch.setattr(audio_assembly_service, "_WAV_MAX_DATA_BYTES", 14_399, raising=False)

    def unexpected_output_work(*_args, **_kwargs):
        raise AssertionError("Output composition started before the size preflight rejected the plan.")

    monkeypatch.setattr(audio_assembly_service, "_compose_output_file", unexpected_output_work)

    with pytest.raises(RuntimeError, match="audiobook.wav.*4 GB classic WAV limit"):
        audio_assembly_service.start_or_continue_composition(project_root, manifest)

    assert report_path.read_bytes() == original_report_bytes
    assert state_path.read_bytes() == original_state_bytes
    assert not (project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME).exists()


def test_audio_assembly_service_size_preflight_allows_exact_legal_boundary(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify a payload equal to the configured byte boundary reaches composition.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK,
        "inter_block_silence_ms": 0,
        "inter_chunk_silence_ms": 0,
    }
    monkeypatch.setattr(audio_assembly_service, "_WAV_MAX_DATA_BYTES", 14_400, raising=False)

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    output_path = project_root / str(report["outputs"][0]["audio_relative_path"])
    with wave.open(str(output_path), "rb") as output_wav:
        assert output_wav.getnframes() == 7200


def test_audio_assembly_service_size_preflight_treats_per_chunk_outputs_independently(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify separate legal files are not rejected by their aggregate size.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    manifest["audio_assembly_settings"] = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_PER_CHUNK,
        "inter_block_silence_ms": 0,
        "inter_chunk_silence_ms": 0,
    }
    monkeypatch.setattr(audio_assembly_service, "_WAV_MAX_DATA_BYTES", 9_600, raising=False)

    report = audio_assembly_service.start_or_continue_composition(project_root, manifest)

    assert [output["file_name"] for output in report["outputs"]] == ["chunk-0001.wav", "chunk-0002.wav"]


@pytest.mark.parametrize("failure_point", ["write", "close"])
def test_audio_assembly_service_removes_temp_after_output_writer_failure(
    tmp_path,
    monkeypatch,
    failure_point: str,
) -> None:
    """
    @brief      Verify failed final-output writes remove temp bytes and preserve publication.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  failure_point Writer operation that raises the simulated error.
    @return     None.
    @exception  None
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    settings = {
        **audio_assembly_service.default_audio_assembly_settings(),
        "output_mode": audio_assembly_service.OUTPUT_MODE_WHOLE_BOOK,
        "inter_block_silence_ms": 0,
        "inter_chunk_silence_ms": 0,
    }
    approved_blocks = audio_assembly_service._load_approved_audio_blocks(  # noqa: SLF001
        project_root,
        include_scene_ambience=True,
    )
    output_item = audio_assembly_service._build_output_plan(project_root, approved_blocks, settings)[0]  # noqa: SLF001
    output_root = project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME
    output_root.mkdir()
    output_path = output_root / str(output_item["file_name"])
    output_path.write_bytes(b"published output")
    temp_path = output_path.with_name(output_path.name + ".tmp")
    real_wave_open = wave.open

    class FailingWriter:
        def __enter__(self):
            temp_path.write_bytes(b"partial temp")
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            if failure_point == "close" and exc_type is None:
                raise OSError("simulated close failure")
            return False

        def setparams(self, _params):
            return None

        def writeframes(self, _data):
            if failure_point == "write":
                raise OSError("simulated write failure")

    def failing_output_open(path, mode=None):
        if mode == "wb" and str(path) == str(temp_path):
            return FailingWriter()
        return real_wave_open(path, mode)

    monkeypatch.setattr(audio_assembly_service.wave, "open", failing_output_open)

    with pytest.raises(OSError, match=f"simulated {failure_point} failure"):
        audio_assembly_service._compose_output_file(project_root, output_item, settings)  # noqa: SLF001

    assert output_path.read_bytes() == b"published output"
    assert not temp_path.exists()


def test_audio_assembly_service_rejects_unapproved_audio_blocks(tmp_path) -> None:
    """
    @brief      Verify composition refuses incomplete Audio Blocks approval state.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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
    @details    The escaping path is injected at the load seam to keep the
                composition-level containment guard covered.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  path_kind Escaping path form under test.
    @return     None.
    @exception  None
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
    """
    project_root, _manifest = _create_project_with_audio_blocks(tmp_path)
    outside_path = tmp_path / "outside_fallback.wav"
    _write_wav(outside_path, 2400)
    escaping_path = _escaping_artifact_path(path_kind, "outside_fallback.wav", outside_path)

    with pytest.raises(RuntimeError, match="without at least one source WAV"):
        audio_assembly_service._reference_wav_params(project_root, [], escaping_path)  # noqa: SLF001

    assert outside_path.is_file()


def test_audio_assembly_reference_params_accepts_a_narrow_path_resolver(tmp_path) -> None:
    """
    @brief      Verify shared WAV lookup preserves speech precedence with an injected path resolver.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    ambience_path = tmp_path / "ambience.wav"
    speech_path = tmp_path / "speech.wav"
    fallback_path = tmp_path / "fallback.wav"
    _write_wav(ambience_path, 4410, channels=2, frame_rate=44_100)
    _write_wav(speech_path, 2400)
    _write_wav(fallback_path, 1600, channels=2, frame_rate=16_000)
    blocks = [
        {"id": "ambience", "content_kind": "scene_ambience"},
        {"id": "speech", "content_kind": "narration"},
    ]
    resolved_ids: list[str] = []

    def resolve_path(_project_root, block):
        """Resolve controlled source paths while recording selection order."""
        block_id = str(block["id"])
        resolved_ids.append(block_id)
        return {"ambience": ambience_path, "speech": speech_path}[block_id]

    params = audio_assembly_service._reference_wav_params(  # noqa: SLF001
        tmp_path,
        blocks,
        fallback_path.name,
        path_resolver=resolve_path,
    )

    assert resolved_ids == ["speech"]
    assert params.nchannels == 1
    assert params.sampwidth == 2
    assert params.framerate == 24_000


def test_audio_assembly_reference_params_resolves_default_path_at_call_time(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify monkeypatching the default block-path seam remains effective after consolidation.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    source_path = tmp_path / "runtime-source.wav"
    _write_wav(source_path, 2400)
    resolved_blocks: list[dict[str, object]] = []

    def resolve_path(_project_root, block):
        """Return the controlled WAV and record the block passed through the default seam."""
        resolved_blocks.append(block)
        return source_path

    monkeypatch.setattr(audio_assembly_service, "_audio_path", resolve_path)

    params = audio_assembly_service._reference_wav_params(  # noqa: SLF001
        tmp_path,
        [{"content_kind": "narration"}],
        "missing.wav",
    )

    assert len(resolved_blocks) == 1
    assert params.framerate == 24_000


def test_audio_assembly_size_preflight_uses_shared_planned_reference_lookup(tmp_path, monkeypatch) -> None:
    """
    @brief      Verify planned virtual-block lookup is injected into the shared WAV resolver.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    fallback_path = tmp_path / "fallback.wav"
    _write_wav(fallback_path, 2400)
    with wave.open(str(fallback_path), "rb") as fallback_wav:
        fallback_params = fallback_wav.getparams()
    captured: dict[str, object] = {}

    def shared_reference_lookup(_root, _blocks, _fallback, *, path_resolver=None):
        """Capture the injected resolver and return controlled WAV parameters."""
        captured["path_resolver"] = path_resolver
        return fallback_params

    monkeypatch.setattr(audio_assembly_service, "_reference_wav_params", shared_reference_lookup)
    monkeypatch.setattr(audio_assembly_service, "_planned_output_frame_count", lambda *_args: 0)

    audio_assembly_service._validate_pending_output_wav_sizes(  # noqa: SLF001
        tmp_path,
        [
            {
                "output_key": "whole-book",
                "file_name": "audiobook.wav",
                "reference_audio_relative_path": fallback_path.name,
                "blocks": [],
            }
        ],
        audio_assembly_service.default_audio_assembly_settings(),
        [],
    )

    assert captured.get("path_resolver") is audio_assembly_service._planned_block_reference_path  # noqa: SLF001


def _escaping_artifact_path(path_kind: str, traversal_file_name: str, absolute_path) -> str:
    """
    @brief      Build one escaping persisted artifact path for traversal tests.
    @param[in]  path_kind Escaping path form under test.
    @param[in]  traversal_file_name Sibling file name used by parent traversal and UNC-like cases.
    @param[in]  absolute_path Absolute path used by the drive-qualified case.
    @return     Escaping path string.
    @exception  AssertionError Raised when the test path kind is unknown.
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
    """
    project_root, manifest = _create_project_with_audio_blocks(tmp_path)
    audio_assembly_service.start_or_continue_composition(project_root, manifest)

    audio_assembly_service.reset_audio_assembly(project_root)

    assert not (project_root / config.AUDIO_ASSEMBLY_REPORT_FILE_NAME).exists()
    assert not (project_root / config.AUDIO_ASSEMBLY_STATE_FILE_NAME).exists()
    assert not list((project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME).glob("*.wav"))
    assert audio_assembly_service.load_audio_assembly_report(project_root) is None
    assert audio_assembly_service.load_operation_state(project_root) is None
    state = audio_assembly_state_service.build_audio_assembly_state(project_root, manifest, "en")
    assert state["stage_status"] == audio_assembly_service.AUDIO_ASSEMBLY_STAGE_NOT_STARTED
    assert state["progress_current"] == state["progress_total"] == 0
    assert state["can_reset"] is False


def test_project_manifest_normalizes_audio_assembly_settings(tmp_path) -> None:
    """
    @brief      Verify project manifests retain normalized Audio Assembly settings.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
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


def _scene_ambience_source_paths(project_root) -> list[Path]:
    """
    @brief      Resolve generated Scene Ambience source paths for cache tests.
    @param[in]  project_root Active project root.
    @return     Ordered source paths.
    @exception  None
    """
    return [
        project_root / str(block["audio_relative_path"])
        for block in audio_blocks_service.load_audio_blocks(project_root)
        if block.get("content_kind") == "scene_ambience"
    ]


def _count_source_binary_reads(monkeypatch, source_paths: list[Path]) -> dict[Path, int]:
    """
    @brief      Count binary `Path.open` reads for selected source files.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  source_paths Source paths whose full-hash reads are counted.
    @return     Mutable resolved-path read counters.
    @exception  None
    """
    resolved_counts = {path.resolve(): 0 for path in source_paths}
    original_open = Path.open

    def counting_open(path, *args, **kwargs):
        """Count selected binary reads and delegate to the original opener."""
        mode = str(args[0] if args else kwargs.get("mode", "r"))
        resolved_path = path.resolve()
        if resolved_path in resolved_counts and "r" in mode and "b" in mode:
            resolved_counts[resolved_path] += 1
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    return resolved_counts


def _loaded_blocks_with_legacy_scene_ambience(project_root, source_relative_path: str) -> list[dict]:
    """
    @brief      Inject one legacy path-carrying metadata-only Scene Ambience row.
    @param[in]  project_root Active project root.
    @param[in]  source_relative_path Persisted-style source path to inject.
    @return     Loaded Audio Blocks including the injected legacy row.
    @exception  None
    """
    loaded_blocks = audio_blocks_service.load_audio_blocks(project_root)
    loaded_blocks[1]["sequence_index"] = 3
    loaded_blocks.insert(
        1,
        {
            **loaded_blocks[0],
            "speech_block_id": "0001-000002-legacy-ambience",
            "sequence_index": 2,
            "speaker_id": "scene_ambience",
            "speaker_display_name": "Scene Ambience",
            "normalized_speaker_name": "scene_ambience",
            "content_kind": "scene_ambience",
            "metadata_only": True,
            "text": "Legacy rain ambience.",
            "sound_prompt": "Legacy rain ambience.",
            "duration_seconds": 0.1,
            "ambience_position": "opener",
            "after_speech_block_id": "",
            "audio_relative_path": source_relative_path,
            "generated": True,
            "approved": True,
        },
    )
    return loaded_blocks


def _write_wav(path, frame_count: int, channels: int = 1, frame_rate: int = 24_000) -> None:
    """
    @brief      Write one small mono PCM WAV test file.
    @param[in]  path Destination WAV path.
    @param[in]  frame_count Number of silent frames to write.
    @param[in]  channels Number of channels to write.
    @param[in]  frame_rate WAV frame rate.
    @return     None.
    @exception  None
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
