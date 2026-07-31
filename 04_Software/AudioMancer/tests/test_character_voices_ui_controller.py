#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_character_voices_ui_controller.py
@brief Character Voices UI controller tests for AudioMancer.
@details Verifies destructive prompt-edit handling and missing narrator-sample
         page-entry warnings, cooperative cancellation, and non-destructive
         replacement for the Character Voices workflow.
"""

# IMPORTS

from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox
import pytest

from audiomancer.services import (
    character_discovery_service,
    character_voices_service,
    narrator_definition_service,
    operation_runtime_service,
    project_workspace_service,
)
from audiomancer.ui.controllers import character_voices_ui_controller
from audiomancer.ui.main_window import MainWindow


def test_character_voices_ui_controller_edit_prompt_clears_sample_and_enters_edit_mode(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify editing a character prompt deletes the existing sample and enters edit mode.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesControllerEdit")
    target_payload = character_voices_service.voice_target_by_id(project_root, "character_alice")
    assert target_payload is not None
    character_voices_service.store_target_sample(
        project_root,
        target_payload,
        "en",
        "Preview text.",
        {
            "generation_mode": "definition",
            "source_model_id": "qwen-designer",
        },
        "Character sample ready.",
        b"RIFF-character",
    )
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        character_voices_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    character_voices_ui_controller.handle_edit_prompt_requested(window, "character_alice")

    assert character_voices_service.has_target_sample(project_root, "character_alice") is False
    assert window._character_voices_page.is_edit_mode() is True
    assert window._character_voices_page._prompt_edit.isReadOnly() is False
    assert window._character_voices_page._preview_text_edit.isReadOnly() is False


def test_character_voices_ui_controller_edit_prompt_keeps_editors_unlocked(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify pressing Edit Voice Prompt keeps both editors unlocked.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesControllerEditReset")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        character_voices_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    character_voices_ui_controller.handle_edit_prompt_requested(window, "character_alice")

    assert window._character_voices_page.is_edit_mode() is True
    assert window._character_voices_page._prompt_edit.isReadOnly() is False
    assert window._character_voices_page._preview_text_edit.isReadOnly() is False


def test_character_voices_ui_controller_page_activation_warns_when_narrator_sample_is_missing(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify entering the page warns once when the selected Narator Voice sample is missing.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(
        tmp_path,
        "CharacterVoicesControllerWarning",
        store_narrator_sample=False,
    )
    window = _build_window(qtbot, project_root)
    warning_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        character_voices_ui_controller.QMessageBox,
        "warning",
        lambda *args, **kwargs: warning_calls.append(args),
    )

    character_voices_ui_controller.handle_page_activated(window)
    character_voices_ui_controller.handle_page_activated(window)

    assert len(warning_calls) == 1
    assert window._character_voices_missing_narrator_popup_shown is True


def test_character_voices_ui_controller_page_activation_syncs_home_status(qtbot, tmp_path) -> None:
    """
    @brief      Verify page activation updates the Character Voices operation summary for Home.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesHomeStatus")
    target_payload = character_voices_service.voice_target_by_id(project_root, "character_alice")
    assert target_payload is not None
    character_voices_service.store_target_sample(
        project_root,
        target_payload,
        "en",
        "Preview text.",
        {
            "generation_mode": "definition",
            "source_model_id": "qwen-designer",
        },
        "Character sample ready.",
        b"RIFF-character",
    )
    window = _build_window(qtbot, project_root)

    character_voices_ui_controller.handle_page_activated(window)

    manifest = project_workspace_service.load_manifest(project_root)
    operation_summary = manifest["operations"]["character_voices"]
    assert manifest["current_stage"] == "character_voices_ready"
    assert operation_summary["status"] == "completed"
    assert operation_summary["progress_current"] == 2
    assert operation_summary["progress_total"] == 2


