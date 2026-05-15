#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ui_state_service.py
@brief Focused tests for the runtime UI-state service.
@details Verifies translated string lookup and application-wide text-scale
         changes used by the settings-backed runtime UI behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-04-05
@version 0.6.0
"""

# IMPORTS

from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from audiomancer import config
from audiomancer.services import ui_state_service, ui_theme_service

# HELPER FUNCTIONS


def _custom_theme(**overrides) -> dict[str, object]:
    """
    @brief      Build one valid custom theme payload for UI-state tests.
    @param[in]  overrides Theme field overrides.
    @return     Valid custom theme payload.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    theme_payload = {
        "schema_version": config.UI_THEME_SCHEMA_VERSION,
        "theme_id": "runtime_theme",
        "display_name": "Runtime Theme",
        "built_in": False,
        "font": {"family": "", "point_size": None, "scale": "normal"},
        "colors": {
            "window_background": "#101820",
            "panel_background": "#F8FBFF",
            "text_primary": "#1B1F24",
            "text_muted": "#5B6670",
            "accent": "#1F6FEB",
            "border": "#7D8790",
            "warning": "#B26A00",
            "success": "#1A7F37",
            "danger": "#A40E26",
            "disabled": "#8C959F",
        },
    }
    theme_payload.update(overrides)
    return theme_payload


def _restore_application_state(application: QApplication, font: QFont, palette: QPalette, stylesheet: str) -> None:
    """
    @brief      Restore global Qt application state changed by theme tests.
    @param[in]  application Running Qt application instance.
    @param[in]  font Font to restore.
    @param[in]  palette Palette to restore.
    @param[in]  stylesheet Stylesheet to restore.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    application.setFont(font)
    application.setPalette(palette)
    application.setStyleSheet(stylesheet)
    ui_state_service._BASE_FONT_FAMILY = None
    ui_state_service._BASE_FONT_POINT_SIZE = None


# PUBLIC API


def test_translate_returns_expected_english_and_romanian_strings() -> None:
    """
    @brief      Verify the UI string catalog resolves EN and RO labels.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    assert ui_state_service.translate("toolbar.settings", "en") == "Settings"
    assert ui_state_service.translate("toolbar.settings", "ro") == "Setari"
    assert ui_state_service.translate("sidebar.text_chunking", "ro") == "Segmentare Text"


def test_v2_selective_impact_strings_cover_supported_languages() -> None:
    """
    @brief      Verify v2 selective-impact labels and confirmations exist in EN and RO.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-04
    @version    0.2.0
    """
    required_keys = (
        "dialog.confirm_cleaned_text_edit_title",
        "project.confirm_cleaned_text_edit",
        "dialog.confirm_chunk_insert_title",
        "dialog.confirm_chunk_delete_title",
        "project.confirm_chunk_edit",
        "project.confirm_chunk_insert",
        "project.confirm_chunk_delete",
        "dialog.character_add_confirm_title",
        "dialog.character_add_confirm_message",
        "dialog.character_edit_title",
        "dialog.character_edit_message",
        "dialog.character_delete_title",
        "dialog.character_delete_message",
        "project.confirm_speech_block_audio_reset",
        "project.confirm_speech_block_sequence_change",
        "audio_blocks.unapprove_selected",
        "project.confirm_audio_block_regeneration",
        "project.confirm_audio_block_approval_change",
        "project.confirm_single_voice_target_invalidation",
        "project.confirm_narrator_voice_invalidation",
        "project.confirm_global_voice_settings_invalidation",
        "project.confirm_audio_assembly_settings_change",
        "status.audio_assembly_settings_saved_reset",
    )

    for language in ("en", "ro"):
        for key in required_keys:
            assert ui_state_service.translate(key, language) != key


