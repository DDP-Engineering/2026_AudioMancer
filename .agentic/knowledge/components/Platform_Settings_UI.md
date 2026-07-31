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
- Resolve the writable data root that owns per-user settings and application logs, separately from the read-only packaged resource root.
- Resolve the per-user documents folder that operator-facing folder pickers start in.
- Load, validate, migrate, and save operator settings, seeding a fresh settings file from the packaged scaffold.
- Configure component logging, time and URL helpers, scrolling, translations, and UI theme/state.
- Present and apply settings through the Settings page and controller.
- Keep operator interface locales (`en`, `ro`) separate from workflow-domain
  source-content and translation language sets.
- Keep every app-owned window, page, and popup string in the shared English and
  Romanian catalog, including visible labels for stable option data.
- Resolve the operator completion-beep preference and expose the shared emitter that consumes it.

## 3. Implementation Overview

`config.py` supplies constants and packaged-resource resolution. It also exposes
`resolve_user_documents_root()`, which keeps the folder operators browse for
their own content separate from `APP_ROOT`: that root owns read-only packaged
resources and is a system directory for a frozen build installed into
`C:\Program Files\AudioMancer`, `/opt`, or `/usr/share`. The resolver is pure
standard library, because `config` is imported by every module and by every
headless test and therefore must not import PySide6. The services
normalize settings and theme payloads before the app shell consumes them;
`settings_ui_controller` and `settings_page` render operator changes. This
component provides cross-cutting platform behavior but does not own any domain
workflow artifact.

`ui_state_service` owns the complete operator-facing English/Romanian string
catalog. Persistent pages call `apply_language()` for captions, empty states,
dynamic choices, and list markers; controllers translate popup and progress
text before passing it to Qt. `settings_ui_controller.apply_current_ui_settings`
also rebuilds the currently visible project page after a language change so
derived notes do not retain the previous locale.

`config.py` keeps two roots apart. `APP_ROOT` owns read-only packaged resources
(prompts, help, licences, icon, `pyproject.toml`). `APP_USER_DATA_ROOT`, produced
by `resolve_user_data_root()`, owns everything the application writes: the active
`settings.json` and the `Logs/` directory. The resolver takes the
`AUDIOMANCER_DATA_DIR` override first, then `APP_ROOT` when a probe file proves
it writable and it is not the PyInstaller `_MEIPASS` extraction folder, and
otherwise the per-user OS location (`%LOCALAPPDATA%` on Windows,
`~/Library/Application Support` on macOS, `$XDG_DATA_HOME` or `~/.local/share`
elsewhere). Portable and source-tree layouts keep data beside the application,
while installations under non-writable prefixes such as `C:\Program Files` or
`/opt` use the per-user location. See
`.agentic/specs/user_data_location.spec.md`.

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

- Settings remain a UTF-8 JSON object. A missing settings file is seeded from the
  validated payload at `APP_DEFAULT_SETTINGS_PATH` (`APP_ROOT/settings.json`, the
  scaffold the packaging script stages beside the executable with API keys and
  discovery cache stripped) when that path differs from the active path and is
  readable; otherwise it receives built-in defaults. The packaged file is only
  ever read. `settings.example.json` is placeholder documentation and is never a
  seed source. Invalid supported values are repaired, while unknown future keys
  are preserved unless an explicit migration removes them.
- `config.SUPPORTED_LANGUAGES` is the operator interface allowlist and contains
  exactly `en` and `ro`. `settings_service.validate_settings()` replaces any
  other persisted or submitted interface language with
  `config.DEFAULT_LANGUAGE` before use or persistence. Cleanup source-content
  languages and AI translation targets have separate configuration contracts.
- Theme payloads have normalized IDs, display names, font and color fields;
  settings validation normalizes AI profile/default IDs and cached TTS runtime
  discovery data before they are consumed.
- `_BUILT_IN_THEMES` order is a contract, not presentation trivia: it is the
  Settings-page theme-combo order, and index 0 is the `classic_light` payload
  that supplies fallback values for colour roles a custom theme omits. New
  built-in themes are appended; existing entries are never reordered. The
  catalog covers brand (`audiomancer_dark`, the default, and
  `audiomancer_parchment`), system baselines (`classic_light`, `default_dark`),
  accessibility (`high_contrast`, `dark_contrast`) and reading-comfort
  registers (`warm_reading`, `midnight_studio`, `ember_night`, `nordic_slate`,
  `ink_and_paper`). Colour-role values and their contrast basis are recorded in
  `.agentic/specs/ui_theme_catalog.spec.md`.
