#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file narator_voice_ui_controller.py
@brief Narator Voice page UI controller for AudioMancer.
@details Handles narrator profile inspection, AI text-only profile suggestion
         generation, explicit narrator selection, Qwen3-backed sample generation,
         sample preview playback, and project-local narrator profile editing.
@author Eng. Dan Dumitru Pasare
@date 2026-04-18
@version 3.20.0
"""

# IMPORTS

from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from audiomancer import config
from audiomancer.services import (
    character_voices_service,
    narrator_definition_service,
    narrator_profile_generation_service,
    project_workspace_service,
    tts_budget_service,
    ui_state_service,
    voice_sample_import_service,
    voiceweaver_runtime_service,
)
from audiomancer.services.operation_runtime_service import raise_if_cancelled
from audiomancer.ui.controllers import (
    audio_blocks_ui_controller,
    misc_ui_controller,
    operation_runner_controller,
    tts_runtime_ui_support,
    workflow_controller_service,
)

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow

settings_service = tts_runtime_ui_support.settings_service


def handle_selection_change_requested(window: "MainWindow", target_profile_id: object) -> None:
    """
    @brief      Switch the inspected narrator profile without changing the selected narator_voice.
    @param[in]  window Main application window.
    @param[in]  target_profile_id Requested narrator-profile identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.5.0
    """
    profile_id = None if target_profile_id in (None, "") else str(target_profile_id)
    window._narator_voice_inspected_profile_id = profile_id
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    window._refresh_narator_voice_page_state(  # noqa: SLF001
        window._current_project_root,
        window._current_manifest,
        current_language,
    )


def handle_create_profile_requested(
    window: "MainWindow",
    profile_payload: dict[str, object],
) -> None:
    """
    @brief      Prompt for one new custom profile name and persist the new narrator profile.
    @param[in]  window Main application window.
    @param[in]  profile_payload Current editor payload used as the custom-profile base.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.5.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None:
        return
    existing_profiles = narrator_definition_service.load_profiles(window._current_project_root)
    proposed_name, accepted = QInputDialog.getText(
        window,
        ui_state_service.translate("dialog.narator_voice_create_title", current_language),
        ui_state_service.translate("dialog.narator_voice_create_prompt", current_language),
        text=str(profile_payload.get("display_name", "")).strip(),
    )
    if not accepted:
        return
    try:
        normalized_name = narrator_definition_service.validate_profile_name(existing_profiles, proposed_name)
    except ValueError as error:
        _show_name_validation_error(window, current_language, str(error))
        return
    created_profile = narrator_definition_service.create_custom_profile(
        window._current_project_root,
        normalized_name,
        str(profile_payload.get("language", narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE)),
        str(profile_payload.get("prompt_text", "")),
        str(profile_payload.get("preview_text", narrator_definition_service.DEFAULT_PREVIEW_TEXT)),
    )
    window._narator_voice_inspected_profile_id = str(created_profile.get("profile_id", "")).strip()
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.narator_voice_profile_created", current_language),
    )


def handle_edit_profile_requested(window: "MainWindow", profile_id: str) -> None:
    """
    @brief      Confirm narrator-profile edit mode and clear the old sample before editing.
    @param[in]  window Main application window.
    @param[in]  profile_id Selected narrator-profile identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.3.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None:
        return
    selected_profile_id = _selected_profile_id(window)
    if selected_profile_id == profile_id and not audio_blocks_ui_controller.confirm_narrator_voice_invalidation(
        window,
        current_language,
    ):
        return
    if not _confirm_profile_edit(window, current_language):
        return
    _stop_preview_playback(window)
    progress_callback = _start_narator_voice_change_progress(
        window,
        current_language,
        selected_profile_id == profile_id,
        "narator_voice.edit_profile",
    )
    try:
        _update_narator_voice_change_progress(progress_callback, 30, "progress.narator_voice_change_profile")
        narrator_definition_service.begin_profile_edit(window._current_project_root, profile_id)
        window._narator_voice_inspected_profile_id = profile_id
        selected_state = narrator_definition_service.load_selected_profile_state(window._current_project_root)
        _sync_manifest_summary(
            window,
            str(selected_state.get("selected_profile_id", "") or "").strip() or None,
            str(selected_state.get("selected_language", "") or "").strip(),
        )
        if selected_profile_id == profile_id:
            audio_blocks_ui_controller.invalidate_audio_blocks_for_voice_targets(
                window,
                (character_voices_service.TARGET_ID_NARRATOR,),
                collect_preserved_paths=False,
                progress_callback=progress_callback,
            )
        window._narator_voice_inspected_profile_id = profile_id
        window._current_manifest = project_workspace_service.load_manifest(window._current_project_root)
        _update_narator_voice_change_progress(progress_callback, 95, "progress.narator_voice_change_refresh")
        window._refresh_narator_voice_page_state(  # noqa: SLF001
            window._current_project_root,
            window._current_manifest,
            current_language,
        )
        window._narator_voice_page.begin_edit_mode()
    except ValueError as error:
        if str(error) == "readonly_profile":
            QMessageBox.warning(
                window,
                ui_state_service.translate("dialog.project_error_title", current_language),
                ui_state_service.translate("narator_voice.error_readonly_profile", current_language),
            )
        return
    finally:
        if progress_callback is not None:
            _finish_narator_voice_change_progress(window)


def handle_save_profile_requested(
    window: "MainWindow",
    profile_payload: dict[str, object],
) -> None:
    """
    @brief      Validate and persist one editable narrator-profile change.
    @param[in]  window Main application window.
    @param[in]  profile_payload Updated narrator-profile payload from the page.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.6.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None:
        return
    selected_profile_id = _selected_profile_id(window)
    existing_profiles = narrator_definition_service.load_profiles(window._current_project_root)
    try:
        normalized_name = narrator_definition_service.validate_profile_name(
            existing_profiles,
            profile_payload.get("display_name", ""),
            exclude_profile_id=str(profile_payload.get("profile_id", "")),
        )
    except ValueError as error:
        _show_name_validation_error(window, current_language, str(error))
        return
    progress_callback = _start_narator_voice_change_progress(
        window,
        current_language,
        selected_profile_id == str(profile_payload.get("profile_id", "")).strip(),
        "narator_voice.save_profile",
    )
    try:
        _update_narator_voice_change_progress(progress_callback, 30, "progress.narator_voice_change_profile")
        updated_profile = narrator_definition_service.update_custom_profile(
            window._current_project_root,
            {
                **dict(profile_payload),
                "display_name": normalized_name,
            },
        )
        window._narator_voice_inspected_profile_id = str(updated_profile.get("profile_id", "")).strip()
        _update_narator_voice_change_progress(progress_callback, 45, "progress.narator_voice_change_refresh")
        window.show_project_state(
            window._current_project_root,
            project_workspace_service.load_manifest(window._current_project_root),
        )
        if selected_profile_id == str(updated_profile.get("profile_id", "")).strip():
            audio_blocks_ui_controller.invalidate_audio_blocks_for_voice_targets(
                window,
                (character_voices_service.TARGET_ID_NARRATOR,),
                collect_preserved_paths=False,
                progress_callback=progress_callback,
            )
        misc_ui_controller.show_message(
            window,
            ui_state_service.translate("status.narator_voice_profile_saved", current_language),
        )
    finally:
        if progress_callback is not None:
            _finish_narator_voice_change_progress(window)


