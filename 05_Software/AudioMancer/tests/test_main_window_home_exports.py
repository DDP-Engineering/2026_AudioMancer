#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_main_window_home_exports.py
@brief Main-window Home export refresh tests for AudioMancer.
@details Verifies the main-window project refresh pushes export readiness into
         the Home export panel.
"""

# IMPORTS

import pytest

from audiomancer import config
from audiomancer.services import project_export_service, project_workspace_service
from audiomancer.ui.main_window import MainWindow
from audiomancer.ui.pages.home_page import HomeProjectPage

# PUBLIC API


def test_main_window_refreshes_home_export_readiness(qtbot, tmp_path, default_settings_payload) -> None:
    """
    @brief      Verify show_project_state updates Home export button readiness.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("HomeExportProject", tmp_path)
    manifest["source_document"] = {
        "original_name": "story.txt",
        "stored_relative_path": "story.txt",
        "file_type": "txt",
        "imported_at": "2026-04-25T12:00:00+00:00",
        "size_bytes": 12,
    }
    manifest["operations"]["cleanup"]["status"] = "completed"
    (project_root / config.CLEANED_TEXT_FILE_NAME).write_text("Ready text.\n", encoding="utf-8")

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window.show_project_state(project_root, manifest)

    assert window._home_page._export_rows[project_export_service.EXPORT_KIND_CLEANED_TEXT]["button"].isEnabled() is True
    assert window._home_page._export_rows[project_export_service.EXPORT_KIND_TEXT_CHUNKS]["button"].isEnabled() is False


def test_main_window_opens_project_with_invalid_character_document(qtbot, tmp_path, default_settings_payload) -> None:
    """
    @brief      Verify an invalid Character Discovery artifact leaves its Home export unavailable.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  tmp_path Pytest temporary directory fixture.
    @param[in]  default_settings_payload Fixture supplying default test settings.
    @return     None.
    @exception  None
    """
    project_root, manifest = project_workspace_service.create_project("InvalidCharacters", tmp_path)
    manifest["operations"]["character_discovery"]["status"] = "completed"
    (project_root / config.CHARACTERS_DOCUMENT_FILE_NAME).write_text("{}\n", encoding="utf-8")

    window = MainWindow(settings_payload=dict(default_settings_payload))
    qtbot.addWidget(window)
    window.show_project_state(project_root, manifest)

    assert window._current_project_root == project_root
    assert window._home_page._export_rows[project_export_service.EXPORT_KIND_CHARACTERS]["button"].isEnabled() is False


@pytest.mark.parametrize(("language", "label"), [("en", "Export partial ZIP"), ("ro", "Exportă ZIP parțial")])
def test_home_displays_partial_assembly_export(qtbot, language, label) -> None:
    """An available partial archive has a distinct button label in both languages."""
    page = HomeProjectPage()
    qtbot.addWidget(page)
    page.apply_language(language)
    page.set_export_states([{"export_kind": "audio_assembly", "status": "partial", "can_export": True}])

    button = page._export_rows["audio_assembly"]["button"]
    assert button.isEnabled()
    assert button.text() == label


# END OF FILE
