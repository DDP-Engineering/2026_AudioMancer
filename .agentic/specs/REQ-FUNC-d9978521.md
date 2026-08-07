<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->

# REQ-FUNC-d9978521 - Character Discovery shall retain last-used enabled AI profile selection

## Behavior

Each start or resume stores the invocation's stable enabled profile ID as the
single last-used selection.  It is not candidate attribution and does not
store copied provider configuration or credentials.  A page refresh preserves
an enabled live page selection.  A fresh page load with no live selection
prefers an enabled persisted last-used ID, otherwise the enabled configured
Character Discovery default, then the first enabled profile.

## Data / interface

The exact root fields of `characters.json` include required string
`character_profile_id_last_used`.  All existing root and checkpoint exact-field
validation remains strict: old seven-field documents, missing/non-string
profile IDs, and extra fields are invalid and use the established Reset-only
page recovery rather than repair or a sidecar.  The document contains no
profile payload, provider settings, or credential fields.

`build_character_discovery_state` accepts the currently live selected ID.  Its
selection order is enabled live ID, enabled persisted last-used ID, enabled
configured default, first enabled ID, then `None`.

## Examples

After a cancelled run with profile A, an operator selects enabled profile B
and presses Resume.  The worker receives B and every state write for that
invocation has `character_profile_id_last_used = "B"`; a later fresh page load
selects B if it remains enabled.

## Acceptance

- Profile choice remains enabled-only and follows the stated precedence.
- Resume uses the operator's current selected profile and replaces the single
  stored last-used ID.
- Invalid documents remain untouched and never leak a raw stored profile ID.