def handle_delete_profile_requested(window: "MainWindow", profile_id: str) -> None:
    """
    @brief      Confirm and delete one persisted narrator profile.
    @param[in]  window Main application window.
    @param[in]  profile_id Target narrator-profile identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.4.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None:
        return
    selected_profile_id = _selected_profile_id(window)
    if selected_profile_id == profile_id and not audio_blocks_ui_controller.confirm_narrator_voice_invalidation(
        window,
        current_language,
    ):
        return
    if not _confirm_delete_profile(window, current_language):
        return
    progress_callback = _start_narator_voice_change_progress(
        window,
        current_language,
        selected_profile_id == profile_id,
        "narator_voice.delete_profile",
    )
    try:
        _update_narator_voice_change_progress(progress_callback, 30, "progress.narator_voice_change_profile")
        narrator_definition_service.delete_profile(window._current_project_root, profile_id)
        selected_state = narrator_definition_service.load_selected_profile_state(window._current_project_root)
        window._narator_voice_inspected_profile_id = (
            str(selected_state.get("selected_profile_id", "") or "").strip() or None
        )
        _sync_manifest_summary(
            window,
            window._narator_voice_inspected_profile_id,
            str(selected_state.get("selected_language", "") or "").strip(),
        )
        if selected_profile_id == profile_id:
            audio_blocks_ui_controller.invalidate_audio_blocks_for_voice_targets(
                window,
                (character_voices_service.TARGET_ID_NARRATOR,),
                collect_preserved_paths=False,
                progress_callback=progress_callback,
            )
        misc_ui_controller.show_message(
            window,
            ui_state_service.translate("status.narator_voice_profile_deleted", current_language),
        )
    except ValueError:
        return
    finally:
        if progress_callback is not None:
            _finish_narator_voice_change_progress(window)


def handle_select_profile_requested(window: "MainWindow", profile_id: str) -> None:
    """
    @brief      Persist one explicit narrator selection.
    @param[in]  window Main application window.
    @param[in]  profile_id Requested narrator-profile identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.4.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None or window._current_manifest is None:
        return
    profile_payload = narrator_definition_service.profile_by_id(window._current_project_root, profile_id)
    if profile_payload is None:
        return
    if not audio_blocks_ui_controller.confirm_narrator_voice_invalidation(window, current_language):
        return
    selected_language = (
        str(window._narator_voice_page._current_language).strip()
        or str(  # noqa: SLF001
            profile_payload.get("language", narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE)
        ).strip()
    )
    progress_callback = _start_narator_voice_change_progress(
        window,
        current_language,
        True,
        "narator_voice.select_profile",
    )
    try:
        _update_narator_voice_change_progress(progress_callback, 30, "progress.narator_voice_change_profile")
        narrator_definition_service.select_narrator_profile(
            window._current_project_root,
            profile_id,
            selected_language,
        )
        window._narator_voice_inspected_profile_id = profile_id
        _sync_manifest_summary(window, profile_id, selected_language)
        audio_blocks_ui_controller.invalidate_audio_blocks_for_voice_targets(
            window,
            (character_voices_service.TARGET_ID_NARRATOR,),
            collect_preserved_paths=False,
            progress_callback=progress_callback,
        )
        misc_ui_controller.show_message(
            window,
            ui_state_service.translate("status.narator_voice_profile_selected", current_language),
        )
    finally:
        if progress_callback is not None:
            _finish_narator_voice_change_progress(window)


