#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file characters_ui_controller.py
@brief Character Discovery page UI controller for AudioMancer.
@details Handles character-discovery start or continue, reset, guarded manual
         add or edit or save or delete actions, and modal progress lifecycle
         for the Characters page.
@author Eng. Dan Dumitru Pasare
@date 2026-04-11
@version 0.18.0
"""

# IMPORTS

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QInputDialog, QMessageBox

from audiomancer.services import (
    audio_blocks_service,
    character_discovery_service,
    character_voices_service,
    chunking_document_service,
    narrator_definition_service,
    operation_runtime_service,
    project_workspace_service,
    speech_blocks_service,
    text_cleanup_state_service,
    ui_state_service,
    workflow_impact_service,
)
from audiomancer.ui.controllers import misc_ui_controller, workflow_controller_service

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


def handle_start_discovery_requested(window: "MainWindow", profile_id: str) -> None:
    """
    @brief      Validate prerequisites and start or resume character discovery.
    @param[in]  window Main application window.
    @param[in]  profile_id Requested AI profile identifier from the page.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.5.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if not _resolve_unsaved_changes(window):
        return
    if window._active_operation_kind is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_no_active_project", current_language),
        )
        return
    if not _has_chunking_output(window._current_project_root):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_missing_chunk_artifact", current_language),
        )
        return
    profile_payload = _resolve_ai_profile(window._settings_payload, profile_id)
    if profile_payload is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate(
                "project.error_missing_character_discovery_profile",
                current_language,
            ),
        )
        return
    if not _has_previous_character_discovery_state(window):
        QMessageBox.information(
            window,
            ui_state_service.translate("dialog.character_discovery_info_title", current_language),
            ui_state_service.translate("project.info_character_discovery", current_language),
        )
    additional_character_discovery_instructions = None
    if not _is_resuming_character_discovery(window):
        additional_character_discovery_instructions = prompt_ai_character_discovery_instructions(
            window,
            current_language,
        )
        if additional_character_discovery_instructions is None:
            return
    _start_operation(
        window,
        operation_name=ui_state_service.translate("characters.start", current_language),
        initial_message=ui_state_service.translate("progress.character_discovery", current_language),
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            character_discovery_service.start_or_continue_discovery(
                project_root,
                manifest,
                profile_payload,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
                additional_character_discovery_instructions=additional_character_discovery_instructions,
            )
        ),
    )


def handle_reset_discovery_requested(window: "MainWindow") -> None:
    """
    @brief      Reset character-discovery artifacts after guarding drafts while preserving narrator profiles.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.3.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if not _resolve_unsaved_changes(window):
        return
    if window._current_project_root is None or window._current_manifest is None:
        return
    character_discovery_service.reset_character_discovery(window._current_project_root)
    reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
        window._current_manifest,
        "character_discovery",
        preserve_operation_kinds=operation_runtime_service.NARRATOR_PROFILE_PRESERVED_OPERATION_KINDS,
    )
    project_workspace_service.save_manifest(reset_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.character_discovery_reset", current_language),
    )


def handle_add_character_requested(window: "MainWindow") -> None:
    """
    @brief      Prompt for a new manual character name and enter add mode.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None:
        return
    if not _resolve_unsaved_changes(window):
        return
    existing_profiles = character_discovery_service.load_character_profiles(window._current_project_root)
    character_name, accepted = QInputDialog.getText(
        window,
        ui_state_service.translate("dialog.character_add_title", current_language),
        ui_state_service.translate("dialog.character_add_prompt", current_language),
    )
    if not accepted:
        return
    try:
        normalized_name = character_discovery_service.validate_manual_character_name(
            existing_profiles,
            character_name,
        )
    except ValueError as error:
        _show_name_validation_error(window, current_language, str(error))
        return
    window._characters_page.begin_add_mode(_build_manual_draft_profile(existing_profiles, normalized_name))


