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
"""

# IMPORTS

from PySide6.QtWidgets import QScrollArea
import pytest

from audiomancer import config
from audiomancer.services import project_export_service, ui_theme_service
from audiomancer.ui.pages import home_page
from audiomancer.ui.pages.home_page import HomeProjectPage

# PUBLIC API


def test_home_page_export_panel_widgets_exist(qtbot) -> None:
    """
    @brief      Verify the Home page builds one export row per supported export kind.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
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
        assert row["button"].text() == "Export"
    for export_kind, row in page._export_rows.items():
        assert row["format"].count() == len(project_export_service.export_formats_for_kind(export_kind))
        assert row["format"].minimumHeight() == page._stage_rows[0].minimumHeight()
        assert row["button"].minimumHeight() == page._stage_rows[0].minimumHeight()
    for spacer in page._export_spacers:
        assert spacer.minimumHeight() == page._stage_rows[0].minimumHeight()
        assert spacer.maximumHeight() == page._stage_rows[0].maximumHeight()
    assert page._export_rows[project_export_service.EXPORT_KIND_NARRATOR_VOICE]["format"].currentData() == (
        project_export_service.EXPORT_FORMAT_ZIP
    )


def test_home_page_uses_compact_non_scrolled_dashboard(qtbot) -> None:
    """
    @brief      Verify the Home page uses a compact dashboard without a local scroll area.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    assert page.findChild(QScrollArea) is None
    assert page._stage_rows[0].minimumHeight() == 28


def test_home_page_project_snapshot_button_follows_project_and_busy_state(qtbot) -> None:
    """
    @brief      Verify the project ZIP export button follows project and operation state.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
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
    assert page._export_rows[project_export_service.EXPORT_KIND_AUDIO_ASSEMBLY]["format"].itemText(0) == "ZIP"


def test_home_page_source_and_options_have_independent_editability(qtbot) -> None:
    """@brief Registered books stay fixed while language and narration remain editable."""
    page = HomeProjectPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    page.set_project_options(False, "ro", "same_narrator")
    assert not hasattr(page, "_import_button")
    assert not hasattr(page, "_start_project_button")
    page.set_source_summary("story.txt")
    for locked in (False, True):
        page.set_project_options(locked, "ro", "same_narrator")
        assert page._target_language_combo.isEnabled()
        assert page._narration_mode_combo.isEnabled()
        assert page._source_label.text() == "Source: story.txt"
    page.set_operation_busy(True)
    assert not page._target_language_combo.isEnabled()
    assert not page._narration_mode_combo.isEnabled()


def test_home_page_refresh_emits_no_option_request(qtbot) -> None:
    """@brief Only deliberate combo activation requests automatic persistence."""
    page = HomeProjectPage()
    qtbot.addWidget(page)
    page.set_project_active(True)
    requests = []
    page.project_options_change_requested.connect(lambda *args: requests.append(args))
    page.set_project_options(True, "ro", "same_narrator")
    page.set_project_options(False, "de", "narrator_and_characters")
    page.apply_language("ro")
    assert requests == []
    page._target_language_combo.activated.emit(page._target_language_combo.currentIndex())
    assert requests == [("de", "narrator_and_characters")]


def test_home_page_stage_rows_use_theme_status_roles(qtbot) -> None:
    """
    @brief      Verify Home workflow status rows use runtime theme color roles.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
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


def test_home_page_theme_fallback_keeps_workflow_style_valid(qtbot) -> None:
    """
    @brief      Verify partial or malformed theme payloads fall back to built-in color roles.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    page.apply_theme({"colors": {"danger": "not-a-color"}})
    page.set_project_active(True)
    page.set_source_summary("story.txt")
    page.set_project_options(True, "en", "same_narrator")

    default_theme = ui_theme_service.theme_by_id(ui_theme_service.default_theme_id(), [])
    default_colors = default_theme["colors"]
    assert isinstance(default_colors, dict)
    page.set_stage_statuses([{"label": "Cleanup", "status": "not_started"}])
    assert f"border: 1px solid {default_colors['border']};" in page._stage_rows[0].styleSheet()


