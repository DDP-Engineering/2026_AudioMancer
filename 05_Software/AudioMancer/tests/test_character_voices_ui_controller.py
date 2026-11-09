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

from audiomancer import config
from audiomancer.services import (
    character_discovery_service,
    character_voices_service,
    narrator_definition_service,
    operation_runtime_service,
    project_workspace_service,
    tts_budget_service,
    ui_state_service,
)
from audiomancer.services.persistence_service import ProjectFileRecoveryError
from audiomancer.ui.controllers import character_voices_ui_controller
from audiomancer.ui.main_window import MainWindow

_MULTILINE_PREVIEW_TEXT = (
    "She weighs each answer before she gives it, and the words arrive quiet but certain.\n"
    "Nothing in her tone hurries, and nothing in it asks to be forgiven."
)


def test_character_voices_ui_controller_edit_prompt_preserves_sample(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify Edit and Cancel leave the persisted sample and downstream audio alone.
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
    audio_path, document = character_voices_service.target_sample_paths(project_root, "character_alice")
    original_document = document.read_bytes()
    invalidated = []
    monkeypatch.setattr(
        character_voices_ui_controller.audio_blocks_ui_controller,
        "invalidate_audio_blocks_for_voice_targets",
        lambda _window, ids: invalidated.extend(ids),
    )
    monkeypatch.setattr(
        character_voices_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

    character_voices_ui_controller.handle_edit_prompt_requested(window, "character_alice")

    assert character_voices_service.has_target_sample(project_root, "character_alice")
    assert window._character_voices_page.is_edit_mode()
    window._character_voices_page._prompt_edit.setPlainText("Draft prompt.")
    window._character_voices_page._cancel_prompt_button.click()

    assert audio_path.read_bytes() == b"RIFF-character"
    assert document.read_bytes() == original_document
    assert invalidated == []



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


@pytest.mark.parametrize(
    ("error_code", "message_key"),
    [
        ("readonly_target", "voice_sample_import.error_readonly_target"),
        ("missing_target", "character_voices.error_target"),
    ],
)
def test_character_voices_edit_prompt_failure_shows_localized_warning(
    monkeypatch, qtbot, tmp_path, error_code, message_key
) -> None:
    """
    @brief      Verify rejected Character Voices edit targets produce localized operator feedback.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  error_code Service error token raised after confirmation.
    @param[in]  message_key Expected localized warning-message key.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesEditFailure")
    window = _build_window(qtbot, project_root)
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        character_voices_ui_controller.QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        character_voices_ui_controller.QMessageBox,
        "warning",
        lambda _window, title, message: warnings.append((title, message)),
    )
    monkeypatch.setattr(
        character_voices_ui_controller.character_voices_service,
        "begin_target_prompt_edit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError(error_code)),
    )
    monkeypatch.setattr(
        character_voices_ui_controller,
        "_sync_manifest_stage",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("failed edit must not synchronize state")),
    )

    character_voices_ui_controller.handle_edit_prompt_requested(window, "character_alice")

    assert warnings == [
        (
            ui_state_service.translate("dialog.project_error_title", "en"),
            ui_state_service.translate(message_key, "en"),
        )
    ]


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


def test_character_voices_page_activation_surfaces_corrupt_manifest_without_target_mutation(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify activation contains a corrupt manifest failure and preserves voice targets and page state.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(
        tmp_path,
        "CharacterVoicesCorruptManifestActivation",
    )
    window = _build_window(qtbot, project_root)
    targets_path = project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME
    target_bytes = targets_path.read_bytes()
    current_target_id = window._character_voices_page.current_target_id()
    (project_root / config.PROJECT_MANIFEST_FILE_NAME).write_text("{corrupt", encoding="utf-8")
    warning_calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        character_voices_ui_controller.QMessageBox,
        "warning",
        lambda *args, **_kwargs: warning_calls.append(args),
    )

    character_voices_ui_controller.handle_page_activated(window)

    assert len(warning_calls) == 1
    assert str(warning_calls[0][2]).strip()
    assert targets_path.read_bytes() == target_bytes
    assert window._character_voices_page.current_target_id() == current_target_id


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


def test_character_voices_first_entry_waits_for_persisted_targets_and_sample_evidence(qtbot, tmp_path) -> None:
    """
    @brief      Verify real first-page entry cannot promote Character Voices before targets and samples exist.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(
        tmp_path,
        "CharacterVoicesFirstEntry",
        initialize_voice_plan=False,
    )
    character_discovery_service.add_character_profile(project_root, "Bob")
    targets_path = project_root / config.CHARACTER_VOICES_TARGETS_FILE_NAME
    assert targets_path.is_file() is False

    window = MainWindow(settings_payload=_default_settings_payload())
    qtbot.addWidget(window)
    window._activate_project(project_root, project_workspace_service.load_manifest(project_root))

    window.set_current_page("character_voices")

    first_entry_manifest = project_workspace_service.load_manifest(project_root)
    first_entry_summary = first_entry_manifest["operations"]["character_voices"]
    assert targets_path.is_file() is True
    assert first_entry_manifest["current_stage"] == "narrator_definition_ready"
    assert first_entry_summary["status"] != "completed"

    character_voices_ui_controller.handle_page_activated(window)

    initialized_manifest = project_workspace_service.load_manifest(project_root)
    initialized_summary = initialized_manifest["operations"]["character_voices"]
    assert initialized_manifest["current_stage"] == "narrator_definition_ready"
    assert initialized_summary["status"] == "in_progress"
    assert initialized_summary["progress_current"] == 1
    assert initialized_summary["progress_total"] == 3

    for target_id in ("character_alice", "character_bob"):
        target_payload = character_voices_service.voice_target_by_id(project_root, target_id)
        assert target_payload is not None
        character_voices_service.store_target_sample(
            project_root,
            target_payload,
            "en",
            "She weighs each answer before she gives it, and the words arrive quiet but certain. "
            "Nothing in her tone hurries, and nothing in it asks to be forgiven.",
            {"generation_mode": "definition", "source_model_id": "qwen-designer"},
            "Character sample ready.",
            b"RIFF-character",
        )
    window._character_voices_page._targets = []

    character_voices_ui_controller.handle_page_activated(window)

    ready_manifest = project_workspace_service.load_manifest(project_root)
    ready_summary = ready_manifest["operations"]["character_voices"]
    assert ready_manifest["current_stage"] == "character_voices_ready"
    assert ready_summary["status"] == "completed"
    assert ready_summary["progress_current"] == 3
    assert ready_summary["progress_total"] == 3


def test_character_voices_import_oserror_stays_in_slot_without_success_side_effects(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify a filesystem import failure is warned and cannot enter success handling.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesImportOSError")
    window = _build_window(qtbot, project_root)
    warning_calls: list[tuple[object, ...]] = []
    success_calls: list[str] = []
    monkeypatch.setattr(
        character_voices_ui_controller.QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(tmp_path / "selected.wav"), "WAV"),
    )
    monkeypatch.setattr(
        character_voices_ui_controller.voice_sample_import_service,
        "validate_imported_wav_sample",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        character_voices_ui_controller.QInputDialog,
        "getMultiLineText",
        lambda *_args, **_kwargs: ("Imported transcript.", True),
    )
    monkeypatch.setattr(
        character_voices_ui_controller.audio_blocks_ui_controller,
        "confirm_single_voice_target_invalidation",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(character_voices_ui_controller, "_stop_preview_playback", lambda *_args: None)

    def _raise_import_oserror(*_args, **_kwargs) -> None:
        """
        @brief      Raise the filesystem failure injected at the service boundary.
        @return     None.
        @exception  OSError Always raised.
        """
        raise OSError("Unable to copy selected sample.")

    monkeypatch.setattr(character_voices_service, "import_target_sample", _raise_import_oserror)
    monkeypatch.setattr(
        character_voices_ui_controller.QMessageBox,
        "warning",
        lambda *args, **_kwargs: warning_calls.append(args),
    )
    monkeypatch.setattr(window, "show_project_state", lambda *_args, **_kwargs: success_calls.append("refresh"))
    monkeypatch.setattr(
        character_voices_ui_controller,
        "_sync_manifest_stage",
        lambda *_args, **_kwargs: success_calls.append("manifest"),
    )
    monkeypatch.setattr(
        character_voices_ui_controller.audio_blocks_ui_controller,
        "invalidate_audio_blocks_for_voice_targets",
        lambda *_args, **_kwargs: success_calls.append("invalidate"),
    )
    monkeypatch.setattr(
        character_voices_ui_controller.misc_ui_controller,
        "show_message",
        lambda *_args, **_kwargs: success_calls.append("notification"),
    )

    character_voices_ui_controller.handle_import_sample_requested(window, "character_alice")

    assert len(warning_calls) == 1
    assert warning_calls[0][1] == "Project Error"
    assert warning_calls[0][2] == "Unable to copy selected sample."
    assert success_calls == []


@pytest.mark.parametrize("outcome", ["changed", "unchanged", "declined", "failed"])
def test_character_voices_ui_controller_save_prompt_persists_preview_text(
    monkeypatch, qtbot, tmp_path, outcome
) -> None:
    """
    @brief      Verify draft Save applies only confirmed, successfully published changes.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  outcome Simulated Save outcome.
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesControllerSave")
    target_id = "character_alice"
    target = character_voices_service.voice_target_by_id(project_root, target_id)
    assert target is not None
    character_voices_service.store_target_sample(
        project_root, target, "en", "Original transcript.", {}, "", b"RIFF-old"
    )
    audio, document = character_voices_service.target_sample_paths(project_root, target_id)
    window = _build_window(qtbot, project_root)
    original_document = document.read_bytes()
    confirmations = []
    warnings = []
    invalidations = []

    def _confirm_save(*_args):
        """@brief Record the confirmation and return the simulated decision."""
        confirmations.append(True)
        return QMessageBox.StandardButton.No if outcome == "declined" else QMessageBox.StandardButton.Yes

    def _fail_publish(*_args):
        """@brief Fail the draft publication before it can change artifacts."""
        raise OSError("Unable to save prompt.")

    monkeypatch.setattr(QMessageBox, "question", _confirm_save)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append(True))
    monkeypatch.setattr(character_voices_ui_controller.misc_ui_controller, "show_message", lambda *_args: None)
    monkeypatch.setattr(
        character_voices_ui_controller.audio_blocks_ui_controller,
        "invalidate_audio_blocks_for_voice_targets",
        lambda _window, ids: invalidations.extend(ids),
    )
    if outcome == "failed":
        monkeypatch.setattr(character_voices_service, "replace_project_files", _fail_publish)

    character_voices_ui_controller.handle_edit_prompt_requested(window, target_id)
    page = window._character_voices_page
    if outcome != "unchanged":
        page._prompt_edit.setPlainText("Updated prompt.")
        page._preview_text_edit.setPlainText(_MULTILINE_PREVIEW_TEXT)
    page._save_prompt_button.click()

    assert page.is_edit_mode() == (outcome in {"declined", "failed"})
    assert confirmations == ([] if outcome == "unchanged" else [True])
    assert warnings == ([True] if outcome == "failed" else [])
    if outcome == "changed":
        updated = character_voices_service.voice_target_by_id(project_root, target_id)
        assert updated["preview_text"] == _MULTILINE_PREVIEW_TEXT
        assert str(updated["prompt_text"]).startswith("Updated prompt.")
        assert updated["sample_metadata"] is None
        assert not audio.exists()
        assert invalidations == [target_id]
    else:
        assert audio.read_bytes() == b"RIFF-old"
        assert document.read_bytes() == original_document
        assert invalidations == []


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


@pytest.mark.parametrize(
    "outcome", ["success", "cancelled", "failed", "failed_first", "recovery_failed", "recovery_invalidation_failed"]
)
def test_character_voices_ui_controller_batch_invalidates_only_saved_targets(
    monkeypatch, qtbot, tmp_path, outcome
) -> None:
    """
    @brief      Verify batch completion invalidates exactly the successfully published samples.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  outcome Simulated batch outcome.
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
    bob_audio, voice_document = character_voices_service.target_sample_paths(project_root, "character_bob")
    voice_backup = tmp_path / "voice_plan_backup.json"
    window = _build_window(qtbot, project_root)
    window._current_page_id = "character_voices"
    window._settings_payload["tts_runtime_probe_succeeded"] = True
    window._settings_payload["tts_runtime_discovered_models"] = [
        {
            "model_id": "qwen-base",
            "backend_name": "qwen3-tts-base",
            "status": "healthy",
            "supported_generation_modes": ["clone"],
        },
        {
            "model_id": "qwen-designer",
            "backend_name": "qwen3-tts-voice-designer",
            "status": "healthy",
            "supported_generation_modes": ["voice_design"],
        },
    ]
    window._refresh_character_voices_page_state(
        project_root,
        project_workspace_service.load_manifest(project_root),
        "en",
    )
    generated_target_ids: list[str] = []
    operation_kinds: list[str] = []
    invalidations: list[tuple[tuple[str, ...], bool]] = []
    warnings: list[str] = []
    recovery_failed = outcome in {"recovery_failed", "recovery_invalidation_failed"}

    def _capture_invalidation(_window, ids, *, refresh_project_state=True):
        """@brief Record the affected IDs and optionally simulate a locked Audio Blocks document."""
        invalidations.append((ids, refresh_project_state))
        if outcome == "recovery_invalidation_failed":
            raise OSError("Audio metadata is locked.")

    monkeypatch.setattr(
        character_voices_ui_controller.audio_blocks_ui_controller,
        "invalidate_audio_blocks_for_voice_targets",
        _capture_invalidation,
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda _window, _title, message: warnings.append(message))
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
        @brief      Store a test sample or fail without contacting VoiceWeaver.
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
        if recovery_failed and generated_target_ids:
            voice_document.replace(voice_backup)
            raise ProjectFileRecoveryError(f"Originals retained in {voice_backup}")
        if outcome == "failed_first" or (outcome == "failed" and generated_target_ids):
            raise RuntimeError("Voice generation failed.")
        character_voices_service.store_target_sample(
            _project_root, target_payload, _voice_language, _preview_text, {}, "", b"RIFF-generated"
        )
        generated_target_ids.append(str(target_payload["target_id"]))

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
        try:
            result = worker_callable(
                window._current_project_root,
                dict(window._current_manifest),
                progress_callback=lambda *_args, **_kwargs: None,
                cancel_requested=lambda: outcome == "cancelled" and bool(generated_target_ids),
            )
        except operation_runtime_service.OperationCancelledError as error:
            cancel_handler(str(error))
        except (RuntimeError, ProjectFileRecoveryError) as error:
            failure_handler(error)
        else:
            success_handler(result)


    monkeypatch.setattr(
        character_voices_ui_controller.operation_runner_controller,
        "start_threaded_operation",
        _start_threaded_operation,
    )

    character_voices_ui_controller.handle_generate_missing_samples_requested(window)

    assert operation_kinds == ["character_voices_generate_all_samples"]
    expected = {
        "success": ("character_alice", "character_bob"),
        "cancelled": ("character_alice",),
        "failed": ("character_alice",),
        "failed_first": (),
        "recovery_failed": ("character_alice",),
        "recovery_invalidation_failed": ("character_alice",),
    }[outcome]
    assert tuple(generated_target_ids) == expected
    assert invalidations == ([(expected, not recovery_failed)] if expected else [])
    if recovery_failed:
        assert voice_backup.is_file()
        assert not voice_document.exists()
        assert len(warnings) == 1
        assert f"Originals retained in {voice_backup}" in warnings[0]
        if outcome == "recovery_invalidation_failed":
            assert "Audio metadata is locked." in warnings[0]
    assert bob_audio.read_bytes() == (b"RIFF-generated" if outcome == "success" else b"RIFF-bob")


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


def test_cancelled_character_sample_batch_refreshes_partial_page_and_manifest(
    monkeypatch, qtbot, tmp_path
) -> None:
    """
    @brief      Verify cancellation refreshes durably stored partial batch progress before status.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesPartialCancel")
    character_discovery_service.add_character_profile(project_root, "Bob")
    selected_narrator_id = narrator_definition_service.load_selected_profile_state(project_root)["selected_profile_id"]
    selected_narrator = narrator_definition_service.profile_by_id(project_root, selected_narrator_id)
    character_voices_service.sync_voice_plan(
        project_root,
        character_discovery_service.load_character_profiles(project_root),
        selected_narrator,
    )
    window = _build_window(qtbot, project_root)
    assert all(
        target["has_sample"] is False
        for target in window._character_voices_page._targets
        if target["target_kind"] == character_voices_service.TARGET_KIND_CHARACTER
    )
    alice_target = character_voices_service.voice_target_by_id(project_root, "character_alice")
    assert alice_target is not None
    character_voices_service.store_target_sample(
        project_root,
        alice_target,
        "en",
        "Alice preview.",
        {"generation_mode": "definition", "source_model_id": "qwen-designer"},
        "Alice sample ready.",
        b"RIFF-alice",
    )
    message_observations: list[tuple[dict[str, bool], dict[str, object]]] = []
    monkeypatch.setattr(
        character_voices_ui_controller.settings_service,
        "load_settings",
        lambda: _default_settings_payload(),
    )

    def _capture_message(*_args, **_kwargs) -> None:
        """
        @brief      Capture page and manifest state when cancellation is presented.
        @return     None.
        @exception  None
        """
        page_samples = {
            str(target["target_id"]): bool(target["has_sample"])
            for target in window._character_voices_page._targets
            if target["target_kind"] == character_voices_service.TARGET_KIND_CHARACTER
        }
        manifest_summary = project_workspace_service.load_manifest(project_root)["operations"]["character_voices"]
        message_observations.append((page_samples, manifest_summary))

    monkeypatch.setattr(character_voices_ui_controller.misc_ui_controller, "show_message", _capture_message)

    character_voices_ui_controller._handle_generate_sample_cancelled(window, "cancelled", "en")

    assert message_observations == [
        (
            {"character_alice": True, "character_bob": False},
            {
                "status": "in_progress",
                "progress_current": 2,
                "progress_total": 3,
                "mode": "manual",
                "warning_count": 0,
            },
        )
    ]


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
            "She weighs each answer before she gives it, and the words arrive quiet but certain. "
            "Nothing in her tone hurries, and nothing in it asks to be forgiven.",
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
            "She weighs each answer before she gives it, and the words arrive quiet but certain. "
            "Nothing in her tone hurries, and nothing in it asks to be forgiven.",
            None,
            lambda: False,
        )

    assert audio_path.read_bytes() == b"RIFF-original"
    assert character_voices_service.load_target_sample_metadata(project_root, "character_alice") == original_metadata


def test_character_shared_runtime_keeps_target_persistence_and_refresh(monkeypatch) -> None:
    """
    @brief      Verify shared runtime data remains owned by character persistence and refresh paths.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @return     None.
    @exception  None
    """
    target = {
        "target_id": "character_alice",
        "target_kind": "character",
        "prompt_text": "Bright character.",
    }
    generation_request = {
        "can_generate": True,
        "model_id": "voice-designer",
        "language": "ro",
    }
    stored_arguments: list[tuple[object, ...]] = []
    refresh_calls: list[tuple[object, object]] = []

    def _run_shared_runtime(
        _settings,
        _messages,
        request_builder,
        prompt_text,
        preview_text,
        _progress_callback,
        _cancel_requested,
        *,
        default_language,
    ):
        """@brief Return shared runtime data after exercising character request construction."""
        assert default_language == "ro"
        assert request_builder([{"model_id": "voice-designer"}]) == generation_request
        assert prompt_text == "Bright character."
        assert preview_text == "Character preview."
        return {
            "generation_request": generation_request,
            "result_summary": "Character sample ready.",
            "audio_bytes": b"RIFF-character",
        }

    monkeypatch.setattr(
        character_voices_ui_controller.tts_runtime_ui_support,
        "run_voice_design_generation",
        _run_shared_runtime,
    )
    monkeypatch.setattr(
        character_voices_ui_controller.character_voices_service,
        "voice_target_generation_request",
        lambda _target, _models, _language: generation_request,
    )
    monkeypatch.setattr(
        character_voices_ui_controller.character_voices_service,
        "store_target_sample",
        lambda *args: stored_arguments.append(args),
    )

    character_voices_ui_controller._generate_and_store_sample(
        "project-root",
        {},
        {},
        target,
        "ro",
        "Character preview.",
        None,
        lambda: False,
    )

    assert stored_arguments == [
        (
            "project-root",
            target,
            "ro",
            "Character preview.",
            generation_request,
            "Character sample ready.",
            b"RIFF-character",
        )
    ]

    window = SimpleNamespace(
        _settings_payload={"old": True},
        _character_voices_inspected_target_id=None,
        _current_project_root="project-root",
        show_project_state=lambda root, manifest: refresh_calls.append((root, manifest)),
    )
    invalidated_targets: list[tuple[str, ...]] = []
    monkeypatch.setattr(character_voices_ui_controller.settings_service, "load_settings", lambda: {"new": True})
    monkeypatch.setattr(
        character_voices_ui_controller.project_workspace_service,
        "load_manifest",
        lambda _root: {"current_stage": "narrator_definition_ready"},
    )
    monkeypatch.setattr(character_voices_ui_controller, "_sync_manifest_stage", lambda _window: None)
    monkeypatch.setattr(
        character_voices_ui_controller.audio_blocks_ui_controller,
        "invalidate_audio_blocks_for_voice_targets",
        lambda _window, target_ids: invalidated_targets.append(target_ids),
    )
    monkeypatch.setattr(character_voices_ui_controller.misc_ui_controller, "show_message", lambda *_args: None)

    character_voices_ui_controller._handle_generate_sample_success(
        window,
        None,
        "character_alice",
        "en",
    )

    assert window._settings_payload == {"new": True}
    assert window._character_voices_inspected_target_id == "character_alice"
    assert refresh_calls == [("project-root", {"current_stage": "narrator_definition_ready"})]
    assert invalidated_targets == [("character_alice",)]


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
    initialize_voice_plan: bool = True,
):
    """
    @brief      Create one project containing a selected narrator and one character target.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  name Project display name.
    @param[in]  store_narrator_sample True when the narrator sample should be stored.
    @param[in]  initialize_voice_plan True when the Character Voices targets file should be initialized.
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
            "She weighs each answer before she gives it, and the words arrive quiet but certain. "
            "Nothing in her tone hurries, and nothing in it asks to be forgiven.",
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
    if initialize_voice_plan:
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
        "preview_text_out_of_range": "Between {minimum_words} and {maximum_words} words, currently {word_count}.",
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
        "tts_runtime_probe_succeeded": False,
        "tts_runtime_probe_message": "",
        "tts_runtime_discovered_models": [],
        "tts_runtime_active_model_id": None,
        "tts_audio_preview_timeout_seconds": 60,
        "tts_audio_generation_timeout_seconds": 300,
    }



def test_character_voices_ui_controller_save_blocks_out_of_range_preview_text(monkeypatch, qtbot, tmp_path) -> None:
    """
    @brief      Verify a character preview outside the shared word range blocks the save.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root = _create_project_with_character_and_selected_narrator(tmp_path, "CharacterVoicesControllerRange")
    window = _build_window(qtbot, project_root)
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        character_voices_ui_controller.QMessageBox,
        "warning",
        lambda _window, title, message: warnings.append((title, message)),
    )
    monkeypatch.setattr(
        character_voices_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args, **kwargs: None,
    )
    minimum_words, maximum_words = tts_budget_service.preview_word_bounds()

    character_voices_ui_controller.handle_save_prompt_requested(
        window,
        {
            "target_id": "character_alice",
            "prompt_text": "Updated prompt.",
            "preview_text": "Only five words here.",
        },
    )

    assert warnings == [
        (
            ui_state_service.translate("dialog.project_error_title", "en"),
            ui_state_service.translate("character_voices.error_preview_text_out_of_range", "en").format(
                word_count=4,
                minimum_words=minimum_words,
                maximum_words=maximum_words,
            ),
        )
    ]
    target_payload = character_voices_service.voice_target_by_id(project_root, "character_alice")
    assert target_payload is not None
    assert target_payload["prompt_text"] != "Updated prompt."


# END OF FILE