def handle_edit_character_requested(window: "MainWindow", character_id: str) -> None:
    """
    @brief      Enter guarded edit mode for the currently selected character.
    @param[in]  window Main application window.
    @param[in]  character_id Requested character identifier from the page.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.3.0
    """
    _ = character_id
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._characters_page.current_character_id() is None:
        return
    if not _confirm_edit_character(window, current_language):
        return
    window._characters_page.begin_edit_mode()


def handle_save_character_requested(
    window: "MainWindow",
    profile_payload: dict[str, object],
    *,
    show_progress: bool = False,
) -> bool:
    """
    @brief      Validate and persist one manual add or edit draft.
    @param[in]  window Main application window.
    @param[in]  profile_payload Draft character profile payload from the page.
    @param[in]  show_progress True to show the synchronous save progress dialog.
    @return     `True` when the character was saved successfully.
    @exception  ValueError Propagated from manual-name validation helpers.
    @exception  RuntimeError Raised when could not persist the new manual character profile.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.5.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None:
        return False
    existing_profiles = character_discovery_service.load_character_profiles(window._current_project_root)
    try:
        normalized_name = character_discovery_service.validate_manual_character_name(
            existing_profiles,
            profile_payload.get("canonical_name", ""),
            exclude_character_id=str(profile_payload.get("character_id", "")).strip(),
        )
    except ValueError as error:
        _show_name_validation_error(window, current_language, str(error))
        return False
    progress_started = False
    progress_callback = None
    saved_character_id: str
    try:
        if window._characters_page.is_add_mode():
            if not _confirm_add_character(window, current_language):
                return False
            progress_callback = _start_character_save_progress(window, current_language, show_progress)
            progress_started = progress_callback is not None
            _update_character_save_progress(progress_callback, 20, "progress.character_save_profile")
            existing_ids = {str(profile.get("character_id", "")).strip() for profile in existing_profiles}
            created_profiles = character_discovery_service.add_character_profile(
                window._current_project_root,
                normalized_name,
            )
            created_profile = next(
                (
                    profile
                    for profile in created_profiles
                    if str(profile.get("character_id", "")).strip() not in existing_ids
                ),
                None,
            )
            if created_profile is None:
                raise RuntimeError("Could not persist the new manual character profile.")
            persisted_payload = dict(profile_payload)
            persisted_payload["character_id"] = created_profile["character_id"]
            persisted_payload["canonical_name"] = normalized_name
            persisted_payload["evidence"] = [dict(item) for item in created_profile["evidence"]]
            character_discovery_service.update_character_profile(
                window._current_project_root,
                persisted_payload,
            )
            saved_character_id = str(created_profile["character_id"])
            _sync_manifest_after_character_add(window, progress_callback=progress_callback)
            status_key = "status.character_added"
        else:
            previous_profile = _character_profile_by_id(
                existing_profiles,
                str(profile_payload.get("character_id", "")).strip(),
            )
            progress_callback = _start_character_save_progress(window, current_language, show_progress)
            progress_started = progress_callback is not None
            _update_character_save_progress(progress_callback, 20, "progress.character_save_profile")
            persisted_payload = dict(profile_payload)
            persisted_payload["canonical_name"] = normalized_name
            updated_profiles = character_discovery_service.update_character_profile(
                window._current_project_root,
                persisted_payload,
            )
            saved_character_id = str(persisted_payload.get("character_id", ""))
            updated_profile = _character_profile_by_id(updated_profiles, saved_character_id)
            _sync_manifest_after_character_edit(window, previous_profile, updated_profile, progress_callback)
            status_key = "status.character_saved"
        _update_character_save_progress(progress_callback, 95, "progress.character_save_refresh")
        window.show_project_state(
            window._current_project_root,
            project_workspace_service.load_manifest(window._current_project_root),
        )
        window._characters_page.apply_selected_character(saved_character_id)
        misc_ui_controller.show_message(
            window,
            ui_state_service.translate(status_key, current_language),
        )
        return True
    finally:
        if progress_started:
            _finish_character_save_progress(window)


def handle_delete_character_requested(window: "MainWindow", character_id: str) -> None:
    """
    @brief      Confirm and delete one persisted character profile.
    @param[in]  window Main application window.
    @param[in]  character_id Target persisted character identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.3.0
    """
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    if window._current_project_root is None:
        return
    if not character_id:
        return
    if not _confirm_delete_character(window, current_language):
        return
    existing_profiles = character_discovery_service.load_character_profiles(window._current_project_root)
    target_index = next(
        (
            index
            for index, profile in enumerate(existing_profiles)
            if str(profile.get("character_id", "")).strip() == character_id
        ),
        -1,
    )
    character_discovery_service.delete_character_profile(
        window._current_project_root,
        character_id,
    )
    _sync_manifest_after_character_delete(window, character_id)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )
    remaining_profiles = character_discovery_service.load_character_profiles(window._current_project_root)
    if remaining_profiles:
        fallback_index = min(target_index, len(remaining_profiles) - 1)
        window._characters_page.apply_selected_character(
            str(remaining_profiles[fallback_index].get("character_id", ""))
        )
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate("status.character_deleted", current_language),
    )


def handle_selection_change_requested(
    window: "MainWindow",
    target_character_id: object,
) -> None:
    """
    @brief      Guard character-list selection changes against unsaved drafts.
    @param[in]  window Main application window.
    @param[in]  target_character_id Requested target character identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
    """
    page = window._characters_page
    if not page.is_dirty():
        page.apply_selected_character(_optional_character_id(target_character_id))
        return
    decision = _prompt_unsaved_changes(
        window,
        ui_state_service.current_language_from_settings(window._settings_payload),
    )
    if decision == "cancel":
        page.restore_current_selection()
        return
    if decision == "save":
        if not _save_current_draft(window):
            page.restore_current_selection()
            return
    else:
        page.discard_changes()
    page.apply_selected_character(_optional_character_id(target_character_id))


def _start_character_save_progress(
    window: "MainWindow",
    language: str,
    show_progress: bool,
):
    """
    @brief      Start the synchronous Character save progress dialog when requested.
    @param[in]  window Main application window.
    @param[in]  language Runtime UI language code.
    @param[in]  show_progress True to show progress.
    @return     Progress update callback or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-11
    @version    0.1.0
    """
    if not show_progress or window._operation_progress_dialog is not None:
        return None
    window._characters_page.set_busy(True)
    misc_ui_controller.create_progress_dialog(
        window,
        ui_state_service.translate("characters.save_character", language),
        ui_state_service.translate("progress.character_save_prepare", language),
        lambda: None,
        cancellable=False,
    )
    misc_ui_controller.process_pending_ui_events()

    def _update(percent: int, message_key: str) -> None:
        """
        @brief      Update the active Character Discovery progress dialog.
        @param[in]  percent Progress percentage displayed to the operator.
        @param[in]  message_key Translation key for the progress message.
        @return     None.
        @version    0.1.0
        """
        misc_ui_controller.update_progress_dialog(
            window,
            percent,
            ui_state_service.translate(message_key, language),
        )
        misc_ui_controller.process_pending_ui_events()

    return _update


def _update_character_save_progress(progress_callback, percent: int, message_key: str) -> None:
    """
    @brief      Update Character save progress when a progress callback exists.
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


