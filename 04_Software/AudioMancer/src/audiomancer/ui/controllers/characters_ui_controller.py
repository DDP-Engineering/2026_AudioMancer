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
@details Handles character-discovery start or continue, reset, guarded manual
         add or edit or save or delete actions, and modal progress lifecycle
         for the Characters page.
@author Eng. Dan Dumitru Pasare
@date 2026-04-11
@version 0.5.0
"""

# IMPORTS

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QInputDialog, QMessageBox

from audiomancer.services import (
    character_discovery_service,
    deterministic_chunking_service,
    project_workspace_service,
    text_cleanup_state_service,
    ui_state_service,
)
from audiomancer.ui.controllers import misc_ui_controller

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
    @date       2026-04-08
    @version    0.2.0
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
        worker_callable=lambda project_root, manifest, progress_callback=None, cancel_requested=None: (
            character_discovery_service.start_or_continue_discovery(
                project_root,
                manifest,
                profile_payload,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
            )
        ),
    )


def handle_reset_discovery_requested(window: "MainWindow") -> None:
    """
    @brief      Reset character-discovery artifacts after guarding unsaved drafts.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
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
    @version    0.2.0
    """
    _ = character_id
    if window._characters_page.current_character_id() is None:
        return
    window._characters_page.begin_edit_mode()


def handle_save_character_requested(
    window: "MainWindow",
    profile_payload: dict[str, object],
) -> bool:
    """
    @brief      Validate and persist one manual add or edit draft.
    @param[in]  window Main application window.
    @param[in]  profile_payload Draft character profile payload from the page.
    @return     `True` when the character was saved successfully.
    @exception  ValueError Propagated from manual-name validation helpers.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
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
    saved_character_id: str
    if window._characters_page.is_add_mode():
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
        persisted_payload["updated_at"] = created_profile.get("updated_at")
        character_discovery_service.update_character_profile(
            window._current_project_root,
            persisted_payload,
        )
        saved_character_id = str(created_profile["character_id"])
        status_key = "status.character_added"
    else:
        persisted_payload = dict(profile_payload)
        persisted_payload["canonical_name"] = normalized_name
        character_discovery_service.update_character_profile(
            window._current_project_root,
            persisted_payload,
        )
        saved_character_id = str(persisted_payload.get("character_id", ""))
        status_key = "status.character_saved"
    _sync_manifest_after_manual_change(window)
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


