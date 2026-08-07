<!-- Copyright (c) 2026 DDP Engineering. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 -->
# REQ-FUNC-9b951004 - Character Discovery shall persist rejected-candidate diagnostics

## Behavior

The authoritative `characters.json` root gains `rejected_candidates`, always
an array. It is empty until candidate merging completes, then retains the
rejections through synthesis interruption, repeated compatible resume, manual
profile maintenance, and completed output. A new or forced run starts with an
empty array.

## Data / interface

Each entry contains exactly `canonical_name`, `reason`, `evidence_count`, and
`identity_merge_count`. `canonical_name` is a non-empty string; `reason` is
`missing_evidence` or `missing_spoken_dialogue_evidence`; `evidence_count` is
a non-negative integer; and `identity_merge_count` is a positive integer.
Entries contain no excerpts, prompts, model responses, provider settings, or
credentials. The strict reader rejects an extra or missing field, an invalid
reason, a blank name, a non-integer count, a negative evidence count, or a
non-positive merge count.

The writer retains exactly one entry for each normalized character identity and
reason. Repeated occurrences merge by retaining the first display spelling and
the greatest evidence and identity-merge counts; entries are ordered by
case-folded canonical name then reason. This makes resumed output deterministic
and prevents warning-count inflation. `character_operation_summary()` returns
the number of persisted unique entries as `warning_count`; state builds one
localized warning per reason/count group; the Characters export includes that
same warning count.

## Examples

Two resumed attempts to persist `Ari/missing_evidence` produce one `Ari`
diagnostic, not two. An entry containing `source_excerpt` is invalid. A
completed document with two valid entries yields manifest, page, and export
warning counts of two.

## Acceptance

The strict document validator, resume path, summary projection, localized page
notes, and character export all use the same durable diagnostic array; no
projection reconstructs diagnostics from transient prompts or model responses.
