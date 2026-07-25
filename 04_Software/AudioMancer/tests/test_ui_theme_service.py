#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file test_ui_theme_service.py
@brief Focused tests for the AudioMancer UI theme service.
@details Verifies built-in theme contracts, custom theme validation, import
         normalization, and resilient collection handling.
@author Eng. Dan Dumitru Pasare
@date 2026-05-13
@version 0.4.0
"""

# IMPORTS

import copy

import pytest

from audiomancer.services import ui_theme_service

# PUBLIC API


def test_built_in_themes_validate_and_are_deep_copied() -> None:
    """
    @brief      Verify built-in themes satisfy the schema and cannot be mutated through callers.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.2.0
    """
    built_in_themes = ui_theme_service.built_in_themes()

    assert [theme["theme_id"] for theme in built_in_themes] == [
        "classic_light",
        "warm_reading",
        "high_contrast",
        "default_dark",
        "dark_contrast",
        "audiomancer_dark",
        "audiomancer_parchment",
    ]
    for theme_payload in built_in_themes:
        validated_theme = ui_theme_service.validate_theme_payload(theme_payload, allow_built_in=True)
        assert validated_theme["built_in"] is True

    classic_colors = built_in_themes[0]["colors"]
    assert isinstance(classic_colors, dict)
    classic_colors["accent"] = "#000000"

    fresh_classic_colors = ui_theme_service.built_in_themes()[0]["colors"]
    assert isinstance(fresh_classic_colors, dict)
    assert fresh_classic_colors["accent"] == "#2F6FED"


def test_validate_theme_payload_rejects_invalid_color_values() -> None:
    """
    @brief      Verify malformed color values fail validation clearly.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    theme_payload = copy.deepcopy(ui_theme_service.built_in_themes()[0])
    theme_payload["built_in"] = False
    theme_payload["theme_id"] = "custom_light"
    colors = theme_payload["colors"]
    assert isinstance(colors, dict)
    colors["accent"] = "blue"

    with pytest.raises(ValueError, match="colors.accent"):
        ui_theme_service.validate_theme_payload(theme_payload)


def test_validate_theme_payload_fills_missing_color_roles_from_classic_light() -> None:
    """
    @brief      Verify omitted custom roles fall back to classic light/default font values.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.2.0
    """
    theme_payload = {
        "schema_version": 1,
        "theme_id": "minimal_theme",
        "display_name": "Minimal Theme",
        "built_in": True,
        "font": {"family": "Arial", "point_size": 11, "scale": "large"},
        "colors": {"accent": "#123abc"},
    }

    validated_theme = ui_theme_service.validate_theme_payload(theme_payload)
    validated_colors = validated_theme["colors"]
    assert isinstance(validated_colors, dict)

    assert validated_theme["built_in"] is False
    assert validated_theme["text_font"] == {"family": "", "point_size": None, "scale": "normal"}
    assert validated_colors["accent"] == "#123ABC"
    assert validated_colors["window_background"] == "#F6F7F9"
    assert validated_colors["text_primary"] == "#202124"


def test_validate_theme_payload_accepts_distinct_text_font() -> None:
    """
    @brief      Verify custom themes can persist text-window font settings separately from UI controls.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    theme_payload = {
        "schema_version": 1,
        "theme_id": "reader_theme",
        "display_name": "Reader Theme",
        "built_in": False,
        "font": {"family": "Segoe UI", "point_size": 10, "scale": "normal"},
        "text_font": {"family": "Georgia", "point_size": 14, "scale": "large"},
        "colors": {},
    }

    validated_theme = ui_theme_service.validate_theme_payload(theme_payload)

    assert validated_theme["font"] == {"family": "Segoe UI", "point_size": 10.0, "scale": "normal"}
    assert validated_theme["text_font"] == {"family": "Georgia", "point_size": 14.0, "scale": "large"}


def test_import_theme_payload_makes_duplicate_ids_unique() -> None:
    """
    @brief      Verify imported theme ids are suffixed when they already exist.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    existing_theme = ui_theme_service.import_theme_payload(
        {
            "schema_version": 1,
            "theme_id": "reading_copy",
            "display_name": "Reading Copy",
            "built_in": False,
            "font": {},
            "colors": {},
        },
        [],
    )
    candidate_theme = {
        "schema_version": 1,
        "theme_id": "reading_copy",
        "display_name": "Reading Copy Again",
        "built_in": False,
        "font": {},
        "colors": {},
    }

    imported_theme = ui_theme_service.import_theme_payload(candidate_theme, [existing_theme])

    assert imported_theme["theme_id"] == "reading_copy_2"


def test_import_theme_payload_strips_built_in_flag_and_generates_missing_id() -> None:
    """
    @brief      Verify imports cannot inject built-in state and can derive an id from the display name.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    imported_theme = ui_theme_service.import_theme_payload(
        {
            "schema_version": 1,
            "display_name": "My Reading Theme",
            "built_in": True,
            "font": {},
            "colors": {},
        },
        [],
    )

    assert imported_theme["theme_id"] == "my_reading_theme"
    assert imported_theme["built_in"] is False


def test_normalize_theme_collection_returns_empty_for_malformed_root_payload() -> None:
    """
    @brief      Verify malformed theme collections self-heal to an empty custom collection.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    assert ui_theme_service.normalize_theme_collection({"bad": "root"}) == []
    assert ui_theme_service.normalize_theme_collection(None) == []