def handle_generate_sample_requested(window: "MainWindow", profile_id: str) -> None:
    """
    @brief      Generate one narrator sample through VoiceWeaver and persist the returned WAV plus metadata.
    @param[in]  window Main application window.
    @param[in]  profile_id Requested narrator-profile identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.5.0
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
    profile_payload = narrator_definition_service.profile_by_id(window._current_project_root, profile_id)
    if profile_payload is None:
        return
    selected_voice_language = window._narator_voice_page.current_voice_language()
    profile_payload = {**dict(profile_payload), "language": selected_voice_language}
    if not _confirm_generate_sample(window, current_language, profile_id):
        return
    invalidate_audio_blocks = _selected_profile_id(window) == profile_id and (
        audio_blocks_ui_controller.confirm_narrator_voice_invalidation(window, current_language)
    )
    if _selected_profile_id(window) == profile_id and not invalidate_audio_blocks:
        return
    preview_text = _limited_preview_text(
        window._narator_voice_page.current_editor_payload().get("preview_text", ""),
        window._settings_payload,
    ).strip()
    if not preview_text:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("narator_voice.error_missing_preview_text", current_language),
        )
        return
    _stop_preview_playback(window)
    settings_payload = dict(window._settings_payload)
    progress_messages = {
        "prepare": ui_state_service.translate("progress.narator_voice_sample_prepare", current_language),
        "load_model": ui_state_service.translate("progress.narator_voice_sample_load_model", current_language),
        "generate": ui_state_service.translate("progress.narator_voice_sample_generate", current_language),
        "download": ui_state_service.translate("progress.narator_voice_sample_download", current_language),
        "qwen_capabilities_missing": ui_state_service.translate(
            "narator_voice.error_qwen_capabilities_missing",
            current_language,
        ),
        "generation_missing_audio": ui_state_service.translate(
            "narator_voice.error_generation_missing_audio",
            current_language,
        ),
        "preview_text_over_budget": ui_state_service.translate(
            "narator_voice.error_preview_text_over_budget",
            current_language,
        ),
    }
    operation_runner_controller.start_threaded_operation(
        window,
        "narator_voice_generate_sample",
        ui_state_service.translate("narator_voice.generate_sample", current_language),
        progress_messages["prepare"],
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            _generate_and_store_sample(
                project_root,
                settings_payload,
                progress_messages,
                profile_payload,
                preview_text,
                progress_callback,
                cancel_requested,
            )
        ),
        set_busy=lambda is_busy: window._narator_voice_page.set_busy(is_busy),
        success_handler=lambda result_payload: _handle_generate_sample_success(
            window,
            result_payload,
            profile_id,
            invalidate_audio_blocks,
            current_language,
        ),
        failure_handler=lambda error: _handle_generate_sample_failure(window, error, current_language),
        cancel_handler=lambda message: _handle_generate_sample_cancelled(window, message, current_language),
        cancellable=False,
    )


def handle_import_sample_requested(window: "MainWindow", profile_id: str) -> None:
    """
    @brief      Import one operator-provided WAV sample for a narrator profile.
    @param[in]  window Main application window.
    @param[in]  profile_id Requested narrator-profile identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
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
    profile_payload = narrator_definition_service.profile_by_id(window._current_project_root, profile_id)
    if profile_payload is None:
        return
    selected_file, _selected_filter = QFileDialog.getOpenFileName(
        window,
        ui_state_service.translate("dialog.voice_sample_import_title", current_language),
        "",
        ui_state_service.translate("dialog.voice_sample_import_filter", current_language),
    )
    if not selected_file:
        return
    try:
        voice_sample_import_service.validate_imported_wav_sample(selected_file)
    except ValueError as error:
        _show_voice_sample_import_error(window, error, current_language)
        return
    default_sample_text = _current_narrator_import_preview_text(window, profile_payload, profile_id)
    sample_text, accepted = QInputDialog.getMultiLineText(
        window,
        ui_state_service.translate("dialog.voice_sample_text_title", current_language),
        ui_state_service.translate("dialog.voice_sample_text_prompt", current_language),
        default_sample_text,
    )
    if not accepted:
        return
    normalized_sample_text = sample_text.strip()
    if not normalized_sample_text:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("narator_voice.error_missing_preview_text", current_language),
        )
        return
    invalidate_audio_blocks = _selected_profile_id(window) == profile_id and (
        audio_blocks_ui_controller.confirm_narrator_voice_invalidation(window, current_language)
    )
    if _selected_profile_id(window) == profile_id and not invalidate_audio_blocks:
        return
    _stop_preview_playback(window)
    try:
        narrator_definition_service.import_profile_sample(
            window._current_project_root,
            {**dict(profile_payload), "language": window._narator_voice_page.current_voice_language()},
            normalized_sample_text,
            selected_file,
        )
        if _selected_profile_id(window) == profile_id:
            narrator_definition_service.copy_selected_narrator_sample(window._current_project_root, profile_id)
    except ValueError as error:
        _show_voice_sample_import_error(window, error, current_language)
        return
    _handle_import_sample_success(window, profile_id, invalidate_audio_blocks, current_language)


