#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file character_voices_ui_controller.py
@brief Character Voices page UI controller for AudioMancer.
@details Handles character-voices target inspection, prompt maintenance, Qwen3-
         backed character sample generation, narrator or character preview
         playback, and page-entry narrator-sample warnings.
@author Eng. Dan Dumitru Pasare
@date 2026-04-21
@version 1.9.0
"""

# IMPORTS

from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QMessageBox

from audiomancer import config
from audiomancer.services import (
    character_voices_service,
    narrator_definition_service,
    operation_runtime_service,
    project_workspace_service,
    ui_state_service,
    voiceweaver_runtime_service,
)
from audiomancer.ui.controllers import (
    audio_blocks_ui_controller,
    misc_ui_controller,
    operation_runner_controller,
    tts_runtime_ui_support,
)

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow

settings_service = tts_runtime_ui_support.settings_service


def handle_page_activated(window: "MainWindow") -> None:
    """
    @brief      Handle page-entry side effects for the Character Voices workflow.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    _sync_manifest_stage(window)
    if window._character_voices_missing_narrator_popup_shown:
        return
    if not window._character_voices_page._targets:  # noqa: SLF001
        return
    narrator_selected = any(
        str(target.get("target_kind", "")).strip() == character_voices_service.TARGET_KIND_NARRATOR
        for target in window._character_voices_page._targets  # noqa: SLF001
    )
    if narrator_selected and not character_voices_service.selected_narrator_sample_exists(window._current_project_root):
        current_language = ui_state_service.current_language_from_settings(window._settings_payload)
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.character_voices_missing_narrator_sample_title", current_language),
            ui_state_service.translate("dialog.character_voices_missing_narrator_sample_message", current_language),
        )
        window._character_voices_missing_narrator_popup_shown = True


def handle_selection_change_requested(window: "MainWindow", target_id: object) -> None:
    """
    @brief      Switch the inspected character-voices target without changing persisted prompt or sample state.
    @param[in]  window Main application window.
    @param[in]  target_id Requested character-voices target identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    normalized_target_id = None if target_id in (None, "") else str(target_id)
    window._character_voices_inspected_target_id = normalized_target_id
    window.show_project_state(window._current_project_root, window._current_manifest)


def handle_voice_language_change_requested(window: "MainWindow", voice_language: object) -> None:
    """
    @brief      Persist one character-voices voice language selection and refresh the page state.
    @param[in]  window Main application window.
    @param[in]  voice_language Requested character-voices voice language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    1.4.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    previous_voice_language = character_voices_service.load_selected_voice_language(window._current_project_root)
    requested_voice_language = narrator_definition_service.narrator_language_code(voice_language)
    if (
        previous_voice_language != requested_voice_language
        and not audio_blocks_ui_controller.confirm_global_voice_settings_invalidation(window, current_language)
    ):
        return
    persisted_voice_language = character_voices_service.save_selected_voice_language(
        window._current_project_root,
        voice_language,
    )
    if previous_voice_language != persisted_voice_language:
        audio_blocks_ui_controller.invalidate_all_audio_blocks_after_voice_settings_change(window)
        window.show_project_state(
            window._current_project_root,
            project_workspace_service.load_manifest(window._current_project_root),
        )
        return
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
    _sync_manifest_stage(window)


