#!/usr/bin/env python3
# -*- coding: utf-8 -*-  # noqa: UP009
# -----------------------------------------------------------------------------
# Copyright (c) 2026 DDP Engineering
# This software is licensed under the GNU Affero General Public License v3.0
# (AGPL-3.0) with additional Non-Commercial restriction.
# See the LICENSE.txt and LICENSE_NC.txt files for full license details.
# -----------------------------------------------------------------------------
"""
@file ui_theme_service.py
@brief Theme schema helpers for AudioMancer UI settings.
@details Defines built-in UI themes, validates custom theme payloads, normalizes
         font and color roles, and prepares import/export payloads without Qt
         dependencies.
@author Eng. Dan Dumitru Pasare
@date 2026-05-13
@version 0.3.0
"""

# IMPORTS

import copy
import re
from typing import Final

from .. import config

# CONSTANTS

# @brief Current persisted theme schema version.
THEME_SCHEMA_VERSION: Final[int] = 1

# @brief Minimum accepted explicit UI font point size.
MIN_FONT_POINT_SIZE: Final[float] = 7.0

# @brief Maximum accepted explicit UI font point size.
MAX_FONT_POINT_SIZE: Final[float] = 18.0

# @brief Maximum display-name length accepted for theme payloads.
MAX_DISPLAY_NAME_LENGTH: Final[int] = 80

# @brief Stable color role names consumed by the UI theme runtime.
THEME_COLOR_ROLES: Final[tuple[str, ...]] = (
    "window_background",
    "panel_background",
    "text_primary",
    "text_muted",
    "accent",
    "border",
    "warning",
    "success",
    "danger",
    "disabled",
)

# @brief Stable slug pattern used for persisted theme identifiers.
_THEME_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_]*$")

# @brief Hex RGB color pattern accepted by the theme schema.
_HEX_COLOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^#[0-9a-fA-F]{6}$")

# @brief Non-slug character pattern used for deterministic display-name slugs.
_SLUG_INVALID_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")

# @brief Default font payload used when theme payloads omit optional font fields.
_DEFAULT_FONT: Final[dict[str, object]] = {
    "family": "",
    "point_size": None,
    "scale": config.DEFAULT_UI_TEXT_SCALE,
}

# @brief Built-in theme payloads. Callers receive deep copies through public helpers.
_BUILT_IN_THEMES: Final[tuple[dict[str, object], ...]] = (
    {
        "schema_version": THEME_SCHEMA_VERSION,
        "theme_id": "classic_light",
        "display_name": "Classic Light",
        "built_in": True,
        "font": copy.deepcopy(_DEFAULT_FONT),
        "text_font": copy.deepcopy(_DEFAULT_FONT),
        "colors": {
            "window_background": "#F6F7F9",
            "panel_background": "#FFFFFF",
            "text_primary": "#202124",
            "text_muted": "#5F6368",
            "accent": "#2F6FED",
            "border": "#D7DDE5",
            "warning": "#D6A300",
            "success": "#2E8B57",
            "danger": "#7A1F1F",
            "disabled": "#A0A0A0",
        },
    },
    {
        "schema_version": THEME_SCHEMA_VERSION,
        "theme_id": "warm_reading",
        "display_name": "Warm Reading",
        "built_in": True,
        "font": copy.deepcopy(_DEFAULT_FONT),
        "text_font": copy.deepcopy(_DEFAULT_FONT),
        "colors": {
            "window_background": "#F4EFE7",
            "panel_background": "#FFF9F0",
            "text_primary": "#27231E",
            "text_muted": "#6E6255",
            "accent": "#7A5C2E",
            "border": "#D8CCBA",
            "warning": "#A66A00",
            "success": "#3D7A4C",
            "danger": "#7A2D2D",
            "disabled": "#A99F92",
        },
    },
    {
        "schema_version": THEME_SCHEMA_VERSION,
        "theme_id": "high_contrast",
        "display_name": "High Contrast",
        "built_in": True,
        "font": copy.deepcopy(_DEFAULT_FONT),
        "text_font": copy.deepcopy(_DEFAULT_FONT),
        "colors": {
            "window_background": "#FFFFFF",
            "panel_background": "#FFFFFF",
            "text_primary": "#000000",
            "text_muted": "#2B2B2B",
            "accent": "#0047CC",
            "border": "#000000",
            "warning": "#8A5A00",
            "success": "#005C2E",
            "danger": "#8B0000",
            "disabled": "#666666",
        },
    },
    {
        "schema_version": THEME_SCHEMA_VERSION,
        "theme_id": "default_dark",
        "display_name": "Default Dark",
        "built_in": True,
        "font": copy.deepcopy(_DEFAULT_FONT),
        "text_font": copy.deepcopy(_DEFAULT_FONT),
        "colors": {
            "window_background": "#181A1F",
            "panel_background": "#22252B",
            "text_primary": "#E8EAED",
            "text_muted": "#AAB0BB",
            "accent": "#6EA8FE",
            "border": "#3A3F48",
            "warning": "#E0A82E",
            "success": "#4FA36B",
            "danger": "#D35D6E",
            "disabled": "#70757E",
        },
    },
    {
        "schema_version": THEME_SCHEMA_VERSION,
        "theme_id": "dark_contrast",
        "display_name": "Dark Contrast",
        "built_in": True,
        "font": copy.deepcopy(_DEFAULT_FONT),
        "text_font": copy.deepcopy(_DEFAULT_FONT),
        "colors": {
            "window_background": "#000000",
            "panel_background": "#101010",
            "text_primary": "#FFFFFF",
            "text_muted": "#D0D0D0",
            "accent": "#66B2FF",
            "border": "#FFFFFF",
            "warning": "#FFD24A",
            "success": "#66E08A",
            "danger": "#FF6B6B",
            "disabled": "#8C8C8C",
        },
    },
)


