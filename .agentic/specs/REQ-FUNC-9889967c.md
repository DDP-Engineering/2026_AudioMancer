<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-FUNC-9889967c - Honor caller instructions for non-resumable translation starts

## Behavior

`start_or_continue_translation` chooses instructions before budget calculation
and uses that exact value for budget calculation, every rendered translation
request, and `additional_translation_instructions` in the durable document.

Selection matrix:

| Existing document | Persisted status | Caller argument | Selected value |
|---|---|---|---|
| no | n/a | any | normalized caller value |
| yes | `running`, `in_progress`, `cancelled`, or `failed` | any | stored value |
| yes | `review_pending` or `completed` | non-`None` | normalized caller value |
| yes | `review_pending` or `completed` | `None` | stored value |

Normalization uses the existing helper: `None` becomes an empty string when a
new document is created, and other supplied values are converted to string and
trimmed. Stored values have already passed strict document validation and are
retained as persisted.

One-off instructions supplied to `retranslate_chunk` remain request-local and
do not overwrite the document's general start/resume instructions.

## Data / interface

No public signature, controller prompt flow, or document schema changes. The
existing `additional_translation_instructions` argument and persisted field
retain their types and meaning.

## Examples

- Resuming a failed document stored with `Keep names` ignores a newly supplied
  `Use casual speech` argument and continues with `Keep names`.
- Restarting work from a completed document with `  Use casual speech  ` uses
  and persists `Use casual speech`.
- Restarting a completed document with no new argument retains its stored
  instructions.

## Acceptance

Parameterized tests cover all resumable statuses, both non-resumable statuses,
the absent non-resumable argument, new-document normalization, prompt content,
budget input, durable persistence, and one-off retranslation isolation.
