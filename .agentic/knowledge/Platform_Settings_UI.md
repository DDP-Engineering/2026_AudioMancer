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

The Settings page rebuilds its theme selector from the normalized merged theme
catalog whenever settings load. Built-ins retain their catalog order and
localized labels; valid persisted custom themes follow them with their
operator-authored display names. The page keeps the normalized custom
collection only for selection and preview resolution. It never replaces the
caller-owned `ui_themes` payload, so Apply or OK preserves custom fields outside
this page's responsibilities.

`ui_state_service` owns the complete operator-facing English/Romanian string
catalog. Persistent pages call `apply_language()` for captions, empty states,
dynamic choices, and list markers; controllers translate popup and progress
text before passing it to Qt. `settings_ui_controller.apply_current_ui_settings`
also rebuilds the currently visible project page after a language change so
derived notes do not retain the previous locale.

Startup passes both validated persisted font-size steps into the early theme
application before constructing `MainWindow`, so newly created widgets inherit
the operator's interface and text-window size choices from their first layout
(`REQ-UX-f9cbdc8c`).

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

Offline Help resolution checks packaged `help/<language>/index.html` content
before the source-checkout English/Romanian guides. The source fallback root is
built with depth-safe `Path.parent` traversal rather than indexed ancestors, so
configuration import also succeeds when a frozen or portable `APP_ROOT` is only
one level below its filesystem anchor. This behavior is covered by
`REQ-PLAT-7cd89b15`.

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
- Outputs: normalized settings written when repairs occur and persistence is
  available, usable validated in-memory settings when a repair write fails,
  exact-byte corruption backups for malformed or undecodable settings,
  component logs, translated strings, a Qt palette/stylesheet/font state, and
  one global scroll-step event filter.

## 6. Data Contracts

AI profile and context-budget settings remain application settings, not fields
in `chunks_text.json`. A resumable AI Chunking run uses the currently selected
enabled profile and current runtime budget while retaining strategy and operator
instructions from the Chunking document.

- Settings remain a UTF-8 JSON object, with an optional UTF-8 byte-order mark
  accepted transparently by `load_settings()` (`REQ-PLAT-2a16daee`). A missing
  settings file is seeded from the
  validated payload at `APP_DEFAULT_SETTINGS_PATH` (`APP_ROOT/settings.json`, the
  scaffold the packaging script stages beside the executable with API keys and
  discovery cache stripped) when that path differs from the active path and is
  readable; otherwise it receives built-in defaults. The packaged file is only
  ever read. The committed `settings.example.json` is the source scaffold copied
  to that packaged identity or to an operator's active settings file; runtime
  seeding never reads the example path directly. Invalid supported values are
  repaired, while unknown future keys are preserved unless an explicit migration
  removes them.
- Scene Ambience placement is the sole configured enablement policy; the retired
  global enablement constant is absent, and settings validation deliberately
  removes the deprecated `scene_ambience_generation_enabled` key
  (`REQ-PLAT-02331830`).
- Every committed example profile represents the optional
  `discovered_model_name` field as a string, matching the loader contract and
  avoiding a repair when an operator copies the scaffold (`REQ-PLAT-dd51f8cd`).
- `build_default_settings()` derives `default_ai_chunking_strategy` and
  `play_completion_beep` from their `config` factory constants, and the committed
  settings scaffold carries the same current values (`REQ-PLAT-ce8e4f6f`). Missing,
  invalid, portable, and unusable-scaffold fallbacks therefore share one source of
  truth. Validation preserves valid explicit operator choices such as `scene` and
  an enabled completion beep; changing a factory default does not migrate or
  rewrite those choices.
- Malformed JSON or invalid UTF-8 settings are preserved byte-for-byte before
  replacement in the first unused same-directory `settings.corrupt.json` or
  `settings.corrupt.<n>.json` backup (`REQ-PLAT-b950f73c`). Backup creation is
  exclusive, flushed, and synced before the existing atomic settings writer
  replaces the active file with built-in defaults.
- Read, backup, or post-backup default-write `OSError` failures return built-in
  defaults for the current run, while a failed validated repair write returns
  the usable repaired payload in memory without changing the active file; all
  paths log only outcomes, never settings contents (`REQ-REL-c822b662`). The
  original bytes remain at the active path when reading, backup, or repair
  persistence fails and remain recoverable in the completed backup when the
  later default write fails.
- `config.SUPPORTED_LANGUAGES` is the operator interface allowlist and contains
  exactly `en` and `ro`. `settings_service.validate_settings()` replaces any
  other persisted or submitted interface language with
  `config.DEFAULT_LANGUAGE` before use or persistence. Cleanup source-content
  languages and AI translation targets have separate configuration contracts.
- Packaged offline Help paths remain relative to `APP_ROOT`, while source
  checkout Help paths retain the repository's `05_SoftwareDocu/UserGuide` and
  `05_SoftwareDocu/UserGuide_ro` entry points; shallow installed roots never
  require a second available ancestor during configuration initialization.
- Theme payloads have normalized IDs, display names, font and color fields;
  settings validation normalizes AI profile/default IDs and cached TTS runtime
  discovery data before they are consumed. Cached VoiceWeaver models use the
  runtime service's public canonical normalizer, retaining scalar generation
  ranges/defaults and deep-copy isolation while dropping unknown model fields
  (`REQ-FUNC-9757d967`, `REQ-FUNC-1fef6b33`).
