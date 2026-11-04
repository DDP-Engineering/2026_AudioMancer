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

import json
from types import SimpleNamespace
import zipfile

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget
import pytest

from audiomancer import config
from audiomancer.services import (
    ai_translation_service,
    project_export_service,
    project_workspace_service,
)
from audiomancer.ui.controllers import home_ui_controller
from audiomancer.ui.main_window import MainWindow
from chunking_test_support import build_chunking_document

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

    source_path = tmp_path / "story.txt"
    source_path.write_text("A complete book.\n", encoding="utf-8")
    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(source_path), ""),
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
    assert window._current_manifest["source_document"] is not None
    assert (window._current_project_root / "story.txt").read_bytes() == source_path.read_bytes()
    assert window._current_manifest["selected_voice_language"] == window._current_manifest["target_language"]


@pytest.mark.parametrize("cancel_at", ["name", "document"])
def test_new_project_document_cancel_preserves_current_project(
    monkeypatch, qtbot, tmp_path, default_settings_payload, cancel_at
):
    """@brief Cancelling the book picker keeps the old project and creates no new folder."""
    current_root, manifest = project_workspace_service.create_project("CurrentProject", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    home_ui_controller.activate_project(window, current_root, manifest)
    window.set_current_page("text_cleanup")
    cleanup_page = window._text_cleanup_page
    cleanup_page.set_processing_state("source", "saved draft", [], True, True, True, "passed", 0)
    cleanup_page._edit_cleaned_button.click()
    cleanup_page._cleaned_text_edit.setPlainText("Keep this unsaved draft")
    monkeypatch.setattr(home_ui_controller.QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(home_ui_controller.QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    monkeypatch.setattr(
        home_ui_controller.QInputDialog, "getText", lambda *args: ("CancelledProject", cancel_at != "name")
    )
    monkeypatch.setattr(home_ui_controller.QFileDialog, "getOpenFileName", lambda *args: ("", ""))

    home_ui_controller.handle_new_project_requested(window)

    assert window._current_project_root == current_root
    assert not (tmp_path / "CancelledProject").exists()
    assert cleanup_page.has_modified_cleaned_text_draft()
    assert cleanup_page._cleaned_text_edit.toPlainText() == "Keep this unsaved draft"


def test_new_project_declined_cleanup_draft_discard_keeps_project_and_draft(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """@brief Verify declining the Cleanup-draft warning prevents the New picker."""
    current_root, current_manifest = project_workspace_service.create_project("CurrentDraft", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window.show_project_state(current_root, current_manifest)
    window.set_current_page("text_cleanup")
    cleanup_page = window._text_cleanup_page
    cleanup_page.set_processing_state("source", "saved draft", [], True, True, True, "passed", 0)
    cleanup_page._edit_cleaned_button.click()
    cleanup_page._cleaned_text_edit.setPlainText("exact unsaved draft")
    questions: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "question",
        lambda *args: questions.append(args) or QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *_args: (_ for _ in ()).throw(AssertionError("picker must not open after declined discard")),
    )

    home_ui_controller.handle_new_project_requested(window)

    assert len(questions) == 1
    assert questions[0][3] == QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    assert questions[0][4] == QMessageBox.StandardButton.No
    assert window._current_project_root == current_root
    assert window._current_manifest == current_manifest
    assert cleanup_page._cleaned_text_edit.toPlainText() == "exact unsaved draft"
    assert cleanup_page._editing_cleaned_text is True


def test_confirmed_new_project_picker_cancel_keeps_cleanup_draft(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """@brief Verify accepting the warning alone does not discard a Cleanup draft."""
    current_root, current_manifest = project_workspace_service.create_project("CurrentDraft", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window.show_project_state(current_root, current_manifest)
    window.set_current_page("text_cleanup")
    cleanup_page = window._text_cleanup_page
    cleanup_page.set_processing_state("source", "saved draft", [], True, True, True, "passed", 0)
    cleanup_page._edit_cleaned_button.click()
    cleanup_page._cleaned_text_edit.setPlainText("exact unsaved draft")
    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(home_ui_controller.QFileDialog, "getExistingDirectory", lambda *_args: "")

    home_ui_controller.handle_new_project_requested(window)

    assert window._current_project_root == current_root
    assert window._current_manifest == current_manifest
    assert cleanup_page._cleaned_text_edit.toPlainText() == "exact unsaved draft"
    assert cleanup_page._editing_cleaned_text is True


def test_open_project_declined_cleanup_draft_discard_keeps_project_and_draft(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """@brief Verify declining the Cleanup-draft warning prevents the Open picker."""
    current_root, current_manifest = project_workspace_service.create_project("CurrentDraft", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window.show_project_state(current_root, current_manifest)
    window.set_current_page("text_cleanup")
    cleanup_page = window._text_cleanup_page
    cleanup_page.set_processing_state("source", "saved draft", [], True, True, True, "passed", 0)
    cleanup_page._edit_cleaned_button.click()
    cleanup_page._cleaned_text_edit.setPlainText("exact unsaved draft")
    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *_args: (_ for _ in ()).throw(AssertionError("picker must not open after declined discard")),
    )

    home_ui_controller.handle_open_project_requested(window)

    assert window._current_project_root == current_root
    assert cleanup_page._cleaned_text_edit.toPlainText() == "exact unsaved draft"
    assert cleanup_page._editing_cleaned_text is True


def test_confirmed_new_project_activation_clears_old_draft_and_loads_new_text(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """@brief Verify a successful confirmed activation replaces the old Cleanup draft."""
    current_root, current_manifest = project_workspace_service.create_project("CurrentDraft", tmp_path)
    new_root, new_manifest = project_workspace_service.create_project("NewProject", tmp_path)
    (new_root / config.CLEANED_TEXT_FILE_NAME).write_text("new authoritative text", encoding="utf-8")
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window.show_project_state(current_root, current_manifest)
    window.set_current_page("text_cleanup")
    cleanup_page = window._text_cleanup_page
    cleanup_page.set_processing_state("source", "saved draft", [], True, True, True, "passed", 0)
    cleanup_page._edit_cleaned_button.click()
    cleanup_page._cleaned_text_edit.setPlainText("exact unsaved draft")
    monkeypatch.setattr(home_ui_controller.QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(home_ui_controller.QFileDialog, "getExistingDirectory", lambda *_args: str(tmp_path))
    monkeypatch.setattr(home_ui_controller.QInputDialog, "getText", lambda *_args: ("NewProject", True))
    monkeypatch.setattr(
        home_ui_controller.project_options_service,
        "create_project_with_source",
        lambda *_args: (new_root, new_manifest),
    )

    monkeypatch.setattr(
        home_ui_controller.QFileDialog, "getOpenFileName", lambda *args: (str(tmp_path / "book.txt"), "")
    )
    home_ui_controller.handle_new_project_requested(window)
    window.set_current_page("text_cleanup")

    assert window._current_project_root == new_root
    assert cleanup_page._editing_cleaned_text is False
    assert cleanup_page._cleaned_text_edit.toPlainText() == "new authoritative text"


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


def test_home_ui_controller_contains_project_creation_filesystem_error(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """@brief Verify a project-creation filesystem failure leaves Home state unchanged."""
    existing_root, existing_manifest = project_workspace_service.create_project(
        "ExistingCreationProject",
        tmp_path,
    )
    expected_error = PermissionError("selected project parent is read-only")
    warnings = []
    activations = []
    success_messages = []
    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        home_ui_controller.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("NewProject", True),
    )
    monkeypatch.setattr(
        home_ui_controller.project_options_service,
        "create_project_with_source",
        lambda *_args: (_ for _ in ()).throw(expected_error),
    )
    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )
    monkeypatch.setattr(
        home_ui_controller,
        "activate_project",
        lambda *args: activations.append(args),
    )
    monkeypatch.setattr(
        home_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args: success_messages.append(args),
    )
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._current_project_root = existing_root
    window._current_manifest = existing_manifest

    monkeypatch.setattr(
        home_ui_controller.QFileDialog, "getOpenFileName", lambda *args: (str(tmp_path / "book.txt"), "")
    )
    home_ui_controller.handle_new_project_requested(window)

    assert warnings == [
        (
            window,
            home_ui_controller.ui_state_service.translate("dialog.project_error_title", "en"),
            str(expected_error),
        )
    ]
    assert window._current_project_root == existing_root
    assert window._current_manifest is existing_manifest
    assert activations == []
    assert success_messages == []


def test_home_ui_controller_contains_source_import_filesystem_error(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """@brief Verify a source-import filesystem failure preserves the active project."""
    project_root, manifest = project_workspace_service.create_project("ImportFailureProject", tmp_path)
    expected_error = PermissionError("source copy is not permitted")
    warnings = []
    state_updates = []
    success_messages = []
    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(tmp_path / "story.txt"), ""),
    )
    monkeypatch.setattr(
        home_ui_controller.project_options_service.import_service,
        "import_source",
        lambda *_args: (_ for _ in ()).throw(expected_error),
    )
    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )
    monkeypatch.setattr(
        home_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args: success_messages.append(args),
    )
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._current_project_root = project_root
    window._current_manifest = manifest
    monkeypatch.setattr(window, "show_project_state", lambda *args: state_updates.append(args))

    home_ui_controller.handle_import_source_requested(window)

    assert warnings == [
        (
            window,
            home_ui_controller.ui_state_service.translate("dialog.project_error_title", "en"),
            str(expected_error),
        )
    ]
    assert window._current_project_root == project_root
    assert window._current_manifest is manifest
    assert state_updates == []
    assert success_messages == []


def test_home_ui_controller_contains_confirmed_repair_filesystem_error(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """@brief Verify a confirmed project-repair filesystem failure preserves Home state."""
    existing_root, existing_manifest = project_workspace_service.create_project(
        "ExistingRepairProject",
        tmp_path,
    )
    selected_root = tmp_path / "RepairTarget"
    expected_error = OSError("project manifest cannot be replaced")
    warnings = []
    activations = []
    success_messages = []
    open_result = {
        "status": "repair_required",
        "project_root": str(selected_root),
        "manifest": {"display_name": "RepairTarget"},
    }
    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(selected_root),
    )
    monkeypatch.setattr(
        home_ui_controller.project_workspace_service,
        "open_project",
        lambda *_args: open_result,
    )
    monkeypatch.setattr(
        home_ui_controller,
        "confirm_project_repair",
        lambda *_args: True,
    )
    monkeypatch.setattr(
        home_ui_controller.project_workspace_service,
        "repair_project",
        lambda *_args: (_ for _ in ()).throw(expected_error),
    )
    monkeypatch.setattr(
        home_ui_controller.QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )
    monkeypatch.setattr(
        home_ui_controller,
        "activate_project",
        lambda *args: activations.append(args),
    )
    monkeypatch.setattr(
        home_ui_controller.misc_ui_controller,
        "show_message",
        lambda *args: success_messages.append(args),
    )
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._current_project_root = existing_root
    window._current_manifest = existing_manifest

    home_ui_controller.handle_open_project_requested(window)

    assert warnings == [
        (
            window,
            home_ui_controller.ui_state_service.translate("dialog.project_error_title", "en"),
            str(expected_error),
        )
    ]
    assert window._current_project_root == existing_root
    assert window._current_manifest is existing_manifest
    assert activations == []
    assert success_messages == []


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
    selected_path = tmp_path / "outside" / "voices.final"
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
    assert archive_calls[0][3] == selected_path.with_name("voices.final.zip")


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
    @brief      Verify the Home ZIP button remains clickable for a project with a registered source.
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

    assert window._home_page._source_label.text() == "Source: Command Performance.pdf"
    assert window._home_page._snapshot_button.isEnabled() is True

    qtbot.mouseClick(window._home_page._snapshot_button, Qt.MouseButton.LeftButton)

    with zipfile.ZipFile(selected_path) as zip_file:
        names = set(zip_file.namelist())
    assert f"{project_root.name}/project.json" in names
    assert f"{project_root.name}/runtime.txt" in names
    assert messages


def test_home_ui_controller_autosaves_project_options_in_manifest(
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
        home_ui_controller,
        "confirm_project_options_change",
        lambda *args, **kwargs: True,
        raising=False,
    )
    monkeypatch.setattr(home_ui_controller.misc_ui_controller, "show_message", lambda *args: messages.append(args))

    home_ui_controller.handle_project_options_change_requested(window, "ro", "same_narrator")

    saved_manifest = project_workspace_service.load_manifest(project_root)
    assert saved_manifest["project_options_locked"] is False
    assert saved_manifest["target_language"] == "ro"
    assert saved_manifest["selected_voice_language"] == "ro"
    assert saved_manifest["voice_assignment_mode"] == "same_narrator"
    assert not hasattr(window._home_page, "_import_button")
    assert messages


def test_home_ui_controller_import_saves_selected_project_options(
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
    assert saved_manifest["project_options_locked"] is True
    assert saved_manifest["target_language"] == "fr"
    assert saved_manifest["selected_voice_language"] == "fr"
    assert saved_manifest["voice_assignment_mode"] == "same_narrator"
    assert window._home_page._target_language_combo.currentData() == "fr"


def test_home_ui_controller_keeps_processed_source_fixed(
    monkeypatch,
    tmp_path,
) -> None:
    """
    @brief      Verify a registered source cannot be replaced even in a legacy unlocked project.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("ProcessedReplacement", tmp_path)
    old_source = project_root / "old_story.txt"
    old_source.write_text("old source", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": old_source.name,
        "stored_relative_path": old_source.name,
        "file_type": "txt",
        "imported_at": "2026-08-02T12:00:00+00:00",
        "size_bytes": old_source.stat().st_size,
    }
    manifest["current_stage"] = "audio_assembly_ready"
    manifest["project_options_locked"] = False
    manifest["target_language"] = "ro"
    manifest["selected_voice_language"] = "en"
    manifest["voice_assignment_mode"] = "same_narrator"
    manifest["operations"] = {
        operation_kind: project_workspace_service.project_manifest_operation_summary(
            operation_kind,
            {
                "status": "completed",
                "progress_current": 1,
                "progress_total": 1,
                "mode": "test",
                "warning_count": 1,
            },
        )
        for operation_kind in config.WORKFLOW_OPERATION_ORDER
    }
    project_workspace_service.save_manifest(manifest, project_root)
    manifest = project_workspace_service.load_manifest(project_root)

    stale_artifact_names = (
        config.EXTRACTED_TEXT_FILE_NAME,
        config.SOURCE_LEDGER_FILE_NAME,
        config.EXTRACTION_METADATA_FILE_NAME,
        config.CLEANED_TEXT_FILE_NAME,
        config.CLEANUP_DOCUMENT_FILE_NAME,
        config.CHUNK_ARTIFACT_FILE_NAME,
        config.TRANSLATED_CHUNKS_FILE_NAME,
        config.CHARACTERS_DOCUMENT_FILE_NAME,
        config.NARRATOR_VOICE_FILE_NAME,
        config.CHARACTER_VOICES_TARGETS_FILE_NAME,
        config.SPEECH_BLOCKS_DOCUMENT_FILE_NAME,
        config.AUDIO_BLOCKS_DOCUMENT_FILE_NAME,
        config.AUDIO_BLOCKS_VOICE_CLONE_PROFILES_FILE_NAME,
        config.AUDIO_ASSEMBLY_REPORT_FILE_NAME,
        config.AUDIO_ASSEMBLY_STATE_FILE_NAME,
    )
    stale_artifact_paths = [project_root / name for name in stale_artifact_names]
    for artifact_path in stale_artifact_paths:
        artifact_path.write_text("stale", encoding="utf-8")
    stale_generated_audio = project_root / config.AUDIO_BLOCKS_GENERATED_AUDIO_FOLDER_NAME / "stale.wav"
    stale_generated_audio.parent.mkdir()
    stale_generated_audio.write_bytes(b"stale audio")
    stale_assembly_audio = project_root / config.AUDIOBOOK_OUTPUT_FOLDER_NAME / "stale.wav"
    stale_assembly_audio.parent.mkdir()
    stale_assembly_audio.write_bytes(b"stale assembly")

    new_source = tmp_path / config.EXTRACTED_TEXT_FILE_NAME
    new_source.write_text("new source", encoding="utf-8")
    refreshed_manifests = []
    window = SimpleNamespace(
        _settings_payload={"language": "en"},
        _current_project_root=project_root,
        _current_manifest=manifest,
        _home_page=SimpleNamespace(
            selected_project_options=lambda: ("de", "narrator_and_characters"),
        ),
        show_project_state=lambda _root, updated: refreshed_manifests.append(updated),
    )
    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(new_source), ""),
    )
    monkeypatch.setattr(home_ui_controller.misc_ui_controller, "show_message", lambda *args: None)

    warnings = []
    monkeypatch.setattr(home_ui_controller.QMessageBox, "warning", lambda *args: warnings.append(args))
    before = {
        path.relative_to(project_root).as_posix(): path.read_bytes()
        for path in project_root.rglob("*")
        if path.is_file()
    }
    home_ui_controller.handle_import_source_requested(window)
    after = {
        path.relative_to(project_root).as_posix(): path.read_bytes()
        for path in project_root.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert warnings
    assert refreshed_manifests == []


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


def test_home_ui_controller_preserves_dotted_export_destination(
    monkeypatch,
    qtbot,
    tmp_path,
    default_settings_payload,
) -> None:
    """
    @brief      Verify Home exports append extensions after the requested dotted name.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("DottedExport", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window._current_project_root = project_root
    window._current_manifest = manifest
    selected_path = tmp_path / "outside" / "draft.final"
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
        lambda *args, **kwargs: (str(selected_path), ""),
    )
    monkeypatch.setattr(home_ui_controller.project_export_service, "render_export", lambda *args, **kwargs: "content")

    home_ui_controller.handle_export_requested(
        window,
        project_export_service.EXPORT_KIND_CLEANED_TEXT,
        project_export_service.EXPORT_FORMAT_TXT,
    )

    assert selected_path.with_name("draft.final.txt").read_text(encoding="utf-8") == "content"
    assert not selected_path.with_name("draft.txt").exists()


def test_home_ui_controller_reselects_stored_source_without_reset(monkeypatch, tmp_path) -> None:
    """
    @brief      Verify selecting the stored source leaves the manifest and artifacts unchanged.
    @param[in]  monkeypatch Pytest monkeypatch fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("SameSource", tmp_path)
    source_path = project_root / "story.txt"
    source_path.write_text("stored source", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": source_path.name,
        "stored_relative_path": source_path.name,
        "file_type": "txt",
        "imported_at": "2026-08-07T12:00:00+00:00",
        "size_bytes": source_path.stat().st_size,
    }
    manifest["current_stage"] = "source_selected"
    project_workspace_service.save_manifest(manifest, project_root)
    artifact_path = project_root / "extracted_text.txt"
    artifact_path.write_text("preserved artifact", encoding="utf-8")
    before = {
        path.relative_to(project_root).as_posix(): path.read_bytes()
        for path in project_root.rglob("*")
        if path.is_file()
    }
    refreshed_manifests = []
    window = SimpleNamespace(
        _settings_payload={"language": "en"},
        _current_project_root=project_root,
        _current_manifest=project_workspace_service.load_manifest(project_root),
        _home_page=SimpleNamespace(selected_project_options=lambda: ("en", "narrator_and_characters")),
        show_project_state=lambda _root, updated: refreshed_manifests.append(updated),
    )
    monkeypatch.setattr(
        home_ui_controller.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(source_path), ""),
    )
    monkeypatch.setattr(home_ui_controller.misc_ui_controller, "show_message", lambda *args: None)

    monkeypatch.setattr(home_ui_controller.QMessageBox, "warning", lambda *args: None)
    home_ui_controller.handle_import_source_requested(window)

    after = {
        path.relative_to(project_root).as_posix(): path.read_bytes()
        for path in project_root.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert refreshed_manifests == []


def test_activate_project_flushes_translation_edit_and_displays_home(
    monkeypatch, qtbot, tmp_path, default_settings_payload
) -> None:
    """@brief Verify project activation flushes old edits before selecting the Home container."""
    project_root, manifest = project_workspace_service.create_project("ActivationTarget", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window.set_current_page("audio_blocks")
    calls = []
    monkeypatch.setattr(window._ai_translation_page, "flush_pending_translation_edit", lambda: calls.append("flush"))

    home_ui_controller.activate_project(window, project_root, manifest)

    assert calls == ["flush"]
    assert window._current_page_id == "home"
    assert window._stack.currentWidget() is window._page_containers["home"]


# END OF FILE


@pytest.mark.parametrize("language", ["en", "ro"])
@pytest.mark.parametrize("change", ["language", "mode"])
def test_home_option_cancel_restores_saved_selection(
    monkeypatch, qtbot, tmp_path, default_settings_payload, language, change
):
    """@brief Declining a change restores both selectors and all persisted bytes."""
    root, manifest = project_workspace_service.create_project("CancelOptions", tmp_path)
    manifest["project_options_locked"] = True
    manifest["operations"]["translation"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, root)
    settings = dict(default_settings_payload, language=language)
    window = MainWindow(settings_payload=settings)
    qtbot.addWidget(window)
    window.show_project_state(root, manifest)
    before = (root / config.PROJECT_MANIFEST_FILE_NAME).read_bytes()
    prompts = []
    monkeypatch.setattr(
        home_ui_controller, "confirm_project_options_change", lambda *args: prompts.append(args) or False, raising=False
    )
    combo = (
        window._home_page._target_language_combo if change == "language" else window._home_page._narration_mode_combo
    )
    selected = "ro" if change == "language" else "same_narrator"
    combo.setCurrentIndex(combo.findData(selected))
    combo.activated.emit(combo.currentIndex())
    assert len(prompts) == 1
    assert (root / config.PROJECT_MANIFEST_FILE_NAME).read_bytes() == before
    assert window._home_page._target_language_combo.currentData() == "en"
    assert window._home_page._narration_mode_combo.currentData() == "narrator_and_characters"


def test_home_language_selection_saves_without_confirmation_on_empty_project(
    monkeypatch, qtbot, tmp_path, default_settings_payload
):
    """@brief Choosing a language immediately persists it without a Start button."""
    root, manifest = project_workspace_service.create_project("AutoLanguage", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window.show_project_state(root, manifest)
    monkeypatch.setattr(
        home_ui_controller,
        "confirm_project_options_change",
        lambda *args: pytest.fail("Empty language change should save directly"),
        raising=False,
    )
    combo = window._home_page._target_language_combo
    combo.setCurrentIndex(combo.findData("ro"))
    combo.activated.emit(combo.currentIndex())
    saved = project_workspace_service.load_manifest(root)
    assert saved["target_language"] == saved["selected_voice_language"] == "ro"
    assert window._current_manifest["target_language"] == "ro"
    assert not hasattr(window._home_page, "_start_project_button")


def test_home_option_handlers_reject_busy_changes(monkeypatch, qtbot, tmp_path, default_settings_payload):
    """@brief Direct requests cannot mutate options or import while a worker runs."""
    root, manifest = project_workspace_service.create_project("BusyOptions", tmp_path)
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window.show_project_state(root, manifest)
    window._active_operation_kind = "cleanup"
    before = (root / config.PROJECT_MANIFEST_FILE_NAME).read_bytes()
    monkeypatch.setattr(home_ui_controller.QFileDialog, "getOpenFileName", lambda *args: pytest.fail("Busy picker"))
    try:
        home_ui_controller.handle_project_options_change_requested(window, "ro", "same_narrator")
        home_ui_controller.handle_import_source_requested(window)
        assert (root / config.PROJECT_MANIFEST_FILE_NAME).read_bytes() == before
    finally:
        window._active_operation_kind = None


@pytest.mark.parametrize("language", ["en", "ro"])
@pytest.mark.parametrize("accept", [False, True])
def test_project_options_confirmation_buttons_and_actual_impact(qtbot, tmp_path, language, accept):
    """@brief Real modal confirmations localize the impact and default to cancellation."""
    root, _manifest = project_workspace_service.create_project("DialogOptions", tmp_path)
    (root / "log_ai_speech_blocks_1.log").write_text("Existing operation log", encoding="utf-8")
    plan = home_ui_controller.project_options_service.plan_project_options_change(root, "en", "same_narrator")
    parent = QWidget()
    qtbot.addWidget(parent)
    dialogs = []

    def respond():
        """@brief Click the explicit requested button in the live modal dialog."""
        dialog = QApplication.activeModalWidget()
        dialogs.append(dialog)
        role = QMessageBox.ButtonRole.AcceptRole if accept else QMessageBox.ButtonRole.RejectRole
        button = next(button for button in dialog.buttons() if dialog.buttonRole(button) == role)
        button.click()

    QTimer.singleShot(0, respond)
    result = home_ui_controller.confirm_project_options_change(parent, plan, language)
    assert result is accept
    dialog = dialogs[0]
    translate = home_ui_controller.ui_state_service.translate
    assert dialog.defaultButton().text() == translate("project.options_cancel", language)
    assert dialog.textFormat() == Qt.TextFormat.PlainText
    assert translate("project.options_reset.speech_blocks", language) in dialog.text()
    assert "log_ai_speech_blocks_1.log" in dialog.detailedText()
    details_button = next(
        button for button in dialog.buttons() if dialog.buttonRole(button) == QMessageBox.ButtonRole.ActionRole
    )
    assert details_button.text() == translate("project.options_show_details", language)
    details_button.click()
    assert details_button.text() == translate("project.options_hide_details", language)
    assert translate("project.options_reset.translation", language) not in dialog.text()
    assert (root / "log_ai_speech_blocks_1.log").exists()


@pytest.mark.parametrize("language", ["en", "ro"])
def test_empty_mode_confirmation_reports_no_existing_results(tmp_path, language):
    """@brief A fresh project's mode change explicitly reports no files to delete."""
    root, _ = project_workspace_service.create_project("NoResults", tmp_path)
    plan = home_ui_controller.project_options_service.plan_project_options_change(root, "en", "same_narrator")
    assert plan.requires_confirmation
    text = home_ui_controller.build_project_options_confirmation_message(plan, language)
    assert home_ui_controller.ui_state_service.translate("project.options_no_results", language) in text
    assert home_ui_controller.ui_state_service.translate("project.options_reset_header", language) not in text


@pytest.mark.parametrize("language", ["en", "ro"])
def test_project_options_confirmation_distinguishes_progress_without_files(tmp_path, language):
    """@brief Summary-only resets explain that there are no files available under details."""
    root, manifest = project_workspace_service.create_project("ProgressOnly", tmp_path)
    manifest["operations"]["translation"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, root)
    plan = home_ui_controller.project_options_service.plan_project_options_change(root, "ro", "narrator_and_characters")
    assert plan.affected_operations and not plan.artifact_paths
    message = home_ui_controller.build_project_options_confirmation_message(plan, language)
    assert home_ui_controller.ui_state_service.translate("project.options_progress_only", language) in message


def test_home_option_failure_reports_error_and_restores_selection(monkeypatch, tmp_path):
    """@brief A failed confirmed save restores the saved selectors without success effects."""
    root, manifest = project_workspace_service.create_project("FailedOptions", tmp_path)
    restored = []
    warnings = []
    window = SimpleNamespace(
        _current_project_root=root,
        _current_manifest=manifest,
        _active_operation_kind=None,
        _settings_payload={"language": "ro"},
        _home_page=SimpleNamespace(set_project_options=lambda *args: restored.append(args)),
        _ai_translation_page=SimpleNamespace(flush_pending_translation_edit=lambda: None),
        stop_all_audio_playback=lambda: None,
        show_project_state=lambda *args: pytest.fail("Failure must not report success"),
    )

    def fail_apply(*args):
        """@brief Simulate a service error after its own transaction rollback."""
        raise PermissionError("Options could not be published")

    monkeypatch.setattr(home_ui_controller, "confirm_project_options_change", lambda *args: True)
    monkeypatch.setattr(home_ui_controller.project_options_service, "apply_project_options_change", fail_apply)
    monkeypatch.setattr(home_ui_controller.QMessageBox, "warning", lambda *args: warnings.append(args))
    home_ui_controller.handle_project_options_change_requested(window, "en", "same_narrator")
    assert restored == [(False, "en", "narrator_and_characters")]
    assert warnings[0][1] == home_ui_controller.ui_state_service.translate("dialog.project_error_title", "ro")
    assert "could not be published" in warnings[0][2]


@pytest.mark.parametrize("accept", [False, True])
@pytest.mark.parametrize("change", ["language", "mode"])
def test_home_option_change_settles_pending_translation_before_planning(
    monkeypatch, qtbot, tmp_path, default_settings_payload, accept, change
):
    """@brief Queued translation edits settle before confirmation and cannot run after reset."""
    root, manifest = project_workspace_service.create_project("PendingTranslation", tmp_path)
    (root / "story.txt").write_text("Original text", encoding="utf-8")
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-11-04T00:00:00Z",
        "size_bytes": 13,
    }
    manifest["target_language"] = "ro"
    manifest["current_stage"] = "text_chunking_ready"
    manifest["operations"]["chunking"]["status"] = "completed"
    project_workspace_service.save_manifest(manifest, root)
    (root / config.CHUNK_ARTIFACT_FILE_NAME).write_text(
        json.dumps(build_chunking_document([{"chunk_id": "chunk-0001", "sequence_index": 1, "text": "Original text"}])),
        encoding="utf-8",
    )
    ai_translation_service.write_translation_document(
        root,
        {
            "target_language": "ro",
            "status": "in_progress",
            "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "usage_available": False},
            "budget_metadata": {
                "context_window": 4096,
                "output_reserve_tokens": 512,
                "prompt_budget_tokens": 100,
                "text_budget_tokens": 2048,
                "safety_margin_tokens": 512,
            },
            "additional_translation_instructions": "",
            "chunks": [{"chunk_id": "chunk-0001", "translated_text": "Earlier translation", "approved": False}],
        },
    )
    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    home_ui_controller.activate_project(window, root, project_workspace_service.load_manifest(root))
    window.set_current_page("ai_translation")
    page = window._ai_translation_page
    page._translated_text_edit.setPlainText("Latest exact translation edit")
    page._edit_timer.stop()  # Deliver deterministically at the option-change boundary.
    assert page._pending_edit is not None
    window.set_current_page("home")

    def confirm_after_save(*args):
        """@brief Confirmation observes the latest committed edit rather than queued work."""
        document = ai_translation_service.load_translation_document(root)
        assert document["chunks"][0]["translated_text"] == "Latest exact translation edit"
        assert page._pending_edit is None
        assert not page._edit_timer.isActive()
        return accept

    monkeypatch.setattr(home_ui_controller, "confirm_project_options_change", confirm_after_save)
    target = "de" if change == "language" else "ro"
    mode = "same_narrator" if change == "mode" else "narrator_and_characters"
    home_ui_controller.handle_project_options_change_requested(window, target, mode)
    assert page._pending_edit is None
    page.flush_pending_translation_edit()
    if accept and change == "language":
        assert not (root / config.TRANSLATED_CHUNKS_FILE_NAME).exists()
    else:
        assert (
            ai_translation_service.load_translation_document(root)["chunks"][0]["translated_text"]
            == "Latest exact translation edit"
        )