def test_character_voices_page_activation_uses_persisted_targets_before_page_load(qtbot, tmp_path) -> None:
    """
    @brief      Verify page activation does not overwrite completed Character Voices progress with an empty UI list.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesEmptyUiSync")
    target_payload = character_voices_service.voice_target_by_id(project_root, "character_alice")
    assert target_payload is not None
    character_voices_service.store_target_sample(
        project_root,
        target_payload,
        "en",
        "Preview text.",
        {
            "generation_mode": "definition",
            "source_model_id": "qwen-designer",
        },
        "Character sample ready.",
        b"RIFF-character",
    )
    manifest = project_workspace_service.load_manifest(project_root)
    manifest["current_stage"] = "character_voices_ready"
    manifest["operations"]["character_voices"] = {
        "status": "completed",
        "progress_current": 2,
        "progress_total": 2,
        "mode": "manual",
        "warning_count": 0,
    }
    project_workspace_service.save_manifest(manifest, project_root)
    window = MainWindow(settings_payload=_default_settings_payload())
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    window._current_page_id = "character_voices"
    window._character_voices_page._targets = []

    character_voices_ui_controller.handle_page_activated(window)

    operation_summary = project_workspace_service.load_manifest(project_root)["operations"]["character_voices"]
    assert operation_summary["status"] == "completed"
    assert operation_summary["progress_current"] == 2
    assert operation_summary["progress_total"] == 2
    assert operation_summary["mode"] == "manual"


def test_character_voices_ui_controller_save_prompt_persists_preview_text(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify Save Voice Prompt persists the edited preview text together with the voice prompt.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesControllerSave")
    window = _build_window(qtbot, project_root)
    monkeypatch.setattr(
        character_voices_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args, **kwargs: None,
    )

    character_voices_ui_controller.handle_save_prompt_requested(
        window,
        {
            "target_id": "character_alice",
            "prompt_text": "Updated prompt.",
            "preview_text": "Preview line one.\nPreview line two.",
        },
    )

    target_payload = character_voices_service.voice_target_by_id(project_root, "character_alice")
    assert target_payload is not None
    assert target_payload["preview_text"] == "Preview line one.\nPreview line two."


def test_character_voices_ui_controller_generate_stops_preview_before_deleting_sample(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify sample regeneration stops preview playback before deleting the old WAV.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesControllerGenerate")
    window = _build_window(qtbot, project_root)
    call_order: list[str] = []
    monkeypatch.setattr(character_voices_ui_controller, "_confirm_generate_sample", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        character_voices_ui_controller.tts_runtime_ui_support,
        "probe_runtime_and_persist_cache_from_settings",
        lambda *_args, **_kwargs: {
            "success": True,
            "discovered_models": [],
            "capability_matrix": {"minimum_qwen_ready": True},
        },
    )
    monkeypatch.setattr(
        character_voices_service,
        "voice_target_generation_request",
        lambda *_args, **_kwargs: {
            "can_generate": True,
            "language": "en",
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "model_parameters": {},
        },
    )
    monkeypatch.setattr(
        character_voices_ui_controller,
        "_stop_preview_playback",
        lambda *_args, **_kwargs: call_order.append("stop"),
    )
    monkeypatch.setattr(
        character_voices_ui_controller.misc_ui_controller,
        "create_progress_dialog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        character_voices_ui_controller.misc_ui_controller,
        "finish_progress_dialog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        character_voices_ui_controller.misc_ui_controller,
        "clear_progress_dialog",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        character_voices_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        character_voices_ui_controller,
        "_generate_and_store_sample",
        lambda *args, **kwargs: call_order.append("delete"),
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
        @brief      Run one threaded-operation worker synchronously for the test.
        @param[in]  window Main window under test.
        @param[in]  operation_kind Operation kind identifier.
        @param[in]  operation_name Operator-facing operation name.
        @param[in]  initial_message Initial progress message.
        @param[in]  worker_callable Worker function supplied by the controller.
        @param[in]  set_busy Busy-state callback.
        @param[in]  success_handler Success callback supplied by the controller.
        @param[in]  failure_handler Failure callback supplied by the controller.
        @param[in]  cancel_handler Cancellation callback supplied by the controller.
        @param[in]  cancellable True when the operation is cancellable.
        @return     None.
        """
        _ = operation_kind
        _ = operation_name
        _ = initial_message
        _ = set_busy
        _ = failure_handler
        _ = cancel_handler
        _ = cancellable
        success_handler(
            worker_callable(
                window._current_project_root,
                dict(window._current_manifest),
                progress_callback=lambda *_args, **_kwargs: None,
                cancel_requested=lambda: False,
            )
        )

    monkeypatch.setattr(
        character_voices_ui_controller.operation_runner_controller,
        "start_threaded_operation",
        _start_threaded_operation,
    )

    character_voices_ui_controller.handle_generate_sample_requested(window, "character_alice")

    assert call_order[:2] == ["stop", "delete"]