- Valid provider base URLs retain their proxy path, query, and fragment data
  through profile normalization so chat and Test Connection can apply the same
  shared endpoint policy (`REQ-FUNC-9273a9ed`).
- `_BUILT_IN_THEMES` order is a contract, not presentation trivia: it is the
  built-in prefix of the Settings-page theme-combo order, and index 0 is the
  `classic_light` payload that supplies fallback values for colour roles a
  custom theme omits. Valid normalized custom themes follow the complete
  built-in prefix. New built-in themes are appended; existing entries are
  never reordered. The catalog covers brand (`audiomancer_dark`, the default,
  and `audiomancer_parchment`), system baselines (`classic_light`, `default_dark`),
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
- The Settings interface-language selector creates one item for every
  `config.SUPPORTED_LANGUAGES` entry, displays its active-locale `language.<code>`
  label, and loads, selects, and persists only the stable code in item data
  (`REQ-UX-ade084a1`).
- Settings theme reload clears and rebuilds the combo from
  `merged_theme_catalog(ui_themes)`, so stale, duplicate, built-in-colliding, and
  invalid custom entries cannot remain visible. Built-in display labels are
  localized; custom `display_name` values remain operator-authored across
  language changes (`REQ-UX-8e33d3cf`).
- Within theme persistence, `SettingsPage.build_settings()` writes the selected
  `ui_theme_id` and leaves the existing `ui_themes` collection untouched.
  Preview resolution uses the loaded normalized custom collection, so a
  selected valid custom theme is shown without giving this page theme editing
  ownership (`REQ-UX-8e33d3cf`).
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
- Component loggers use an explicit per-call level when supplied and otherwise
  use `DEFAULT_LOG_LEVEL`; there is no inert per-component override registry
  (`REQ-NFR-82f739cc`).
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

These cover configuration constants and default-seed/scaffold parity, one-level frozen-root initialization,
source and packaged Help resolution, writable data-root resolution across
portable, override and read-only installation layouts, settings
load/validate/self-heal/seed/save, BOM acceptance, corruption backup and
non-destructive I/O fallback, component logging, URL joining, scroll-step
behavior, runtime language/theme
application, theme schema validation, Settings-page editing, and completion-beep
preference resolution and emission. Settings-page coverage includes merged
built-in/custom catalog order, custom selection round-trips, preview styles,
operator-authored names, normalization filtering, and clean repeated reloads.
Localization coverage additionally checks
Settings dynamic labels, every audited persistent page, runtime current-page
refresh, and direct popup/progress API calls. Minimum
validation after a change: run the focused modules above with `uv run pytest`,
plus `uv run python -m py_compile` and `uv run ruff check` on changed files.

## 10. Limitations And Future Work

- Settings are stored as a plaintext UTF-8 JSON object, including any AI or TTS
  API keys; secret hygiene remains the operator's responsibility and is not
  scrubbed by validation.
- Corruption backups preserve the original plaintext bytes and can therefore
  contain the same API keys as the active settings file; operators should keep
  those backups private and delete them only after recovering any needed values.
- Settings and themes are dictionary-based and not yet modeled with typed
  classes.
- Settings can select and preview valid custom themes already present in
  `ui_themes`, but custom-theme creation, editing, deletion, import, and export
  are not exposed by the current Settings page.
- Unknown extra settings keys are preserved rather than strictly validated.
- The writable data root is resolved once at `config` import time, so changing
  `AUDIOMANCER_DATA_DIR` or the writability of the application root requires a
  process restart to take effect.
- Writability is decided by a probe file rather than `os.access`, which costs one
  transient file creation per process start. `os.access` is not usable here
  because on Windows it ignores directory ACLs.

## Files

From the adopted component map:

- `04_Software/AudioMancer/settings.example.json`
- `04_Software/AudioMancer/settings.json`
- `04_Software/AudioMancer/src/audiomancer/app.py`
- `04_Software/AudioMancer/src/audiomancer/config.py`
- `04_Software/AudioMancer/src/audiomancer/services/logging_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/settings_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/time_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ui_scroll_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/ui_theme_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/url_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/settings_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/settings_page.py`
- `04_Software/AudioMancer/tests/test_app_entrypoint.py`
- `04_Software/AudioMancer/tests/test_config_contract.py`
- `04_Software/AudioMancer/tests/test_localization_parity.py`
- `04_Software/AudioMancer/tests/test_logging_service.py`
- `04_Software/AudioMancer/tests/test_misc_ui_controller.py`
- `04_Software/AudioMancer/tests/test_operator_status_font_role.py`
- `04_Software/AudioMancer/tests/test_settings_page.py`
- `04_Software/AudioMancer/tests/test_settings_service.py`
- `04_Software/AudioMancer/tests/test_ui_scroll_service.py`
- `04_Software/AudioMancer/tests/test_ui_state_service.py`
- `04_Software/AudioMancer/tests/test_ui_theme_service.py`
- `04_Software/AudioMancer/tests/test_ui_localization_coverage.py`
- `04_Software/AudioMancer/tests/test_url_service.py`
- `04_Software/AudioMancer/tests/test_user_data_location.py`
