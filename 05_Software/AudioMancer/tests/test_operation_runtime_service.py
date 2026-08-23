#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_operation_runtime_service.py
@brief Focused tests for shared operation runtime helpers.
@details Verifies percent conversion and downstream reset behavior shared by
         extraction, cleanup, and future workflow operations.
"""

# IMPORTS

import json
from pathlib import Path

from audiomancer import config
from audiomancer.services import narrator_definition_service, operation_runtime_service, project_workspace_service
from audiomancer.services.time_service import utc_now_iso


def test_progress_percent_clamps_to_zero_and_hundred() -> None:
    """
    @brief      Verify shared unit-progress conversion stays inside the UI range.
    @return     None.
    @exception  None
    """
    assert operation_runtime_service.progress_percent(0, 0) == 0
    assert operation_runtime_service.progress_percent(1, 4) == 25
    assert operation_runtime_service.progress_percent(99, 4) == 100


def test_emit_progress_update_uses_standard_payload_shape() -> None:
    """
    @brief      Verify shared progress emission sends the modal callback contract.
    @return     None.
    @exception  None
    """
    received_payloads: list[tuple[int, int, int, str, dict[str, object] | None]] = []

    def collect_progress_payload(
        progress_current: int,
        progress_total: int,
        progress_percent_value: int,
        message: str,
        token_usage: dict[str, object] | None,
    ) -> None:
        """
        @brief      Collect one five-argument progress callback payload.
        @param[in]  progress_current Current progress unit count.
        @param[in]  progress_total Total progress unit count.
        @param[in]  progress_percent_value Normalized progress percentage.
        @param[in]  message Progress message text.
        @param[in]  token_usage Optional token-usage payload.
        @return     None.
        @exception  None
        """
        received_payloads.append((progress_current, progress_total, progress_percent_value, message, token_usage))

    operation_runtime_service.emit_progress_update(
        collect_progress_payload,
        2,
        4,
        "Half done",
        {"total_tokens": 12},
    )

    assert received_payloads == [(2, 4, 50, "Half done", {"total_tokens": 12})]


def test_emit_progress_update_can_omit_token_usage_payload() -> None:
    """
    @brief      Verify shared progress emission supports four-argument callbacks.
    @return     None.
    @exception  None
    """
    received_payloads: list[tuple[int, int, int, str]] = []

    def collect_progress_payload(
        progress_current: int,
        progress_total: int,
        progress_percent_value: int,
        message: str,
    ) -> None:
        """
        @brief      Collect one four-argument progress callback payload.
        @param[in]  progress_current Current progress unit count.
        @param[in]  progress_total Total progress unit count.
        @param[in]  progress_percent_value Normalized progress percentage.
        @param[in]  message Progress message text.
        @return     None.
        @exception  None
        """
        received_payloads.append((progress_current, progress_total, progress_percent_value, message))

    operation_runtime_service.emit_progress_update(
        collect_progress_payload,
        1,
        4,
        "Quarter done",
        include_token_usage=False,
    )

    assert received_payloads == [(1, 4, 25, "Quarter done")]


def test_utc_now_iso_uses_utc_without_microseconds() -> None:
    """
    @brief      Verify shared timestamps use the persisted UTC ISO format.
    @return     None.
    @exception  None
    """
    timestamp = utc_now_iso()

    assert timestamp.endswith("+00:00")
    assert "." not in timestamp


def test_build_operation_state_payload_uses_shared_envelope() -> None:
    """
    @brief      Verify shared operation-state envelope normalizes workflow-specific payloads.
    @return     None.
    @exception  None
    """
    payload = operation_runtime_service.build_operation_state_payload(
        status="running",
        progress_current=1,
        progress_total=3,
        mode="ai_assisted",
        warning_count=2,
        metadata={"warnings": ["one", "two"]},
        resume_checkpoint={"next_index": 1},
    )

    assert payload == {
        "status": "running",
        "progress_current": 1,
        "progress_total": 3,
        "mode": "ai_assisted",
        "warning_count": 2,
        "metadata": {"warnings": ["one", "two"]},
        "resume_checkpoint": {"next_index": 1},
    }
    for field_name in (
        "folder_relative_path",
        "input_paths",
        "output_paths",
        "artifact_paths",
        "started_at",
        "completed_at",
        "updated_at",
    ):
        assert field_name not in payload


def test_operation_json_artifact_round_trips_via_shared_io(tmp_path) -> None:
    """
    @brief      Verify shared operation JSON helpers write and reload root-level artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("SharedJsonRuntime", tmp_path)

    output_path = operation_runtime_service.write_operation_json_artifact(
        project_root,
        "speech_blocks",
        config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME,
        {"status": "completed", "progress_current": 3, "progress_total": 3},
    )
    state_payload = operation_runtime_service.load_operation_state_payload(
        project_root,
        "speech_blocks",
        config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME,
    )
    artifact_payload = operation_runtime_service.load_optional_json_artifact(output_path)

    assert output_path == project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME
    assert state_payload == {"status": "completed", "progress_current": 3, "progress_total": 3}
    assert artifact_payload == state_payload