- `translate`, `apply_theme`, `apply_ui_settings`, `load_settings`, and
  `save_settings` are the shared public runtime entry points.
- `localized_language_label()` maps stable translation-language codes and their
  canonical English labels to the active operator locale. Font-size steps,
  chunking strategies, built-in theme IDs, and language codes keep
  language-neutral item data while their combo labels are replaced in place;
  relabeling therefore preserves the selected and persisted value.
- App-owned popup titles, messages, prompt labels, file filters, progress
  operation names, and initial statuses must be translated before display.
  Brand names, provider/model IDs, file formats, numeric units, project
  content, and operator-authored names remain unchanged.
- `play_completion_beep` is the persisted operator preference for an audible
  end-of-operation signal. `ui_state_service.completion_beep_enabled_from_settings`
  is the pure resolver (a non-mapping payload and a missing key both yield the
  `DEFAULT_PLAY_COMPLETION_BEEP` behavior of staying silent), and
  `misc_ui_controller.play_completion_beep(window)` is the only emitter. Consumers
  call the emitter rather than reading the settings key or `QApplication.beep()`
  directly, so the preference has exactly one interpretation.
- Each run writes one log file named
  `<APP_NAME>_<YYYYMMDD>_<HHMMSS>_<pid>.log` under `Logs/`. The process id is
  part of the name because the run handler opens with `mode="w"`: without it two
  instances started in the same second share one path and the second truncates
  the first run's log. Retention cleanup is best-effort and skips any entry it
  cannot inspect or remove.
- `resolve_user_documents_root()` returns the first existing directory among an
  `XDG_DOCUMENTS_DIR` override (POSIX other than macOS), the home documents
  folder, and the home directory. It never returns a missing path, because
  `QFileDialog` silently falls back to the process working directory when given
  one. It records nothing: no settings field remembers a last-used folder.

## 7. Workflow Integration

App startup loads settings before main-window construction. Settings changes
flow from the Settings page/controller through `save_settings`, then apply UI
language/theme and global scrolling without changing workflow-domain artifacts.
When a project is open, the controller refreshes only the current workflow page
from canonical state in the new language; other pages refresh normally when
navigated to.
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
- `tests/test_user_data_location.py`
- `tests/test_settings_service.py`
- `tests/test_logging_service.py`
- `tests/test_url_service.py`
- `tests/test_ui_scroll_service.py`
- `tests/test_ui_state_service.py`
- `tests/test_ui_theme_service.py`
- `tests/test_settings_page.py`
- `tests/test_misc_ui_controller.py`
- `tests/test_localization_parity.py`
- `tests/test_ui_localization_coverage.py`

These cover configuration constants, writable data-root resolution across
portable, override and read-only installation layouts, settings
load/validate/self-heal/seed/save, component logging, URL joining, scroll-step
behavior, runtime language/theme
application, theme schema validation, Settings-page editing, and completion-beep
preference resolution and emission. Localization coverage additionally checks
Settings dynamic labels, every audited persistent page, runtime current-page
refresh, and direct popup/progress API calls. Minimum
validation after a change: run the focused modules above with `uv run pytest`,
plus `uv run python -m py_compile` and `uv run ruff check` on changed files.

## 10. Limitations And Future Work

- Settings are stored as a plaintext UTF-8 JSON object, including any AI or TTS
  API keys; secret hygiene remains the operator's responsibility and is not
  scrubbed by validation.
- Settings and themes are dictionary-based and not yet modeled with typed
  classes.
- Unknown extra settings keys are preserved rather than strictly validated.
- The writable data root is resolved once at `config` import time, so changing
  `AUDIOMANCER_DATA_DIR` or the writability of the application root requires a
  process restart to take effect.
- Writability is decided by a probe file rather than `os.access`, which costs one
  transient file creation per process start. `os.access` is not usable here
  because on Windows it ignores directory ACLs.
