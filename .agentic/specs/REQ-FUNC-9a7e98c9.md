<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-FUNC-9a7e98c9 - Flush pending translation edits before worker dispatch

## Behavior

The Start/Resume action synchronously flushes the page's pending translated-text
edit before emitting `start_translation_requested`. The flush stops the
single-shot timer, clears the pending tuple before persistence observers run,
and emits one `translated_text_changed` event. The subsequent start event is
therefore observable only after persistence has completed.

Calling the flush without a pending tuple emits nothing. Entering busy state
also stops the timer defensively, so no timeout callback can run after a worker
has begun. Existing selection-change, approval, retranslation, and close flows
continue to use the same idempotent flush operation.

## Data / interface

No persistence architecture or signal signature changes. The ordering contract
is:

1. `translated_text_changed(chunk_id, exact_text)` when an edit is pending;
2. synchronous controller persistence and page refresh;
3. `start_translation_requested(profile_id)`;
4. page busy state with an inactive edit timer.

## Examples

Typing `latest` and immediately selecting Start/Resume produces an update event
for `latest` before the start observer loads the translation document. Clicking
Start/Resume with no pending edit produces only the start event.

## Acceptance

- Page tests observe update-before-start order and an inactive timer.
- Re-entering busy state cannot produce a later translated-text callback.
- A controller-level test proves the mocked worker reads the latest exact edit.
- No-pending and already-flushed paths do not duplicate persistence.
