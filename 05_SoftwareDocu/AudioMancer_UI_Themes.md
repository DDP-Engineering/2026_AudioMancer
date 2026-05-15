<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer UI Themes

## 1. Purpose

Provides the Settings-backed UI theme system for the `AudioMancer` desktop
application.

It gives operators built-in visual themes, editable custom themes, separate
font controls for UI controls and text windows, and portable JSON import/export
while keeping theme validation independent from Qt widgets.

## 2. Responsibilities

- define the persisted UI theme schema
- provide the built-in theme catalog
- validate custom theme payloads and fill missing optional roles
- normalize persisted custom theme collections during settings validation
- support custom-theme duplicate, import, and export payloads
- apply selected theme colors, UI fonts, and text-window fonts to the running
  Qt application
- expose Settings-page controls for create, edit, delete, import, export, and
  preview behavior

It does not own project workflow state, generated audio, AI settings, or
application packaging.

## 3. Implementation Overview

The theme schema and catalog are implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/ui_theme_service.py`

The built-in catalog currently contains `Classic Light`, `Warm Reading`,
`High Contrast`, `Default Dark`, and `Dark Contrast`.

Runtime theme application is implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`

Settings persistence and UI integration are implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/settings_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/settings_page.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/settings_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/main_window.py`

High-level flow:

1. `settings_service.load_settings()` validates `ui_theme_id` and `ui_themes`
   from `settings.json`.
2. `ui_theme_service.merged_theme_catalog(...)` combines built-in themes with
   normalized custom themes.
3. `settings_page.SettingsPage` displays the catalog and edits custom themes in
   an in-dialog draft.
4. `settings_ui_controller.save_settings_from_dialog(...)` persists the
   normalized page payload through `settings_service.save_settings(...)`.
5. `ui_state_service.apply_ui_settings(...)` resolves the selected theme,
  updates the application UI font, text-window stylesheet, palette,
  theme-aware widgets, and then reapplies language strings.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config` for defaults and schema version
- `audiomancer.services.settings_service` for settings lifecycle validation
- `audiomancer.services.ui_state_service` for runtime Qt application updates
- `audiomancer.services.persistence_service` for atomic JSON export writes
- `audiomancer.ui.pages.settings_page` for operator controls

External dependencies:

- Python standard library: `copy`, `json`, `pathlib`, `re`
- PySide6 widgets and GUI classes for the Settings page and runtime theme
  application

## 5. Inputs And Outputs

Inputs:

- built-in theme definitions in `ui_theme_service.py`
- persisted `settings.json` fields `ui_theme_id` and `ui_themes`
- operator edits from the Settings dialog
- imported theme JSON files selected through the Settings dialog

Outputs:

- normalized in-memory theme payloads
- persisted `settings.json` custom theme collection
- exported portable theme JSON files
- updated Qt application UI font, text-window font stylesheet, palette, and
  stylesheet
- localized status messages for import/export and Settings save flows

## 6. Data Contracts

Theme payload contract:

- `schema_version`: integer, currently `1`
- `theme_id`: lowercase slug using letters, numbers, and underscores
- `display_name`: non-empty operator-facing name, maximum 80 characters
- `built_in`: boolean, preserved only for built-in catalog payloads
- `font.family`: optional font family string
- `font.point_size`: `null` or a number from `7.0` through `18.0`
- `font.scale`: legacy compatibility field, normalized to a supported value
  but not exposed in Settings or applied at runtime
- `text_font.family`: optional font family string for `QTextEdit` and
  `QPlainTextEdit` text windows that contain book-manipulation text; read-only
  operator notes and bottom status panels use the UI-control font instead
- `text_font.point_size`: `null` or a number from `7.0` through `18.0`
- `text_font.scale`: legacy compatibility field, normalized to a supported
  value but not exposed in Settings or applied at runtime
- `colors`: hex RGB role map using `#RRGGBB`

Stable color roles:

- `window_background`
- `panel_background`
- `text_primary`
- `text_muted`
- `accent`
- `border`
- `warning`
- `success`
- `danger`
- `disabled`

Persisted settings fields:

- `ui_theme_id`: selected theme identifier
- `ui_themes`: list of custom theme payloads

Deterministic behavior:

- missing optional UI or text-window font values fall back to default font
  behavior
- missing color roles fall back to the `classic_light` built-in values
- invalid custom themes are dropped during settings validation
- selected missing theme ids are repaired to `config.DEFAULT_UI_THEME_ID`
- imported duplicate theme ids receive numeric suffixes
- built-in themes exported to JSON are exported as custom-safe payloads

## 7. Workflow Integration

The theme system sits between persisted application settings and the visible Qt
shell.

Upstream:

