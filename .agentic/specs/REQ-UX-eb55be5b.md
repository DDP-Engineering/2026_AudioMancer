<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-UX-eb55be5b - Preserve the selected enabled translation profile across refreshes

## Behavior

Before rebuilding AI Translation state, the main window captures the page's
current profile identifier. That candidate is supplied to both the translation
state builder and profile state builder, so their `selected_profile_id` values
are resolved from the same input and agree during the refresh.

Resolution keeps the candidate only when it is present and enabled. Otherwise
it selects the configured AI Translation default when that profile is enabled,
then the first enabled profile in settings order, then `None`. Initial loading
passes no live candidate and follows the same default fallback. The selection
is session-local and does not add settings persistence.

## Data / interface

`build_ai_translation_state(...)` accepts an optional
`selected_profile_id: str | None = None` argument and passes it to
`build_ai_translation_profile_state(...)`. The returned translation-state
dictionary and profile-state dictionary carry the same resolved identifier.

## Examples

With enabled default `profile-a` and current `profile-b`, a refresh keeps
`profile-b`. If `profile-b` is disabled or removed, the refresh selects
`profile-a`. If both are unavailable, the first enabled profile is selected.

## Acceptance

- Editing, approval, operation completion/failure/cancellation, and
  retranslation refresh paths retain a still-enabled live selection through
  the shared main-window refresh entry point.
- Removed and disabled candidates follow the documented fallback order.
- Initial load still selects the configured enabled default.
- Both state-builder outputs agree on the selected identifier.