def test_load_operation_state_file_accepts_missing_and_dict_payloads(tmp_path) -> None:
    """
    @brief      Verify exact state-file loading normalizes missing and dictionary payloads.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    state_path = tmp_path / "operation_state.json"
    assert operation_runtime_service.load_operation_state_file(state_path) is None

    state_path.write_text(json.dumps({"status": "running", "progress_current": 1}), encoding="utf-8")

    assert operation_runtime_service.load_operation_state_file(state_path) == {
        "status": "running",
        "progress_current": 1,
    }


def test_load_operation_state_file_tolerates_malformed_json(tmp_path) -> None:
    """
    @brief      Verify corrupt operation state is treated as absent for clean restart.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    state_path = tmp_path / "operation_state.json"
    state_path.write_text("{", encoding="utf-8")

    assert operation_runtime_service.load_operation_state_file(state_path) is None


def test_project_artifact_helpers_handle_missing_and_malformed_inputs(tmp_path) -> None:
    """
    @brief      Verify shared project artifact probes normalize missing, corrupt, and text artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("SharedArtifactRuntime", tmp_path)
    (project_root / "bad.json").write_text("{", encoding="utf-8")
    (project_root / "notes.txt").write_text("usable", encoding="utf-8")

    assert operation_runtime_service.load_project_json_artifact(project_root, "missing.json") is None
    assert operation_runtime_service.load_project_json_artifact(project_root, "bad.json") is None
    assert operation_runtime_service.project_artifact_exists(project_root, "notes.txt") is True
    assert operation_runtime_service.project_text_artifact_has_content(project_root, "notes.txt") is True
    assert operation_runtime_service.project_text_artifact_has_content(project_root, "missing.txt") is False


def test_optional_string_and_runtime_value_helpers_normalize_null_like_values() -> None:
    """
    @brief      Verify shared optional string and runtime null helpers keep consistent semantics.
    @return     None.
    @exception  None
    """
    assert operation_runtime_service.optional_string(None) is None
    assert operation_runtime_service.optional_string("  name  ") == "name"
    assert operation_runtime_service.optional_string("  name  ", strip=False) == "  name  "
    assert operation_runtime_service.is_missing_runtime_value(" null ") is True
    assert operation_runtime_service.valid_runtime_value(" None ") == ""
    assert operation_runtime_service.valid_runtime_value(" model-a ") == "model-a"


def test_project_relative_path_resolver_rejects_escapes(tmp_path) -> None:
    """
    @brief      Verify shared project-relative path helpers reject traversal and absolute paths.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("PathRuntime", tmp_path)
    artifact_path = project_root / "safe.txt"
    artifact_path.write_text("safe", encoding="utf-8")

    assert operation_runtime_service.is_path_inside_project(project_root, artifact_path) is True
    assert operation_runtime_service.is_path_inside_project(project_root, tmp_path / "outside.txt") is False
    assert operation_runtime_service.resolve_project_relative_path(project_root, "safe.txt") == artifact_path.resolve()
    assert (
        operation_runtime_service.try_resolve_project_relative_path(project_root, "safe.txt") == artifact_path.resolve()
    )
    assert operation_runtime_service.try_resolve_project_relative_path(project_root, "") is None
    assert operation_runtime_service.try_resolve_project_relative_path(project_root, "../escape.txt") is None
    assert (
        operation_runtime_service.try_resolve_project_relative_path(
            project_root,
            str((tmp_path / "outside.txt").resolve()),
        )
        is None
    )
    assert (
        operation_runtime_service.try_resolve_project_relative_path(
            project_root,
            "//server/share/outside.txt",
        )
        is None
    )
    assert operation_runtime_service.project_relative_path_exists(project_root, "safe.txt") is True
    assert operation_runtime_service.project_relative_path_exists(project_root, "../escape.txt") is False


