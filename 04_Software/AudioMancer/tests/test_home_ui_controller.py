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
         activation correctly through the main-window shell and presents
         project-open failures to the operator.
"""

# IMPORTS

import zipfile

from PySide6.QtCore import Qt

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


def test_home_ui_controller_project_dialogs_start_outside_the_install_root(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify both project dialogs start at the documents root, or at the open project.
    @details    Covers REQ-UX-de071609-49bf-486b-b2f7-810d4abc61ec / SPEC-DIALOG-START.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None.
    """
    documents_root = tmp_path / "Documents"
    documents_root.mkdir()
    start_directories = []

    monkeypatch.setattr(
        home_ui_controller.config,
        "resolve_user_documents_root",
        lambda: documents_root,
    )
    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: start_directories.append(args[2]) or "",
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    home_ui_controller.handle_new_project_requested(window)
    home_ui_controller.handle_open_project_requested(window)

    assert start_directories == [str(documents_root), str(documents_root)]

    projects_parent = tmp_path / "books"
    projects_parent.mkdir()
    project_root, manifest = project_workspace_service.create_project("DialogStartProject", projects_parent)
    window._current_project_root = project_root
    window._current_manifest = manifest
    start_directories.clear()

    home_ui_controller.handle_new_project_requested(window)
    home_ui_controller.handle_open_project_requested(window)

    assert start_directories == [str(project_root.parent), str(project_root)]


def test_home_ui_controller_shows_warning_for_open_project_error(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify expected project-open failures are presented without escaping the UI slot.
    @details    Covers REQ-UX-da3b47c4-e633-4132-b147-8e28e50ae0db / S-0001.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    """
    expected_errors = [
        PermissionError("chunks_text.json is locked"),
        ValueError("project manifest is invalid"),
    ]
    warnings = []

    def raise_expected_error(_selected_folder):
        """
        @brief      Raise the next expected project-open failure.
        @param[in]  _selected_folder Ignored folder selected by the controller.
        @return     None.
        @exception  PermissionError Raised for the filesystem-error branch.
        @exception  ValueError Raised for the invalid-project branch.
        """
        raise expected_errors[len(warnings)]

    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        home_ui_controller.project_workspace_service,
        "open_project",
        raise_expected_error,
    )
    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)

    home_ui_controller.handle_open_project_requested(window)
    home_ui_controller.handle_open_project_requested(window)

    assert [warning[0] for warning in warnings] == [window, window]
    assert [warning[1] for warning in warnings] == [
        home_ui_controller.ui_state_service.translate("dialog.project_error_title", "en"),
        home_ui_controller.ui_state_service.translate("dialog.project_error_title", "en"),
    ]
    assert [warning[2] for warning in warnings] == [str(error) for error in expected_errors]
    assert window._current_project_root is None
    assert window._current_manifest is None


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


def test_home_ui_controller_routes_zip_export_to_archive_writer(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify ZIP artifact exports use the archive writer and `.zip` extension.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("ArchiveExportProject", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._current_project_root = project_root
    window._current_manifest = manifest
    selected_path = tmp_path / "outside" / "voices"
    archive_calls = []

    monkeypatch.setattr(
        home_ui_controller.project_export_service,
        "build_export_states",
        lambda *_args: [
            {
                "export_kind": project_export_service.EXPORT_KIND_NARRATOR_VOICE,
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
        "create_archive_export",
        lambda *args, **kwargs: archive_calls.append(args),
    )
    monkeypatch.setattr(
        home_ui_controller.project_export_service,
        "render_export",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("render_export should not handle ZIP")),
    )

    home_ui_controller.handle_export_requested(
        window,
        project_export_service.EXPORT_KIND_NARRATOR_VOICE,
        project_export_service.EXPORT_FORMAT_ZIP,
    )

    assert archive_calls
    assert archive_calls[0][2] == project_export_service.EXPORT_KIND_NARRATOR_VOICE
    assert archive_calls[0][3] == selected_path.with_suffix(".zip")


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
    """
    project_root, manifest = project_workspace_service.create_project("SnapshotWriteProject", tmp_path)
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


def test_home_ui_controller_snapshot_button_click_exports_open_unlocked_project(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify the Home ZIP button exports an active project before option locking.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("SnapshotButtonProject", tmp_path)
    (project_root / "draft.txt").write_text("draft payload\n", encoding="utf-8")
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    home_ui_controller.activate_project(window, project_root, manifest)
    selected_path = tmp_path / "external" / "button_snapshot.zip"
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

    assert window._home_page._snapshot_button.isEnabled() is True

    qtbot.mouseClick(window._home_page._snapshot_button, Qt.MouseButton.LeftButton)

    with zipfile.ZipFile(selected_path) as zip_file:
        names = set(zip_file.namelist())
    assert f"{project_root.name}/project.json" in names
    assert f"{project_root.name}/draft.txt" in names
    assert messages


def test_home_ui_controller_snapshot_button_click_exports_locked_source_project(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify the Home ZIP button remains clickable when the locked-source note is visible.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("SnapshotLockedSourceProject", tmp_path)
    source_path = tmp_path / "Command Performance.pdf"
    source_path.write_text("source placeholder\n", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": source_path.name,
        "stored_relative_path": source_path.name,
        "file_type": "pdf",
        "imported_at": "2026-04-26T00:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["project_options_locked"] = True
    manifest["current_stage"] = "text_chunking_ready"
    project_workspace_service.save_manifest(manifest, project_root)
    (project_root / "runtime.txt").write_text("runtime payload\n", encoding="utf-8")
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    home_ui_controller.activate_project(window, project_root, manifest)
    selected_path = tmp_path / "external" / "locked_source_snapshot.zip"
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

    assert "Locked source: Command Performance.pdf" in window._home_page._source_lock_label.text()
    assert window._home_page._snapshot_button.isEnabled() is True

    qtbot.mouseClick(window._home_page._snapshot_button, Qt.MouseButton.LeftButton)

    with zipfile.ZipFile(selected_path) as zip_file:
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