def handle_generate_profiles_requested(window: "MainWindow", profile_id: str) -> None:
    """
    @brief      Run AI-assisted text-only narrator profile generation.
    @param[in]  window Main application window.
    @param[in]  profile_id Selected enabled AI profile identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
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
    selected_profile = workflow_controller_service.resolve_enabled_ai_profile(window._settings_payload, profile_id)
    if selected_profile is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_missing_narrator_generation_profile", current_language),
        )
        return
    if not _confirm_generate_profiles(window, current_language):
        return
    profile_count, accepted = QInputDialog.getInt(
        window,
        ui_state_service.translate("dialog.narator_voice_generate_profiles_title", current_language),
        ui_state_service.translate("dialog.narator_voice_generate_profiles_count_prompt", current_language),
        config.DEFAULT_NARRATOR_PROFILE_GENERATION_COUNT,
        1,
        config.MAX_NARRATOR_PROFILE_GENERATION_COUNT,
        1,
    )
    if not accepted:
        return
    additional_profile_instructions = None
    if _is_resuming_profile_generation(window):
        pass
    else:
        additional_profile_instructions = prompt_ai_narrator_profile_instructions(window, current_language)
        if additional_profile_instructions is None:
            return
    voice_language = window._narator_voice_page.current_voice_language()
    preview_limit = _preview_text_character_limit(window._settings_payload)
    operation_runner_controller.start_threaded_operation(
        window,
        "narrator_definition",
        ui_state_service.translate("narator_voice.generate_profiles", current_language),
        ui_state_service.translate("progress.narator_voice_generate_profiles", current_language),
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            narrator_profile_generation_service.generate_narrator_profiles(
                project_root,
                manifest,
                selected_profile,
                profile_count,
                voice_language,
                preview_limit,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
                additional_profile_instructions=additional_profile_instructions,
            )
        ),
        set_busy=lambda is_busy: window._narator_voice_page.set_busy(is_busy),
        success_handler=lambda result_payload: _handle_generate_profiles_success(window, result_payload),
        failure_handler=lambda error: _handle_generate_profiles_failure(window, error, current_language),
        cancel_handler=lambda message: _handle_generate_profiles_cancelled(window, message, current_language),
    )


def _handle_generate_profiles_success(window: "MainWindow", result_payload: object) -> None:
    """
    @brief      Refresh Narator Voice state after generated profiles are appended.
    @param[in]  window Main application window.
    @param[in]  result_payload Successful generation report payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    report_payload = dict(result_payload) if isinstance(result_payload, dict) else {}
    generated_profile_ids = [
        str(profile_id).strip()
        for profile_id in list(report_payload.get("generated_profile_ids", []))
        if str(profile_id).strip()
    ]
    if generated_profile_ids:
        window._narator_voice_inspected_profile_id = generated_profile_ids[0]
    if window._current_project_root is not None:
        window.show_project_state(
            window._current_project_root,
            project_workspace_service.load_manifest(window._current_project_root),
        )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.narator_voice_profiles_generated", current_language).format(
            generated_count=len(generated_profile_ids),
        ),
    )


def _handle_generate_profiles_failure(window: "MainWindow", error: Exception, current_language: str) -> None:
    """
    @brief      Refresh Narator Voice state after profile generation fails.
    @param[in]  window Main application window.
    @param[in]  error Raised operation exception.
    @param[in]  current_language Current UI language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
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


def _handle_generate_profiles_cancelled(window: "MainWindow", message: str, current_language: str) -> None:
    """
    @brief      Refresh Narator Voice state after profile generation is cancelled.
    @param[in]  window Main application window.
    @param[in]  message Cancellation message.
    @param[in]  current_language Current UI language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    _ = message
    if window._current_project_root is not None:
        window.show_project_state(
            window._current_project_root,
            project_workspace_service.load_manifest(window._current_project_root),
        )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.operation_cancelled", current_language),
    )