def handle_reset_prompt_requested(window: "MainWindow", target_id: str) -> None:
    """
    @brief      Reset one editable character prompt to the derived default prompt and refresh the page state.
    @param[in]  window Main application window.
    @param[in]  target_id Requested character-voices target identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    target_payload = character_voices_service.voice_target_by_id(window._current_project_root, target_id)
    if target_payload is None:
        return
    if not audio_blocks_ui_controller.confirm_single_voice_target_invalidation(window, current_language):
        return
    _stop_preview_playback(window)
    character_voices_service.reset_target_prompt(
        window._current_project_root,
        target_id,
        str(target_payload.get("default_prompt_text", "")).strip(),
    )
    window._character_voices_inspected_target_id = target_id
    window.show_project_state(window._current_project_root, window._current_manifest)
    _sync_manifest_stage(window)
    audio_blocks_ui_controller.invalidate_audio_blocks_for_voice_targets(window, (target_id,))
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.character_voices_prompt_reset", current_language),
    )


def handle_edit_prompt_requested(window: "MainWindow", target_id: str) -> None:
    """
    @brief      Confirm character-voices prompt edit mode and clear the old target sample before editing.
    @param[in]  window Main application window.
    @param[in]  target_id Selected character-voices target identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.4.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None:
        return
    if not audio_blocks_ui_controller.confirm_single_voice_target_invalidation(window, current_language):
        return
    if not _confirm_prompt_edit(window, current_language):
        return
    _stop_preview_playback(window)
    try:
        character_voices_service.begin_target_prompt_edit(window._current_project_root, target_id)
    except ValueError:
        return
    window._character_voices_inspected_target_id = target_id
    _sync_manifest_stage(window)
    audio_blocks_ui_controller.invalidate_audio_blocks_for_voice_targets(window, (target_id,))
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
    window._character_voices_page.begin_edit_mode()


def handle_save_prompt_requested(window: "MainWindow", target_payload: dict[str, object]) -> None:
    """
    @brief      Validate and persist one editable character-voices target prompt change.
    @param[in]  window Main application window.
    @param[in]  target_payload Updated character-voices target payload from the page.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.3.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    try:
        updated_target = character_voices_service.save_target_prompt(
            window._current_project_root,
            str(target_payload.get("target_id", "")),
            str(target_payload.get("prompt_text", "")),
            str(target_payload.get("preview_text", "")),
        )
    except ValueError as error:
        if str(error) == "empty_prompt":
            QMessageBox.warning(
                window,
                ui_state_service.translate("dialog.project_error_title", current_language),
                ui_state_service.translate("character_voices.error_missing_prompt", current_language),
            )
        elif str(error) == "empty_preview_text":
            QMessageBox.warning(
                window,
                ui_state_service.translate("dialog.project_error_title", current_language),
                ui_state_service.translate("character_voices.error_missing_preview_text", current_language),
            )
        return
    window._character_voices_inspected_target_id = str(updated_target.get("target_id", "")).strip()
    window.show_project_state(window._current_project_root, window._current_manifest)
    _sync_manifest_stage(window)
    audio_blocks_ui_controller.invalidate_audio_blocks_for_voice_targets(
        window,
        (str(updated_target.get("target_id", "")).strip(),),
    )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.character_voices_prompt_saved", current_language),
    )


def handle_generate_sample_requested(window: "MainWindow", target_id: str) -> None:
    """
    @brief      Generate one character-voices sample through VoiceWeaver and persist the returned WAV plus metadata.
    @param[in]  window Main application window.
    @param[in]  target_id Requested character-voices target identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.3.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._active_operation_kind is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_no_active_project", current_language),
        )
        return
    target_payload = character_voices_service.voice_target_by_id(window._current_project_root, target_id)
    if target_payload is None:
        return
    if not _confirm_generate_sample(window, current_language, target_id):
        return
    if not audio_blocks_ui_controller.confirm_single_voice_target_invalidation(window, current_language):
        return
    editor_payload = window._character_voices_page.current_editor_payload()
    voice_language = window._character_voices_page.current_voice_language()
    preview_text = str(editor_payload.get("preview_text", "")).strip()
    if str(editor_payload.get("target_id", "")).strip() != str(target_id).strip():
        preview_text = character_voices_service.effective_target_preview_text(target_payload, voice_language)
    if not preview_text:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("character_voices.error_missing_preview_text", current_language),
        )
        return
    _stop_preview_playback(window)
    settings_payload = dict(window._settings_payload)
    progress_messages = {
        "prepare": ui_state_service.translate("progress.character_voices_sample_prepare", current_language),
        "load_model": ui_state_service.translate("progress.character_voices_sample_load_model", current_language),
        "generate": ui_state_service.translate("progress.character_voices_sample_generate", current_language),
        "download": ui_state_service.translate("progress.character_voices_sample_download", current_language),
        "qwen_capabilities_missing": ui_state_service.translate(
            "character_voices.error_qwen_capabilities_missing",
            current_language,
        ),
        "generation_missing_audio": ui_state_service.translate(
            "character_voices.error_generation_missing_audio",
            current_language,
        ),
    }
    operation_runner_controller.start_threaded_operation(
        window,
        "character_voices_generate_sample",
        ui_state_service.translate("character_voices.generate_sample", current_language),
        progress_messages["prepare"],
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            _generate_and_store_sample(
                project_root,
                settings_payload,
                progress_messages,
                target_payload,
                voice_language,
                preview_text,
                progress_callback,
                cancel_requested,
            )
        ),
        set_busy=lambda is_busy: window._character_voices_page.set_busy(is_busy),
        success_handler=lambda result_payload: _handle_generate_sample_success(
            window,
            result_payload,
            target_id,
            current_language,
        ),
        failure_handler=lambda error: _handle_generate_sample_failure(window, error, current_language),
        cancel_handler=lambda message: _handle_generate_sample_cancelled(window, message, current_language),
        cancellable=False,
    )


