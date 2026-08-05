<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-UX-7e8fb80a - Preserve translation editor context on same-content refresh

## Behavior

Refreshing AI Translation state may rebuild the chunk list, but displaying the
selected chunk compares source and translated values independently with the
corresponding editor text. An editor whose incoming value is identical is not
cleared and does not receive `setPlainText`, so Qt retains its document-backed
cursor, anchor, undo/redo stack, and both scroll-bar positions.

The translated-text loading guard is active only while a genuinely different
authoritative translated value is assigned. A same-content refresh therefore
does not manufacture another manual-edit signal, while a differing value still
replaces stale content under the guard.

## Data / interface

The existing `AiTranslationPage.set_translation_state(...)` and
`_show_selected_chunk(row)` interfaces remain unchanged. Equality is exact
string equality; whitespace is operator-owned content and is not normalized.

## Examples

If the editor contains `alpha beta`, its cursor is between the words, and the
refreshed chunk also contains `alpha beta`, the document is untouched and a
subsequent `X` produces `alphaX beta` at that cursor.

If the refreshed chunk contains `alpha beta!`, the translated editor becomes
exactly `alpha beta!` without emitting `translated_text_changed`.

## Acceptance

- A debounce flush followed by controller-driven same-content state refresh
  preserves cursor/anchor, selection, undo availability, and both scroll bars.
- Typing after that refresh produces the exact expected character order in the
  next emitted or persisted translation.
- Source and translated editors each preserve state independently when equal.
- A differing authoritative value updates only the editor whose value differs.