def test_reset_operation_data_clears_known_root_artifacts_only(tmp_path) -> None:
    """
    @brief      Verify S-0003 clears known flat artifacts without deleting unrelated root files.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("ResetRuntime", tmp_path)
    (project_root / "story.txt").write_text("raw", encoding="utf-8")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("raw", encoding="utf-8")
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("clean", encoding="utf-8")
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text("[]", encoding="utf-8")
    (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text("[]", encoding="utf-8")
    (project_root / "notes.txt").write_text("keep", encoding="utf-8")

    operation_runtime_service.reset_operation_data(
        project_root,
        "cleanup",
        include_current=True,
    )

    assert (project_root / "story.txt").is_file()
    assert (project_root / "notes.txt").read_text(encoding="utf-8") == "keep"
    assert (project_root / config.EXTRACTED_TEXT_FILE_NAME).is_file()
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).exists() is False
    assert (project_root / config.CHUNK_ARTIFACT_FILE_NAME).exists() is False
    assert (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).exists() is False


def test_reset_operation_data_deletes_only_character_discovery_ai_logs(tmp_path) -> None:
    """
    @brief      Verify Character Discovery reset removes both owned AI-log token families only.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("ResetCharacterLogs", tmp_path)
    current_log_path = project_root / "log_ai_character_discovery_current.log"
    historical_log_path = project_root / "log_ai_characters_historical.log"
    unrelated_log_path = project_root / "log_ai_translation_unrelated.log"
    for log_path in (current_log_path, historical_log_path, unrelated_log_path):
        log_path.write_text("transaction", encoding="utf-8")

    operation_runtime_service.reset_operation_data(
        project_root,
        "character_discovery",
        include_current=True,
    )

    assert not current_log_path.exists()
    assert not historical_log_path.exists()
    assert unrelated_log_path.is_file()


def test_reset_operation_data_deletes_referenced_character_samples_before_targets_document(
    monkeypatch,
    tmp_path,
) -> None:
    """
    @brief      Verify Character Voices reset removes every owned sample before its metadata document.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("ResetCharacterSamples", tmp_path)
    generated_sample_path = project_root / "audio_alice.wav"
    imported_sample_path = project_root / "imported_bob.wav"
    generated_sample_path.write_bytes(b"RIFF-generated")
    imported_sample_path.write_bytes(b"RIFF-imported")
    targets_path = project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME
    targets_path.write_text(
        json.dumps(
            [
                {
                    "target_id": "character_alice",
                    "target_kind": "character",
                    "sample_audio_path": generated_sample_path.name,
                    "sample_metadata": {"sample_source": "voice_designer"},
                },
                {
                    "target_id": "character_bob",
                    "target_kind": "character",
                    "sample_audio_path": imported_sample_path.name,
                    "sample_metadata": {"sample_source": "imported_sample"},
                },
            ]
        ),
        encoding="utf-8",
    )
    original_unlink = Path.unlink

    def unlink_with_order_assertion(path: Path, *args, **kwargs) -> None:
        """
        @brief      Assert samples are absent before the targets document is removed.
        @param[in]  path Path selected for deletion.
        @return     None.
        @exception  AssertionError Raised when reset deletes metadata first.
        """
        if path == targets_path:
            assert not generated_sample_path.exists()
            assert not imported_sample_path.exists()
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink_with_order_assertion)

    operation_runtime_service.reset_operation_data(
        project_root,
        "character_voices",
        include_current=True,
    )

    assert not targets_path.exists()
    assert not generated_sample_path.exists()
    assert not imported_sample_path.exists()


def test_character_discovery_reset_preserves_narrator_and_deletes_character_samples(tmp_path) -> None:
    """
    @brief      Verify narrator-preserving discovery reset still clears downstream character samples.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("ResetDiscoverySamples", tmp_path)
    narrator_definition_service.ensure_narrator_voice_document(project_root)
    narrator_sample_path = project_root / "audio_narator_preserved.wav"
    character_sample_path = project_root / "audio_character_removed.wav"
    narrator_sample_path.write_bytes(b"RIFF-narrator")
    character_sample_path.write_bytes(b"RIFF-character")
    targets_path = project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME
    targets_path.write_text(
        json.dumps(
            [
                {
                    "target_id": "narrator",
                    "target_kind": "narrator",
                    "sample_audio_path": narrator_sample_path.name,
                    "sample_metadata": {"sample_source": "narrator_definition"},
                },
                {
                    "target_id": "character_alice",
                    "target_kind": "character",
                    "sample_audio_path": character_sample_path.name,
                    "sample_metadata": {"sample_source": "voice_designer"},
                },
            ]
        ),
        encoding="utf-8",
    )

    operation_runtime_service.reset_operation_data(
        project_root,
        "character_discovery",
        include_current=True,
        preserve_operation_kinds=operation_runtime_service.NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
    )

    assert (project_root / config.NARRATOR_VOICE_FILE_NAME).is_file()
    assert narrator_sample_path.is_file()
    assert not targets_path.exists()
    assert not character_sample_path.exists()