def test_home_page_has_workflow_stepper_matching_stage_count(qtbot) -> None:
    """
    @brief      Verify the Home page exposes a workflow stepper with one step per stage.
    @details    Covers REQ-UX-4e19bb60-74c3-4d60-9d8d-7da332c055ef / SPEC-HOME-STEPPER.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    stages = [
        {"label": f"Stage {index}", "status": "not_started", "note": ""} for index in range(len(page._stage_rows))
    ]
    page.set_stage_statuses(stages)

    assert hasattr(page, "_workflow_stepper")
    assert page._workflow_stepper.step_count() == len(page._stage_rows)


def test_home_page_workflow_stepper_reflects_status_tokens(qtbot) -> None:
    """
    @brief      Verify the stepper reports stage status tokens in provided order.
    @details    Covers REQ-UX-9920bf16-f2cc-4aa8-be6d-6572a11ec1d5 / SPEC-HOME-STEPPER-STATUS.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    stages = [
        {"label": "Text Cleanup", "status": "finished", "note": ""},
        {"label": "Text Chunking", "status": "in_progress", "note": ""},
        {"label": "AI Translation", "status": "not_started", "note": ""},
    ]
    page.set_stage_statuses(stages)

    assert page._workflow_stepper.statuses() == ["finished", "in_progress", "not_started"]


def test_home_page_project_title_uses_serif_font(qtbot) -> None:
    """
    @brief      Verify the project-name label uses the Georgia serif display family.
    @details    Covers REQ-UX-336e32b5-9d9e-4ab5-8a5c-e63b66631147 / SPEC-HOME-SERIF.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)

    assert page._name_label.font().family() == "Georgia"


@pytest.mark.parametrize(
    ("has_source", "options_locked", "source_name"),
    [
        (False, False, None),
        (True, False, "draft.txt"),
        (True, True, "locked.txt"),
    ],
)
def test_home_page_language_switch_preserves_all_source_statuses(
    qtbot,
    has_source: bool,
    options_locked: bool,
    source_name: str | None,
) -> None:
    """
    @brief      Verify language changes retain truthful source status and controls.
    @param[in]  qtbot Qt test helper fixture.
    @param[in]  has_source Whether a source is currently selected.
    @param[in]  options_locked Whether project options are locked.
    @param[in]  source_name Current source display name.
    @return     None.
    @exception  None
    """
    page = HomeProjectPage()
    qtbot.addWidget(page)
    page.set_project_state("Project", "/project", "source_selected")
    page.set_source_summary(source_name if has_source else None)
    page.set_project_options(options_locked, "en", "narrator_and_characters")

    page.apply_language("ro")

    assert page._source_label.text() == f"Sursa: {source_name or 'niciuna'}"
    assert not hasattr(page, "_import_button")


@pytest.mark.parametrize("stage_count", [9, 10])
@pytest.mark.parametrize("stepper_width", [360.0, 468.0, 640.0, 790.0, 1040.0, 1600.0])
def test_workflow_stepper_keeps_end_captions_inside_its_width(stepper_width, stage_count) -> None:
    """
    @brief      Verify the outermost stage captions are never drawn off the stepper.
    @details    Covers REQ-UX-bd974d8e: each caption is centred on its bead and is
                one bead spacing wide, so the bead inset has to be at least half a
                caption or the first and last stage names are clipped at the edges.
    @param[in]  stepper_width Stepper width in pixels.
    @param[in]  stage_count Number of workflow stages drawn.
    @return     None.
    @exception  None
    """
    margin_x, gap = home_page._stepper_bead_layout(stepper_width, stage_count)

    first_caption_left = margin_x - gap / 2.0
    last_caption_right = margin_x + (stage_count - 1) * gap + gap / 2.0

    assert first_caption_left >= 0.0
    assert last_caption_right <= stepper_width


# END OF FILE