def test_character_voices_ui_controller_batch_regenerates_all_current_character_samples(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify batch generation regenerates every current character target.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesControllerBatch")
    character_discovery_service.add_character_profile(project_root, "Bob")
    selected_narrator_id = narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"]
    selected_narrator = narrator_definition_service.profile_by_id(project_root, selected_narrator_id)
    assert selected_narrator is not None
    character_voices_service.sync_voice_plan(
        project_root,
        character_discovery_service.load_character_profiles(project_root),
        selected_narrator,
    )
    bob_target = character_voices_service.voice_target_by_id(project_root, "character_bob")
    assert bob_target is not None
    character_voices_service.store_target_sample(
        project_root,
        bob_target,
        "en",
        "Preview text.",
        {
            "generation_mode": "definition",
            "source_model_id": "qwen-designer",
        },
        "Character sample ready.",
        b"RIFF-bob",
    )
    window = _build_window(qtbot, project_root)
    window._current_page_id = "character_voices"
    window._settings_payload["tts_runtime_probe_succeeded"] = True
    window._settings_payload["tts_runtime_discovered_models"] = [
        {
            "model_id": "qwen-base",
            "backend_name": "qwen3-tts-base",
            "status": "healthy",
            "supported_generation_modes": ["base", "clone"],
        },
        {
            "model_id": "qwen-designer",
            "backend_name": "qwen3-tts-voice-designer",
            "status": "healthy",
            "supported_generation_modes": ["definition", "voice_designer"],
        },
    ]
    window._refresh_character_voices_page_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
    )
    generated_target_ids: list[str] = []
    operation_kinds: list[str] = []
    monkeypatch.setattr(
        character_voices_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        character_voices_ui_controller,
        "_stop_preview_playback",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        character_voices_ui_controller.misc_ui_controller,
        "show_message",
        lambda *_args, **_kwargs: None,
    )

    def _fake_generate_and_store_sample(
        _project_root,
        _settings_payload,
        _progress_messages,
        target_payload,
        _voice_language,
        _preview_text,
        _progress_callback,
        _cancel_requested,
    ) -> None:
        """
        @brief      Capture the generated target id without contacting VoiceWeaver.
        @param[in]  _project_root Unused project root.
        @param[in]  _settings_payload Unused settings payload.
        @param[in]  _progress_messages Unused progress messages.
        @param[in]  target_payload Target payload supplied by the batch worker.
        @param[in]  _voice_language Unused voice language.
        @param[in]  _preview_text Unused preview text.
        @param[in]  _progress_callback Unused progress callback.
        @param[in]  _cancel_requested Unused cancellation callback.
        @return     None.
        """
        generated_target_ids.append(str(target_payload.get("target_id", "")))

    monkeypatch.setattr(
        character_voices_ui_controller,
        "_generate_and_store_sample",
        _fake_generate_and_store_sample,
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
        @brief      Run one threaded-operation worker synchronously for the test.
        @param[in]  window Main window under test.
        @param[in]  operation_kind Operation kind identifier.
        @param[in]  operation_name Operator-facing operation name.
        @param[in]  initial_message Initial progress message.
        @param[in]  worker_callable Worker function supplied by the controller.
        @param[in]  set_busy Busy-state callback.
        @param[in]  success_handler Success callback supplied by the controller.
        @param[in]  failure_handler Failure callback supplied by the controller.
        @param[in]  cancel_handler Cancellation callback supplied by the controller.
        @param[in]  cancellable True when the operation is cancellable.
        @return     None.
        """
        _ = operation_name
        _ = initial_message
        _ = set_busy
        _ = failure_handler
        _ = cancel_handler
        _ = cancellable
        operation_kinds.append(operation_kind)
        success_handler(
            worker_callable(
                window._current_project_root,
                dict(window._current_manifest),
                progress_callback=lambda *_args, **_kwargs: None,
                cancel_requested=lambda: False,
            )
        )

    monkeypatch.setattr(
        character_voices_ui_controller.operation_runner_controller,
        "start_threaded_operation",
        _start_threaded_operation,
    )

    character_voices_ui_controller.handle_generate_missing_samples_requested(window)

    assert operation_kinds == ["character_voices_generate_all_samples"]
    assert generated_target_ids == ["character_alice", "character_bob"]


def test_character_voices_ui_controller_batch_targets_only_generatable_characters() -> None:
    """
    @brief      Verify direct batch generation requests ignore non-generatable character targets.
    @return     None.
    @exception  None
    """
    window = SimpleNamespace(
        _character_voices_page=SimpleNamespace(
            _targets=[
                {
                    "target_id": "narrator",
                    "target_kind": character_voices_service.TARGET_KIND_NARRATOR,
                    "can_generate_sample": False,
                },
                {
                    "target_id": "character_alice",
                    "target_kind": character_voices_service.TARGET_KIND_CHARACTER,
                    "can_generate_sample": False,
                },
                {
                    "target_id": "character_bob",
                    "target_kind": character_voices_service.TARGET_KIND_CHARACTER,
                    "can_generate_sample": True,
                },
            ]
        )
    )

    target_payloads = character_voices_ui_controller._current_character_target_payloads(window)

    assert [target_payload["target_id"] for target_payload in target_payloads] == ["character_bob"]


def test_character_sample_generation_cancel_during_model_load(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-UX-010 wires cancellation into Character Voices runtime polling.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  OperationCancelledError Expected cancellation signal.
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesCancel")
    target_payload = character_voices_service.voice_target_by_id(project_root, "character_alice")
    assert target_payload is not None
    settings_payload = _default_settings_payload()
    observed_cancel_callbacks: list[object] = []
    cancel_checks = iter((False, False, True))
    monkeypatch.setattr(
        character_voices_ui_controller.tts_runtime_ui_support,
        "probe_runtime_and_persist_cache_from_settings",
        lambda *_args, **_kwargs: {
            "success": True,
            "discovered_models": [],
            "capability_matrix": {"minimum_qwen_ready": True},
        },
    )
    monkeypatch.setattr(
        character_voices_service,
        "voice_target_generation_request",
        lambda *_args, **_kwargs: {
            "can_generate": True,
            "language": "en",
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "model_parameters": {},
        },
    )
    monkeypatch.setattr(
        character_voices_ui_controller.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"active_model": "qwen-base"},
    )
    monkeypatch.setattr(
        character_voices_ui_controller.tts_runtime_ui_support,
        "persist_runtime_status_from_settings",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        character_voices_ui_controller.voiceweaver_runtime_service,
        "load_model",
        lambda *_args, **_kwargs: None,
    )

    def _cancel_aware_wait(*_args, **kwargs):
        """
        @brief      Assert runtime polling receives and honors the cancellation callback.
        @return     Completed status when cancellation is not supplied.
        @exception  OperationCancelledError Raised when cancellation is requested.
        """
        observed_cancel_callbacks.append(kwargs.get("cancel_requested"))
        if callable(kwargs.get("cancel_requested")) and kwargs["cancel_requested"]():
            raise operation_runtime_service.OperationCancelledError("Character sample generation cancelled.")
        return {"active_model": "qwen-designer", "operation": {"status": "completed"}}

    monkeypatch.setattr(
        character_voices_ui_controller.voiceweaver_runtime_service,
        "wait_for_terminal_operation",
        _cancel_aware_wait,
    )

    with pytest.raises(operation_runtime_service.OperationCancelledError):
        character_voices_ui_controller._generate_and_store_sample(
            project_root,
            settings_payload,
            _sample_progress_messages(),
            target_payload,
            "en",
            "Preview text.",
            None,
            lambda: next(cancel_checks, True),
        )

    assert observed_cancel_callbacks and callable(observed_cancel_callbacks[0])


def test_failed_character_sample_generation_preserves_existing_sample(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify REQ-UX-010 failed Character Voices generation keeps the previous sample intact.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  RuntimeError Expected runtime generation failure.
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesFailurePreserves")
    target_payload = character_voices_service.voice_target_by_id(project_root, "character_alice")
    assert target_payload is not None
    character_voices_service.store_target_sample(
        project_root,
        target_payload,
        "en",
        "Original preview.",
        {
            "generation_mode": "definition",
            "source_model_id": "qwen-designer",
        },
        "Original sample ready.",
        b"RIFF-original",
    )
    audio_path, _metadata_path = character_voices_service.target_sample_paths(project_root, "character_alice")
    original_metadata = character_voices_service.load_target_sample_metadata(project_root, "character_alice")
    monkeypatch.setattr(
        character_voices_ui_controller.tts_runtime_ui_support,
        "probe_runtime_and_persist_cache_from_settings",
        lambda *_args, **_kwargs: {
            "success": True,
            "discovered_models": [],
            "capability_matrix": {"minimum_qwen_ready": True},
        },
    )
    monkeypatch.setattr(
        character_voices_service,
        "voice_target_generation_request",
        lambda *_args, **_kwargs: {
            "can_generate": True,
            "language": "en",
            "generation_mode": "definition",
            "model_id": "qwen-designer",
            "source_model_id": "qwen-designer",
            "model_parameters": {},
        },
    )
    monkeypatch.setattr(
        character_voices_ui_controller.voiceweaver_runtime_service,
        "read_status",
        lambda *_args, **_kwargs: {"active_model": "qwen-designer"},
    )
    monkeypatch.setattr(
        character_voices_ui_controller.tts_runtime_ui_support,
        "persist_runtime_status_from_settings",
        lambda *_args, **_kwargs: None,
    )

    def _fail_generation(*_args, **_kwargs) -> None:
        """
        @brief      Simulate a runtime generation failure after generation starts.
        @return     None.
        @exception  RuntimeError Always raised.
        """
        raise RuntimeError("runtime failed")

    monkeypatch.setattr(
        character_voices_ui_controller.voiceweaver_runtime_service,
        "generate_voice_design",
        _fail_generation,
    )

    with pytest.raises(RuntimeError, match="runtime failed"):
        character_voices_ui_controller._generate_and_store_sample(
            project_root,
            _default_settings_payload(),
            _sample_progress_messages(),
            target_payload,
            "en",
            "Preview text.",
            None,
            lambda: False,
        )

    assert audio_path.read_bytes() == b"RIFF-original"
    assert character_voices_service.load_target_sample_metadata(project_root, "character_alice") == original_metadata


def test_character_voices_progress_messages_hide_model_id(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify Character Voices generation progress text does not disclose the concrete runtime model id.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    _project_root = _create_project_with_character_and_selected_narrator(
        tmp_path,
        "CharacterVoicesControllerProgressPrivacy",
    )
    _ = qtbot
    observed_updates: list[tuple[int, str]] = []

    character_voices_ui_controller._update_load_progress(
        lambda _current, _total, percent, message: observed_updates.append((percent, message)),
        {
            "operation": {
                "progress_percent": 40,
                "stage": "Loaded Qwen3-TTS-VoiceDesigner model qwen-designer.",
            }
        },
        "Loading voice generation model...",
    )
    character_voices_ui_controller._update_generation_progress(
        lambda _current, _total, percent, message: observed_updates.append((percent, message)),
        {
            "operation": {
                "progress_percent": 50,
                "stage": "Generating with qwen-designer.",
            }
        },
        "Generating character sample...",
    )

    assert observed_updates[0][1] == "Loading voice generation model..."
    assert observed_updates[1][1] == "Generating character sample..."
    assert all("qwen" not in message.casefold() for _percent, message in observed_updates)


def _create_project_with_character_and_selected_narrator(
    tmp_path,
    name: str,
    store_narrator_sample: bool = True,
):
    """
    @brief      Create one project containing a selected narrator and one character target.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  name Project display name.
    @param[in]  store_narrator_sample True when the narrator sample should be stored.
    @return     Created project root path.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project(name, tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-20T12:00:00+00:00",
        "size_bytes": 128,
    }
    manifest["current_stage"] = "narrator_definition_ready"
    manifest["voice_assignment_mode"] = "narrator_and_characters"
    project_workspace_service.save_manifest(manifest, project_root)

    narrator_profile = narrator_definition_service.create_custom_profile(
        project_root,
        "Test Narrator",
        "English",
        "Warm narrator prompt.",
        "Preview text.",
    )
    if store_narrator_sample:
        narrator_definition_service.store_profile_sample(
            project_root,
            narrator_profile,
            "Preview text.",
            {
                "generation_mode": "definition",
                "source_model_id": "qwen-designer",
                "language": "en",
            },
            "Narator voice sample ready.",
            b"RIFF-narrator",
        )
    narrator_definition_service.select_narrator_profile(project_root, narrator_profile["profile_id"], "en")
    character_discovery_service.add_character_profile(project_root, "Alice")
    alice_profile = character_discovery_service.load_character_profiles(project_root)[0]
    character_discovery_service.update_character_profile(
        project_root,
        {
            **dict(alice_profile),
            "canonical_name": "Alice",
            "gender_hint": "female",
            "voice_definition_prompt": "A gentle female voice for Alice.",
        },
    )
    selected_narrator = narrator_definition_service.profile_by_id(project_root, narrator_profile["profile_id"])
    assert selected_narrator is not None
    character_voices_service.sync_voice_plan(
        project_root,
        character_discovery_service.load_character_profiles(project_root),
        selected_narrator,
    )
    return project_root


def _build_window(qtbot, project_root):
    """
    @brief      Build one main window and activate a prepared project.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  project_root Prepared project root path.
    @return     Main window under test.
    @exception  None
    """
    window = MainWindow(settings_payload=_default_settings_payload())
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))
    window._current_page_id = "character_voices"
    window._refresh_character_voices_page_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
    )
    return window


