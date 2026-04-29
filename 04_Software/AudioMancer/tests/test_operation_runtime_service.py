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
@author Eng. Dan Dumitru Pasare
@date 2026-04-22
@version 0.8.0
"""

# IMPORTS

import json

from audiomancer import config
from audiomancer.services import operation_runtime_service, project_workspace_service
from audiomancer.services.time_service import utc_now_iso


def test_progress_percent_clamps_to_zero_and_hundred() -> None:
    """
    @brief      Verify shared unit-progress conversion stays inside the UI range.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.1
    """
    assert operation_runtime_service.progress_percent(0, 0) == 0
    assert operation_runtime_service.progress_percent(1, 4) == 25
    assert operation_runtime_service.progress_percent(99, 4) == 100


def test_emit_progress_update_uses_standard_payload_shape() -> None:
    """
    @brief      Verify shared progress emission sends the modal callback contract.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.1
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
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-29
        @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    timestamp = utc_now_iso()

    assert timestamp.endswith("+00:00")
    assert "." not in timestamp


def test_build_operation_state_payload_uses_shared_envelope() -> None:
    """
    @brief      Verify shared operation-state envelope normalizes workflow-specific payloads.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    payload = operation_runtime_service.build_operation_state_payload(
        status="running",
        input_paths=["input.txt"],
        output_paths=["output.json"],
        artifact_paths=["report.json"],
        progress_current=1,
        progress_total=3,
        mode="ai_assisted",
        started_at="2026-04-29T12:00:00+00:00",
        completed_at=None,
        warning_count=2,
        metadata={"warnings": ["one", "two"]},
        resume_checkpoint={"next_index": 1},
        updated_at="2026-04-29T12:01:00+00:00",
    )

    assert payload == {
        "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
        "status": "running",
        "input_paths": ["input.txt"],
        "output_paths": ["output.json"],
        "artifact_paths": ["report.json"],
        "progress_current": 1,
        "progress_total": 3,
        "mode": "ai_assisted",
        "started_at": "2026-04-29T12:00:00+00:00",
        "completed_at": None,
        "updated_at": "2026-04-29T12:01:00+00:00",
        "warning_count": 2,
        "metadata": {"warnings": ["one", "two"]},
        "resume_checkpoint": {"next_index": 1},
    }


def test_operation_json_artifact_round_trips_via_shared_io(tmp_path) -> None:
    """
    @brief      Verify shared operation JSON helpers write and reload root-level artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("SharedJsonRuntime", tmp_path)

    output_path = operation_runtime_service.write_operation_json_artifact(
        project_root,
        "speech_blocks",
        config.SPEECH_BLOCKS_STATE_FILE_NAME,
        {"status": "completed", "progress_current": 3, "progress_total": 3},
    )
    state_payload = operation_runtime_service.load_operation_state_payload(
        project_root,
        "speech_blocks",
        config.SPEECH_BLOCKS_STATE_FILE_NAME,
    )
    artifact_payload = operation_runtime_service.load_optional_json_artifact(output_path)

    assert output_path == project_root / config.SPEECH_BLOCKS_STATE_FILE_NAME
    assert state_payload == {"status": "completed", "progress_current": 3, "progress_total": 3}
    assert artifact_payload == state_payload


def test_load_operation_state_file_accepts_missing_and_dict_payloads(tmp_path) -> None:
    """
    @brief      Verify exact state-file loading normalizes missing and dictionary payloads.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
    """
    state_path = tmp_path / "operation_state.json"
    assert operation_runtime_service.load_operation_state_file(state_path) is None

    state_path.write_text(json.dumps({"status": "running", "progress_current": 1}), encoding="utf-8")

    assert operation_runtime_service.load_operation_state_file(state_path) == {
        "status": "running",
        "progress_current": 1,
    }


