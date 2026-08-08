#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_settings_page.py
@brief Focused tests for the simplified AudioMancer settings (Appearance) page.
@details Verifies built-in/custom theme selection and preview, interface/text
         font-size step selectors, localization, reload, and merged settings output.
"""

# IMPORTS

from audiomancer import config
from audiomancer.services import ui_state_service, ui_theme_service
from audiomancer.ui.pages.settings_page import SettingsPage

# LOCAL HELPERS


def _custom_theme(theme_id: str, display_name: str, *, accent: str = "#7654AB") -> dict[str, object]:
    """
    @brief      Build one valid custom-theme payload for Settings-page tests.
    @param[in]  theme_id Stable custom theme identifier.
    @param[in]  display_name Operator-authored theme name.
    @param[in]  accent Optional distinctive accent color.
    @return     Valid custom-theme payload with one operator-owned extension field.
    @exception  None
    """
    return {
        "schema_version": 1,
        "theme_id": theme_id,
        "display_name": display_name,
        "built_in": False,
        "font": {},
        "text_font": {},
        "colors": {
            "window_background": "#102030",
            "panel_background": "#203040",
            "text_primary": "#F0F1F2",
            "accent": accent,
        },
        "operator_extension": {"preserve": True},
    }


# PUBLIC API


def test_settings_page_offers_exactly_supported_ui_languages(qtbot) -> None:
    """
    @brief      Verify the interface language selector offers only English and Romanian.
    @details    Covers S-0002 and REQ-UX-6f6f2126-58f4-4c7e-955a-74bc4ca70284.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = SettingsPage()
    qtbot.addWidget(page)

    language_items = [page._language_combo.itemText(index) for index in range(page._language_combo.count())]

    assert config.SUPPORTED_LANGUAGES == ("en", "ro")
    assert language_items == ["en", "ro"]


def test_settings_page_loads_and_builds_merged_settings(qtbot) -> None:
    """
    @brief      Verify the settings page loads and rebuilds persisted values.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = SettingsPage()
    qtbot.addWidget(page)

    existing_settings = {
        "language": "en",
        "ui_theme_id": config.DEFAULT_UI_THEME_ID,
        "ui_themes": [],
        "play_completion_beep": False,
        "ui_scroll_steps_per_wheel_notch": 1,
        "llm_profiles": [{"id": "kept"}],
    }

    page.load_settings(
        {
            "language": "ro",
            "ui_theme_id": config.DEFAULT_UI_THEME_ID,
            "ui_themes": [],
            "play_completion_beep": True,
            "ui_scroll_steps_per_wheel_notch": 4,
            "ui_font_size_step": "large",
            "text_font_size_step": "very_large",
        }
    )

    assert page._language_combo.currentText() == "ro"
    assert page._language_combo.minimumWidth() >= 96
    assert page._completion_beep_checkbox.isChecked() is True
    assert page._scroll_steps_spin.value() == 4
    assert page._ui_font_size_combo.currentData() == "large"
    assert page._text_font_size_combo.currentData() == "very_large"

    page._language_combo.setCurrentText("en")
    page._completion_beep_checkbox.setChecked(False)
    page._scroll_steps_spin.setValue(2)

    rebuilt = page.build_settings(existing_settings)

    assert rebuilt["language"] == "en"
    assert rebuilt["ui_theme_id"] == config.DEFAULT_UI_THEME_ID
    assert rebuilt["play_completion_beep"] is False
    assert rebuilt["ui_scroll_steps_per_wheel_notch"] == 2
    assert rebuilt["ui_font_size_step"] == "large"
    assert rebuilt["text_font_size_step"] == "very_large"
    assert rebuilt["llm_profiles"] == [{"id": "kept"}]


def test_settings_page_theme_selector_loads_and_persists(qtbot) -> None:
    """
    @brief      Verify the theme selector reflects the loaded id and persists a new choice.
    @details    Covers REQ-UX-8e33d3cf-f881-4dbb-86d2-2f97f05b0669 / SPEC-SET-THEME.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings({"language": "en", "ui_theme_id": "warm_reading"})

    expected_built_in_ids = [str(theme["theme_id"]) for theme in ui_theme_service.built_in_themes()]
    actual_theme_ids = [str(page._theme_combo.itemData(index)) for index in range(page._theme_combo.count())]

    assert actual_theme_ids == expected_built_in_ids
    assert page._theme_combo.currentData() == "warm_reading"

    high_contrast_index = page._theme_combo.findData("high_contrast")
    assert high_contrast_index >= 0
    page._theme_combo.setCurrentIndex(high_contrast_index)

    rebuilt = page.build_settings({"language": "en"})
    assert rebuilt["ui_theme_id"] == "high_contrast"