def _sample_progress_messages() -> dict[str, str]:
    """
    @brief      Provide worker-safe Character Voices progress strings for direct helper tests.
    @return     Progress and error message payload.
    @exception  None
    """
    return {
        "prepare": "Preparing character sample...",
        "load_model": "Loading voice generation model...",
        "generate": "Generating character sample...",
        "download": "Downloading character sample...",
        "batch_prepare": "Preparing character samples...",
        "batch_target": "Generating {current}/{total}: {target_name}",
        "qwen_capabilities_missing": "Missing capabilities: {missing_capabilities}.",
        "generation_missing_audio": "Missing generated audio.",
    }


def _default_settings_payload() -> dict[str, object]:
    """
    @brief      Provide the default settings payload test helper.
    @return     None.
    @exception  None
    """
    return {
        "language": "en",
        "play_completion_beep": False,
        "llm_profiles": [],
        "default_ai_cleanup_profile_id": None,
        "default_ai_chunking_profile_id": None,
        "default_ai_translation_profile_id": None,
        "default_speech_blocks_profile_id": None,
        "default_ai_chunking_strategy": "paragraph",
        "default_character_extraction_profile_id": None,
        "tts_runtime_base_url": "http://127.0.0.1:8059",
        "tts_runtime_api_key": "",
        "tts_runtime_probe_succeeded": False,
        "tts_runtime_probe_message": "",
        "tts_runtime_discovered_models": [],
        "tts_runtime_active_model_id": None,
        "tts_runtime_device_diagnostics": {},
        "tts_audio_preview_timeout_seconds": 60,
        "tts_audio_generation_timeout_seconds": 300,
    }


# END OF FILE
