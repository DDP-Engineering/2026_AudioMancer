<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: Complete UI Localization Coverage

Companion specification for the UX requirement that every app-owned
operator-facing string is available in English and Romanian and is applied to
the active Qt surface.

- Requirement: the `ux` localization binding requirement.
- Affected files:
  - `05_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
  - `05_Software/AudioMancer/src/audiomancer/ui/pages/*.py`
  - `05_Software/AudioMancer/src/audiomancer/ui/controllers/*.py`

## Behavior

### Persistent windows and pages

Every app-owned title, group title, label, button, checkbox, option label,
empty-state message, placeholder, special spin-box value, and tooltip shall be
resolved from the shared UI string catalog. Calling `apply_language(language)`
shall refresh both static widget text and dynamic option labels without
changing the option data, current selection, persisted setting, or operator
content.

The audit includes the shell, sidebar, Settings, AI Settings, TTS Settings,
Home, Text Cleanup, Text Chunking, AI Translation, Characters, Narator Voice,
Character Voices, Speech Blocks, Audio Blocks, Audio Assembly, and the shared
operation-progress dialog.

### Dialogs and operation progress

Every app-owned popup title, message, prompt label, custom button, file filter,
operation name, and initial operation status shall be resolved through
`ui_state_service.translate()` before it is passed to Qt or a shared dialog
helper. An empty file-dialog start path is data, not operator-facing text.

### Dynamic choices

Stable internal values remain language-neutral while their visible labels are
localized:

- UI and text-window font-size steps;
- built-in theme names, while custom theme names remain operator-authored;
- chunking strategy tokens;
- project and workflow language codes;
- empty, unknown, and not-translated values;
- TTS automatic/random special values.

Changing the UI language must preserve the current item by its data value.

### Exclusions

Brand names, provider/model identifiers, URLs, API field abbreviations,
technical file-format names, numeric units, generated project content, and
operator-authored names are not translated. Qt-native standard buttons are
outside the app-owned catalog unless AudioMancer supplies custom text.

## Acceptance

- [ ] English and Romanian catalogs contain identical keys.
- [ ] Settings fully localizes labels, preview content, font-size choices, and
      built-in theme names while preserving combo data and selection.
- [ ] Each audited persistent page has no known app-owned English fallback
      after Romanian is applied.
- [ ] Language and chunking-strategy choices use localized labels with stable
      language-neutral data.
- [ ] TTS special values and help text are localized.
- [ ] App-owned popup and operation-progress text is translated before display.
- [ ] Focused UI localization and dialog tests pass without running the full
      application test suite.