def _handle_generate_sample_success(
    window: "MainWindow",
    result_payload: object,
    profile_id: str,
    invalidate_audio_blocks: bool,
    current_language: str,
) -> None:
    """
    @brief      Refresh narrator UI state after successful sample generation.
    @param[in]  window Main application window.
    @param[in]  result_payload Worker result payload.
    @param[in]  profile_id Generated narrator profile identifier.
    @param[in]  invalidate_audio_blocks True when downstream audio blocks must reset.
    @param[in]  current_language Current UI language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.5.0
    """
    _ = result_payload
    window._settings_payload = settings_service.load_settings()
    window._narator_voice_inspected_profile_id = profile_id
    progress_callback = _start_narator_voice_change_progress(
        window,
        current_language,
        invalidate_audio_blocks,
        "narator_voice.generate_sample",
    )
    try:
        if window._current_project_root is not None:
            _update_narator_voice_change_progress(progress_callback, 35, "progress.narator_voice_change_refresh")
            selected_state = narrator_definition_service.load_selected_profile_state(window._current_project_root)
            if str(selected_state.get("selected_profile_id", "") or "").strip() == str(profile_id).strip():
                profile_payload = narrator_definition_service.profile_by_id(window._current_project_root, profile_id)
                selected_language = str(
                    selected_state.get("selected_language")
                    or selected_state.get("language")
                    or (profile_payload or {}).get("language")
                    or narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE
                ).strip()
                _sync_manifest_summary(window, profile_id, selected_language)
            window.show_project_state(
                window._current_project_root,
                project_workspace_service.load_manifest(window._current_project_root),
            )
        if invalidate_audio_blocks:
            audio_blocks_ui_controller.invalidate_audio_blocks_for_voice_targets(
                window,
                (character_voices_service.TARGET_ID_NARRATOR,),
                collect_preserved_paths=False,
                progress_callback=progress_callback,
            )
        misc_ui_controller.show_message(
            window,
            ui_state_service.translate("status.narator_voice_sample_generated", current_language),
        )
    finally:
        if progress_callback is not None:
            _finish_narator_voice_change_progress(window)


def _handle_import_sample_success(
    window: "MainWindow",
    profile_id: str,
    invalidate_audio_blocks: bool,
    current_language: str,
) -> None:
    """
    @brief      Refresh narrator UI state after successful sample import.
    @param[in]  window Main application window.
    @param[in]  profile_id Imported narrator profile identifier.
    @param[in]  invalidate_audio_blocks True when downstream audio blocks must reset.
    @param[in]  current_language Current UI language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    window._settings_payload = settings_service.load_settings()
    window._narator_voice_inspected_profile_id = profile_id
    progress_callback = _start_narator_voice_change_progress(
        window,
        current_language,
        invalidate_audio_blocks,
        "narator_voice.import_sample",
    )
    try:
        if window._current_project_root is not None:
            _update_narator_voice_change_progress(progress_callback, 35, "progress.narator_voice_change_refresh")
            selected_state = narrator_definition_service.load_selected_profile_state(window._current_project_root)
            if str(selected_state.get("selected_profile_id", "") or "").strip() == str(profile_id).strip():
                selected_language = str(
                    selected_state.get("selected_language")
                    or selected_state.get("language")
                    or narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE
                ).strip()
                _sync_manifest_summary(window, profile_id, selected_language)
            window.show_project_state(
                window._current_project_root,
                project_workspace_service.load_manifest(window._current_project_root),
            )
        if invalidate_audio_blocks:
            audio_blocks_ui_controller.invalidate_audio_blocks_for_voice_targets(
                window,
                (character_voices_service.TARGET_ID_NARRATOR,),
                collect_preserved_paths=False,
                progress_callback=progress_callback,
            )
        misc_ui_controller.show_message(
            window,
            ui_state_service.translate("status.narator_voice_sample_imported", current_language),
        )
    finally:
        if progress_callback is not None:
            _finish_narator_voice_change_progress(window)


def _handle_generate_sample_failure(window: "MainWindow", error: Exception, current_language: str) -> None:
    """
    @brief      Refresh narrator UI state after failed sample generation.
    @param[in]  window Main application window.
    @param[in]  error Raised operation exception.
    @param[in]  current_language Current UI language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
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
    @brief      Refresh narrator UI state after cancelled sample generation.
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
    @brief      Start or stop local playback of the stored narrator sample for the inspected profile.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-17
    @version    1.0.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._narator_voice_page._preview_active:  # noqa: SLF001
        _stop_preview_playback(window)
        return
    if window._current_project_root is None:
        return
    current_profile_id = window._narator_voice_page.current_profile_id()
    if current_profile_id is None:
        return
    audio_path, _metadata_path = narrator_definition_service.profile_sample_paths(
        window._current_project_root,
        current_profile_id,
    )
    if not audio_path.is_file():
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("narator_voice.error_missing_sample", current_language),
        )
        return
    window._narator_voice_audio_player.setSource(QUrl.fromLocalFile(str(audio_path)))
    window._narator_voice_page.set_preview_active(True)
    window._narator_voice_audio_player.play()


def handle_preview_playback_state_changed(window: "MainWindow") -> None:
    """
    @brief      Refresh the narrator preview button state after local playback changes.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.1.0
    """
    if window._narator_voice_audio_player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
        window._narator_voice_page.set_preview_active(False)


def _start_narator_voice_change_progress(
    window: "MainWindow",
    language: str,
    show_progress: bool,
    operation_name_key: str,
):
    """
    @brief      Start synchronous Narator Voice change progress when requested.
    @param[in]  window Main application window.
    @param[in]  language Runtime UI language code.
    @param[in]  show_progress True to show progress.
    @param[in]  operation_name_key Runtime UI key for the progress title.
    @return     Progress update callback or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    if not show_progress:
        return None
    window._narator_voice_page.set_busy(True)
    operation_name = ui_state_service.translate(operation_name_key, language)
    initial_message = ui_state_service.translate("progress.narator_voice_change_prepare", language)
    if window._operation_progress_dialog is None:
        misc_ui_controller.create_progress_dialog(
            window,
            operation_name,
            initial_message,
            lambda: None,
            cancellable=False,
        )
    else:
        window._operation_progress_dialog.start(
            operation_name,
            initial_message,
            cancellable=False,
        )
    misc_ui_controller.process_pending_ui_events()

    def _update(percent: int, message_key: str) -> None:
        misc_ui_controller.update_progress_dialog(
            window,
            percent,
            ui_state_service.translate(message_key, language),
        )
        misc_ui_controller.process_pending_ui_events()

    return _update


def _update_narator_voice_change_progress(progress_callback, percent: int, message_key: str) -> None:
    """
    @brief      Update Narator Voice change progress when a progress callback exists.
    @param[in]  progress_callback Optional progress callback.
    @param[in]  percent Progress percentage.
    @param[in]  message_key Runtime UI translation key.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    if progress_callback is not None:
        progress_callback(percent, message_key)