def _finish_character_save_progress(window: "MainWindow") -> None:
    """
    @brief      Close and clear the synchronous Character save progress dialog.
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
            "progress.character_save_refresh",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )
    misc_ui_controller.finish_progress_dialog(window)
    misc_ui_controller.clear_progress_dialog(window)
    window._characters_page.set_busy(False)
    misc_ui_controller.process_pending_ui_events()


def _start_operation(
    window: "MainWindow",
    operation_name: str,
    initial_message: str,
    worker_callable,
) -> None:
    """
    @brief      Start one modal character-discovery operation on a worker thread.
    @param[in]  window Main application window.
    @param[in]  operation_name Operator-facing operation title.
    @param[in]  initial_message Initial progress-dialog message.
    @param[in]  worker_callable Callable performing the background operation.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.3.0
    """
    workflow_controller_service.start_operation(
        window,
        operation_kind="character_discovery",
        operation_name=operation_name,
        initial_message=initial_message,
        worker_callable=worker_callable,
        set_busy=lambda is_busy: window._characters_page.set_busy(is_busy),
        success_handler=lambda result_payload: _handle_discovery_success(window, result_payload),
        failure_handler=lambda error: _handle_discovery_failure(window, error),
        cancel_handler=lambda message: _handle_discovery_cancelled(window, message),
    )


def _handle_discovery_success(window: "MainWindow", result_payload: object) -> None:
    """
    @brief      Refresh character-discovery UI state after a successful worker run.
    @param[in]  window Main application window.
    @param[in]  result_payload Worker result payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.2.0
    """
    assert isinstance(result_payload, dict)
    _sync_manifest_after_discovery(window, result_payload)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.characters_discovered",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def _handle_discovery_failure(window: "MainWindow", error: Exception) -> None:
    """
    @brief      Refresh character-discovery UI state after a failed worker run.
    @param[in]  window Main application window.
    @param[in]  error Raised operation exception.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    _sync_manifest_from_disk(window)
    QMessageBox.warning(
        window,
        ui_state_service.translate(
            "dialog.project_error_title",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
        str(error),
    )


def _handle_discovery_cancelled(window: "MainWindow", message: str) -> None:
    """
    @brief      Refresh character-discovery UI state after a cancelled worker run.
    @param[in]  window Main application window.
    @param[in]  message Cancellation message.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-24
    @version    0.1.0
    """
    _ = message
    _sync_manifest_from_disk(window)
    misc_ui_controller.show_message(
        window,
        ui_state_service.translate(
            "status.operation_cancelled",
            ui_state_service.current_language_from_settings(window._settings_payload),
        ),
    )


def _sync_manifest_after_discovery(
    window: "MainWindow",
    report: dict[str, object],
) -> None:
    """
    @brief      Persist manifest state after a successful discovery run.
    @param[in]  window Main application window.
    @param[in]  report Final character-discovery report payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
    """
    _ = report
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    operation_state = _character_operation_summary(window._current_project_root)
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    if operation_state is not None:
        operations["character_discovery"] = project_workspace_service.project_manifest_operation_summary(
            "character_discovery",
            operation_state,
        )
    updated_manifest["operations"] = operations
    updated_manifest["current_stage"] = "character_discovery_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _sync_manifest_after_character_add(
    window: "MainWindow",
    progress_callback=None,
) -> None:
    """
    @brief      Refresh character metadata after adding one manual character.
    @param[in]  window Main application window.
    @param[in]  progress_callback Optional synchronous progress updater.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.2.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    _update_character_save_progress(progress_callback, 45, "progress.character_save_character_voices")
    _sync_character_voice_plan(window._current_project_root)
    _update_character_save_progress(progress_callback, 85, "progress.character_save_manifest")
    _save_refreshed_manual_manifest(
        window,
        current_stage=str(window._current_manifest.get("current_stage", "character_discovery_ready")),
    )


def _sync_manifest_after_character_edit(
    window: "MainWindow",
    previous_profile: dict[str, object] | None,
    updated_profile: dict[str, object] | None,
    progress_callback=None,
) -> None:
    """
    @brief      Refresh selective downstream state after editing one character.
    @param[in]  window Main application window.
    @param[in]  previous_profile Previously persisted profile payload.
    @param[in]  updated_profile Updated persisted profile payload.
    @param[in]  progress_callback Optional synchronous progress updater.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.3.0
    """
    if (
        window._current_project_root is None
        or window._current_manifest is None
        or not isinstance(updated_profile, dict)
    ):
        return
    project_root = window._current_project_root
    character_id = str(updated_profile.get("character_id", "")).strip()
    display_name = str(updated_profile.get("canonical_name", "")).strip()
    voice_target_ids: tuple[str, ...] = ()
    _update_character_save_progress(progress_callback, 35, "progress.character_save_character_voices")
    if _voice_definition_source_changed(previous_profile, updated_profile):
        voice_target_ids = (character_voices_service.mark_character_voice_target_stale(project_root, character_id),)
    _update_character_save_progress(progress_callback, 50, "progress.character_save_speech_blocks")
    _speech_report, _renamed_speech_block_ids = speech_blocks_service.update_character_speech_block_display_name(
        project_root,
        character_id,
        display_name=display_name,
    )
    _update_character_save_progress(progress_callback, 70, "progress.character_save_audio_blocks")
    _audio_report, artifact_summary = audio_blocks_service.remove_audio_blocks_for_speech_blocks(
        project_root,
        (),
        voice_target_ids=voice_target_ids,
        collect_preserved_paths=False,
        preserve_invalidated_blocks=True,
    )
    reset_assembly = bool(voice_target_ids or artifact_summary.deleted_count)
    if reset_assembly:
        workflow_impact_service.reset_audio_assembly_outputs(project_root)
    current_stage = (
        "character_discovery_ready" if reset_assembly else str(window._current_manifest.get("current_stage"))
    )
    _update_character_save_progress(progress_callback, 85, "progress.character_save_manifest")
    _save_refreshed_manual_manifest(window, current_stage=current_stage, reset_audio_assembly=reset_assembly)


def _sync_manifest_after_character_delete(window: "MainWindow", character_id: str) -> None:
    """
    @brief      Refresh selective downstream state after deleting one character.
    @param[in]  window Main application window.
    @param[in]  character_id Deleted character identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    project_root = window._current_project_root
    voice_target_id = character_voices_service.remove_character_voice_target(project_root, character_id)
    _speech_report, affected_speech_block_ids = speech_blocks_service.fallback_character_speech_blocks_to_narrator(
        project_root,
        character_id,
    )
    _audio_report, artifact_summary = audio_blocks_service.remove_audio_blocks_for_speech_blocks(
        project_root,
        affected_speech_block_ids,
        voice_target_ids=(voice_target_id,),
    )
    reset_assembly = bool(affected_speech_block_ids or voice_target_id or artifact_summary.deleted_count)
    if reset_assembly:
        workflow_impact_service.reset_audio_assembly_outputs(project_root)
    current_stage = (
        "character_discovery_ready" if reset_assembly else str(window._current_manifest.get("current_stage"))
    )
    _save_refreshed_manual_manifest(window, current_stage=current_stage, reset_audio_assembly=reset_assembly)


