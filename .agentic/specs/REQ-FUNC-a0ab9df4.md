<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-FUNC-a0ab9df4 - Preserve review state when selected-chunk retranslation is interrupted

## Behavior

`retranslate_chunk` treats a provider exception and `OperationCancelledError`
as an unsuccessful one-off attempt, not as a failed or cancelled batch. It
propagates the original exception after persisting token usage accrued by
completed provider segments. It does not replace any chunk text or approval,
including with partial translated segments, and derives the document status
from the unchanged review records. A completed verified result remains completed.
An unsuccessful one-off request never promotes an interrupted batch to completed.
Cancellation at the publication boundary records usage and preserves the original
text and approval state.

A successful selected-chunk attempt keeps the established contract: replace
only the selected text, clear only its approval, persist the new budget and
usage, and derive status from all chunks. Main batch translation continues to
persist `cancelled` or `failed` on interruption.

## Data / interface

On interrupted selected retranslation, `budget_metadata` and general
`additional_translation_instructions` remain their pre-attempt values; only
`token_usage` and the derived `status` may change.

## Examples

- A completed two-chunk document stays completed and downstream-complete after
  either cancellation or provider failure while retrying one chunk.
- A review-pending document stays review-pending, and a document containing an
  untranslated chunk stays in-progress.
- If segment one accrues usage and segment two fails, no segment-one text is
  stored in the selected chunk, but segment-one usage is stored.

## Acceptance

Focused tests cover both exception types, all three derived statuses, complete
chunk-record equality, usage after a partial segment, successful retranslation,
one-off instruction isolation, downstream completion, and distinct batch
interruption statuses.
