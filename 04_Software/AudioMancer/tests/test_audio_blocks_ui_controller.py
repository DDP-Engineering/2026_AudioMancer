#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_audio_blocks_ui_controller.py
@brief Audio Blocks UI controller tests for AudioMancer.
@details Verifies confirmation gating, destructive rerun reset behavior, and
         manifest advancement after approval of all generated audio blocks.
@author Eng. Dan Dumitru Pasare
@date 2026-04-23
@version 0.3.1
"""

# IMPORTS

import json

from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import character_voices_service, project_workspace_service, speech_blocks_service
from audiomancer.ui.controllers import audio_blocks_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_audio_blocks_ui_controller_requires_confirmation_before_starting(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify Audio Blocks generation stops when the operator declines the confirmation popup.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying valid baseline settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.2.0
    """
    project_root = _create_project(tmp_path, "AudioBlocksControllerConfirm")
    window = _build_window(qtbot, project_root, default_settings_payload)
    monkeypatch.setattr(
        audio_blocks_ui_controller.tts_runtime_ui_support,
        "probe_runtime_and_persist_cache",
        lambda *_args, **_kwargs: {"success": True, "discovered_models": _minimum_qwen_models()},
    )
    monkeypatch.setattr(
        audio_blocks_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )
    start_calls = []
    monkeypatch.setattr(
        audio_blocks_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )

    audio_blocks_ui_controller.handle_start_generation_requested(window)

    assert start_calls == []


