<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-FUNC-c30ccde3 - Whitespace-only Cleanup edits preserve only unambiguous paragraph provenance

## Behavior

Whitespace-only paragraph reconstruction groups both prior and rebuilt
paragraphs by the shared normalized-content comparison key. A match is
unambiguous only when that key occurs exactly once in the prior records and
exactly once in the rebuilt records. Positional order never resolves duplicate
keys. Merged, split, unmatched, and ambiguous paragraphs keep the conservative
metadata produced by user-edited paragraph classification.

For an unambiguous match whose prior record has
`provenance_available = true` and at least one source unit identifier, copy its
ordered, first-occurrence-deduplicated `source_unit_ids`, source page fields,
page-transition flags, confidence, and reason codes. Append
`user_whitespace_realign` once after the retained reason codes. Keep the safe
role policy: an explicitly classified scene separator remains one, and a prior
scene-separator role is not carried onto classifier-negative text.

If the prior record has unavailable or empty provenance, retain role and reason
history only; clear source unit identifiers and source page fields, set both
transition flags false, and keep `provenance_available = false`. Every
unresolved rebuilt paragraph uses the same unavailable provenance fields.
Warning-producing retained reason codes continue through the existing runtime
warning projection. A document may contain both truthfully matched and
unresolved paragraphs.

Lexical edits keep the existing `user_edited` structure source and unavailable
provenance. Whitespace-only edits keep `cleanup_roles`, current offset
reconstruction, scene-separator classification, and downstream chunking
behavior. No metadata field is added or removed.

## Data / interface

No public API or schema change. `save_user_cleaned_text` continues to persist
the existing paragraph fields. The private whitespace realignment helper
matches runtime records containing `text` and updates only existing fields.

## Examples

- Unique prior paragraphs `Alpha` and `Beta` retain only their own source IDs.
- Two prior or two rebuilt `Same` paragraphs are ambiguous and retain no source
  provenance, regardless of position.
- A merged `Alpha Beta` and split `Alpha` / `Beta` are unresolved.
- A unique `Alpha` can retain provenance while a new or split neighbor cannot.
- Prior `deterministic_fallback` remains in `reason_codes` and therefore in
  downstream `warning_flags`, followed once by `user_whitespace_realign`.

## Acceptance

Focused Cleanup service, quality-contract, and metadata tests cover unique,
mixed, ambiguous, merge/split, warning, lexical-edit, scene-separator, role,
chunking, and persisted-offset behavior without changing the metadata schema.