# HELPER FUNCTIONS


def _classic_light_theme() -> dict[str, object]:
    """
    @brief      Return a deep copy of the classic light built-in theme.
    @return     Classic light theme payload.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    return copy.deepcopy(_BUILT_IN_THEMES[0])


def _normalize_display_name(display_name: object) -> str:
    """
    @brief      Normalize and validate one operator-facing theme name.
    @param[in]  display_name Candidate display name.
    @return     Trimmed display name.
    @exception  ValueError Raised when the display name is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    if not isinstance(display_name, str):
        raise ValueError("Theme display_name must be a string.")
    normalized_name = display_name.strip()
    if not normalized_name:
        raise ValueError("Theme display_name must not be empty.")
    if len(normalized_name) > MAX_DISPLAY_NAME_LENGTH:
        raise ValueError(f"Theme display_name must be {MAX_DISPLAY_NAME_LENGTH} characters or shorter.")
    return normalized_name


def _normalize_theme_id(theme_id: object) -> str:
    """
    @brief      Normalize and validate one persisted theme identifier.
    @param[in]  theme_id Candidate theme id.
    @return     Trimmed stable theme id.
    @exception  ValueError Raised when the id is not a supported slug.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    if not isinstance(theme_id, str):
        raise ValueError("Theme theme_id must be a string.")
    normalized_id = theme_id.strip()
    if not _THEME_ID_PATTERN.fullmatch(normalized_id):
        raise ValueError("Theme theme_id must use lowercase letters, numbers, and underscores.")
    return normalized_id


def _theme_id_from_name(display_name: str) -> str:
    """
    @brief      Build a deterministic custom-theme id from a display name.
    @param[in]  display_name Valid display name.
    @return     Lowercase slug suitable for the theme_id field.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    normalized_id = _SLUG_INVALID_PATTERN.sub("_", display_name.strip().casefold()).strip("_")
    return normalized_id or "custom_theme"


