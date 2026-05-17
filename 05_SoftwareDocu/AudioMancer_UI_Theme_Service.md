<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer UI Theme Service

## 1. Purpose

Documents `src/audiomancer/services/ui_theme_service.py`, the Qt-independent
theme schema helper used by Settings and runtime UI styling.

The broader Settings UI workflow is documented in
`AudioMancer_UI_Themes.md`; this page covers the service boundary expected by
the implementation audit.

## 2. Responsibilities

- define the current persisted theme schema version
- provide the built-in theme catalog
- validate and normalize custom theme payloads
- normalize font family, point-size, and scale fields
- normalize stable color-role values as `#RRGGBB`
- merge built-in and custom themes for Settings and runtime lookup
- duplicate, import, and export custom theme payloads with stable ids

It does not apply Qt palettes or widgets directly, persist `settings.json`, or
own Settings dialog interactions.

## 3. Implementation Overview

Implementation file:

- `04_Software/AudioMancer/src/audiomancer/services/ui_theme_service.py`

Main public constants:

- `THEME_SCHEMA_VERSION`
- `MIN_FONT_POINT_SIZE`
- `MAX_FONT_POINT_SIZE`
- `MAX_DISPLAY_NAME_LENGTH`
- `THEME_COLOR_ROLES`

Main public functions:

- `built_in_themes()`
- `default_theme_id()`
- `validate_theme_payload(...)`
- `normalize_theme_collection(...)`
- `merged_theme_catalog(...)`
- `theme_by_id(...)`
- `duplicate_theme(...)`
- `export_theme_payload(...)`
- `import_theme_payload(...)`

The service stores built-in themes as internal payloads and returns deep copies
to callers. Validation rejects malformed payloads; collection normalization
drops invalid custom themes and duplicate or built-in ids deterministically.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config` for default text scale and allowed scale options

External dependencies:

- Python standard library: `copy`, `re`, and `typing`

There are no Qt dependencies in this service.

## 5. Inputs And Outputs

Inputs:

- persisted `ui_themes` values from `settings.json`
- selected `ui_theme_id` values
- imported theme JSON payloads
- operator-entered display names for duplicated themes

Outputs:

- normalized theme dictionaries
- merged theme catalog lists
- exported custom-theme payloads
- `ValueError` for invalid single-theme payloads

## 6. Data Contracts

Theme payload fields:

- `schema_version`: must equal `THEME_SCHEMA_VERSION`
- `theme_id`: lowercase slug made of letters, numbers, and underscores
- `display_name`: non-empty string up to `MAX_DISPLAY_NAME_LENGTH`
- `built_in`: preserved only when validation allows built-in payloads
- `font`: object with `family`, nullable numeric `point_size`, and supported
  `scale`
- `text_font`: same shape as `font`
- `colors`: object containing every role in `THEME_COLOR_ROLES`

Color values must be six-digit hex RGB strings. Missing font or color fields
fall back to service defaults during validation where supported.

## 7. Workflow Integration

Upstream callers:

- `settings_service.py` validates persisted theme settings during load/save
- `settings_page.py` edits, duplicates, imports, and exports themes
- `ui_state_service.py` builds runtime style sheets from validated theme data
- `home_page.py` reads default theme colors for generated export styling

Downstream consumers:

- Settings dialog controls
- runtime UI theme application
- persisted `settings.json` fields `ui_theme_id` and `ui_themes`

## 8. Usage

Resolve a selected theme:

```python
from audiomancer.services import ui_theme_service

theme = ui_theme_service.theme_by_id(settings["ui_theme_id"], settings["ui_themes"])
```

Import a custom theme:

```python
imported_theme = ui_theme_service.import_theme_payload(candidate_payload, existing_themes)
```

## 9. Validation And Tests

Focused tests:

- `04_Software/AudioMancer/tests/test_ui_theme_service.py`
- related integration coverage in `tests/test_settings_service.py`,
  `tests/test_settings_page.py`, `tests/test_ui_state_service.py`, and
  `tests/test_home_page.py`

Minimum validation after service changes:

```powershell
uv run python -m py_compile src\audiomancer\services\ui_theme_service.py tests\test_ui_theme_service.py
uv run ruff check src\audiomancer\services\ui_theme_service.py tests\test_ui_theme_service.py --fix
uv run ruff format src\audiomancer\services\ui_theme_service.py tests\test_ui_theme_service.py
uv run pytest tests\test_ui_theme_service.py
```

## 10. Limitations And Future Work

- the service validates schema and colors but does not perform contrast-ratio
  analysis
- imported themes are schema-validated but not cryptographically signed
- Qt widget styling remains owned by UI state and page code