def handle_generate_missing_samples_requested(window: "MainWindow") -> None:
    """
    @brief      Regenerate samples for all current character targets.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-01
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._active_operation_kind is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_no_active_project", current_language),
        )
        return
    target_payloads = _current_character_target_payloads(window)
    if not target_payloads:
        return
    if not _confirm_generate_missing_samples(window, current_language, len(target_payloads)):
        return
    if not audio_blocks_ui_controller.confirm_single_voice_target_invalidation(window, current_language):
        return
    _stop_preview_playback(window)
    settings_payload = dict(window._settings_payload)
    voice_language = window._character_voices_page.current_voice_language()
    progress_messages = {
        "prepare": ui_state_service.translate("progress.character_voices_sample_prepare", current_language),
        "load_model": ui_state_service.translate("progress.character_voices_sample_load_model", current_language),
        "generate": ui_state_service.translate("progress.character_voices_sample_generate", current_language),
        "download": ui_state_service.translate("progress.character_voices_sample_download", current_language),
        "batch_prepare": ui_state_service.translate("progress.character_voices_batch_prepare", current_language),
        "batch_target": ui_state_service.translate("progress.character_voices_batch_target", current_language),
        "qwen_capabilities_missing": ui_state_service.translate(
            "character_voices.error_qwen_capabilities_missing",
            current_language,
        ),
        "generation_missing_audio": ui_state_service.translate(
            "character_voices.error_generation_missing_audio",
            current_language,
        ),
    }
    operation_runner_controller.start_threaded_operation(
        window,
        "character_voices_generate_all_samples",
        ui_state_service.translate("character_voices.generate_missing_samples", current_language),
        progress_messages["batch_prepare"],
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            _generate_and_store_character_samples(
                project_root,
                settings_payload,
                progress_messages,
                target_payloads,
                voice_language,
                progress_callback,
                cancel_requested,
            )
        ),
        set_busy=lambda is_busy: window._character_voices_page.set_busy(is_busy),
        success_handler=lambda result_payload: _handle_generate_missing_samples_success(
            window,
            result_payload,
            target_payloads,
            current_language,
        ),
        failure_handler=lambda error: _handle_generate_sample_failure(window, error, current_language),
        cancel_handler=lambda message: _handle_generate_sample_cancelled(window, message, current_language),
        cancellable=True,
    )


def _handle_generate_missing_samples_success(
    window: "MainWindow",
    result_payload: object,
    target_payloads: list[dict[str, object]],
    current_language: str,
) -> None:
    """
    @brief      Refresh Character Voices UI state after successful batch character sample generation.
    @param[in]  window Main application window.
    @param[in]  result_payload Worker result payload.
    @param[in]  target_payloads Batch target payloads.
    @param[in]  current_language Current UI language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-01
    @version    0.2.0
    """
    _ = result_payload
    window._settings_payload = settings_service.load_settings()
    if target_payloads:
        window._character_voices_inspected_target_id = str(target_payloads[-1].get("target_id", "")).strip() or None
    if window._current_project_root is not None:
        window.show_project_state(
            window._current_project_root,
            project_workspace_service.load_manifest(window._current_project_root),
        )
    _sync_manifest_stage(window)
    audio_blocks_ui_controller.invalidate_audio_blocks_for_voice_targets(
        window,
        tuple(str(target_payload.get("target_id", "")).strip() for target_payload in target_payloads),
    )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.character_voices_missing_samples_generated", current_language),
    )


def _handle_generate_sample_success(
    window: "MainWindow",
    result_payload: object,
    target_id: str,
    current_language: str,
) -> None:
    """
    @brief      Refresh Character Voices UI state after successful sample generation.
    @param[in]  window Main application window.
    @param[in]  result_payload Worker result payload.
    @param[in]  target_id Generated character-voices target identifier.
    @param[in]  current_language Current UI language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    _ = result_payload
    window._settings_payload = settings_service.load_settings()
    window._character_voices_inspected_target_id = target_id
    if window._current_project_root is not None:
        window.show_project_state(
            window._current_project_root,
            project_workspace_service.load_manifest(window._current_project_root),
        )
    _sync_manifest_stage(window)
    audio_blocks_ui_controller.invalidate_audio_blocks_for_voice_targets(window, (target_id,))
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.character_voices_sample_generated", current_language),
    )


