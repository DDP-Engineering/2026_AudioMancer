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
@date 2026-04-25
@version 0.4.1
"""

# IMPORTS

from audiomancer.services import project_export_service
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


def test_home_page_project_snapshot_button_follows_project_and_busy_state(qtbot) -> None:
    """
    @brief      Verify the project ZIP export button follows project and operation state.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-25
    @version    0.2.0
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    page.set_project_state("Project", "D:/Project", "source_selected")
    assert page._snapshot_button.isEnabled() is False

    page.set_project_options(True, "en", "narrator_and_characters")
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
    @brief      Verify source import and project locking follow selected source state.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-26
    @version    0.2.0
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    page.set_project_active(True)
    page.set_project_options(False, "ro", "same_narrator")

    assert page._import_button.isEnabled() is True
    assert page._snapshot_button.isEnabled() is False
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


# END OF FILE
