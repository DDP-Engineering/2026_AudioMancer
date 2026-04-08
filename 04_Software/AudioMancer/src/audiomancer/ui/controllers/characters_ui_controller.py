#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file characters_ui_controller.py
@brief Character Discovery page UI controller for AudioMancer.
@details Handles character-discovery start or continue, reset, manual profile
         edits, and modal progress lifecycle for the Characters page.
@author Eng. Dan Dumitru Pasare
@date 2026-04-08
@version 0.2.0
"""

# IMPORTS

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from audiomancer.services import character_discovery_service
from audiomancer.services import home_presenter_service
from audiomancer.services import project_workspace_service
from audiomancer.services import text_cleanup_state_service
from audiomancer.services import ui_state_service
from audiomancer.ui.controllers import misc_ui_controller

if TYPE_CHECKING:
    from audiomancer.ui.main_window import MainWindow


# PUBLIC API


def handle_start_discovery_requested(window: "MainWindow", profile_id: str) -> None:
    """
    @brief      Validate and start or continue one character-discovery run.
    @param[in]  window Active main window instance.
    @param[in]  profile_id Selected enabled AI profile identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    current_language = ui_state_service.current_language_from_settings(
        window._settings_payload
    )
    if window._active_operation_kind is not None:
        return
    if window._current_project_root is None or window._current_manifest is None:
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_no_active_project", current_language),
        )
        return
    if not _has_chunking_output(window._current_manifest):
        QMessageBox.warning(
            window,
            ui_state_service.translate("dialog.project_error_title", current_language),
            ui_state_service.translate("project.error_missing_chunk_artifact", current_language),
        )
        return
    effective_profile_id = _effective_profile_id(window, profile_id)
    profile_payload = _resolve_ai_profile(window._settings_payload, effective_profile_id)
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
    _start_operation(
        window,
        operation_name=ui_state_service.translate("characters.start", current_language),
        initial_message=ui_state_service.translate("progress.character_discovery", current_language),
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: character_discovery_service.start_or_continue_discovery(
            project_root,
            manifest,
            profile_payload,
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
        ),
    )


def handle_reset_discovery_requested(window: "MainWindow") -> None:
    """
    @brief      Reset all persisted character-discovery runtime data.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    current_language = ui_state_service.current_language_from_settings(
        window._settings_payload
    )
    if window._current_project_root is None or window._current_manifest is None:
        return
    character_discovery_service.reset_character_discovery(window._current_project_root)
    reset_manifest = text_cleanup_state_service.build_manifest_after_operation_reset(
        window._current_manifest,
        "character_discovery",
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


def handle_profile_changed(
    window: "MainWindow",
    profile_payload: dict[str, object],
) -> None:
    """
    @brief      Persist one operator edit to a discovered character profile.
    @param[in]  window Active main window instance.
    @param[in]  profile_payload Updated character profile payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.1
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    character_discovery_service.update_character_profile(
        window._current_project_root,
        profile_payload,
    )
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def handle_character_profile_changed(
    window: "MainWindow",
    profile_payload: dict[str, object],
) -> None:
    """
    @brief      Preserve backward compatibility for the previous handler name.
    @param[in]  window Active main window instance.
    @param[in]  profile_payload Updated character profile payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    handle_profile_changed(window, profile_payload)


# LOCAL HELPERS


def _start_operation(
    window: "MainWindow",
    operation_name: str,
    initial_message: str,
    worker_callable,
) -> None:
    """
    @brief      Run one character-discovery operation with modal progress handling.
    @param[in]  window Active main window instance.
    @param[in]  operation_name Operator-facing operation label.
    @param[in]  initial_message Initial progress-dialog message text.
    @param[in]  worker_callable Callable that performs the operation.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    window._characters_page.set_busy(True)
    window._active_operation_kind = "character_discovery"
    window._active_operation_name = operation_name
    window._operation_cancel_requested = False
    misc_ui_controller.create_progress_dialog(
        window,
        operation_name,
        initial_message,
        lambda: _cancel_active_operation(window),
    )
    try:
        result_payload = worker_callable(
            window._current_project_root,
            dict(window._current_manifest),
            progress_callback=lambda current, total, percent, message: misc_ui_controller.update_progress_dialog(
                window,
                percent,
                message,
            ),
            cancel_requested=lambda: _is_cancel_requested(window),
        )
    except character_discovery_service.OperationCancelledError as error:
        misc_ui_controller.update_progress_dialog(window, 100, str(error))
        misc_ui_controller.fail_progress_dialog(window, str(error))
        _sync_manifest_from_disk(window)
        misc_ui_controller.show_message(
            window,
            ui_state_service.translate(
                "status.operation_cancelled",
                ui_state_service.current_language_from_settings(window._settings_payload),
            ),
        )
    except Exception as error:
        misc_ui_controller.update_progress_dialog(window, 100, str(error))
        misc_ui_controller.fail_progress_dialog(window, str(error))
        _sync_manifest_from_disk(window)
        QMessageBox.warning(
            window,
            ui_state_service.translate(
                "dialog.project_error_title",
                ui_state_service.current_language_from_settings(window._settings_payload),
            ),
            str(error),
        )
    else:
        misc_ui_controller.finish_progress_dialog(window)
        _sync_manifest_after_discovery(window, result_payload)
        misc_ui_controller.show_message(
            window,
            ui_state_service.translate(
                "status.characters_discovered",
                ui_state_service.current_language_from_settings(window._settings_payload),
            ),
        )
    finally:
        window._characters_page.set_busy(False)
        misc_ui_controller.clear_progress_dialog(window)
        window._active_operation_kind = None
        window._active_operation_name = None
        window._operation_cancel_requested = False


