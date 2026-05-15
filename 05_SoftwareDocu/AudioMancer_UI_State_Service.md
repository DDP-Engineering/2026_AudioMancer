<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer UI State Service

## 1. Purpose

Provides the shared runtime UI-state helpers for the `AudioMancer` desktop
application.

It centralizes operator-facing UI strings, language lookup, and runtime theme
application so pages and controllers do not keep separate translation, UI-font,
or text-window font-size logic.

## 2. Responsibilities

- store the English and Romanian runtime UI string catalog
- resolve one translated string or one full language catalog on demand
- fall back to the configured default language for unknown language codes
- resolve the current UI language from persisted settings payloads
- apply selected theme UI font, text-window font, color, palette, and
  stylesheet values to the running Qt application
- apply the selected language to the main-window shell when supported
- log invalid language and theme-application decisions

It does not own settings persistence, help-file content, workflow state, or
page-specific layout behavior.

## 3. Implementation Overview

The component is implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`

Main public functions:

- `translate(key, language)`
- `get_ui_strings(language)`
- `current_language_from_settings(settings_payload)`
- `apply_text_scale(application, ui_text_scale)` for compatibility and tests
- `apply_theme(application, theme_payload, ui_text_scale)`
- `build_theme_stylesheet(theme_payload, base_point_size=None)`
- `apply_language(main_window, language)`
- `apply_ui_settings(application, main_window, settings_payload)`

Runtime flow:

1. Settings are loaded by the application settings layer.
2. `apply_ui_settings(...)` resolves and applies the selected theme, then
   applies the selected language.
3. `apply_theme(...)` captures the base application font once, applies the
   selected theme UI font size directly, updates the Qt palette and text-window
   stylesheet, and refreshes top-level widgets.
4. `apply_language(...)` resolves the requested language and calls
   `main_window.apply_language(...)` when the main window exposes that hook.
5. Pages and controllers use stable catalog keys through `translate(...)` or a
   language catalog copied by `get_ui_strings(...)`.

## 4. Dependencies

Internal dependencies:

- `04_Software/AudioMancer/src/audiomancer/config.py`
- `04_Software/AudioMancer/src/audiomancer/services/logging_service.py`
- Qt main-window and page classes that consume translated labels

External dependencies:

- `PySide6.QtGui.QFont`
- `PySide6.QtWidgets.QApplication`
- `PySide6.QtWidgets.QWidget`

## 5. Inputs And Outputs

Inputs:

- stable string keys such as `toolbar.settings` and `speech_blocks.insert_block`
- language codes such as `en` and `ro`
- persisted settings payloads with `language`, `ui_theme_id`, and `ui_themes`
- a running `QApplication`
- a main window that may expose `apply_language(language)`

Outputs:

- translated strings or copied language catalogs
- updated application and top-level widget UI fonts, text-window font
  stylesheet, palette, and stylesheet
- language updates delegated to the main window
- warning and info records through the `ui_state` component logger

The component does not write project files or settings files.

## 6. Data Contracts

The central string catalog is `_UI_STRINGS`, keyed first by language code and
then by stable UI identifier. Existing code should use stable keys instead of
hard-coded labels for operator-facing runtime text.

Speech Blocks selected-audio preview uses the page-specific
`speech_blocks.generate_audio_selected` key so its compact `Generate Audio`
label can remain shorter than the Audio Blocks page's `Re-Generate Audio`
button at larger UI font sizes.

Supported text-scale keys are defined by `_UI_SCALE_FACTORS`:

- `very_small`
- `small`
- `normal`
- `large`
- `very_large`

Unknown language codes fall back to `config.DEFAULT_LANGUAGE`. Unknown string
keys fall back to the default-language value and finally to the key itself.
The theme `font` payload controls labels, buttons, and other interface
controls. The theme `text_font` payload is emitted into the stylesheet for
multi-line `QTextEdit` and `QPlainTextEdit` windows used for book text,
character descriptions, prompts, speech blocks, audio-block text, and preview
text. Read-only operator notes and bottom status panels opt back into the UI
font through the `audiomancerFontRole=ui_controls` dynamic Qt property because
they are interface feedback, not book-manipulation text. Legacy theme `scale`
fields are accepted by schema validation but are not applied by the runtime
theme path.

## 7. Workflow Integration

The service sits between settings persistence and visible UI widgets.

The main application uses it after loading settings so the shell, toolbar,
sidebar, dialogs, pages, and status messages use the selected language and
theme. Page classes and controllers consume the catalog while building labels,
buttons, group titles, notes, confirmation text, and status messages.
Current v2 entries cover Text Chunking insert/delete confirmations, selective
Character Discovery add/edit/delete confirmations, voice-target and narrator
audio invalidation confirmations, Speech Blocks selected-block and sequence
impact confirmations, Audio Blocks selected reset/regeneration and
approval-change confirmations, Audio Assembly settings-change confirmation, and
the related result/status messages. Current Character Voices entries cover both
single-sample generation and the confirmed batch action that regenerates all
current character samples. Current settings-dialog entries also cover the
Settings `Apply`/`OK` flow and the AI Settings plus TTS Settings `Save`/`OK`
flow in both English and Romanian.

Because all operator-facing labels are centralized here, UI text changes must
update both English and Romanian catalog entries in the same implementation
change.

## 8. Usage

Typical string lookup:

```python
label = translate("toolbar.settings", "en")
```

Typical startup application:

```python
apply_ui_settings(application, main_window, settings_payload)
```

Typical page-level language refresh:

```python
strings = get_ui_strings(language)
button.setText(strings["speech_blocks.save_block"])
```

## 9. Validation And Tests

Documentation audit status:

- reviewed against the current implementation on 2026-05-15

Focused tests:

- `04_Software/AudioMancer/tests/test_ui_state_service.py`

The v2 translation-catalog test verifies that the English and Romanian catalogs
contain the selective-impact labels, dialog titles, confirmation messages, and
status messages introduced by the preservation workflow.

Minimum validation after changing this component:

```powershell
uv run python -m py_compile src/audiomancer/services/ui_state_service.py tests/test_ui_state_service.py
uv run ruff check src/audiomancer/services/ui_state_service.py tests/test_ui_state_service.py --fix
uv run ruff format src/audiomancer/services/ui_state_service.py tests/test_ui_state_service.py
uv run pytest tests/test_ui_state_service.py
```

When catalog keys used by pages change, also run the focused page tests that
consume those keys.

## 10. Limitations And Future Work

The catalog is a Python dictionary, so missing-key coverage depends on focused
tests and exercised UI paths. The service does not load external translation
files and does not perform pluralization, locale-specific formatting, or
right-to-left layout handling.
