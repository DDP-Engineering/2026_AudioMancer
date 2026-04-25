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
@version 0.2.0
"""

# IMPORTS

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


# END OF FILE