def _finish_narator_voice_change_progress(window: "MainWindow") -> None:
    """
    @brief      Close and clear the synchronous Narator Voice change progress dialog.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    misc_ui_controller.update_progress_dialog(
        window,
        100,
        ui_state_service.translate(
            "progress.narator_voice_change_refresh",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )
    misc_ui_controller.finish_progress_dialog(window)
    misc_ui_controller.clear_progress_dialog(window)
    window._narator_voice_page.set_busy(False)
    misc_ui_controller.process_pending_ui_events()


def _generate_and_store_sample(
    project_root,
    settings_payload: dict[str, object],
    progress_messages: dict[str, str],
    profile_payload: dict[str, object],
    preview_text: str,
    progress_callback,
    cancel_requested,
) -> None:
    """
    @brief      Execute one VoiceWeaver sample-generation flow and persist the returned narrator audio artifacts.
    @param[in]  project_root Active project root.
    @param[in]  settings_payload Persisted settings snapshot.
    @param[in]  progress_messages Worker-safe progress and error messages.
    @param[in]  profile_payload Target narrator-profile payload.
    @param[in]  preview_text Preview text synthesized for the sample.
    @param[in]  progress_callback Optional threaded-runner progress callback.
    @param[in]  cancel_requested Optional cooperative cancellation callback.
    @return     None.
    @exception  RuntimeError Raised when VoiceWeaver fails or does not expose downloadable audio.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-18
    @version    1.5.0
    """
    _emit_sample_progress(
        progress_callback,
        2,
        progress_messages["prepare"],
    )
    probe_result = tts_runtime_ui_support.probe_runtime_and_persist_cache_from_settings(settings_payload)
    if not bool(probe_result.get("success", False)):
        raise RuntimeError(str(probe_result.get("message", "")))
    raise_if_cancelled(cancel_requested)
    capability_matrix = dict(probe_result.get("capability_matrix", {}))
    if not bool(capability_matrix.get("minimum_qwen_ready", False)):
        raise RuntimeError(
            progress_messages["qwen_capabilities_missing"].format(
                missing_capabilities=", ".join(capability_matrix.get("missing_qwen_capabilities", [])),
            )
        )
    discovered_models = list(probe_result.get("discovered_models", []))
    tts_plan = narrator_definition_service.load_tts_plan(project_root, discovered_models)
    generation_request = narrator_definition_service.profile_generation_request(
        profile_payload,
        tts_plan,
        discovered_models,
    )
    budget_payload = tts_budget_service.resolve_cached_tts_budget(discovered_models)
    safe_word_count = tts_budget_service.estimated_safe_word_count(budget_payload)
    preview_word_count = tts_budget_service.estimated_word_count(preview_text)
    if preview_word_count > safe_word_count:
        raise RuntimeError(
            progress_messages["preview_text_over_budget"].format(
                word_count=preview_word_count,
                safe_word_count=safe_word_count,
            )
        )
    if not bool(generation_request.get("can_generate", False)):
        raise RuntimeError(str(generation_request.get("unavailable_reason", "")))
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
        raise_if_cancelled(cancel_requested)
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
            cancel_requested=cancel_requested,
        )
        tts_runtime_ui_support.persist_runtime_status_from_settings(settings_payload, load_status)
        load_operation = load_status.get("operation", {})
        if not isinstance(load_operation, dict) or str(load_operation.get("status", "")).strip().lower() != "completed":
            raise RuntimeError(voiceweaver_runtime_service.operation_failed_message(load_status))
        active_model_id = _active_model_id_from_status(load_status)
        if active_model_id != model_id:
            raise RuntimeError(f"VoiceWeaver did not activate the requested model '{model_id}'.")

    raise_if_cancelled(cancel_requested)
    _emit_sample_progress(
        progress_callback,
        35,
        progress_messages["generate"],
    )
    voiceweaver_runtime_service.generate_voice_design(
        base_url,
        runtime_api_key,
        str(generation_request.get("language", narrator_definition_service.DEFAULT_NARRATOR_LANGUAGE)),
        preview_text,
        str(profile_payload.get("prompt_text", "")),
        model_parameters=dict(generation_request.get("model_parameters", {}))
        if isinstance(generation_request.get("model_parameters"), dict)
        else None,
        supported_languages=list(generation_request.get("supported_languages", []))
        if isinstance(generation_request.get("supported_languages"), list)
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
        cancel_requested=cancel_requested,
    )
    tts_runtime_ui_support.persist_runtime_status_from_settings(settings_payload, final_status)
    final_operation = final_status.get("operation", {})
    if not isinstance(final_operation, dict) or str(final_operation.get("status", "")).strip() != "completed":
        raise RuntimeError(voiceweaver_runtime_service.operation_failed_message(final_status))
    final_result = final_status.get("result", {})
    if not isinstance(final_result, dict) or not bool(final_result.get("available", False)):
        raise RuntimeError(progress_messages["generation_missing_audio"])

    raise_if_cancelled(cancel_requested)
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
    narrator_definition_service.store_profile_sample(
        project_root,
        profile_payload,
        preview_text,
        generation_request,
        str(final_result.get("summary", "")),
        audio_bytes,
    )
    selected_state = narrator_definition_service.load_selected_profile_state(project_root)
    if (
        str(selected_state.get("selected_profile_id", "") or "").strip()
        == str(profile_payload.get("profile_id", "")).strip()
    ):
        narrator_definition_service.copy_selected_narrator_sample(
            project_root,
            str(profile_payload.get("profile_id", "")).strip(),
        )


def _limited_preview_text(preview_text: object, settings_payload: dict[str, object]) -> str:
    """
    @brief      Limit narrator sample preview text using the persisted TTS setting.
    @param[in]  preview_text Candidate preview text.
    @param[in]  settings_payload Current application settings payload.
    @return     Preview text capped at the configured character limit.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    try:
        character_limit = int(
            settings_payload.get(
                "tts_preview_text_character_limit",
                config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT,
            )
        )
    except (TypeError, ValueError):
        character_limit = config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT
    return str(preview_text or "")[: max(character_limit, 1)]


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


