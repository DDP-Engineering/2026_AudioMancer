<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Platform Settings UI

## 1. Purpose

Platform Settings UI owns shared configuration, settings validation, logging,
locale/theme state, and settings-page integration used by every workflow page.

## 2. Responsibilities

- Define application paths, defaults, resource identity, and configuration constants.
- Load, validate, migrate, and save operator settings.
- Configure component logging, time and URL helpers, scrolling, translations, and UI theme/state.
- Present and apply settings through the Settings page and controller.

## 3. Implementation Overview

`config.py` supplies constants and packaged-resource resolution. The services
normalize settings and theme payloads before the app shell consumes them;
`settings_ui_controller` and `settings_page` render operator changes. This
component provides cross-cutting platform behavior but does not own any domain
workflow artifact.

## 4. Dependencies

- Internal: `config.py` supplies paths/defaults; settings, logging, time, URL,
  scroll, UI-state and theme services provide the shared runtime contracts;
  Settings page/controller render and persist operator changes.
- External: Python JSON/path/logging facilities and PySide6 application, palette,
  font and widget APIs. All other components depend on these contracts, but this
  component does not own their project or operation state.

## 5. Inputs And Outputs

- Inputs: the configured settings path, persisted JSON payload, operator edits,
  built-in/custom theme payloads, runtime language, wheel-step setting, and
  valid HTTP(S) runtime/provider URLs.
- Outputs: normalized settings written when repairs occur, component logs,
  translated strings, a Qt palette/stylesheet/font state, and one global
  scroll-step event filter.

## 6. Data Contracts

AI profile and context-budget settings remain application settings, not fields
in `chunks_text.json`. A resumable AI Chunking run uses the currently selected
enabled profile and current runtime budget while retaining strategy and operator
instructions from the Chunking document.

- Settings remain a UTF-8 JSON object. Missing files receive defaults; invalid
  supported values are repaired, while unknown future keys are preserved unless
  an explicit migration removes them.
- Theme payloads have normalized IDs, display names, font and color fields;
  settings validation normalizes AI profile/default IDs and cached TTS runtime
  discovery data before they are consumed.
- `translate`, `apply_theme`, `apply_ui_settings`, `load_settings`, and
  `save_settings` are the shared public runtime entry points.

## 7. Workflow Integration

App startup loads settings before main-window construction. Settings changes
flow from the Settings page/controller through `save_settings`, then apply UI
language/theme and global scrolling without changing workflow-domain artifacts.
AI and TTS settings surfaces consume the same normalized payload but retain
their runtime-domain behavior.

## 8. Usage

Use the shell Settings action to edit shared appearance/language preferences.
Services call `load_settings()` at startup and `save_settings(payload)` after
deliberate changes; UI code uses `translate` and `apply_ui_settings` rather
than maintaining separate language or theme state.

## 9. Validation And Tests

Primary automated coverage:

- `tests/test_config_contract.py`
- `tests/test_settings_service.py`
- `tests/test_logging_service.py`
- `tests/test_url_service.py`
- `tests/test_ui_scroll_service.py`
- `tests/test_ui_state_service.py`
- `tests/test_ui_theme_service.py`
- `tests/test_settings_page.py`
- `tests/test_localization_parity.py`

These cover configuration constants, settings load/validate/self-heal/save,
component logging, URL joining, scroll-step behavior, runtime language/theme
application, theme schema validation, and Settings-page editing. Minimum
validation after a change: run the focused modules above with `uv run pytest`,
plus `uv run python -m py_compile` and `uv run ruff check` on changed files.

## 10. Limitations And Future Work

- Settings are stored as a plaintext UTF-8 JSON object, including any AI or TTS
  API keys; secret hygiene remains the operator's responsibility and is not
  scrubbed by validation.
- Settings and themes are dictionary-based and not yet modeled with typed
  classes.
- Unknown extra settings keys are preserved rather than strictly validated.