def _unique_theme_id(base_theme_id: str, reserved_theme_ids: set[str]) -> str:
    """
    @brief      Suffix one theme id until it is unique in a reserved id set.
    @param[in]  base_theme_id Preferred theme id.
    @param[in]  reserved_theme_ids Already-used theme ids.
    @return     Unique theme id.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    if base_theme_id not in reserved_theme_ids:
        return base_theme_id
    suffix_index = 2
    while f"{base_theme_id}_{suffix_index}" in reserved_theme_ids:
        suffix_index += 1
    return f"{base_theme_id}_{suffix_index}"


def _normalize_font(font_payload: object) -> dict[str, object]:
    """
    @brief      Normalize and validate one theme font payload.
    @param[in]  font_payload Candidate font object.
    @return     Normalized font payload.
    @exception  ValueError Raised when font fields are invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    if font_payload is None:
        return copy.deepcopy(_DEFAULT_FONT)
    if not isinstance(font_payload, dict):
        raise ValueError("Theme font must be an object.")

    font_family = font_payload.get("family", _DEFAULT_FONT["family"])
    if not isinstance(font_family, str):
        raise ValueError("Theme font.family must be a string.")

    point_size = font_payload.get("point_size", _DEFAULT_FONT["point_size"])
    if point_size is not None:
        if isinstance(point_size, bool) or not isinstance(point_size, (int, float)):
            raise ValueError("Theme font.point_size must be null or a number.")
        point_size = float(point_size)
        if point_size < MIN_FONT_POINT_SIZE or point_size > MAX_FONT_POINT_SIZE:
            raise ValueError(
                f"Theme font.point_size must be between {MIN_FONT_POINT_SIZE:.1f} and {MAX_FONT_POINT_SIZE:.1f}."
            )

    font_scale = font_payload.get("scale", _DEFAULT_FONT["scale"])
    if font_scale not in config.UI_TEXT_SCALE_OPTIONS:
        raise ValueError("Theme font.scale must be a supported UI text-scale option.")

    return {
        "family": font_family.strip(),
        "point_size": point_size,
        "scale": font_scale,
    }


def _normalize_colors(colors_payload: object) -> dict[str, str]:
    """
    @brief      Normalize and validate color roles for one theme.
    @param[in]  colors_payload Candidate colors object.
    @return     Complete normalized color-role map.
    @exception  ValueError Raised when one color value is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    if colors_payload is None:
        colors_payload = {}
    if not isinstance(colors_payload, dict):
        raise ValueError("Theme colors must be an object.")

    default_colors = _classic_light_theme()["colors"]
    assert isinstance(default_colors, dict)
    normalized_colors: dict[str, str] = {}
    for role_name in THEME_COLOR_ROLES:
        color_value = colors_payload.get(role_name, default_colors[role_name])
        if not isinstance(color_value, str) or not _HEX_COLOR_PATTERN.fullmatch(color_value.strip()):
            raise ValueError(f"Theme colors.{role_name} must be a #RRGGBB color value.")
        normalized_colors[role_name] = color_value.strip().upper()
    return normalized_colors


# PUBLIC API


def built_in_themes() -> list[dict[str, object]]:
    """
    @brief      Return all built-in UI theme payloads.
    @return     Deep-copy list of built-in themes.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    return [copy.deepcopy(theme_payload) for theme_payload in _BUILT_IN_THEMES]


def default_theme_id() -> str:
    """
    @brief      Return the default UI theme identifier.
    @return     Built-in default theme id.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    return "classic_light"


def validate_theme_payload(theme_payload: object, *, allow_built_in: bool = False) -> dict[str, object]:
    """
    @brief      Validate and normalize one theme payload.
    @param[in]  theme_payload Candidate theme payload.
    @param[in]  allow_built_in Preserve a valid built-in flag when True.
    @return     Normalized theme payload.
    @exception  ValueError Raised when required schema values are invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.2.0
    """
    if not isinstance(theme_payload, dict):
        raise ValueError("Theme payload root must be an object.")
    if theme_payload.get("schema_version") != THEME_SCHEMA_VERSION:
        raise ValueError(f"Theme schema_version must be {THEME_SCHEMA_VERSION}.")

    display_name = _normalize_display_name(theme_payload.get("display_name"))
    theme_id = _normalize_theme_id(theme_payload.get("theme_id"))
    return {
        "schema_version": THEME_SCHEMA_VERSION,
        "theme_id": theme_id,
        "display_name": display_name,
        "built_in": bool(theme_payload.get("built_in")) if allow_built_in else False,
        "font": _normalize_font(theme_payload.get("font")),
        "text_font": _normalize_font(theme_payload.get("text_font")),
        "colors": _normalize_colors(theme_payload.get("colors")),
    }


def normalize_theme_collection(theme_payloads: object) -> list[dict[str, object]]:
    """
    @brief      Normalize one persisted custom-theme collection.
    @param[in]  theme_payloads Candidate list of custom theme payloads.
    @return     Valid custom themes with duplicate ids removed deterministically.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    if not isinstance(theme_payloads, list):
        return []

    normalized_themes: list[dict[str, object]] = []
    reserved_theme_ids = {theme["theme_id"] for theme in built_in_themes()}
    for theme_payload in theme_payloads:
        try:
            normalized_theme = validate_theme_payload(theme_payload)
        except ValueError:
            continue
        theme_id = str(normalized_theme["theme_id"])
        if theme_id in reserved_theme_ids:
            continue
        reserved_theme_ids.add(theme_id)
        normalized_themes.append(normalized_theme)
    return normalized_themes