def test_settings_page_custom_theme_selection_uses_merged_catalog_and_preserves_payload(qtbot) -> None:
    """
    @brief      Verify valid custom themes follow built-ins and round-trip without payload loss.
    @details    Covers REQ-UX-8e33d3cf for merged order, selection, and page-unowned fields.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    custom_themes = [
        _custom_theme("operator_twilight", "Operator Twilight"),
        _custom_theme("studio_personal", "Studio Personal", accent="#C08040"),
    ]
    settings_payload = {
        "language": "en",
        "ui_theme_id": "operator_twilight",
        "ui_themes": custom_themes,
        "future_setting": {"preserve": "unchanged"},
    }

    page.load_settings(settings_payload)

    expected_theme_ids = [str(theme["theme_id"]) for theme in ui_theme_service.built_in_themes()]
    expected_theme_ids.extend(["operator_twilight", "studio_personal"])
    actual_theme_ids = [str(page._theme_combo.itemData(index)) for index in range(page._theme_combo.count())]
    rebuilt = page.build_settings(settings_payload)

    assert actual_theme_ids == expected_theme_ids
    assert page._theme_combo.currentData() == "operator_twilight"
    assert rebuilt["ui_theme_id"] == "operator_twilight"
    assert rebuilt["ui_themes"] == custom_themes
    assert rebuilt["ui_themes"][0]["operator_extension"] == {"preserve": True}
    assert rebuilt["future_setting"] == {"preserve": "unchanged"}


def test_settings_page_custom_theme_preview_uses_loaded_custom_collection(qtbot) -> None:
    """
    @brief      Verify preview stylesheet resolution uses the selected loaded custom theme.
    @details    Covers REQ-UX-8e33d3cf custom-theme preview behavior.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    custom_theme = _custom_theme("preview_custom", "Preview Custom", accent="#4A7BC2")

    page.load_settings(
        {
            "language": "en",
            "ui_theme_id": "preview_custom",
            "ui_themes": [custom_theme],
        }
    )

    preview_stylesheet = page._preview_group.styleSheet()
    assert page._theme_combo.currentData() == "preview_custom"
    assert "#4A7BC2" in preview_stylesheet
    assert "#203040" in preview_stylesheet


def test_settings_page_language_change_preserves_custom_theme_display_name(qtbot) -> None:
    """
    @brief      Verify language changes translate built-ins but preserve custom display names.
    @details    Covers REQ-UX-8e33d3cf operator-authored custom-theme naming.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    custom_display_name = "Tema mea – Studio"
    page.load_settings(
        {
            "language": "en",
            "ui_theme_id": "tema_studio",
            "ui_themes": [_custom_theme("tema_studio", custom_display_name)],
        }
    )

    page.apply_language("ro")

    built_in_index = page._theme_combo.findData("classic_light")
    custom_index = page._theme_combo.findData("tema_studio")
    assert page._theme_combo.itemText(built_in_index) == ui_state_service.translate(
        "settings.theme_name.classic_light",
        "ro",
    )
    assert page._theme_combo.itemText(custom_index) == custom_display_name
    assert page._theme_combo.currentData() == "tema_studio"


def test_settings_page_reloading_theme_catalog_clears_stale_and_invalid_items(qtbot) -> None:
    """
    @brief      Verify repeated loads replace rather than append the normalized custom catalog.
    @details    Covers REQ-UX-8e33d3cf clean reload and existing normalization filtering.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings(
        {
            "ui_theme_id": "stale_custom",
            "ui_themes": [_custom_theme("stale_custom", "Stale Custom")],
        }
    )
    invalid_theme = _custom_theme("invalid_custom", "Invalid Custom")
    invalid_theme["colors"] = {"accent": "not-a-color"}
    fresh_theme = _custom_theme("fresh_custom", "Fresh Custom")

    page.load_settings(
        {
            "ui_theme_id": "fresh_custom",
            "ui_themes": [fresh_theme, fresh_theme, invalid_theme],
        }
    )

    theme_ids = [str(page._theme_combo.itemData(index)) for index in range(page._theme_combo.count())]
    built_in_count = len(ui_theme_service.built_in_themes())
    assert theme_ids[built_in_count:] == ["fresh_custom"]
    assert len(theme_ids) == len(set(theme_ids))
    assert "stale_custom" not in theme_ids
    assert "invalid_custom" not in theme_ids
    assert page._theme_combo.currentData() == "fresh_custom"


def test_settings_page_interface_font_size_selector_persists(qtbot) -> None:
    """
    @brief      Verify the interface font-size selector loads and persists a step.
    @details    Covers REQ-UX-bcc4485f-102b-4e39-9f48-c5bde30b99f3 / SPEC-SET-UIFONT.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings({"language": "en", "ui_font_size_step": "small"})

    assert page._ui_font_size_combo.currentData() == "small"
    assert page._ui_font_size_combo.count() == len(config.UI_FONT_SIZE_STEPS)

    page._ui_font_size_combo.setCurrentIndex(page._ui_font_size_combo.findData("huge"))
    rebuilt = page.build_settings({"language": "en"})
    assert rebuilt["ui_font_size_step"] == "huge"


def test_settings_page_text_font_size_selector_persists(qtbot) -> None:
    """
    @brief      Verify the text-window font-size selector loads and persists a step.
    @details    Covers REQ-UX-a3f0f73c-54ea-4ddd-9ec7-4ab8a84d57b1 / SPEC-SET-TEXTFONT.
    @param[in]  qtbot Qt test helper fixture.
    @return     None.
    @exception  None
    """
    page = SettingsPage()
    qtbot.addWidget(page)
    page.load_settings({"language": "en", "text_font_size_step": "medium"})

    assert page._text_font_size_combo.currentData() == "medium"
    assert page._text_font_size_combo.count() == len(config.UI_FONT_SIZE_STEPS)

    page._text_font_size_combo.setCurrentIndex(page._text_font_size_combo.findData("extra_small"))
    rebuilt = page.build_settings({"language": "en"})
    assert rebuilt["text_font_size_step"] == "extra_small"


# END OF FILE
