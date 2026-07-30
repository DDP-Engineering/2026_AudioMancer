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
@details Verifies translated string lookup, application-wide text-scale changes,
         and settings-backed runtime preference resolution used by the
         settings-backed runtime UI behavior.
@author Eng. Dan Dumitru Pasare
@date 2026-06-09
@version 0.8.0
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


def test_operator_status_pane_height_scales_with_line_count(qtbot) -> None:
    """
    @brief      Verify the operator-status pane height follows the requested row count.
    @details    Covers REQ-UX-032: the status pane uses a compact, font-aware
                three-row height derived from the reference widget font metrics.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-06-09
    @version    0.1.0
    """
    widget = QWidget()
    qtbot.addWidget(widget)

    line_height = widget.fontMetrics().lineSpacing()
    three_rows = ui_state_service.operator_status_pane_height(widget, 3)

    assert three_rows == int(line_height * 3 + 4 * 2 + 2 * 2)
    assert three_rows < ui_state_service.operator_status_pane_height(widget, 5)
    assert ui_state_service.operator_status_pane_height(widget, 0) == ui_state_service.operator_status_pane_height(
        widget, 1
    )


def test_selective_impact_strings_cover_supported_languages() -> None:
    """
    @brief      Verify selective-impact labels and confirmations exist in EN and RO.
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


def test_ai_settings_dialog_flow_strings_cover_supported_languages() -> None:
    """
    @brief      Verify AI Settings dialog action labels exist in EN and RO.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    required_keys = (
        "ai_settings.cancel",
        "ai_settings.save",
        "ai_settings.ok",
        "ai_settings.default_context_mode",
        "ai_settings.context_mode_balanced",
        "ai_settings.context_mode_wide_scene",
        "ai_settings.context_mode_maximum",
    )

    for language in ("en", "ro"):
        for key in required_keys:
            translated_value = ui_state_service.translate(key, language)
            assert translated_value != key
            assert translated_value.strip()