def _save_refreshed_manual_manifest(
    window: "MainWindow",
    current_stage: str,
    reset_audio_assembly: bool = False,
) -> None:
    """
    @brief      Save manifest summaries after selective manual character maintenance.
    @param[in]  window Main application window.
    @param[in]  current_stage Stage token to persist.
    @param[in]  reset_audio_assembly True to mark Audio Assembly not started.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    default_operations = text_cleanup_state_service.normalized_manifest_operations({})
    operation_state = _character_operation_summary(window._current_project_root)
    if operation_state is not None:
        operations["character_discovery"] = project_workspace_service.project_manifest_operation_summary(
            "character_discovery",
            operation_state,
        )
    speech_state = speech_blocks_service.load_operation_state(window._current_project_root)
    if speech_state is not None:
        operations["speech_blocks"] = project_workspace_service.project_manifest_operation_summary(
            "speech_blocks",
            speech_state,
        )
    audio_state = audio_blocks_service.load_operation_state(window._current_project_root)
    if audio_state is not None:
        operations["audio_blocks"] = project_workspace_service.project_manifest_operation_summary(
            "audio_blocks",
            audio_state,
        )
    if reset_audio_assembly:
        operations["audio_assembly"] = default_operations["audio_assembly"]
    updated_manifest["operations"] = operations
    updated_manifest["current_stage"] = current_stage or "character_discovery_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)


def _sync_character_voice_plan(project_root: str) -> None:
    """
    @brief      Synchronize Character Voices targets from current narrator and character state.
    @param[in]  project_root Active project root.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    profiles = narrator_definition_service.load_profiles(project_root)
    selected_state = narrator_definition_service.load_selected_profile_state(project_root)
    selected_profile_id = str(selected_state.get("selected_profile_id", "") or "").strip()
    narrator_profile = next(
        (profile for profile in profiles if str(profile.get("profile_id", "")).strip() == selected_profile_id),
        None,
    )
    character_voices_service.sync_voice_plan(
        project_root,
        character_discovery_service.load_character_profiles(project_root),
        narrator_profile,
        character_voices_service.load_selected_voice_language(project_root),
    )