def test_theme_settings_strings_cover_supported_languages() -> None:
    """
    @brief      Verify theme-management labels and messages exist in EN and RO.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    required_keys = (
        "settings.theme_group",
        "settings.apply",
        "settings.ok",
        "settings.theme",
        "settings.theme_new",
        "settings.theme_duplicate",
        "settings.theme_delete",
        "settings.theme_import",
        "settings.theme_export",
        "settings.theme_import_failed",
        "settings.theme_export_failed",
        "settings.theme_import_too_large",
        "settings.theme_imported",
        "settings.theme_exported",
        "settings.theme_name",
        "settings.theme_font_family",
        "settings.theme_text_font_family",
        "settings.theme_font_size",
        "settings.theme_text_font_size",
        "settings.theme_colors",
        "settings.theme_preview",
        "settings.theme_preview_label",
        "settings.theme_preview_input",
        "settings.theme_preview_button",
        "settings.theme_preview_status",
        "settings.theme_builtin_readonly",
        "settings.theme_color_window_background",
        "settings.theme_color_panel_background",
        "settings.theme_color_text_primary",
        "settings.theme_color_text_muted",
        "settings.theme_color_accent",
        "settings.theme_color_border",
        "settings.theme_color_success",
        "settings.theme_color_warning",
        "settings.theme_color_danger",
        "settings.theme_color_disabled",
        "settings.theme_color.window_background",
        "settings.theme_color.panel_background",
        "settings.theme_color.text_primary",
        "settings.theme_color.text_muted",
        "settings.theme_color.accent",
        "settings.theme_color.border",
        "settings.theme_color.success",
        "settings.theme_color.warning",
        "settings.theme_color.danger",
        "settings.theme_color.disabled",
        "dialog.theme_name_title",
        "dialog.theme_name_prompt",
        "dialog.theme_delete_title",
        "dialog.theme_delete_message",
        "dialog.theme_import_title",
        "dialog.theme_export_title",
        "dialog.theme_import_error_title",
        "dialog.theme_export_error_title",
        "status.theme_imported",
        "status.theme_exported",
        "status.theme_deleted",
    )

    for language in ("en", "ro"):
        for key in required_keys:
            translated_value = ui_state_service.translate(key, language)
            assert translated_value != key
            assert translated_value.strip()


def test_apply_text_scale_updates_application_font(qtbot) -> None:
    """
    @brief      Verify one UI text-scale preset updates the application font.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-04-05
    @version    0.1.0
    """
    application = QApplication.instance()
    original_font = QFont(application.font())
    original_palette = QPalette(application.palette())
    original_stylesheet = application.styleSheet()

    ui_state_service._BASE_FONT_FAMILY = None
    ui_state_service._BASE_FONT_POINT_SIZE = None
    try:
        ui_state_service.apply_text_scale(application, "normal")
        normal_size = application.font().pointSizeF()

        ui_state_service.apply_text_scale(application, "very_large")
        large_size = application.font().pointSizeF()
    finally:
        _restore_application_state(application, original_font, original_palette, original_stylesheet)

    assert large_size > normal_size


def test_apply_theme_updates_application_font_family(qtbot) -> None:
    """
    @brief      Verify a theme can set the application font family.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    application = QApplication.instance()
    original_font = QFont(application.font())
    original_palette = QPalette(application.palette())
    original_stylesheet = application.styleSheet()
    theme_payload = _custom_theme(font={"family": "Courier New", "point_size": 11.0, "scale": "normal"})

    try:
        ui_state_service.apply_theme(application, theme_payload, "normal")
        themed_font = QFont(application.font())
    finally:
        _restore_application_state(application, original_font, original_palette, original_stylesheet)

    assert themed_font.family() == "Courier New"
    assert themed_font.pointSizeF() == 11.0


def test_apply_theme_updates_application_palette_roles(qtbot) -> None:
    """
    @brief      Verify a theme updates key application palette roles.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    application = QApplication.instance()
    original_font = QFont(application.font())
    original_palette = QPalette(application.palette())
    original_stylesheet = application.styleSheet()
    theme_payload = _custom_theme()

    try:
        ui_state_service.apply_theme(application, theme_payload, "normal")
        palette = QPalette(application.palette())
        stylesheet = application.styleSheet()
    finally:
        _restore_application_state(application, original_font, original_palette, original_stylesheet)

    assert palette.color(QPalette.ColorRole.Window).name().upper() == "#101820"
    assert palette.color(QPalette.ColorRole.Base).name().upper() == "#F8FBFF"
    assert palette.color(QPalette.ColorRole.Text).name().upper() == "#1B1F24"
    assert palette.color(QPalette.ColorRole.Highlight).name().upper() == "#1F6FEB"
    assert "QGroupBox" in stylesheet
    assert "#7D8790" in stylesheet


def test_build_theme_stylesheet_applies_text_window_font() -> None:
    """
    @brief      Verify text-window font settings are scoped to multi-line text editors.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.2.0
    """
    theme_payload = _custom_theme(
        font={"family": "Courier New", "point_size": 11.0, "scale": "normal"},
        text_font={"family": "Georgia", "point_size": 14.0, "scale": "large"},
    )

    stylesheet = ui_state_service.build_theme_stylesheet(theme_payload, base_point_size=10.0)

    assert "QTextEdit, QPlainTextEdit" in stylesheet
    assert "font-family: 'Georgia';" in stylesheet
    assert "font-size: 14.0pt;" in stylesheet
    assert f'QPlainTextEdit[{ui_state_service.CONTROL_TEXT_FONT_ROLE_PROPERTY}="' in stylesheet
    assert f'"{ui_state_service.CONTROL_TEXT_FONT_ROLE_VALUE}"]' in stylesheet
    assert "font-family: 'Courier New';" in stylesheet
    assert "font-size: 11.0pt;" in stylesheet


def test_apply_ui_settings_falls_back_to_default_theme_for_missing_theme_id(qtbot) -> None:
    """
    @brief      Verify missing selected theme ids fall back to the default built-in theme at runtime.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    application = QApplication.instance()
    main_window = QWidget()
    qtbot.addWidget(main_window)
    original_font = QFont(application.font())
    original_palette = QPalette(application.palette())
    original_stylesheet = application.styleSheet()
    settings_payload = {
        "language": config.DEFAULT_LANGUAGE,
        "ui_text_scale": config.DEFAULT_UI_TEXT_SCALE,
        "ui_theme_id": "missing_theme",
        "ui_themes": [_custom_theme()],
    }

    try:
        ui_state_service.apply_ui_settings(application, main_window, settings_payload)
        palette = QPalette(application.palette())
    finally:
        _restore_application_state(application, original_font, original_palette, original_stylesheet)

    default_theme = ui_theme_service.theme_by_id(ui_theme_service.default_theme_id(), [])
    default_colors = default_theme["colors"]
    assert isinstance(default_colors, dict)
    assert palette.color(QPalette.ColorRole.Window).name().upper() == default_colors["window_background"]


# END OF FILE
