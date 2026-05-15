#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_home_page.py
@brief Home page widget tests for AudioMancer.
@details Verifies the export panel rows, readiness buttons, and runtime
         language application.
@author Eng. Dan Dumitru Pasare
@date 2026-05-14
@version 0.5.0
"""

# IMPORTS

from PySide6.QtWidgets import QScrollArea

from audiomancer import config
from audiomancer.services import project_export_service, ui_theme_service
from audiomancer.ui.pages.home_page import HomeProjectPage

# PUBLIC API


def test_home_page_export_panel_widgets_exist(qtbot) -> None:
    """
    @brief      Verify the Home page builds one export row per supported export kind.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.1
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    assert page._snapshot_button.text() == "Export Project ZIP"
    assert page._snapshot_button.isEnabled() is False
    assert page._exports_group.title() == "Exports"
    assert set(page._export_rows) == set(project_export_service.EXPORT_KIND_OPTIONS)
    assert len(page._stage_rows) == 9
    assert page._stage_list.count() == 9
    for stage_row in page._stage_rows:
        assert stage_row.isReadOnly() is True
    for row in page._export_rows.values():
        assert set(row) == {"format", "button"}
        assert row["format"].count() == 2
        assert row["button"].text() == "Export"


def test_home_page_uses_compact_non_scrolled_dashboard(qtbot) -> None:
    """
    @brief      Verify the Home page no longer adds a duplicate page title or page-local scroll area.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-06
    @version    0.1.0
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    assert hasattr(page, "_title_label") is False
    assert page.findChild(QScrollArea) is None
    assert page._stage_rows[0].minimumHeight() == 28


def test_home_page_project_snapshot_button_follows_project_and_busy_state(qtbot) -> None:
    """
    @brief      Verify the project ZIP export button follows project and operation state.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.3.0
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    page.set_project_state("Project", "D:/Project", "source_selected")
    assert page._snapshot_button.isEnabled() is True

    page.set_operation_busy(True)
    assert page._snapshot_button.isEnabled() is False

    page.set_operation_busy(False)
    assert page._snapshot_button.isEnabled() is True


def test_home_page_export_buttons_follow_readiness_state(qtbot) -> None:
    """
    @brief      Verify export buttons enable only for available artifacts.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    page.set_export_states(
        [
            {
                "export_kind": project_export_service.EXPORT_KIND_CLEANED_TEXT,
                "status": project_export_service.EXPORT_STATUS_AVAILABLE,
                "can_export": True,
            },
            {
                "export_kind": project_export_service.EXPORT_KIND_TEXT_CHUNKS,
                "status": project_export_service.EXPORT_STATUS_MISSING_ARTIFACT,
                "can_export": False,
            },
        ]
    )

    assert page._export_rows[project_export_service.EXPORT_KIND_CLEANED_TEXT]["button"].isEnabled() is True
    assert page._export_rows[project_export_service.EXPORT_KIND_TEXT_CHUNKS]["button"].isEnabled() is False
    assert (
        page._export_rows[project_export_service.EXPORT_KIND_TEXT_CHUNKS]["button"].toolTip()
        == "Text Chunks: Missing artifact"
    )


def test_home_page_language_application_updates_export_labels(qtbot) -> None:
    """
    @brief      Verify runtime language changes update export panel labels.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.1.0
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    page.apply_language("ro")

    assert page._snapshot_button.text() == "Exporta ZIP Proiect"
    assert page._exports_group.title() == "Exporturi"
    assert page._export_rows[project_export_service.EXPORT_KIND_CLEANED_TEXT]["button"].text() == "Exporta"
    assert (
        page._export_rows[project_export_service.EXPORT_KIND_CLEANED_TEXT]["button"]
        .toolTip()
        .startswith("Text Curatat:")
    )


def test_home_page_project_options_lock_controls_source_import(qtbot) -> None:
    """
    @brief      Verify source import, ZIP export, and project locking follow project state.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.3.0
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    page.set_project_active(True)
    page.set_project_options(False, "ro", "same_narrator")

    assert page._import_button.isEnabled() is True
    assert page._snapshot_button.isEnabled() is True
    assert page._target_language_caption.text() == "Translation language"
    assert page._narration_mode_caption.text() == "Audio output style"
    assert page._target_language_combo.isEnabled() is True
    assert page._narration_mode_combo.isEnabled() is True
    assert page._start_project_button.isEnabled() is False

    page.set_source_locked(True, "story.txt")

    assert page._import_button.isEnabled() is True
    assert page._start_project_button.isEnabled() is True
    assert "Selected source: story.txt" in page._source_lock_label.text()

    page.set_project_options(True, "ro", "same_narrator")

    assert page._import_button.isEnabled() is False
    assert page._snapshot_button.isEnabled() is True
    assert "Locked source: story.txt" in page._source_lock_label.text()
    assert page._target_language_combo.isEnabled() is False
    assert page._narration_mode_combo.isEnabled() is False
    assert page._start_project_button.isEnabled() is False


def test_home_page_stage_rows_use_theme_status_roles(qtbot) -> None:
    """
    @brief      Verify Home workflow status rows use runtime theme color roles.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)
    theme_payload = ui_theme_service.validate_theme_payload(
        {
            "schema_version": config.UI_THEME_SCHEMA_VERSION,
            "theme_id": "home_theme",
            "display_name": "Home Theme",
            "built_in": False,
            "font": {},
            "colors": {
                "panel_background": "#FEFEFE",
                "border": "#112233",
                "disabled": "#445566",
                "warning": "#778899",
                "success": "#AABBCC",
                "danger": "#DDEEFF",
                "text_primary": "#010203",
            },
        }
    )

    page.apply_theme(theme_payload)
    page.set_stage_statuses(
        [
            {"label": "Draft", "status": "not_started", "note": ""},
            {"label": "Working", "status": "in_progress", "note": ""},
            {"label": "Done", "status": "finished", "note": ""},
        ]
    )

    assert "color: #445566;" in page._stage_rows[0].styleSheet()
    assert "color: #778899;" in page._stage_rows[1].styleSheet()
    assert "color: #AABBCC;" in page._stage_rows[2].styleSheet()
    assert "border: 1px solid #112233;" in page._stage_rows[0].styleSheet()
    assert "background: #FEFEFE;" in page._stage_rows[0].styleSheet()


def test_home_page_theme_fallback_keeps_source_lock_style_valid(qtbot) -> None:
    """
    @brief      Verify partial or malformed theme payloads fall back to built-in color roles.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    page.apply_theme({"colors": {"danger": "not-a-color"}})
    page.set_project_active(True)
    page.set_source_locked(True, "story.txt")
    page.set_project_options(True, "en", "same_narrator")

    default_theme = ui_theme_service.theme_by_id(ui_theme_service.default_theme_id(), [])
    default_colors = default_theme["colors"]
    assert isinstance(default_colors, dict)
    assert f"color: {default_colors['danger']};" in page._source_lock_label.styleSheet()


# END OF FILE