- `settings_service` loads and validates the persisted payload at startup
- `settings_page` emits edited theme values after the operator saves Settings

Downstream:

- `ui_state_service.apply_theme(...)` updates the Qt application UI font,
  text-window stylesheet, palette, and stylesheet
- `MainWindow.apply_theme(...)` forwards normalized themes to theme-aware pages
- `HomePage.apply_theme(...)` uses semantic color roles for stage rows and
  source-lock status text

## 8. Usage

Resolve a selected theme from settings:

```python
from audiomancer import config
from audiomancer.services import ui_theme_service

selected_theme = ui_theme_service.theme_by_id(
    settings_payload.get("ui_theme_id", config.DEFAULT_UI_THEME_ID),
    settings_payload.get("ui_themes", []),
)
```

Export and re-import a theme payload:

```python
export_payload = ui_theme_service.export_theme_payload(selected_theme)
imported_theme = ui_theme_service.import_theme_payload(export_payload, existing_custom_themes)
```

Settings dialog operator path:

1. Open `Settings`.
2. Select a built-in theme, or create/duplicate a custom theme.
3. Edit custom theme name, UI font, text-window font, and color roles.
4. Save Settings to persist and apply the selected theme.
5. Use `Apply` to preview persisted changes without closing the dialog, or
   `OK` to apply and close.
6. Export or import portable theme JSON as needed.

## 9. Validation And Tests

Automated tests:

- `04_Software/AudioMancer/tests/test_ui_theme_service.py`
- `04_Software/AudioMancer/tests/test_settings_service.py`
- `04_Software/AudioMancer/tests/test_settings_page.py`
- `04_Software/AudioMancer/tests/test_ui_state_service.py`
- `04_Software/AudioMancer/tests/test_home_page.py`

Covered behaviors:

- built-in themes validate and are deep copied
- invalid color values and malformed custom themes are rejected or dropped
- settings defaults and migration include theme fields
- Settings page creates, edits, deletes, imports, exports, and previews themes
- runtime theme application updates UI font, text-window font, and palette
  roles
- theme Settings strings resolve in English and Romanian
- Home page status rows consume semantic theme roles

Minimum validation after a theme change:

```powershell
uv run python -m py_compile src/audiomancer/config.py
uv run python -m py_compile src/audiomancer/services/settings_service.py
uv run python -m py_compile src/audiomancer/services/ui_state_service.py
uv run python -m py_compile src/audiomancer/services/ui_theme_service.py
uv run python -m py_compile src/audiomancer/ui/pages/settings_page.py
uv run python -m py_compile src/audiomancer/ui/controllers/settings_ui_controller.py
uv run ruff check src/audiomancer/config.py src/audiomancer/services/settings_service.py src/audiomancer/services/ui_state_service.py src/audiomancer/services/ui_theme_service.py src/audiomancer/ui/pages/settings_page.py src/audiomancer/ui/controllers/settings_ui_controller.py tests/test_ui_theme_service.py tests/test_settings_service.py tests/test_settings_page.py tests/test_ui_state_service.py --fix
uv run ruff format src/audiomancer/config.py src/audiomancer/services/settings_service.py src/audiomancer/services/ui_state_service.py src/audiomancer/services/ui_theme_service.py src/audiomancer/ui/pages/settings_page.py src/audiomancer/ui/controllers/settings_ui_controller.py tests/test_ui_theme_service.py tests/test_settings_service.py tests/test_settings_page.py tests/test_ui_state_service.py
uv run pytest tests/test_ui_theme_service.py tests/test_settings_service.py tests/test_settings_page.py tests/test_ui_state_service.py
uv run pytest tests/test_home_page.py
```

Manual smoke test:

1. Launch AudioMancer.
2. Open Settings.
3. Select each built-in theme and save.
4. Create a custom theme.
5. Change UI font, text-window font, and accent color.
6. Save and confirm the main shell updates.
7. Reopen Settings and confirm values persisted.
8. Export the theme.
9. Delete the custom theme.
10. Import the exported theme and save.
11. Switch UI language to Romanian and confirm theme controls translate.

## 10. Limitations And Future Work

- Theme editing currently covers the principal semantic roles and Home-page
  role consumers; additional pages may adopt semantic theme roles over time.
- The former top-level `ui_text_scale` setting, theme scale controls, and
  default-size checkboxes are deprecated; interface and multi-line text editor
  sizing are controlled by explicit `font.point_size` and
  `text_font.point_size` values.
- Imported theme files are plain JSON and do not include signatures or
  provenance metadata.
- Theme font selection depends on fonts available to the local operating
  system.
- Manual visual QA remains useful because Qt platform styles can differ across
  Windows and Linux.