def _handle_generate_sample_failure(window: "MainWindow", error: Exception, current_language: str) -> None:
    """
    @brief      Refresh Character Voices UI state after failed sample generation.
    @param[in]  window Main application window.
    @param[in]  error Raised operation exception.
    @param[in]  current_language Current UI language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    window._settings_payload = settings_service.load_settings()
    if window._current_project_root is not None:
        window.show_project_state(
            window._current_project_root,
            project_workspace_service.load_manifest(window._current_project_root),
        )
    QMessageBox.warning(
        window,
        ui_state_service.translate("dialog.project_error_title", current_language),
        str(error),
    )


def _handle_generate_sample_cancelled(window: "MainWindow", message: str, current_language: str) -> None:
    """
    @brief      Refresh Character Voices UI state after cancelled sample generation.
    @param[in]  window Main application window.
    @param[in]  message Cancellation message.
    @param[in]  current_language Current UI language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    _ = message
    window._settings_payload = settings_service.load_settings()
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.operation_cancelled", current_language),
    )


def handle_preview_toggle_requested(window: "MainWindow") -> None:
    """
    @brief      Start or stop local playback of the stored character-voices sample for the inspected target.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._character_voices_page._preview_active:  # noqa: SLF001
        _stop_preview_playback(window)
        return
    if window._current_project_root is None:
        return
    current_target_id = window._character_voices_page.current_target_id()
    if current_target_id is None:
        return
    target_payload = character_voices_service.voice_target_by_id(window._current_project_root, current_target_id)
    audio_path = None
    if (
        isinstance(target_payload, dict)
        and str(target_payload.get("target_kind", "")).strip() == character_voices_service.TARGET_KIND_CHARACTER
    ):
        audio_path, _metadata_path = character_voices_service.target_sample_paths(
            window._current_project_root, current_target_id
        )
    else:
        audio_path, _metadata_path = narrator_definition_service.selected_narrator_sample_paths(
            window._current_project_root
        )
    if audio_path is None or not audio_path.is_file():
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("character_voices.error_missing_sample", current_language),
        )
        return
    window._character_voices_audio_player.setSource(QUrl.fromLocalFile(str(audio_path)))
    window._character_voices_page.set_preview_active(True)
    window._character_voices_audio_player.play()


def handle_preview_playback_state_changed(window: "MainWindow") -> None:
    """
    @brief      Refresh the character-voices preview button state after local playback changes.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-20
    @version    1.0.0
    """
    if window._character_voices_audio_player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
        window._character_voices_page.set_preview_active(False)


def _generate_and_store_sample(
    project_root,
    settings_payload: dict[str, object],
    progress_messages: dict[str, str],
    target_payload: dict[str, object],
    voice_language: str,
    preview_text: str,
    progress_callback,
    cancel_requested,
) -> None:
    """
    @brief      Execute the generate and store sample helper.
    @param[in]  project_root Active project root.
    @param[in]  settings_payload Persisted settings snapshot.
    @param[in]  progress_messages Worker-safe progress and error messages.
    @param[in]  target_payload Payload for `target_payload`.
    @param[in]  voice_language Value for `voice_language`.
    @param[in]  preview_text Text value for `preview_text`.
    @param[in]  progress_callback Optional threaded-runner progress callback.
    @param[in]  cancel_requested Optional cooperative cancellation callback.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    _ = cancel_requested
    _emit_sample_progress(
        progress_callback,
        2,
        progress_messages["prepare"],
    )
    probe_result = tts_runtime_ui_support.probe_runtime_and_persist_cache_from_settings(settings_payload)
    if not bool(probe_result.get("success", False)):
        raise RuntimeError(str(probe_result.get("message", "")))
    capability_matrix = dict(probe_result.get("capability_matrix", {}))
    if not bool(capability_matrix.get("minimum_qwen_ready", False)):
        raise RuntimeError(
            progress_messages["qwen_capabilities_missing"].format(
                missing_capabilities=", ".join(capability_matrix.get("missing_qwen_capabilities", [])),
            )
        )
    discovered_models = list(probe_result.get("discovered_models", []))
    generation_request = character_voices_service.voice_target_generation_request(
        target_payload,
        discovered_models,
        voice_language,
    )
    if not bool(generation_request.get("can_generate", False)):
        raise RuntimeError(str(generation_request.get("unavailable_reason", "")))
    character_voices_service.delete_target_sample(
        project_root,
        str(target_payload.get("target_id", "")).strip(),
    )
    base_url = str(settings_payload.get("tts_runtime_base_url", "")).strip()
    runtime_api_key = str(settings_payload.get("tts_runtime_api_key", ""))
    preview_timeout_seconds = tts_runtime_ui_support.preview_timeout_seconds_from_settings(settings_payload)
    model_id = str(generation_request.get("model_id", "")).strip()
    initial_status = voiceweaver_runtime_service.read_status(
        base_url,
        runtime_api_key,
        timeout_seconds=preview_timeout_seconds,
    )
    tts_runtime_ui_support.persist_runtime_status_from_settings(settings_payload, initial_status)
    active_model_id = _active_model_id_from_status(initial_status)
    _emit_sample_progress(
        progress_callback,
        10,
        progress_messages["prepare"],
    )
    if active_model_id != model_id:
        _emit_sample_progress(
            progress_callback,
            25,
            progress_messages["load_model"],
        )
        voiceweaver_runtime_service.load_model(
            base_url,
            runtime_api_key,
            model_id,
            timeout_seconds=preview_timeout_seconds,
        )
        load_status = voiceweaver_runtime_service.wait_for_terminal_operation(
            base_url,
            runtime_api_key,
            progress_callback=lambda status_payload: _update_load_progress(
                progress_callback,
                status_payload,
                progress_messages["load_model"],
            ),
            timeout_seconds=preview_timeout_seconds,
        )
        tts_runtime_ui_support.persist_runtime_status_from_settings(settings_payload, load_status)
        load_operation = load_status.get("operation", {})
        if not isinstance(load_operation, dict) or str(load_operation.get("status", "")).strip().lower() != "completed":
            raise RuntimeError(voiceweaver_runtime_service.operation_failed_message(load_status))
        active_model_id = _active_model_id_from_status(load_status)
        if active_model_id != model_id:
            raise RuntimeError(f"VoiceWeaver did not activate the requested model '{model_id}'.")

    _emit_sample_progress(
        progress_callback,
        35,
        progress_messages["generate"],
    )
    voiceweaver_runtime_service.generate_voice_design(
        base_url,
        runtime_api_key,
        str(generation_request.get("language", voice_language)),
        preview_text,
        str(target_payload.get("prompt_text", "")),
        model_parameters=dict(generation_request.get("model_parameters", {}))
        if isinstance(generation_request.get("model_parameters"), dict)
        else None,
        timeout_seconds=preview_timeout_seconds,
    )
    final_status = voiceweaver_runtime_service.wait_for_terminal_operation(
        base_url,
        runtime_api_key,
        progress_callback=lambda status_payload: _update_generation_progress(
            progress_callback,
            status_payload,
            progress_messages["generate"],
        ),
        timeout_seconds=preview_timeout_seconds,
    )
    tts_runtime_ui_support.persist_runtime_status_from_settings(settings_payload, final_status)
    final_operation = final_status.get("operation", {})
    if not isinstance(final_operation, dict) or str(final_operation.get("status", "")).strip() != "completed":
        raise RuntimeError(voiceweaver_runtime_service.operation_failed_message(final_status))
    final_result = final_status.get("result", {})
    if not isinstance(final_result, dict) or not bool(final_result.get("available", False)):
        raise RuntimeError(progress_messages["generation_missing_audio"])

    _emit_sample_progress(
        progress_callback,
        95,
        progress_messages["download"],
    )
    audio_bytes = voiceweaver_runtime_service.download_generated_voice(
        base_url,
        runtime_api_key,
        timeout_seconds=preview_timeout_seconds,
    )
    character_voices_service.store_target_sample(
        project_root,
        target_payload,
        voice_language,
        preview_text,
        generation_request,
        str(final_result.get("summary", "")),
        audio_bytes,
    )