def test_project_artifact_helpers_handle_missing_and_malformed_inputs(tmp_path) -> None:
    """
    @brief      Verify shared project artifact probes normalize missing, corrupt, and text artifacts.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.0
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
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-29
    @version    0.1.1
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
    @brief      Verify one operation reset clears known flat artifacts without deleting unrelated root files.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("ResetRuntime", tmp_path)
    (project_root / "story.txt").write_text("raw", encoding="utf-8")
    (project_root / config.EXTRACTED_TEXT_FILE_NAME).write_text("raw", encoding="utf-8")
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("clean", encoding="utf-8")
    (project_root / config.CLEANUP_REPORT_FILE_NAME).write_text("{}", encoding="utf-8")
    (project_root / config.CHUNK_ARTIFACT_FILE_NAME).write_text("[]", encoding="utf-8")
    (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).write_text("[]", encoding="utf-8")
    (project_root / "notes.txt").write_text("keep", encoding="utf-8")

    operation_runtime_service.reset_operation_data(
        project_root,
        "cleanup",
        include_current=True,
        keep_input_snapshots=False,
    )

    assert (project_root / "story.txt").is_file()
    assert (project_root / "notes.txt").read_text(encoding="utf-8") == "keep"
    assert (project_root / config.EXTRACTED_TEXT_FILE_NAME).is_file()
    assert (project_root / config.CLEANED_TEXT_FILE_NAME).exists() is False
    assert (project_root / config.CLEANUP_REPORT_FILE_NAME).exists() is False
    assert (project_root / config.CHUNK_ARTIFACT_FILE_NAME).exists() is False
    assert (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).exists() is False


def test_reset_operation_data_preserves_requested_narrator_artifacts(tmp_path) -> None:
    """
    @brief      Verify upstream resets can preserve narrator-definition artifacts while clearing dependents.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("PreserveNarratorRuntime", tmp_path)
    (project_root / config.NARRATOR_PROFILE_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.NARRATOR_SELECTION_FILE_NAME).write_text("{}\n", encoding="utf-8")
    (project_root / config.SELECTED_NARRATOR_AUDIO_FILE_NAME).write_bytes(b"RIFF")
    (project_root / config.SELECTED_NARRATOR_METADATA_FILE_NAME).write_text("{}\n", encoding="utf-8")
    (project_root / config.CHARACTER_PROFILE_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).write_text("[]\n", encoding="utf-8")
    (project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text("[]\n", encoding="utf-8")

    operation_runtime_service.reset_operation_data(
        project_root,
        "character_discovery",
        include_current=True,
        preserve_operation_kinds=operation_runtime_service.NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
    )

    assert (project_root / config.NARRATOR_PROFILE_FILE_NAME).is_file()
    assert (project_root / config.NARRATOR_SELECTION_FILE_NAME).is_file()
    assert (project_root / config.SELECTED_NARRATOR_AUDIO_FILE_NAME).is_file()
    assert (project_root / config.SELECTED_NARRATOR_METADATA_FILE_NAME).is_file()
    assert not (project_root / config.CHARACTER_PROFILE_FILE_NAME).exists()
    assert not (project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME).exists()
    assert not (project_root / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).exists()


def test_resolve_operation_path_uses_project_root_without_creating_folders(tmp_path) -> None:
    """
    @brief      Verify read-only path resolution uses the flat project root as a side effect-free operation path.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("ResolveRuntime", tmp_path)

    resolved_path = operation_runtime_service.resolve_operation_path(
        project_root,
        "translation",
        config.TRANSLATION_STATE_FILE_NAME,
    )

    assert resolved_path == project_root / config.TRANSLATION_STATE_FILE_NAME
    assert not any(
        (project_root / folder_name).exists() for folder_name in ("30_translation", "40_character_discovery")
    )


def test_ensure_default_operation_state_creates_not_started_state_only(tmp_path) -> None:
    """
    @brief      Verify default state initialization creates state metadata without reports or outputs.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("DefaultStateRuntime", tmp_path)

    state_path = operation_runtime_service.ensure_default_operation_state(project_root, "translation")
    second_state_path = operation_runtime_service.ensure_default_operation_state(project_root, "translation")

    assert state_path == project_root / config.TRANSLATION_STATE_FILE_NAME
    assert second_state_path == state_path
    assert (project_root / config.TRANSLATION_REPORT_FILE_NAME).exists() is False
    assert (project_root / config.TRANSLATED_CHUNKS_FILE_NAME).exists() is False
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["status"] == "not_started"
    assert state_payload["input_paths"] == []
    assert state_payload["output_paths"] == []
    assert state_payload["artifact_paths"] == []
    assert state_payload["metadata"] == {}
    assert state_payload["resume_checkpoint"] is None


def test_ensure_default_operation_state_creates_zero_character_discovery_metadata(tmp_path) -> None:
    """
    @brief      Verify first Characters page access creates zero-valued discovery metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("DefaultCharacterStateRuntime", tmp_path)

    state_path = operation_runtime_service.ensure_default_operation_state(project_root, "character_discovery")

    assert state_path == project_root / config.CHARACTER_DISCOVERY_STATE_FILE_NAME
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["status"] == "not_started"
    assert state_payload["progress_current"] == 0
    assert state_payload["progress_total"] == 0
    assert state_payload["output_paths"] == []
    assert state_payload["artifact_paths"] == []
    assert state_payload["metadata"]["source_chunk_count"] == 0
    assert state_payload["metadata"]["character_count"] == 0
    assert state_payload["metadata"]["analyzed_window_count"] == 0
    assert state_payload["metadata"]["merged_candidate_count"] == 0
    assert state_payload["metadata"]["window_size"] == 0
    assert state_payload["metadata"]["window_overlap"] == 0
    assert state_payload["metadata"]["warnings"] == []
    assert state_payload["resume_checkpoint"] is None


def test_ensure_default_operation_state_creates_zero_audio_blocks_metadata(tmp_path) -> None:
    """
    @brief      Verify first Audio Blocks page access creates zero-valued generation metadata.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-27
    @version    0.1.0
    """
    project_root, _manifest = project_workspace_service.create_project("DefaultAudioBlocksStateRuntime", tmp_path)

    state_path = operation_runtime_service.ensure_default_operation_state(project_root, "audio_blocks")

    assert state_path == project_root / config.AUDIO_BLOCKS_STATE_FILE_NAME
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["status"] == "not_started"
    assert state_payload["progress_current"] == 0
    assert state_payload["progress_total"] == 0
    assert state_payload["output_paths"] == []
    assert state_payload["artifact_paths"] == []
    assert state_payload["metadata"]["voice_language"] == ""
    assert state_payload["metadata"]["speech_block_count"] == 0
    assert state_payload["metadata"]["generated_block_count"] == 0
    assert state_payload["metadata"]["approved_block_count"] == 0
    assert state_payload["metadata"]["clone_profile_count"] == 0
    assert state_payload["metadata"]["prompt_count"] == 0
    assert state_payload["metadata"]["reused_prompt_count"] == 0
    assert state_payload["metadata"]["regenerated_prompt_count"] == 0
    assert state_payload["metadata"]["current_phase"] == ""
    assert state_payload["metadata"]["current_block_id"] == ""
    assert state_payload["metadata"]["model_token_budget"] == 0
    assert state_payload["metadata"]["model_audio_seconds_budget"] == 0.0
    assert state_payload["resume_checkpoint"] is None


# END OF FILE
