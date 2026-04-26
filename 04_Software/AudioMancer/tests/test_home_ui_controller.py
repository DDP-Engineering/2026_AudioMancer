#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_home_ui_controller.py
@brief Home UI controller tests for AudioMancer.
@details Verifies the Home-page UI controller still drives project creation and
         activation correctly through the main-window shell.
@author Eng. Dan Dumitru Pasare
@date 2026-04-06
@version 0.5.1
"""

# IMPORTS

import zipfile

from audiomancer.services import project_export_service, project_workspace_service
from audiomancer.ui.controllers import home_ui_controller
from audiomancer.ui.main_window import MainWindow

# PUBLIC API


def test_home_ui_controller_creates_and_activates_project(
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    """
    @brief      Verify the Home UI controller creates and activates a new project.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-06
    @version    0.1.0
    """
    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        home_ui_controller.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("ControllerProject", True),
    )

    window = MainWindow(
        settings_payload={
            "language": "en",
            "ui_text_scale": "normal",
            "play_completion_beep": False,
            "llm_profiles": [],
            "default_ai_cleanup_profile_id": None,
            "default_ai_chunking_profile_id": None,
            "default_ai_chunking_strategy": "paragraph",
            "default_character_extraction_profile_id": None,
        }
    )
    qtbot.addWidget(window)

    home_ui_controller.handle_new_project_requested(window)

    assert window._current_project_root == tmp_path / "ControllerProject"
    assert window._current_manifest is not None
    assert window._current_manifest["display_name"] == "ControllerProject"


def test_home_ui_controller_rejects_export_inside_project(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify project exports cannot be saved inside the active runtime project root.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ExportRejectProject", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._current_project_root = project_root
    window._current_manifest = manifest
    warnings = []
    render_calls = []

    monkeypatch.setattr(
        home_ui_controller.project_export_service,
        "build_export_states",
        lambda *_args: [
            {
                "export_kind": project_export_service.EXPORT_KIND_CLEANED_TEXT,
                "status": project_export_service.EXPORT_STATUS_AVAILABLE,
                "can_export": True,
            }
        ],
    )
    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(project_root / "export.txt"), ""),
    )
    monkeypatch.setattr(home_ui_controller.QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args))
    monkeypatch.setattr(
        home_ui_controller.project_export_service,
        "render_export",
        lambda *args, **kwargs: render_calls.append(args),
    )

    home_ui_controller.handle_export_requested(
        window,
        project_export_service.EXPORT_KIND_CLEANED_TEXT,
        project_export_service.EXPORT_FORMAT_TXT,
    )

    assert warnings
    assert "outside the active project folder" in warnings[0][2]
    assert render_calls == []


def test_home_ui_controller_applies_selected_export_extension_and_writes_utf8(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify successful exports add the selected extension and write UTF-8 content.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ExportWriteProject", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._current_project_root = project_root
    window._current_manifest = manifest
    selected_path = tmp_path / "outside" / "romanian_export"

    monkeypatch.setattr(
        home_ui_controller.project_export_service,
        "build_export_states",
        lambda *_args: [
            {
                "export_kind": project_export_service.EXPORT_KIND_AI_TRANSLATION,
                "status": project_export_service.EXPORT_STATUS_AVAILABLE,
                "can_export": True,
            }
        ],
    )
    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(selected_path), ""),
    )
    monkeypatch.setattr(
        home_ui_controller.project_export_service,
        "render_export",
        lambda *args, **kwargs: "Text românesc cu ș, ț, ă.\n",
    )

    home_ui_controller.handle_export_requested(
        window,
        project_export_service.EXPORT_KIND_AI_TRANSLATION,
        project_export_service.EXPORT_FORMAT_MARKDOWN,
    )

    export_path = selected_path.with_suffix(".md")
    assert export_path.read_text(encoding="utf-8") == "Text românesc cu ș, ț, ă.\n"


def test_home_ui_controller_rejects_snapshot_inside_project(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify project ZIP snapshots cannot be saved inside the active project root.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("SnapshotRejectProject", tmp_path)
    manifest = project_workspace_service.lock_project_options(project_root, "en", "narrator_and_characters")
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._current_project_root = project_root
    window._current_manifest = manifest
    warnings = []
    create_calls = []

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(project_root / "snapshot.zip"), ""),
    )
    monkeypatch.setattr(home_ui_controller.QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args))
    monkeypatch.setattr(
        home_ui_controller.project_snapshot_service,
        "create_project_snapshot",
        lambda *args, **kwargs: create_calls.append(args),
    )

    home_ui_controller.handle_project_snapshot_requested(window)

    assert warnings
    assert "outside the active project folder" in warnings[0][2]
    assert create_calls == []


def test_home_ui_controller_blocks_snapshot_during_active_operation(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify project ZIP snapshots are blocked while a long operation is active.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("SnapshotBusyProject", tmp_path)
    manifest = project_workspace_service.lock_project_options(project_root, "en", "narrator_and_characters")
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._current_project_root = project_root
    window._current_manifest = manifest
    window._active_operation_kind = "text_cleanup"
    warnings = []
    dialog_calls = []

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: dialog_calls.append(args),
    )
    monkeypatch.setattr(home_ui_controller.QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args))

    home_ui_controller.handle_project_snapshot_requested(window)

    assert warnings
    assert "blocked while an operation is running" in warnings[0][2]
    assert dialog_calls == []


def test_home_ui_controller_applies_zip_extension_and_writes_snapshot(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify successful project ZIP snapshot export appends `.zip` and writes a readable archive.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    project_root, manifest = project_workspace_service.create_project("SnapshotWriteProject", tmp_path)
    manifest = project_workspace_service.lock_project_options(project_root, "en", "narrator_and_characters")
    (project_root / "runtime.txt").write_text("runtime payload\n", encoding="utf-8")
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._current_project_root = project_root
    window._current_manifest = manifest
    selected_path = tmp_path / "external" / "snapshot_without_extension"
    messages = []

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(selected_path), ""),
    )
    monkeypatch.setattr(home_ui_controller.misc_ui_controller, "show_message", lambda *args: messages.append(args))
    monkeypatch.setattr(
        home_ui_controller.operation_runner_controller,
        "start_threaded_operation",
        _run_threaded_operation_synchronously,
    )

    home_ui_controller.handle_project_snapshot_requested(window)

    snapshot_path = selected_path.with_suffix(".zip")
    with zipfile.ZipFile(snapshot_path) as zip_file:
        names = set(zip_file.namelist())
    assert f"{project_root.name}/project.json" in names
    assert f"{project_root.name}/runtime.txt" in names
    assert messages


def test_home_ui_controller_locks_project_options_in_manifest(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify Home option locking persists target language and narration mode.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("LockedOptionsProject", tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-26T12:00:00+00:00",
        "size_bytes": 5,
    }
    manifest["current_stage"] = "source_selected"
    project_workspace_service.save_manifest(manifest, project_root)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window.show_project_state(project_root, project_workspace_service.load_manifest(project_root))
    messages = []

    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "question",
        lambda *args, **kwargs: home_ui_controller.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(home_ui_controller.misc_ui_controller, "show_message", lambda *args: messages.append(args))

    home_ui_controller.handle_project_options_lock_requested(window, "ro", "same_narrator")

    saved_manifest = project_workspace_service.load_manifest(project_root)
    assert saved_manifest["project_options_locked"] is True
    assert saved_manifest["target_language"] == "ro"
    assert saved_manifest["selected_voice_language"] == "ro"
    assert saved_manifest["voice_assignment_mode"] == "same_narrator"
    assert window._home_page._import_button.isEnabled() is False
    assert messages


def test_home_ui_controller_import_preserves_unlocked_draft_project_options(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify source import keeps Home draft language and narration mode selections.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.1.0
    """
    project_root, manifest = project_workspace_service.create_project("ImportDraftOptionsProject", tmp_path)
    source_path = tmp_path / "story.txt"
    source_path.write_text("Story text.\n", encoding="utf-8")
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window.show_project_state(project_root, manifest)
    window._home_page._target_language_combo.setCurrentIndex(window._home_page._target_language_combo.findData("fr"))
    window._home_page._narration_mode_combo.setCurrentIndex(
        window._home_page._narration_mode_combo.findData("same_narrator")
    )

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(source_path), ""),
    )

    home_ui_controller.handle_import_source_requested(window)

    saved_manifest = project_workspace_service.load_manifest(project_root)
    assert saved_manifest["project_options_locked"] is False
    assert saved_manifest["target_language"] == "fr"
    assert saved_manifest["selected_voice_language"] == "fr"
    assert saved_manifest["voice_assignment_mode"] == "same_narrator"
    assert window._home_page._target_language_combo.currentData() == "fr"


def _run_threaded_operation_synchronously(
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
) -> None:
    """
    @brief      Execute a threaded operation inline for controller tests.
    @param[in]  window Active main window shell.
    @param[in]  operation_kind Stable operation token.
    @param[in]  operation_name Operator-facing operation name.
    @param[in]  initial_message Initial progress message.
    @param[in]  worker_callable Worker callable.
    @param[in]  set_busy Busy-state callback.
    @param[in]  success_handler Success callback.
    @param[in]  failure_handler Failure callback.
    @param[in]  cancel_handler Cancellation callback.
    @param[in]  cancellable Progress-dialog cancellation flag.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    _ = operation_kind
    _ = operation_name
    _ = initial_message
    _ = failure_handler
    _ = cancel_handler
    _ = cancellable
    set_busy(True)
    result = worker_callable(
        window._current_project_root,
        dict(window._current_manifest),
        progress_callback=lambda *_args: None,
        cancel_requested=lambda: False,
    )
    success_handler(result)
    set_busy(False)


# END OF FILE