def test_theme_by_id_returns_default_for_missing_theme_id() -> None:
    """
    @brief      Verify unresolved theme ids fall back to the default built-in theme.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    resolved_theme = ui_theme_service.theme_by_id("missing_theme", [])

    assert resolved_theme["theme_id"] == ui_theme_service.default_theme_id()
    assert resolved_theme["built_in"] is True


def test_duplicate_and_export_theme_payloads_are_custom_payloads() -> None:
    """
    @brief      Verify duplicate and export helpers return custom-safe payloads.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    duplicated_theme = ui_theme_service.duplicate_theme(ui_theme_service.built_in_themes()[0], "Classic Copy")
    exported_theme = ui_theme_service.export_theme_payload(ui_theme_service.built_in_themes()[0])

    assert duplicated_theme["theme_id"] == "classic_copy"
    assert duplicated_theme["display_name"] == "Classic Copy"
    assert duplicated_theme["built_in"] is False
    assert exported_theme["theme_id"] == "classic_light"
    assert exported_theme["built_in"] is False


def test_exported_built_in_theme_imports_as_custom_copy_with_unique_id() -> None:
    """
    @brief      Verify exported built-ins round-trip as custom themes with safe ids.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-14
    @version    0.1.0
    """
    exported_theme = ui_theme_service.export_theme_payload(ui_theme_service.built_in_themes()[0])

    imported_theme = ui_theme_service.import_theme_payload(exported_theme, [])

    assert imported_theme["theme_id"] == "classic_light_2"
    assert imported_theme["display_name"] == "Classic Light"
    assert imported_theme["built_in"] is False


# @brief Expected color roles for the AudioMancer Dark brand theme (REQ-UX-fe3699e9, SPEC-THEME-DARK).
_AUDIOMANCER_DARK_COLORS = {
    "window_background": "#0B2429",
    "panel_background": "#10313A",
    "text_primary": "#F1E9DA",
    "text_muted": "#98AEAC",
    "accent": "#E3AC52",
    "border": "#22474D",
    "warning": "#E0A82E",
    "success": "#58A877",
    "danger": "#DA655C",
    "disabled": "#5E7A78",
}

# @brief Expected color roles for the AudioMancer Parchment brand theme (REQ-UX-5e28b833, SPEC-THEME-PARCHMENT).
_AUDIOMANCER_PARCHMENT_COLORS = {
    "window_background": "#F1E8D6",
    "panel_background": "#FFFDF6",
    "text_primary": "#17292C",
    "text_muted": "#5B6D6B",
    "accent": "#B07A22",
    "border": "#E4D8C0",
    "warning": "#A6701A",
    "success": "#2F7A4E",
    "danger": "#A93C36",
    "disabled": "#A99F8B",
}


def _theme_with_id(theme_id: str) -> dict[str, object]:
    """
    @brief      Return the built-in theme payload with the given id.
    @param[in]  theme_id Target built-in theme identifier.
    @return     Matching built-in theme payload.
    @exception  StopIteration Raised when no built-in theme has the id.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    return next(theme for theme in ui_theme_service.built_in_themes() if theme["theme_id"] == theme_id)


def test_audiomancer_dark_theme_has_brand_roles() -> None:
    """
    @brief      Verify the AudioMancer Dark built-in theme exposes the brand color roles.
    @details    Covers REQ-UX-fe3699e9-a737-44a0-8e69-ffc490d54bfc / SPEC-THEME-DARK.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    dark_theme = _theme_with_id("audiomancer_dark")

    assert dark_theme["built_in"] is True
    assert dark_theme["display_name"] == "AudioMancer Dark"
    assert dark_theme["colors"] == _AUDIOMANCER_DARK_COLORS


def test_audiomancer_parchment_theme_has_brand_roles() -> None:
    """
    @brief      Verify the AudioMancer Parchment built-in theme exposes the brand color roles.
    @details    Covers REQ-UX-5e28b833-8917-4f9b-9733-f438e6400a7e / SPEC-THEME-PARCHMENT.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    parchment_theme = _theme_with_id("audiomancer_parchment")

    assert parchment_theme["built_in"] is True
    assert parchment_theme["display_name"] == "AudioMancer Parchment"
    assert parchment_theme["colors"] == _AUDIOMANCER_PARCHMENT_COLORS


def test_default_theme_id_is_audiomancer_dark() -> None:
    """
    @brief      Verify AudioMancer Dark is the default theme and the missing-id fallback resolves it.
    @details    Covers REQ-UX-5692f984-04af-46a1-bbf0-b71cfad0f3cd / SPEC-THEME-DEFAULT and keeps the
                REQ-UX-ce3d3202 fallback-follows-default contract green.
    @return     None.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-07-25
    @version    0.1.0
    """
    assert ui_theme_service.default_theme_id() == "audiomancer_dark"

    resolved_theme = ui_theme_service.theme_by_id("missing_theme", [])
    assert resolved_theme["theme_id"] == "audiomancer_dark"
    assert resolved_theme["built_in"] is True


# END OF FILE