def _voice_definition_source_changed(
    previous_profile: dict[str, object] | None,
    updated_profile: dict[str, object] | None,
) -> bool:
    """
    @brief      Return whether compact character voice-target fields changed.
    @param[in]  previous_profile Previous profile payload.
    @param[in]  updated_profile Updated profile payload.
    @return     True when identity, sex/gender, age, voice prompt text, or preview text changed.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.5.0
    """
    if not isinstance(previous_profile, dict) or not isinstance(updated_profile, dict):
        return False
    comparable_fields = (
        "canonical_name",
        "gender_hint",
        "gender_confidence",
        "age_hint",
        "age_confidence",
        "voice_definition_prompt",
        "preview_text",
    )
    return any(
        str(previous_profile.get(field_name, "")).strip() != str(updated_profile.get(field_name, "")).strip()
        for field_name in comparable_fields
    )


def _character_profile_by_id(
    profiles: list[dict[str, object]],
    character_id: str,
) -> dict[str, object] | None:
    """
    @brief      Resolve one character profile by stable identifier.
    @param[in]  profiles Candidate profile payload list.
    @param[in]  character_id Stable character identifier.
    @return     Matching profile payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    normalized_character_id = str(character_id).strip()
    return next(
        (
            dict(profile)
            for profile in profiles
            if str(profile.get("character_id", "")).strip() == normalized_character_id
        ),
        None,
    )


def _sync_manifest_from_disk(window: "MainWindow") -> None:
    """
    @brief      Reload persisted operation state after failure or cancellation.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.2.0
    """
    workflow_controller_service.sync_manifest_operation_from_disk(
        window,
        "character_discovery",
        _character_operation_summary,
        current_stage="translation_ready",
    )


def _resolve_unsaved_changes(window: "MainWindow") -> bool:
    """
    @brief      Resolve the active dirty draft before a disruptive action.
    @param[in]  window Main application window.
    @return     `True` when the action may continue.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
    """
    page = window._characters_page
    if not page.is_dirty():
        return True
    current_language = ui_state_service.current_language_from_settings(window._settings_payload)
    decision = _prompt_unsaved_changes(window, current_language)
    if decision == "cancel":
        page.restore_current_selection()
        return False
    if decision == "discard":
        page.discard_changes()
        return True
    return _save_current_draft(window)


def _save_current_draft(window: "MainWindow") -> bool:
    """
    @brief      Persist the current page draft when one exists.
    @param[in]  window Main application window.
    @return     `True` when no draft exists or save succeeded.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    draft_payload = window._characters_page.current_draft_payload()
    if draft_payload is None:
        return True
    return handle_save_character_requested(window, draft_payload)