def _generate_and_store_character_samples(
    project_root,
    settings_payload: dict[str, object],
    progress_messages: dict[str, str],
    target_payloads: list[dict[str, object]],
    voice_language: str,
    progress_callback,
    cancel_requested,
) -> dict[str, object]:
    """
    @brief      Generate samples sequentially for all current character voice targets.
    @param[in]  project_root Active project root.
    @param[in]  settings_payload Persisted settings snapshot.
    @param[in]  progress_messages Worker-safe progress and error messages.
    @param[in]  target_payloads Character target payloads to generate.
    @param[in]  voice_language Selected character-voices voice language.
    @param[in]  progress_callback Optional threaded-runner progress callback.
    @param[in]  cancel_requested Optional cooperative cancellation callback.
    @return     Batch result summary.
    @exception  OperationCancelledError Raised when cancellation is requested between targets.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-01
    @version    0.1.0
    """
    total_count = len(target_payloads)
    if total_count == 0:
        return {"generated_count": 0}
    _emit_sample_progress(progress_callback, 0, progress_messages["batch_prepare"])
    generated_count = 0
    for target_index, target_payload in enumerate(target_payloads, start=1):
        if cancel_requested is not None and cancel_requested():
            raise operation_runtime_service.OperationCancelledError("Character sample batch cancelled.")
        target_name = (
            str(target_payload.get("display_name", "")).strip() or str(target_payload.get("target_id", "")).strip()
        )
        batch_message = progress_messages["batch_target"].format(
            current=target_index,
            total=total_count,
            target_name=target_name,
        )
        preview_text = character_voices_service.effective_target_preview_text(target_payload, voice_language)
        if not preview_text:
            raise RuntimeError(progress_messages["generation_missing_audio"])

        def _emit_current_target_progress(
            _current,
            _total,
            percent,
            message,
            current_target_index=target_index,
            current_batch_message=batch_message,
        ) -> None:
            """
            @brief      Forward one target-local progress update into the batch progress range.
            @param[in]  _current Unused target-local current value.
            @param[in]  _total Unused target-local total value.
            @param[in]  percent Target-local percentage.
            @param[in]  message Target-local progress message.
            @param[in]  current_target_index Bound one-based target index.
            @param[in]  current_batch_message Bound batch target message.
            @return     None.
            @author     Eng. Dan Dumitru Pasare
            @date       2026-05-01
            @version    0.1.0
            """
            _emit_batch_sample_progress(
                progress_callback,
                current_target_index,
                total_count,
                percent,
                current_batch_message,
                message,
            )

        _generate_and_store_sample(
            project_root,
            settings_payload,
            progress_messages,
            target_payload,
            voice_language,
            preview_text,
            _emit_current_target_progress,
            cancel_requested,
        )
        generated_count += 1
        _emit_batch_sample_progress(
            progress_callback,
            target_index,
            total_count,
            100,
            batch_message,
            progress_messages["download"],
        )
    return {"generated_count": generated_count}