def _sync_manifest_summary(
    window: "MainWindow",
    profile_id: str | None,
    selected_language: str,
) -> None:
    """
    @brief      Synchronize manifest narrator summary fields and the selected narrator audio copy.
    @param[in]  window Main application window.
    @param[in]  profile_id Explicitly selected narrator-profile identifier or `None`.
    @param[in]  selected_language Selected narrator language label.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-08
    @version    1.3.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    profile_payload = narrator_definition_service.profile_by_id(window._current_project_root, profile_id)
    updated_manifest = dict(window._current_manifest)
    if profile_payload is None:
        updated_manifest["narrator_profile_name"] = None
        updated_manifest["narrator_language"] = None
        updated_manifest["operations"]["narrator_definition"] = (
            project_workspace_service.project_manifest_operation_summary("narrator_definition")
        )
        narrator_definition_service.clear_selected_narrator_sample(window._current_project_root)
    else:
        updated_manifest["narrator_profile_name"] = (
            narrator_definition_service.display_profile_name(profile_payload) or None
        )
        updated_manifest["narrator_language"] = narrator_definition_service.narrator_language_code(selected_language)
        selected_metadata = None
        profile_id_value = str(profile_payload.get("profile_id", "")).strip()
        if narrator_definition_service.has_profile_sample(
            window._current_project_root,
            profile_id_value,
        ):
            selected_metadata = narrator_definition_service.copy_selected_narrator_sample(
                window._current_project_root,
                profile_id_value,
            )
        else:
            narrator_definition_service.clear_selected_narrator_sample_artifacts(window._current_project_root)
        _ = selected_metadata
        updated_manifest["operations"]["narrator_definition"] = (
            project_workspace_service.project_manifest_operation_summary(
                "narrator_definition",
                {
                    "status": "completed",
                    "progress_current": 1,
                    "progress_total": 1,
                    "mode": "manual",
                    "warning_count": 0,
                },
            )
        )
    updated_manifest["current_stage"] = "narrator_definition_ready"
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
    window._narator_voice_audio_player.stop()
    window._narator_voice_audio_player.setSource(QUrl())
    window._narator_voice_page.set_preview_active(False)


def _confirm_delete_profile(window: "MainWindow", language: str) -> bool:
    """
    @brief      Confirm the delete profile.
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
            ui_state_service.translate("dialog.narator_voice_delete_title", language),
            ui_state_service.translate("dialog.narator_voice_delete_message", language),
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_profile_edit(window: "MainWindow", language: str) -> bool:
    """
    @brief      Confirm the profile edit.
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
            ui_state_service.translate("dialog.narator_voice_edit_title", language),
            ui_state_service.translate("dialog.narator_voice_edit_message", language),
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_generate_sample(window: "MainWindow", language: str, profile_id: str) -> bool:
    """
    @brief      Confirm the generate sample.
    @param[in]  window Value for `window`.
    @param[in]  language Language code.
    @param[in]  profile_id Profile identifier.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    has_existing_sample = window._current_project_root is not None and narrator_definition_service.has_profile_sample(
        window._current_project_root, profile_id
    )
    message_key = (
        "dialog.narator_voice_generate_sample_message_replace"
        if has_existing_sample
        else "dialog.narator_voice_generate_sample_message"
    )
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.narator_voice_generate_sample_title", language),
            ui_state_service.translate(message_key, language),
        )
        == QMessageBox.StandardButton.Yes
    )