def handle_delete_character_requested(window: "MainWindow", character_id: str) -> None:
    """
    @brief      Confirm and delete one persisted character profile.
    @param[in]  window Main application window.
    @param[in]  character_id Target persisted character identifier.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.2.0
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
    _sync_manifest_after_manual_change(window)
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


def handle_character_profile_changed(
    window: "MainWindow",
    profile_payload: dict[str, object],
) -> None:
    """
    @brief      Persist one page profile payload through the explicit save path.
    @param[in]  window Main application window.
    @param[in]  profile_payload Character profile payload from the page.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.2.0
    """
    handle_save_character_requested(window, profile_payload)


def _start_operation(
    window: "MainWindow",
    operation_name: str,
    initial_message: str,
    worker_callable,
) -> None:
    """
    @brief      Execute one modal character-discovery operation lifecycle.
    @param[in]  window Main application window.
    @param[in]  operation_name Operator-facing operation title.
    @param[in]  initial_message Initial progress-dialog message.
    @param[in]  worker_callable Callable performing the background operation.
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
            progress_callback=lambda current, total, percent, message, token_usage=None: (
                misc_ui_controller.update_progress_dialog(
                    window,
                    percent,
                    message,
                    token_usage,
                )
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
    @brief      Persist manifest state after a successful discovery run.
    @param[in]  window Main application window.
    @param[in]  report Final character-discovery report payload.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    _ = report
    assert window._current_project_root is not None
    assert window._current_manifest is not None
    operation_state = character_discovery_service.load_operation_state(window._current_project_root)
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


def _sync_manifest_after_manual_change(window: "MainWindow") -> None:
    """
    @brief      Refresh manifest operation state after manual character maintenance.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-11
    @version    0.2.0
    """
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operation_state = character_discovery_service.load_operation_state(window._current_project_root)
    if operation_state is not None:
        operations["character_discovery"] = project_workspace_service.project_manifest_operation_summary(
            "character_discovery",
            operation_state,
        )
    updated_manifest["operations"] = operations
    updated_manifest["current_stage"] = "character_discovery_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)


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
    if window._current_project_root is None or window._current_manifest is None:
        return
    updated_manifest = dict(window._current_manifest)
    operations = text_cleanup_state_service.normalized_manifest_operations(updated_manifest)
    operation_state = character_discovery_service.load_operation_state(window._current_project_root)
    if operation_state is not None:
        operations["character_discovery"] = project_workspace_service.project_manifest_operation_summary(
            "character_discovery",
            operation_state,
        )
    updated_manifest["operations"] = operations
    updated_manifest["current_stage"] = "translation_ready"
    project_workspace_service.save_manifest(updated_manifest, window._current_project_root)
    window.show_project_state(
        window._current_project_root,
        project_workspace_service.load_manifest(window._current_project_root),
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
    cancel_button = message_box.addButton(
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


def _confirm_delete_character(window: "MainWindow", language: str) -> bool:
    """
    @brief      Ask the operator to confirm deletion of the selected character.
    @param[in]  window Main application window.
    @param[in]  language Runtime UI language code.
    @return     `True` when deletion was confirmed.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    return (
        QMessageBox.question(
            window,
            ui_state_service.translate("dialog.character_delete_title", language),
            ui_state_service.translate("dialog.character_delete_message", language),
        )
        == QMessageBox.StandardButton.Yes
    )


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
    return {
        "character_id": draft_id,
        "canonical_name": canonical_name,
        "aliases": [],
        "gender_hint": "",
        "age_band": "",
        "role_summary": "",
        "description": "",
        "temperament": "",
        "social_status": "",
        "speaking_style": "",
        "accent_or_dialect_hints": "",
        "voice_notes": "",
        "relationship_hints": [],
        "confidence": "",
        "evidence": [
            {
                "chunk_id": character_discovery_service.MANUAL_CHARACTER_EVIDENCE_CHUNK_ID,
                "sequence_index": 0,
                "source_excerpt": character_discovery_service.MANUAL_CHARACTER_EVIDENCE_NOTE,
                "reason": character_discovery_service.MANUAL_CHARACTER_EVIDENCE_NOTE,
            }
        ],
        "updated_at": None,
    }


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
    return bool(
        character_discovery_service.load_operation_state(window._current_project_root)
        or character_discovery_service.load_character_discovery_report(window._current_project_root)
        or character_discovery_service.load_character_profiles(window._current_project_root)
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
    if not isinstance(settings_payload, dict):
        return None
    if selected_profile_id in (None, ""):
        return None
    for profile in list(settings_payload.get("llm_profiles", [])):
        if not isinstance(profile, dict):
            continue
        if not bool(profile.get("enabled", True)):
            continue
        if str(profile.get("id", "")).strip() == str(selected_profile_id):
            return dict(profile)
    return None


def _effective_profile_id(window: "MainWindow", selected_profile_id: str) -> str:
    """
    @brief      Prefer the persisted resume profile when discovery already started.
    @param[in]  window Main application window.
    @param[in]  selected_profile_id Newly selected profile identifier.
    @return     Effective profile identifier for the next discovery run.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    if window._current_project_root is None:
        return selected_profile_id
    operation_state = character_discovery_service.load_operation_state(window._current_project_root)
    if isinstance(operation_state, dict):
        metadata = operation_state.get("metadata", {})
        if isinstance(metadata, dict):
            persisted_profile_id = str(metadata.get("ai_profile_id", "")).strip()
            if persisted_profile_id:
                return persisted_profile_id
    return selected_profile_id


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
    return bool(deterministic_chunking_service.load_chunks(project_root))


def _cancel_active_operation(window: "MainWindow") -> None:
    """
    @brief      Mark the active character-discovery operation for cancellation.
    @param[in]  window Main application window.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    window._operation_cancel_requested = True


def _is_cancel_requested(window: "MainWindow") -> bool:
    """
    @brief      Read the current cancellation flag for the active operation.
    @param[in]  window Main application window.
    @return     `True` when cancellation was requested.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-08
    @version    0.1.0
    """
    return bool(window._operation_cancel_requested)


# END OF FILE