def _emit_batch_sample_progress(
    progress_callback,
    target_index: int,
    total_count: int,
    target_percent: int,
    batch_message: str,
    detail_message: str,
) -> None:
    """
    @brief      Emit one aggregate batch progress update for a per-target sample step.
    @param[in]  progress_callback Optional threaded-runner progress callback.
    @param[in]  target_index One-based target index currently being processed.
    @param[in]  total_count Total target count.
    @param[in]  target_percent Current target-local percent.
    @param[in]  batch_message Batch target status text.
    @param[in]  detail_message Current per-target stage text.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-01
    @version    0.1.0
    """
    if progress_callback is None or total_count <= 0:
        return
    bounded_percent = max(0, min(int(target_percent), 100))
    aggregate_percent = int((((target_index - 1) * 100) + bounded_percent) / total_count)
    message = f"{batch_message}\n{detail_message}" if detail_message else batch_message
    progress_callback(target_index, total_count, aggregate_percent, message)


def _update_generation_progress(
    progress_callback,
    status_payload: dict[str, object],
    stage_text: str,
) -> None:
    """
    @brief      Update the generation progress.
    @param[in]  progress_callback Optional threaded-runner progress callback.
    @param[in]  status_payload Payload for `status_payload`.
    @param[in]  stage_text Progress stage text.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    operation_payload = status_payload.get("operation", {})
    if not isinstance(operation_payload, dict):
        return
    percent = int(operation_payload.get("progress_percent", 0))
    mapped_percent = 35 + int(max(0, min(percent, 100)) * 0.55)
    _emit_sample_progress(progress_callback, mapped_percent, stage_text)


def _update_load_progress(
    progress_callback,
    status_payload: dict[str, object],
    stage_text: str,
) -> None:
    """
    @brief      Update the load progress.
    @param[in]  progress_callback Optional threaded-runner progress callback.
    @param[in]  status_payload Payload for `status_payload`.
    @param[in]  stage_text Progress stage text.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.2.0
    """
    operation_payload = status_payload.get("operation", {})
    if not isinstance(operation_payload, dict):
        return
    percent = int(operation_payload.get("progress_percent", 0))
    mapped_percent = 25 + int(max(0, min(percent, 100)) * 0.10)
    _emit_sample_progress(progress_callback, mapped_percent, stage_text)


def _emit_sample_progress(progress_callback, percent: int, message: str) -> None:
    """
    @brief      Emit one sample-generation progress update when a runner callback is available.
    @param[in]  progress_callback Optional threaded-runner progress callback.
    @param[in]  percent Current progress percent.
    @param[in]  message Current operator-facing status text.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    if progress_callback is not None:
        progress_callback(0, 100, percent, message)


