<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# REQ-FUNC-e42171cc - Cleanup shall reject newly introduced rendered alphanumeric fusion

## Behavior

Fusion validation examines the completed rendered text together with its
retained source-span and rendered-boundary projection. Two Unicode-alphanumeric
characters touching at one output offset count as introduced fusion only when
they belong to different retained source spans. Existing adjacency within one
span is outside this check.

An otherwise introduced join is authorized only when an applicable
`dehyphenate` decision actually removed the source-terminal hyphen from the
left retained span at that output offset. A dehyphenation whose left unit was
dropped, or whose projection belongs elsewhere in the same dropped-unit chain,
does not authorize the join. `join_preserving_hyphen` remains safe because the
rendered hyphen separates the alphanumeric endpoints.

Spaces, line separators, paragraph separators, punctuation, and every other
non-alphanumeric rendered boundary are safe. Any positive fusion count aborts
rendering with `CleanupRenderError` before text or metadata publication;
successful quality reports retain `introduced_fusion_count = 0`.

## Data / interface

No public signature or persisted schema changes. `render_cleanup` continues to
return `(cleaned_text, metadata)`. Its private rendered-boundary projection may
carry transient evidence identifying whether dehyphenation was applied and to
which retained left source span; that evidence is not persisted.

## Examples

- `alpha` plus a rendered space plus `beta` is safe.
- `inter-` plus applicable `dehyphenate` plus `national` renders
  `international` and is safe.
- `civil-` plus `join_preserving_hyphen` plus `defense` stays safe.
- `alpha` plus an unauthorized empty boundary plus `beta` is rejected.
- Dropping intervening units cannot make `alpha` and `beta` touch unless the
  actual left retained span is dehyphenated at that join.
- `word` beside punctuation or punctuation beside `word` is safe.

## Acceptance

Focused renderer tests prove safe separator, dehyphenation, preserved-hyphen,
and punctuation cases remain green; direct and dropped-chain unsafe joins raise
before a result is returned; and the fusion counter returns a positive value
for a controlled unsafe rendered projection.