def test_audio_blocks_ui_controller_completed_rerun_resets_downstream_before_dispatch(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify completed Audio Blocks reruns reset Audio Blocks and Audio Assembly before dispatch.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying valid baseline settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.3.0
    """
    project_root = _create_project(tmp_path, "AudioBlocksControllerRerun")
    manifest = project_workspace_service.load_manifest(project_root)
    manifest["current_stage"] = "audio_assembly_ready"
    manifest["operations"]["audio_blocks"]["status"] = "completed"
    manifest["operations"]["audio_assembly"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    _seed_audio_blocks_run(project_root, approved=False)
    window = _build_window(qtbot, project_root, default_settings_payload)
    monkeypatch.setattr(
        audio_blocks_ui_controller.tts_runtime_ui_support,
        "probe_runtime_and_persist_cache",
        lambda *_args, **_kwargs: {"success": True, "discovered_models": _minimum_qwen_models()},
    )
    monkeypatch.setattr(
        audio_blocks_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    start_calls = []
    monkeypatch.setattr(
        audio_blocks_ui_controller,
        "_start_operation",
        lambda _window, **kwargs: start_calls.append(kwargs),
    )

    audio_blocks_ui_controller.handle_start_generation_requested(window)

    assert len(start_calls) == 1
    assert window._current_manifest is not None
    assert window._current_manifest["current_stage"] == "speech_blocks_ready"
    assert window._current_manifest["operations"]["audio_blocks"]["status"] == "not_started"
    assert window._current_manifest["operations"]["audio_assembly"]["status"] == "not_started"
    assert not (project_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME).exists()
    assert not (project_root / config.AUDIO_BLOCKS_STATE_FILE_NAME).exists()
    assert not (project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "0001_000001_narrator.wav").exists()


def test_audio_blocks_ui_controller_approve_all_advances_manifest_after_full_approval(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify Approve All marks all generated blocks approved and
                advances the project stage to Audio Blocks ready.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying valid baseline settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.1
    """
    project_root = _create_project(tmp_path, "AudioBlocksControllerApproveAll")
    _seed_audio_blocks_run(project_root, approved=False)
    window = _build_window(qtbot, project_root, default_settings_payload)
    monkeypatch.setattr(
        audio_blocks_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args, **kwargs: None,
    )

    audio_blocks_ui_controller.handle_approve_all_requested(window)

    updated_manifest = project_workspace_service.load_manifest(project_root)
    report = json.loads(
        (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_REPORT_FILE_NAME).read_text(
            encoding="utf-8"
        )
    )
    output_payload = json.loads(
        (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert updated_manifest["current_stage"] == "audio_blocks_ready"
    assert updated_manifest["operations"]["audio_blocks"]["status"] == "completed"
    assert report["audio_blocks_stage_status"] == "completed"
    assert all(bool(block["approved"]) for block in output_payload)


def test_audio_blocks_ui_controller_preserves_selected_block_after_regeneration_refresh(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify regeneration refresh restores the requested speech-block row selection.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying valid baseline settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    project_root = _create_project(tmp_path, "AudioBlocksControllerPreserveRegenerate")
    _seed_audio_blocks_run(project_root, approved=False)
    window = _build_window(qtbot, project_root, default_settings_payload)
    window._audio_blocks_page.select_block_id("0001-000002")
    monkeypatch.setattr(audio_blocks_ui_controller.misc_ui_controller, "show_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        audio_blocks_ui_controller,
        "_sync_manifest_after_audio_blocks_update",
        lambda active_window: active_window._audio_blocks_page.select_block_id("0001-000001"),
    )

    def _start_threaded_operation(
        window,
        operation_kind,
        operation_name,
        initial_message,
        worker_callable,
        set_busy,
        success_handler,
        failure_handler,
        cancel_handler,
        cancellable=True,
    ):
        """
        @brief      Synchronously invoke the success handler for operation-start testing.
        @return     None.
        @exception  None
        @author     Eng. Dan Dumitru Pasare
        @date       2026-04-25
        @version    0.1.0
        """
        _ = window
        _ = operation_kind
        _ = operation_name
        _ = initial_message
        _ = worker_callable
        _ = set_busy
        _ = failure_handler
        _ = cancel_handler
        _ = cancellable
        success_handler(None)

    monkeypatch.setattr(
        audio_blocks_ui_controller.operation_runner_controller,
        "start_threaded_operation",
        _start_threaded_operation,
    )

    audio_blocks_ui_controller._start_operation(  # noqa: SLF001
        window,
        operation_name="Regenerate",
        initial_message="Regenerating",
        worker_callable=lambda *_args, **_kwargs: None,
        success_message_key="status.audio_block_regenerated",
        preserved_block_id="0001-000002",
    )

    assert window._audio_blocks_page.selected_block_id() == "0001-000002"


def test_audio_blocks_ui_controller_preserves_selected_block_after_selected_playback_stop(
    qtbot, tmp_path, default_settings_payload
) -> None:
    """
    @brief      Verify stopping selected-block playback keeps the played row selected.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying valid baseline settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    project_root = _create_project(tmp_path, "AudioBlocksControllerPreservePlayback")
    _seed_audio_blocks_run(project_root, approved=False)
    window = _build_window(qtbot, project_root, default_settings_payload)
    window._audio_blocks_page.select_block_id("0001-000001")
    window._audio_blocks_playback_mode = "selected"
    window._audio_blocks_playback_block_ids = ["0001-000002"]
    window._audio_blocks_playback_index = 0

    audio_blocks_ui_controller.handle_selected_playback_toggle_requested(window, "0001-000002")

    assert window._audio_blocks_page.selected_block_id() == "0001-000002"


def _create_project(tmp_path, name: str):
    """
    @brief      Create one project fixture with Speech Blocks ready for Audio Blocks.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  name Project display name.
    @return     Project root folder.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-23T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["original_language"] = "en"
    manifest["current_stage"] = "speech_blocks_ready"
    manifest["operations"]["chunking"]["status"] = "completed"
    manifest["operations"]["chunking"]["output_paths"] = [
        f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.CHUNK_ARTIFACT_FILE_NAME}"
    ]
    manifest["operations"]["speech_blocks"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, project_root)
    character_voices_service.save_selected_voice_language(project_root, "en")
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "sequence_index": 1,
                    "chapter_label": None,
                    "text": 'Narration one. "Hello there."',
                    "source_start_line": 1,
                    "source_end_line": 1,
                    "chunking_mode": "deterministic",
                    "semantic_strategy": None,
                    "scene_note": None,
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH / config.SPEECH_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(
            [
                {
                    "speech_block_id": "0001-000001",
                    "sequence_index": 1,
                    "chunk_id": "chunk-0001",
                    "source_language": "en",
                    "speaker_kind": speech_blocks_service.SPEAKER_KIND_NARRATOR,
                    "speaker_id": "narrator",
                    "speaker_display_name": "Narrator",
                    "content_kind": speech_blocks_service.CONTENT_KIND_NARRATION,
                    "text": "Narration one.",
                    "warning_flags": [],
                },
                {
                    "speech_block_id": "0001-000002",
                    "sequence_index": 2,
                    "chunk_id": "chunk-0001",
                    "source_language": "en",
                    "speaker_kind": speech_blocks_service.SPEAKER_KIND_CHARACTER,
                    "speaker_id": "alice",
                    "speaker_display_name": "Alice",
                    "content_kind": speech_blocks_service.CONTENT_KIND_DIALOGUE,
                    "text": "Hello there.",
                    "warning_flags": [],
                },
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root


def _build_window(qtbot, project_root, default_settings_payload):
    """
    @brief      Build a main window fixture with minimum TTS runtime capabilities.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  project_root Active project root folder.
    @param[in]  default_settings_payload Baseline settings payload fixture.
    @return     Initialized main window.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    settings_payload = dict(default_settings_payload)
    settings_payload["tts_runtime_discovered_models"] = _minimum_qwen_models()
    window = MainWindow(settings_payload=settings_payload)
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    return window


def _seed_audio_blocks_run(project_root, approved: bool) -> None:
    """
    @brief      Write one generated Audio Blocks run fixture.
    @param[in]  project_root Active project root folder.
    @param[in]  approved True when all generated blocks should be approved.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    audio_root = project_root / config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH
    generated_root = audio_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME
    generated_root.mkdir(parents=True, exist_ok=True)
    output_payload = [
        {
            "speech_block_id": "0001-000001",
            "sequence_index": 1,
            "chunk_id": "chunk-0001",
            "speaker_id": "narrator",
            "speaker_display_name": "Narrator",
            "normalized_speaker_name": "narrator",
            "text": "Narration one.",
            "voice_target_id": "narrator",
            "voice_source_kind": "narrator_sample",
            "audio_relative_path": "audio_blocks/0001_000001_narrator.wav",
            "metadata_relative_path": "audio_blocks/0001_000001_narrator.json",
            "generated": True,
            "approved": approved,
            "approved_at": "2026-04-23T12:10:00+00:00" if approved else None,
            "generated_at": "2026-04-23T12:09:00+00:00",
            "runtime_result_summary": "Narrator ready.",
            "warning_flags": [],
        },
        {
            "speech_block_id": "0001-000002",
            "sequence_index": 2,
            "chunk_id": "chunk-0001",
            "speaker_id": "alice",
            "speaker_display_name": "Alice",
            "normalized_speaker_name": "alice",
            "text": "Hello there.",
            "voice_target_id": "character_alice",
            "voice_source_kind": "character_sample",
            "audio_relative_path": "audio_blocks/0001_000002_alice.wav",
            "metadata_relative_path": "audio_blocks/0001_000002_alice.json",
            "generated": True,
            "approved": approved,
            "approved_at": "2026-04-23T12:10:00+00:00" if approved else None,
            "generated_at": "2026-04-23T12:09:00+00:00",
            "runtime_result_summary": "Alice ready.",
            "warning_flags": [],
        },
    ]
    (audio_root / "artifact.txt").write_text("stale", encoding="utf-8")
    (generated_root / "0001_000001_narrator.wav").write_bytes(b"RIFF-1")
    (generated_root / "0001_000001_narrator.json").write_text("{}\n", encoding="utf-8")
    (generated_root / "0001_000002_alice.wav").write_bytes(b"RIFF-2")
    (generated_root / "0001_000002_alice.json").write_text("{}\n", encoding="utf-8")
    (audio_root / config.AUDIO_BLOCKS_OUTPUT_FILE_NAME).write_text(
        json.dumps(output_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (audio_root / config.AUDIO_BLOCKS_REPORT_FILE_NAME).write_text(
        json.dumps(
            {
                "voice_language": "en",
                "audio_blocks_stage_status": "completed" if approved else "in_progress",
                "generated_block_count": 2,
                "approved_block_count": 2 if approved else 0,
                "total_block_count": 2,
                "warning_count": 0,
                "warnings": [],
                "updated_at": "2026-04-23T12:10:00+00:00",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (audio_root / config.AUDIO_BLOCKS_STATE_FILE_NAME).write_text(
        json.dumps(
            {
                "folder_relative_path": config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH,
                "status": "completed",
                "input_paths": [
                    f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.SPEECH_BLOCKS_OUTPUT_FILE_NAME}"
                ],
                "output_paths": [
                    f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.AUDIO_BLOCKS_OUTPUT_FILE_NAME}"
                ],
                "artifact_paths": [
                    f"{config.PROJECT_ROOT_ARTIFACT_RELATIVE_PATH}/{config.AUDIO_BLOCKS_REPORT_FILE_NAME}"
                ],
                "progress_current": 2,
                "progress_total": 2,
                "mode": "tts_generation",
                "started_at": "2026-04-23T12:00:00+00:00",
                "completed_at": "2026-04-23T12:10:00+00:00",
                "updated_at": "2026-04-23T12:10:00+00:00",
                "warning_count": 0,
                "metadata": {
                    "voice_language": "en",
                    "input_fingerprint": "stable",
                    "speech_block_count": 2,
                    "generated_block_count": 2,
                    "approved_block_count": 2 if approved else 0,
                    "clone_profile_count": 2,
                    "current_phase": "generate_blocks",
                    "current_block_id": None,
                },
                "resume_checkpoint": {"next_profile_index": 2, "next_speech_block_index": 2},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _minimum_qwen_models() -> list[dict[str, object]]:
    """
    @brief      Return a minimal healthy Qwen model list for controller tests.
    @return     Runtime model metadata list.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    return [
        {
            "model_id": "qwen-base",
            "backend_name": "qwen3-tts-base",
            "status": "healthy",
            "supported_generation_modes": ["clone"],
            "supported_presets": [],
        }
    ]


# END OF FILE