def _preview_timeout_seconds(window: "MainWindow") -> int:
    """
    @brief      Resolve the preview timeout seconds.
    @param[in]  window Value for `window`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.2.0
    """
    return tts_runtime_ui_support.preview_timeout_seconds(window)


def _persist_runtime_status(window: "MainWindow", status_payload: dict[str, object]) -> None:
    """
    @brief      Persist the runtime status.
    @param[in]  window Value for `window`.
    @param[in]  status_payload Payload for `status_payload`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.2.0
    """
    tts_runtime_ui_support.persist_runtime_status(window, status_payload)


def _active_model_id_from_status(status_payload: dict[str, object]) -> str | None:
    """
    @brief      Execute the active model id from status helper.
    @param[in]  status_payload Payload for `status_payload`.
    @return     Helper result.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-22
    @version    0.2.0
    """
    return tts_runtime_ui_support.active_model_id_from_status(status_payload)


def _sync_manifest_stage(window: "MainWindow") -> None:
    """
    @brief      Synchronize the manifest stage.
    @param[in]  window Value for `window`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    current_stage = str(window._current_manifest.get("current_stage", "")).strip()
    if current_stage not in config.PROJECT_WORKFLOW_STAGES:
        return
    current_stage_rank = config.PROJECT_WORKFLOW_STAGES.index(current_stage)
    narrator_stage_rank = config.PROJECT_WORKFLOW_STAGES.index("narrator_definition_ready")
    desired_stage = (
        "character_voices_ready"
        if character_voices_service.character_voices_is_ready(
            window._current_project_root,
            list(window._character_voices_page._targets),  # noqa: SLF001
        )
        else "narrator_definition_ready"
    )
    if current_stage_rank < narrator_stage_rank and desired_stage == "narrator_definition_ready":
        return
    if current_stage == desired_stage:
        return
    updated_manifest = dict(window._current_manifest)
    updated_manifest["current_stage"] = desired_stage
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _stop_preview_playback(window: "MainWindow") -> None:
    """
    @brief      Execute the stop preview playback helper.
    @param[in]  window Value for `window`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    window._character_voices_audio_player.stop()
    window._character_voices_audio_player.setSource(QUrl())
    window._character_voices_page.set_preview_active(False)