def merged_theme_catalog(custom_themes: object) -> list[dict[str, object]]:
    """
    @brief      Merge built-in themes with one custom-theme collection.
    @param[in]  custom_themes Candidate persisted custom themes.
    @return     Built-in themes followed by valid custom themes.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    return [*built_in_themes(), *normalize_theme_collection(custom_themes)]


def theme_by_id(theme_id: object, custom_themes: object) -> dict[str, object]:
    """
    @brief      Resolve one theme by id from the merged catalog.
    @param[in]  theme_id Candidate theme identifier.
    @param[in]  custom_themes Candidate persisted custom themes.
    @return     Matching theme payload or the default built-in theme.
    @exception  None.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    candidate_id = str(theme_id).strip() if isinstance(theme_id, str) else ""
    for theme_payload in merged_theme_catalog(custom_themes):
        if theme_payload["theme_id"] == candidate_id:
            return copy.deepcopy(theme_payload)
    return _classic_light_theme()


def duplicate_theme(theme_payload: dict[str, object], new_name: str) -> dict[str, object]:
    """
    @brief      Duplicate one valid theme as a custom theme with a new name.
    @param[in]  theme_payload Source theme payload.
    @param[in]  new_name Display name for the duplicated theme.
    @return     Custom duplicate theme payload.
    @exception  ValueError Raised when the source payload or name is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    source_theme = validate_theme_payload(theme_payload, allow_built_in=True)
    display_name = _normalize_display_name(new_name)
    duplicated_theme = copy.deepcopy(source_theme)
    duplicated_theme["theme_id"] = _theme_id_from_name(display_name)
    duplicated_theme["display_name"] = display_name
    duplicated_theme["built_in"] = False
    return duplicated_theme


def export_theme_payload(theme_payload: dict[str, object]) -> dict[str, object]:
    """
    @brief      Prepare one theme payload for standalone JSON export.
    @param[in]  theme_payload Source theme payload.
    @return     Normalized custom export payload.
    @exception  ValueError Raised when the source payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    return validate_theme_payload(theme_payload)


def import_theme_payload(candidate_payload: object, existing_themes: object) -> dict[str, object]:
    """
    @brief      Validate one imported theme and assign a non-conflicting custom id.
    @param[in]  candidate_payload Imported theme payload.
    @param[in]  existing_themes Candidate persisted custom themes already present.
    @return     Normalized imported custom theme payload.
    @exception  ValueError Raised when the imported payload is invalid.
    @author     Eng. Dan Dumitru Pasare
    @date       2026-05-13
    @version    0.1.0
    """
    if not isinstance(candidate_payload, dict):
        raise ValueError("Theme payload root must be an object.")

    display_name = _normalize_display_name(candidate_payload.get("display_name"))
    payload_with_id = dict(candidate_payload)
    if not isinstance(payload_with_id.get("theme_id"), str) or not str(payload_with_id.get("theme_id")).strip():
        payload_with_id["theme_id"] = _theme_id_from_name(display_name)

    imported_theme = validate_theme_payload(payload_with_id)
    reserved_theme_ids = {str(theme_payload["theme_id"]) for theme_payload in merged_theme_catalog(existing_themes)}
    imported_theme["theme_id"] = _unique_theme_id(str(imported_theme["theme_id"]), reserved_theme_ids)
    imported_theme["built_in"] = False
    return imported_theme


# END OF FILE