def test_tts_settings_dialog_flow_strings_cover_supported_languages() -> None:
    """
    @brief      Verify TTS Settings dialog action labels exist in EN and RO.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-15
    @version    0.1.0
    """
    required_keys = (
        "tts_settings.cancel",
        "tts_settings.save",
        "tts_settings.ok",
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
    # Font size is now owned by the global font-size steps, not the theme point_size:
    # with the default 'normal' step the applied size equals the pre-apply base font size.
    assert themed_font.pointSizeF() == original_font.pointSizeF()


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


def test_build_theme_stylesheet_styles_toolbar_buttons_for_legibility() -> None:
    """
    @brief      Verify the theme stylesheet gives QToolBar buttons the theme text color.
    @details    Toolbar actions are QToolButtons; without explicit QToolButton rules the native
                Windows style keeps default (dark) text, so labels like "Settings" become invisible
                on a dark themed toolbar. Covers REQ-UX-22740d0a-a29c-4937-977a-d3d43070dcc5 / SPEC-THEME-TOOLBAR.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    theme_payload = ui_theme_service.theme_by_id("audiomancer_dark", [])
    text_primary = theme_payload["colors"]["text_primary"]

    stylesheet = ui_state_service.build_theme_stylesheet(theme_payload, base_point_size=10.0)

    assert "QToolBar {" in stylesheet
    assert "QToolButton {" in stylesheet
    toolbutton_block = stylesheet.split("QToolButton {", 1)[1].split("}", 1)[0]
    assert f"color: {text_primary};" in toolbutton_block


def _qss_block(stylesheet: str, selector: str) -> str:
    """
    @brief      Return the declaration body of one flat (non-nested) QSS rule.
    @param[in]  stylesheet Full stylesheet text.
    @param[in]  selector Rule selector without the opening brace.
    @return     Text between the rule's braces.
    @exception  AssertionError Raised when the selector is not present.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    marker = f"{selector} {{"
    assert marker in stylesheet, f"missing rule: {selector}"
    return stylesheet.split(marker, 1)[1].split("}", 1)[0]


def test_theme_stylesheet_group_boxes_are_rounded_cards() -> None:
    """
    @brief      Verify QGroupBox renders as a rounded, filled card.
    @details    Covers REQ-UX-c3920985-0f4d-45a5-927a-bb0cb4adbce4 / SPEC-QSS-CARDS.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    theme = ui_theme_service.theme_by_id("audiomancer_dark", [])
    stylesheet = ui_state_service.build_theme_stylesheet(theme, base_point_size=10.0)

    block = _qss_block(stylesheet, "QGroupBox")
    assert "border-radius: 10px;" in block
    assert f"background-color: {theme['colors']['panel_background']};" in block


def test_theme_stylesheet_controls_use_rounded_corners() -> None:
    """
    @brief      Verify buttons and single-line inputs use rounded corners.
    @details    Covers REQ-UX-b37f9db2-2007-4dd7-8479-0f413be6f106 / SPEC-QSS-RADIUS.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    theme = ui_theme_service.theme_by_id("audiomancer_dark", [])
    stylesheet = ui_state_service.build_theme_stylesheet(theme, base_point_size=10.0)

    assert "border-radius: 8px;" in _qss_block(stylesheet, "QPushButton")
    input_block = _qss_block(
        stylesheet,
        "QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QTableWidget, QListWidget",
    )
    assert "border-radius: 8px;" in input_block


def test_theme_stylesheet_styles_scrollbars() -> None:
    """
    @brief      Verify scrollbar handles use theme colors with an accent hover.
    @details    Covers REQ-UX-5f397ed7-59b5-4acf-8981-9fab7eb3ca10 / SPEC-QSS-SCROLLBAR.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    theme = ui_theme_service.theme_by_id("audiomancer_dark", [])
    stylesheet = ui_state_service.build_theme_stylesheet(theme, base_point_size=10.0)

    handle = _qss_block(stylesheet, "QScrollBar::handle:vertical")
    assert f"background: {theme['colors']['border']};" in handle
    hover = _qss_block(stylesheet, "QScrollBar::handle:vertical:hover")
    assert f"background: {theme['colors']['accent']};" in hover


def test_theme_stylesheet_makes_popups_legible() -> None:
    """
    @brief      Verify combobox popups and menus use theme panel/text colors.
    @details    Covers REQ-UX-e9f779cf-7032-4a23-b8ca-2f305f71c7b9 / SPEC-QSS-POPUP.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    theme = ui_theme_service.theme_by_id("audiomancer_dark", [])
    panel = theme["colors"]["panel_background"]
    text_primary = theme["colors"]["text_primary"]
    stylesheet = ui_state_service.build_theme_stylesheet(theme, base_point_size=10.0)

    view = _qss_block(stylesheet, "QComboBox QAbstractItemView")
    assert f"background-color: {panel};" in view
    assert f"color: {text_primary};" in view
    menu = _qss_block(stylesheet, "QMenu")
    assert f"background-color: {panel};" in menu
    assert f"color: {text_primary};" in menu


def test_theme_stylesheet_progress_bar_uses_accent() -> None:
    """
    @brief      Verify progress-bar chunks use the theme accent color.
    @details    Covers REQ-UX-56d1df5c-36f3-4e55-b3b1-d075ec3a80bc / SPEC-QSS-PROGRESS.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    theme = ui_theme_service.theme_by_id("audiomancer_dark", [])
    stylesheet = ui_state_service.build_theme_stylesheet(theme, base_point_size=10.0)

    chunk = _qss_block(stylesheet, "QProgressBar::chunk")
    assert f"background-color: {theme['colors']['accent']};" in chunk


def test_theme_stylesheet_marks_active_sidebar_item_with_accent() -> None:
    """
    @brief      Verify the sidebar's selected item gets a left accent border in the stylesheet.
    @details    Covers REQ-UX-03b36e7b-8b07-412f-a861-9af51161b1a9 / SPEC-NAV-ACCENT.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    theme = ui_theme_service.theme_by_id("audiomancer_dark", [])
    stylesheet = ui_state_service.build_theme_stylesheet(theme, base_point_size=10.0)

    selected = _qss_block(stylesheet, "QListWidget#navigationSidebar::item:selected")
    assert f"3px solid {theme['colors']['accent']}" in selected


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


def test_font_size_step_resolution() -> None:
    """
    @brief      Verify font-size step factors and point-size resolution.
    @details    Covers REQ-UX-b5b21ac7-95f0-43bc-823e-6b8f769de448 / SPEC-FONT-RESOLVE.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    assert ui_state_service.font_size_step_factor("extra_small") == 0.80
    assert ui_state_service.font_size_step_factor("normal") == 1.00
    assert ui_state_service.font_size_step_factor("huge") == 1.50
    assert ui_state_service.font_size_step_factor("does_not_exist") == 1.00

    assert round(ui_state_service.resolve_font_point_size("large", 10.0), 4) == 11.5
    assert round(ui_state_service.resolve_font_point_size("small", 10.0), 4) == 9.0
    assert round(ui_state_service.resolve_font_point_size("does_not_exist", 10.0), 4) == 10.0


def test_apply_ui_settings_scales_ui_and_text_fonts_independently(qtbot) -> None:
    """
    @brief      Verify the UI step scales the app font and the text step sizes text editors independently.
    @details    Covers REQ-UX-6ca3a291-f6d1-43c0-abb4-fd53b5594255 / SPEC-FONT-UISCALE and
                REQ-UX-012a6341-ef3a-4098-af0d-a614e353d70e / SPEC-FONT-TEXTSCALE.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    application = QApplication.instance()
    window = QWidget()
    qtbot.addWidget(window)
    settings_payload = {
        "language": config.DEFAULT_LANGUAGE,
        "ui_theme_id": ui_theme_service.default_theme_id(),
        "ui_font_size_step": "large",
        "text_font_size_step": "very_large",
    }

    ui_state_service.apply_ui_settings(application, window, settings_payload)

    base_point_size = ui_state_service._BASE_FONT_POINT_SIZE
    assert base_point_size is not None
    ui_point = ui_state_service.resolve_font_point_size("large", base_point_size)
    text_point = ui_state_service.resolve_font_point_size("very_large", base_point_size)

    assert round(application.font().pointSizeF(), 2) == round(ui_point, 2)
    stylesheet = application.styleSheet()
    assert f"font-size: {ui_point:.1f}pt;" in stylesheet
    assert f"font-size: {text_point:.1f}pt;" in stylesheet


def test_completion_beep_enabled_from_settings_resolves_persisted_flag() -> None:
    """
    @brief      Verify the completion-beep preference resolves from a settings payload.
    @details    Covers REQ-FUNC-bdee3fe2-4f27-4e2e-a702-cb6abafbdd46 / S-BEEP-RESOLVE and
                REQ-FUNC-337ba16d-5990-4f3c-be79-18964d53036f / S-BEEP-RESOLVE.
    @return     None.
    @exception  None
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    assert ui_state_service.completion_beep_enabled_from_settings({"play_completion_beep": True}) is True
    assert ui_state_service.completion_beep_enabled_from_settings({"play_completion_beep": False}) is False
    assert (
        ui_state_service.completion_beep_enabled_from_settings({})
        is config.DEFAULT_PLAY_COMPLETION_BEEP
    )
    assert ui_state_service.completion_beep_enabled_from_settings(None) is False


# END OF FILE