def _confirm_prompt_edit(window: "MainWindow", language: str) -> bool:
    """
    @brief      Confirm the prompt edit.
    @param[in]  window Value for `window`.
    @param[in]  language Language code.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.character_voices_edit_title", language),
            ui_state_service.translate("dialog.character_voices_edit_message", language),
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_generate_sample(window: "MainWindow", language: str, target_id: str) -> bool:
    """
    @brief      Confirm the generate sample.
    @param[in]  window Value for `window`.
    @param[in]  language Language code.
    @param[in]  target_id Target identifier.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    has_existing_sample = window._current_project_root is not None and character_voices_service.has_target_sample(
        window._current_project_root,
        target_id,
    )
    message_key = (
        "dialog.character_voices_generate_sample_message_replace"
        if has_existing_sample
        else "dialog.character_voices_generate_sample_message"
    )
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.character_voices_generate_sample_title", language),
            ui_state_service.translate(message_key, language),
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_generate_missing_samples(window: "MainWindow", language: str, sample_count: int) -> bool:
    """
    @brief      Confirm batch generation for character targets with missing samples.
    @param[in]  window Main application window.
    @param[in]  language Runtime UI language code.
    @param[in]  sample_count Number of samples that will be generated.
    @return     True when the operator confirms the batch run.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-01
    @version    0.1.0
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.character_voices_generate_missing_samples_title", language),
            ui_state_service.translate("dialog.character_voices_generate_missing_samples_message", language).format(
                sample_count=sample_count
            ),
        )
        == QMessageBox.StandardButton.Yes
    )


def _current_character_target_payloads(window: "MainWindow") -> list[dict[str, object]]:
    """
    @brief      Build the batch target list for all current generatable character targets.
    @param[in]  window Main application window.
    @return     Ordered list of character target payloads allowed to generate samples.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-01
    @version    0.2.0
    """
    return [
        dict(target_payload)
        for target_payload in window._character_voices_page._targets  # noqa: SLF001
        if str(target_payload.get("target_kind", "")).strip() == character_voices_service.TARGET_KIND_CHARACTER
        and bool(target_payload.get("can_generate_sample", False))
    ]


# END OF FILE