def test_character_voice_sample_reset_preserves_unowned_and_unsafe_paths(tmp_path) -> None:
    """
    @brief      Verify Character Voices reset never broad-deletes or follows unsafe sample references.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("SafeCharacterSampleReset", tmp_path)
    unreferenced_wav_path = project_root / "audio_unreferenced.wav"
    unrelated_root_wav_path = project_root / "project_theme.wav"
    referenced_non_wav_path = project_root / "character_notes.txt"
    referenced_directory_path = project_root / "audio_directory.wav"
    traversal_target_path = tmp_path / "traversal_target.wav"
    absolute_target_path = tmp_path / "absolute_target.wav"
    for file_path in (
        unreferenced_wav_path,
        unrelated_root_wav_path,
        referenced_non_wav_path,
        traversal_target_path,
        absolute_target_path,
    ):
        file_path.write_bytes(b"keep")
    referenced_directory_path.mkdir()
    targets_path = project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME
    targets_path.write_text(
        json.dumps(
            [
                {
                    "target_id": "character_traversal",
                    "target_kind": "character",
                    "sample_audio_path": "../traversal_target.wav",
                },
                {
                    "target_id": "character_absolute",
                    "target_kind": "character",
                    "sample_audio_path": str(absolute_target_path.resolve()),
                },
                {
                    "target_id": "character_non_wav",
                    "target_kind": "character",
                    "sample_audio_path": referenced_non_wav_path.name,
                },
                {
                    "target_id": "character_directory",
                    "target_kind": "character",
                    "sample_audio_path": referenced_directory_path.name,
                },
            ]
        ),
        encoding="utf-8",
    )

    operation_runtime_service.reset_operation_data(
        project_root,
        "character_voices",
        include_current=True,
    )

    assert unreferenced_wav_path.is_file()
    assert unrelated_root_wav_path.is_file()
    assert referenced_non_wav_path.is_file()
    assert referenced_directory_path.is_dir()
    assert traversal_target_path.is_file()
    assert absolute_target_path.is_file()


def test_character_voice_sample_reset_tolerates_non_utf8_targets_document(tmp_path) -> None:
    """
    @brief      Verify corrupt non-UTF-8 metadata cannot block Character Voices reset.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("CorruptCharacterSampleReset", tmp_path)
    unrelated_wav_path = project_root / "audio_unrelated.wav"
    unrelated_wav_path.write_bytes(b"RIFF-unrelated")
    targets_path = project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME
    targets_path.write_bytes(b"\xff\xfe\x00")

    operation_runtime_service.reset_operation_data(
        project_root,
        "character_voices",
        include_current=True,
    )

    assert not targets_path.exists()
    assert unrelated_wav_path.is_file()


def test_reset_operation_data_preserves_character_voice_document_and_samples(tmp_path) -> None:
    """
    @brief      Verify explicit Character Voices preservation retains its metadata and samples.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("PreserveCharacterSamples", tmp_path)
    character_sample_path = project_root / "audio_character_preserved.wav"
    character_sample_path.write_bytes(b"RIFF-character")
    targets_path = project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME
    targets_path.write_text(
        json.dumps(
            [
                {
                    "target_id": "character_alice",
                    "target_kind": "character",
                    "sample_audio_path": character_sample_path.name,
                    "sample_metadata": {"sample_source": "voice_designer"},
                }
            ]
        ),
        encoding="utf-8",
    )

    operation_runtime_service.reset_operation_data(
        project_root,
        "character_discovery",
        include_current=True,
        preserve_operation_kinds=("character_voices",),
    )

    assert targets_path.is_file()
    assert character_sample_path.is_file()


def test_reset_operation_data_preserves_requested_narrator_artifacts(tmp_path) -> None:
    """
    @brief      Verify upstream resets can preserve narrator-definition artifacts while clearing dependents.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("PreserveNarratorRuntime", tmp_path)
    narrator_definition_service.ensure_narrator_voice_document(project_root)
    narrator_audio_path = project_root / "audio_narator_preserved.wav"
    narrator_audio_path.write_bytes(b"RIFF")
    (project_root / config.CHARACTERS_DOCUMENT_FILE_NAME).write_text("{}\n", encoding="utf-8")
    (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME).write_text("[]\n", encoding="utf-8")

    operation_runtime_service.reset_operation_data(
        project_root,
        "character_discovery",
        include_current=True,
        preserve_operation_kinds=operation_runtime_service.NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
    )

    assert (project_root / config.NARRATOR_VOICE_FILE_NAME).is_file()
    assert narrator_audio_path.is_file()
    assert not (project_root / config.CHARACTERS_DOCUMENT_FILE_NAME).exists()
    assert not (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).exists()
    assert not (project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME).exists()