def _current_narrator_import_preview_text(
    window: "MainWindow",
    profile_payload: dict[str, object],
    profile_id: str,
) -> str:
    """
    @brief      Resolve the initial transcript text for narrator sample import.
    @param[in]  window Main application window.
    @param[in]  profile_payload Persisted narrator profile payload.
    @param[in]  profile_id Imported profile identifier.
    @return     Initial sample transcript text.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    if str(window._narator_voice_page.current_profile_id() or "").strip() == str(profile_id).strip():
        return str(window._narator_voice_page.current_editor_payload().get("preview_text", "") or "").strip()
    return str(profile_payload.get("preview_text", "") or "").strip()


def _show_voice_sample_import_error(window: "MainWindow", error: ValueError, language: str) -> None:
    """
    @brief      Show one localized voice-sample import validation error.
    @param[in]  window Main application window.
    @param[in]  error Validation exception.
    @param[in]  language Current UI language code.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    message_key = {
        "unsupported_file_type": "voice_sample_import.error_unsupported_file_type",
        "missing_file": "voice_sample_import.error_missing_file",
        "invalid_wav": "voice_sample_import.error_invalid_wav",
        "sample_too_short": "voice_sample_import.error_sample_too_short",
        "sample_silent": "voice_sample_import.error_sample_silent",
        "empty_preview_text": "voice_sample_import.error_empty_sample_text",
        "readonly_target": "voice_sample_import.error_readonly_target",
    }.get(str(error), "voice_sample_import.error_invalid_wav")
    QMessageBox.warning(
        window,
        ui_state_service.translate("dialog.project_error_title", language),
        ui_state_service.translate(message_key, language).format(
            min_duration_seconds=config.DEFAULT_IMPORTED_VOICE_SAMPLE_MIN_SECONDS,
        ),
    )


def _confirm_generate_profiles(window: "MainWindow", language: str) -> bool:
    """
    @brief      Confirm AI-assisted text-only narrator profile generation.
    @param[in]  window Main application window.
    @param[in]  language Runtime UI language code.
    @return     True when the operator accepts token-consuming AI work.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.narator_voice_generate_profiles_title", language),
            ui_state_service.translate("dialog.narator_voice_generate_profiles_message", language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def prompt_ai_narrator_profile_instructions(window: "MainWindow", language: str) -> str | None:
    """
    @brief      Ask the operator for optional extra AI narrator profile prompt rules.
    @param[in]  window Main application window.
    @param[in]  language Runtime UI language code.
    @return     Extra narrator profile instructions, an empty string, or None when cancelled.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    instructions = misc_ui_controller.prompt_multiline_text(
        window,
        ui_state_service.translate("dialog.narator_profile_generation_extra_prompt_title", language),
        ui_state_service.translate("dialog.narator_profile_generation_extra_prompt_label", language),
        "",
    )
    if instructions is None:
        return None
    return instructions.strip()


def _is_resuming_profile_generation(window: "MainWindow") -> bool:
    """
    @brief      Return whether the narrator profile generation request resumes saved AI work.
    @param[in]  window Main application window.
    @return     True when a compatible unfinished operation may reuse saved prompt rules.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    if window._current_project_root is None:
        return False
    operation_state = narrator_profile_generation_service.load_operation_state(window._current_project_root)
    if not isinstance(operation_state, dict):
        return False
    is_ai_profile_generation = (
        str(operation_state.get("mode", ""))
        == narrator_profile_generation_service.NARRATOR_PROFILE_GENERATION_MODE_AI_ASSISTED
    )
    return is_ai_profile_generation and str(operation_state.get("status", "")) in {
        "running",
        "failed",
        "cancelled",
    }


def _preview_text_character_limit(settings_payload: dict[str, object] | None) -> int:
    """
    @brief      Resolve the configured narrator preview text character limit.
    @param[in]  settings_payload Current application settings payload.
    @return     Positive preview text character limit.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    if not isinstance(settings_payload, dict):
        return config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT
    try:
        character_limit = int(
            settings_payload.get(
                "tts_preview_text_character_limit",
                config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT,
            )
        )
    except (TypeError, ValueError):
        return config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT
    return character_limit if character_limit > 0 else config.DEFAULT_TTS_PREVIEW_TEXT_CHARACTER_LIMIT


def _show_name_validation_error(window: "MainWindow", language: str, error_code: str) -> None:
    """
    @brief      Execute the show name validation error helper.
    @param[in]  window Value for `window`.
    @param[in]  language Language code.
    @param[in]  error_code Value for `error_code`.
    @return     None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-21
    @version    0.1.0
    """
    message_key = (
        "narator_voice.error_duplicate_profile_name"
        if error_code == "duplicate_name"
        else "narator_voice.error_invalid_profile_name"
    )
    QMessageBox.warning(
        window,
        ui_state_service.translate("dialog.project_error_title", language),
        ui_state_service.translate(message_key, language),
    )


def _selected_profile_id(window: "MainWindow") -> str | None:
    """
    @brief      Resolve the currently selected narrator-profile identifier from project state.
    @param[in]  window Main application window.
    @return     Selected narrator-profile identifier or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-23
    @version    0.1.0
    """
    if window._current_project_root is None:
        return None
    selected_state = narrator_definition_service.load_selected_profile_state(window._current_project_root)
    selected_profile_id = str(selected_state.get("selected_profile_id", "") or "").strip()
    return selected_profile_id or None


# END OF FILE