def _sync_manifest_after_discovery(
    window: "MainWindow",
    report: dict[str, object],
) -> None:
    """
    @brief      Persist the latest discovery operation state into the manifest.
    @param[in]  window Active main window instance.
    @param[in]  report Latest character-discovery report payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    _ = report
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    operation_state = character_discovery_service.load_operation_state(
        window._current_project_root
    )
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    if operation_state is not None:
        operations["character_discovery"] = operation_state
    updated_manifest["operations"] = operations
    updated_manifest["current_stage"] = "character_discovery_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _sync_manifest_from_disk(window: "MainWindow") -> None:
    """
    @brief      Reload persisted discovery state from disk after failure or cancel.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operation_state = character_discovery_service.load_operation_state(
        window._current_project_root
    )
    if operation_state is not None:
        operations["character_discovery"] = operation_state
    updated_manifest["operations"] = operations
    updated_manifest["current_stage"] = "translation_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
    )


def _resolve_ai_profile(
    settings_payload: dict[str, object] | None,
    profile_id: str | None,
) -> dict[str, object] | None:
    """
    @brief      Resolve one enabled AI profile payload from settings by id.
    @param[in]  settings_payload Persisted application settings payload.
    @param[in]  profile_id Requested profile identifier.
    @return     Resolved profile payload or `None`.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    if not isinstance(settings_payload, dict) or not profile_id:
        return None
    raw_profiles = settings_payload.get("llm_profiles", [])
    if not isinstance(raw_profiles, list):
        return None
    for profile in raw_profiles:
        if not isinstance(profile, dict) or not bool(profile.get("enabled", True)):
            continue
        if str(profile.get("id", "")).strip() == str(profile_id).strip():
            return dict(profile)
    return None


def _effective_profile_id(window: "MainWindow", requested_profile_id: str) -> str:
    """
    @brief      Resolve the resumable profile id for one discovery run.
    @param[in]  window Active main window instance.
    @param[in]  requested_profile_id Newly selected profile identifier.
    @return     Persisted resumable profile id or the requested one.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    if window._current_project_root is None:
        return requested_profile_id
    operation_state = character_discovery_service.load_operation_state(
        window._current_project_root
    )
    if not isinstance(operation_state, dict):
        return requested_profile_id
    if str(operation_state.get("status", "")) not in {"running", "failed"}:
        return requested_profile_id
    metadata = operation_state.get("metadata", {})
    if not isinstance(metadata, dict):
        return requested_profile_id
    persisted_profile_id = metadata.get("ai_profile_id")
    return (
        str(persisted_profile_id)
        if persisted_profile_id not in (None, "")
        else requested_profile_id
    )


def _has_previous_character_discovery_state(window: "MainWindow") -> bool:
    """
    @brief      Determine whether discovery has already started or completed once.
    @param[in]  window Active main window instance.
    @return     True when persisted character-discovery state or outputs exist.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    if window._current_project_root is None:
        return False
    if character_discovery_service.load_character_discovery_report(window._current_project_root) is not None:
        return True
    if character_discovery_service.load_character_profiles(window._current_project_root):
        return True
    operation_state = character_discovery_service.load_operation_state(window._current_project_root)
    return isinstance(operation_state, dict)


def _has_chunking_output(manifest: dict[str, object]) -> bool:
    """
    @brief      Determine whether chunking output exists for character discovery.
    @param[in]  manifest Active project manifest payload.
    @return     True when chunking output paths are present.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    chunking_operation = home_presenter_service.manifest_operation(manifest, "chunking")
    output_paths = chunking_operation.get("output_paths", [])
    return isinstance(output_paths, list) and bool(output_paths)


def _cancel_active_operation(window: "MainWindow") -> None:
    """
    @brief      Mark the active discovery operation for cancellation.
    @param[in]  window Active main window instance.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    if window._active_operation_kind is not None:
        window._operation_cancel_requested = True


def _is_cancel_requested(window: "MainWindow") -> bool:
    """
    @brief      Check whether the current discovery operation should cancel.
    @param[in]  window Active main window instance.
    @return     True when cancellation was requested.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    misc_ui_controller.process_pending_ui_events()
    return window._operation_cancel_requested


# END OF FILE
