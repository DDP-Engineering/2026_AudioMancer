<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-FUNC-ee95beb7 - Reject selected-chunk retranslation before translation starts

## Behavior

The selected-chunk retranslation controller validates that authoritative
translation state has started before prompting for instructions or starting an
operation. A `not_started` summary is an unavailable action and returns without
calling the operation runner, presenting an avoidable operation error, saving
the manifest, or creating/modifying the translation document.

The page remains the primary availability boundary; this controller check is a
defensive boundary for impossible programmatic or stale-signal requests.

## Data / interface

The existing `handle_retranslate_selected_requested(window, profile_id,
chunk_id)` signature remains unchanged. It reads the authoritative translation
summary for the active project before instruction collection and dispatch.

## Examples

For a chunked project with no `translated_text.json`, directly invoking the
handler leaves `current_stage` and the manifest file unchanged and starts no
threaded operation.

## Acceptance

- The unavailable handler path has no worker, prompt, error, manifest, or
  translation-document side effects.
- A started translation continues through the existing validation and worker
  flow without semantic changes.