def _prompt_unsaved_changes(window: "MainWindow", language: str) -> str:
    """
    @brief      Show the save or discard or cancel prompt for a dirty draft.
    @param[in]  window Main application window.
    @param[in]  language Runtime UI language code.
    @return     Decision token: `save`, `discard`, or `cancel`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    message_box = QMessageBox(window)
    message_box.setIcon(QMessageBox.Icon.Question)
    message_box.setWindowTitle(ui_state_service.translate("dialog.character_unsaved_title", language))
    message_box.setText(ui_state_service.translate("dialog.character_unsaved_message", language))
    save_button = message_box.addButton(
        ui_state_service.translate("characters.prompt_save", language),
        QMessageBox.ButtonRole.AcceptRole,
    )
    discard_button = message_box.addButton(
        ui_state_service.translate("characters.prompt_discard", language),
        QMessageBox.ButtonRole.DestructiveRole,
    )
    message_box.addButton(
        ui_state_service.translate("characters.prompt_cancel", language),
        QMessageBox.ButtonRole.RejectRole,
    )
    message_box.exec()
    clicked_button = message_box.clickedButton()
    if clicked_button == save_button:
        return "save"
    if clicked_button == discard_button:
        return "discard"
    return "cancel"


def _confirm_add_character(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator to confirm adding a manual character.
    @param[in]  window Main application window.
    @param[in]  language Runtime UI language code.
    @return     `True` when the add was confirmed.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    decision = QMessageBox.question(
        window,
        ui_state_service.translate("dialog.character_add_confirm_title", language),
        ui_state_service.translate("dialog.character_add_confirm_message", language),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return decision == QMessageBox.StandardButton.Yes


def _confirm_edit_character(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator to confirm editing a persisted character.
    @param[in]  window Main application window.
    @param[in]  language Runtime UI language code.
    @return     `True` when the edit was confirmed.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.1.0
    """
    decision = QMessageBox.question(
        window,
        ui_state_service.translate("dialog.character_edit_title", language),
        ui_state_service.translate("dialog.character_edit_message", language),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return decision == QMessageBox.StandardButton.Yes


def _confirm_delete_character(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator to confirm deletion of the selected character.
    @param[in]  window Main application window.
    @param[in]  language Runtime UI language code.
    @return     `True` when deletion was confirmed.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
    """
    decision = QMessageBox.question(
        window,
        ui_state_service.translate("dialog.character_delete_title", language),
        ui_state_service.translate("dialog.character_delete_message", language),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return decision == QMessageBox.StandardButton.Yes


def _show_name_validation_error(
    window: "MainWindow",
    language: str,
    error_code: str,
) -> None:
    """
    @brief      Show one localized manual-character name validation error.
    @param[in]  window Main application window.
    @param[in]  language Runtime UI language code.
    @param[in]  error_code Stable validation error token.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    message_key = (
        "project.error_duplicate_character_name"
        if error_code == "duplicate_name"
        else "project.error_invalid_character_name"
    )
    QMessageBox.warning(
        window,
        ui_state_service.translate("dialog.project_error_title", language),
        ui_state_service.translate(message_key, language),
    )


def _build_manual_draft_profile(
    existing_profiles: list[dict[str, object]],
    canonical_name: str,
) -> dict[str, object]:
    """
    @brief      Build one temporary unsaved manual-character draft payload.
    @param[in]  existing_profiles Persisted character profile payload list.
    @param[in]  canonical_name Validated new canonical name.
    @return     Unsaved draft payload with synthetic manual evidence.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    existing_ids = {str(profile.get("character_id", "")).strip() for profile in existing_profiles}
    base_slug = _draft_slug(canonical_name)
    draft_id = f"draft_{base_slug}" if base_slug else "draft_character"
    suffix = 2
    while draft_id in existing_ids:
        draft_id = f"draft_{base_slug}_{suffix}"
        suffix += 1
    return character_discovery_service.regenerate_character_voice_definition(
        {
            "character_id": draft_id,
            "canonical_name": canonical_name,
            "aliases": [],
            "gender_hint": "",
            "gender_confidence": "",
            "age_hint": "",
            "age_confidence": "",
            "voice_definition_prompt": "",
            "confidence": "",
            "evidence": [
                {
                    "chunk_id": character_discovery_service.MANUAL_CHARACTER_EVIDENCE_CHUNK_ID,
                    "sequence_index": 0,
                    "source_excerpt": character_discovery_service.MANUAL_CHARACTER_EVIDENCE_NOTE,
                    "reason": character_discovery_service.MANUAL_CHARACTER_EVIDENCE_NOTE,
                }
            ],
        }
    )


def _draft_slug(canonical_name: str) -> str:
    """
    @brief      Build a simple ASCII-safe slug for manual draft identifiers.
    @param[in]  canonical_name Manual character canonical name.
    @return     Lowercase slug string.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    return "".join(character if character.isalnum() else "_" for character in canonical_name.casefold()).strip("_")


def _optional_character_id(value: object) -> str | None:
    """
    @brief      Normalize one optional character identifier value.
    @param[in]  value Candidate identifier value from Qt signals.
    @return     String identifier or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    if value in (None, ""):
        return None
    return str(value)


def _has_previous_character_discovery_state(window: "MainWindow") -> bool:
    """
    @brief      Check whether discovery has persisted prior runtime artifacts.
    @param[in]  window Main application window.
    @return     `True` when state, report, or profiles already exist.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    if window._current_project_root is None:
        return False
    return character_discovery_service.load_character_document(window._current_project_root) is not None


def prompt_ai_character_discovery_instructions(window: "MainWindow", language: str) -> str | None:
    """
    @brief      Ask the operator for optional extra AI Character Discovery prompt rules.
    @param[in]  window Active main window instance.
    @param[in]  language Runtime UI language code.
    @return     Extra Character Discovery instructions, an empty string, or None when cancelled.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    instructions = misc_ui_controller.prompt_multiline_text(
        window,
        ui_state_service.translate("dialog.character_discovery_extra_prompt_title", language),
        ui_state_service.translate("dialog.character_discovery_extra_prompt_label", language),
        "",
    )
    if instructions is None:
        return None
    return instructions.strip()


def _is_resuming_character_discovery(window: "MainWindow") -> bool:
    """
    @brief      Return whether Character Discovery can resume saved AI work.
    @param[in]  window Active main window instance.
    @return     True when a running, failed, or cancelled AI Character Discovery operation is present.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.1
    """
    if window._current_project_root is None:
        return False
    document = character_discovery_service.load_character_document(window._current_project_root)
    if not isinstance(document, dict):
        return False
    return str(document.get("status", "")) in {"running", "failed", "cancelled"}


def _character_operation_summary(project_root: str | Path) -> dict[str, object] | None:
    """Load the authoritative character document and derive its operation summary."""
    document = character_discovery_service.load_character_document(project_root)
    if document is None:
        return None
    return character_discovery_service.character_operation_summary(
        document,
        len(character_discovery_service.load_input_chunks(project_root)),
    )


def _resolve_ai_profile(
    settings_payload: dict[str, object],
    selected_profile_id: str | None,
) -> dict[str, object] | None:
    """
    @brief      Resolve one enabled AI profile payload from settings.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  selected_profile_id Requested profile identifier.
    @return     Matching enabled profile payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    return workflow_controller_service.resolve_enabled_ai_profile(settings_payload, selected_profile_id)


def _has_chunking_output(project_root: str | None) -> bool:
    """
    @brief      Check whether the manifest advertises chunking output artifacts.
    @param[in]  project_root Active project root path.
    @return     `True` when chunk output can be loaded from disk.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    if not project_root:
        return False
    return bool(chunking_document_service.load_chunks(project_root))


# END OF FILE