def test_reset_operation_data_preserves_text_revision_artifacts(tmp_path) -> None:
    """
    @brief      Verify text revisions can preserve discovered characters and prepared voices.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("PreserveTextRevisionRuntime", tmp_path)
    (project_root / config.CHARACTERS_DOCUMENT_FILE_NAME).write_text("{}\n", encoding="utf-8")
    narrator_definition_service.ensure_narrator_voice_document(project_root)
    (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME).write_text("[]\n", encoding="utf-8")

    operation_runtime_service.reset_operation_data(
        project_root,
        "chunking",
        include_current=True,
        preserve_operation_kinds=operation_runtime_service.TEXT_REVISION_PRESERVED_OPERATION_KINDS,
    )

    assert (project_root / config.CHARACTERS_DOCUMENT_FILE_NAME).is_file()
    assert (project_root / config.NARRATOR_VOICE_FILE_NAME).is_file()
    assert (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).is_file()
    assert not (project_root / config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME).exists()
    assert not (project_root / config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME).exists()


def test_resolve_operation_path_uses_project_root_without_creating_folders(tmp_path) -> None:
    """
    @brief      Verify read-only path resolution uses the flat project root as a side effect-free operation path.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("ResolveRuntime", tmp_path)

    resolved_path = operation_runtime_service.resolve_operation_path(
        project_root,
        "translation",
        config.TRANSLATED_CHUNKS_FILE_NAME,
    )

    assert resolved_path == project_root / config.TRANSLATED_CHUNKS_FILE_NAME
    assert not any(
        (project_root / folder_name).exists() for folder_name in ("30_translation", "40_character_discovery")
    )


def test_ensure_default_operation_state_creates_not_started_state_only(tmp_path) -> None:
    """
    @brief      Verify default state initialization creates state metadata without reports or outputs.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("DefaultStateRuntime", tmp_path)

    state_path = operation_runtime_service.ensure_default_operation_state(project_root, "translation")
    second_state_path = operation_runtime_service.ensure_default_operation_state(project_root, "translation")

    assert state_path is None
    assert second_state_path is None
    assert (project_root / "translation_state.json").exists() is False
    assert (project_root / "translation_report.json").exists() is False
    assert (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).exists() is False


def test_ensure_default_operation_state_creates_compact_character_discovery_state(tmp_path) -> None:
    """
    @brief      Verify first Characters page access creates compact discovery state.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("DefaultCharacterStateRuntime", tmp_path)

    state_path = operation_runtime_service.ensure_default_operation_state(
        project_root,
        "character_discovery",
    )

    assert state_path is None
    assert not (project_root / config.CHARACTERS_DOCUMENT_FILE_NAME).exists()


def test_ensure_default_operation_state_skips_audio_blocks(tmp_path) -> None:
    """
    @brief      Verify REQ-FUNC-e4b08ab6 creates no Audio Blocks state artifact.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, _manifest = project_workspace_service.create_project("DefaultAudioBlocksStateRuntime", tmp_path)

    state_path = operation_runtime_service.ensure_default_operation_state(project_root, "audio_blocks")

    assert state_path is None
    assert not (project_root / config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME).exists()


def test_reset_operation_data_attempts_later_artifacts_after_unlink_failure(tmp_path, monkeypatch) -> None:
    """Verify one locked artifact does not prevent reset from attempting later owned files."""
    project_root, _manifest = project_workspace_service.create_project("ResetFailureCollection", tmp_path)
    locked_path = project_root / config.CLEANED_TEXT_FILE_NAME
    later_path = project_root / config.CHUNK_ARTIFACT_FILE_NAME
    locked_path.write_text("locked", encoding="utf-8")
    later_path.write_text("later", encoding="utf-8")
    original_unlink = Path.unlink

    def _unlink(path, *args, **kwargs):
        if path == locked_path:
            raise PermissionError("locked cleanup output")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _unlink)

    operation_runtime_service.reset_operation_data(project_root, "cleanup", include_current=True)

    assert locked_path.exists()
    assert not later_path.exists()


# END OF FILE
