<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# Spec: Cleanup + Chunking quality contract

Companion specification for the current Cleanup + Chunking requirement
snapshots.

## Behavior

Cleanup projects the canonical source ledger into one safe text output. Native
document structure and unit roles are resolved before line-boundary decisions.
PDF and TXT use deterministic layout/text evidence; only contradictory or
low-confidence cases may be adjudicated by an optional LLM.

The durable Cleanup state is one `cleanup.json`. It is both checkpoint and final
metadata. `clean_text.txt` is the only Cleanup text output. No report, state,
paragraph-metadata sidecar, schema version, migration, or compatibility branch
is retained.

Cleanup remains usable without an LLM. Provider incompatibility, insufficient
context, invalid structured output, and exhausted batch retries apply the
deterministic prior locally and do not abort the rest of the document.

Chunking consumes completed Cleanup paragraphs, roles, confidence, and
provenance from `cleanup.json`. Semantic structure takes precedence over target
chunk-size balance.

## Canonical generation naming

AudioMancer uses one hard-break implementation and one canonical persisted
schema. Active source, tests, fixtures, support modules, specifications,
requirements, logs, and current documentation use unversioned names. No
product-generation label distinguishes the current contract.

Strict validation remains authoritative. Corrupt, incomplete, or old-shaped
data is rejected through the same generic validation paths; removing
generation-specific compatibility assets does not relax the canonical schema.

### Development-phase schema compatibility

While AudioMancer is in development, only the current canonical project-artifact
schema is supported. Schema corrections are intentionally breaking: loaders do
not detect, default, normalize, or migrate fields from older persisted shapes.
Project artifacts created by an earlier schema are not compatibility targets.

For Chunking, every chunk must contain the complete current field set. A
`chunks_text.json` document that omits `starts_after_scene_separator` is
incompatible even when every older field is otherwise valid. A direct load
raises `IncompatibleChunkingDocumentError`. During project open, the existing
bounded recovery resets Chunking and all downstream derived operation data,
retries validation once, and preserves Source, Extraction, and Cleanup. This
destructive derived-state reset is an accepted development-phase migration
cost, not a request to add a compatibility branch.

Version tokens remain only when they are part of a real current contract, such
as an external API route, an artifact-format token, semantic source metadata, a
release/dependency identifier, or historical changelog material.

## Supported domain

- Formats: TXT, Markdown, RTF, DOCX, ODT, EPUB, and PDF with extractable text.
- Source-content languages: `en`, `ro`, `de`, `fr`, `ru`, `pt`, `es`, and `it`,
  exposed as `config.CLEANUP_SUPPORTED_SOURCE_LANGUAGES`.
- Operator interface languages are a separate platform contract and do not
  derive from the Cleanup source-content language set.
- Scripts: Latin and Cyrillic.
- Predominantly CJK or Hangul source text is rejected before Cleanup rendering.
- PDF without an extractable text layer remains unsupported.

## Cleanup document

The root is a strict object with no additional fields:

```text
{
  "status": "running | paused | finalizing | completed | failed",
  "phase": "analysis | adjudication | rendering | done",
  "started_at": string,
  "updated_at": string,
  "completed_at": string | null,
  "source_hash": sha256,
  "ledger_hash": sha256,
  "policy_hash": sha256,
  "prompt_hash": sha256,
  "profile_fingerprint": object | null,
  "document_profile": object,
  "unit_operations": [UnitOperation],
  "boundaries": [BoundaryDecision],
  "paragraphs": [ParagraphRecord],
  "progress": Progress,
  "warnings": [string],
  "token_usage": TokenUsage,
  "quality_report": QualityReport,
  "output_hash": sha256 | null,
  "user_modified": boolean,
  "structure_source": "cleanup_roles | user_edited"
}
```

`profile_fingerprint` contains only profile ID, backend kind, model name,
context window, structured-output capability, and request-policy settings. It
never contains an API key or prompt fragment.

`policy_hash` is the SHA-256 of the canonical deterministic analysis result and
its effective thresholds. `prompt_hash` is the SHA-256 of the exact prompt
templates, examples, and response schema.

### UnitOperation

```text
{
  "operation_id": string,
  "action": "drop_page_artifact | set_role",
  "target_id": unit_id,
  "evidence": string,
  "role": role | null
}
```

Roles are `body`, `heading`, `scene_separator`, `list_item`, `verse`,
`preformatted`, `footnote`, or `page_artifact`.

### BoundaryDecision

```text
{
  "boundary_id": string,
  "left_unit_id": string | null,
  "right_unit_id": string | null,
  "kind": string,
  "page_transition": boolean,
  "left_role": role | null,
  "right_role": role | null,
  "prior": {
    "choice": choice,
    "confidence": "strong | medium | low",
    "reason_codes": [string]
  },
  "adjudication": {
    "state": "not_required | pending | completed | fallback",
    "primary_choice": choice | null,
    "verifier_choice": choice | null,
    "accepted": boolean
  },
  "final": {
    "choice": choice,
    "origin": "native | deterministic | llm | fallback | user",
    "confidence": "strong | medium | low",
    "reason_codes": [string]
  }
}
```

Boundary choices are `join_with_space`, `set_paragraph_break`,
`set_semantic_line_break`, `dehyphenate`, `join_preserving_hyphen`, and
`document_end`. `join_without_space`, generic `preserve`, and replacement text
are invalid.

### ParagraphRecord

Paragraph records do not duplicate text. They contain output offsets, role,
confidence, reason codes, source page range, page-transition flags, and source
unit IDs. Chunking slices `clean_text.txt` by these offsets after verifying
`output_hash`.

### Progress

```text
{
  "question_count": integer >= 0,
  "batch_order": [[boundary_id]],
  "next_batch_index": integer >= 0,
  "completed_request_count": integer >= 0,
  "estimated_request_count": integer >= 0,
  "estimated_input_tokens": integer >= 0
}
```

### Loaded-document validation

`load_cleanup_document` treats persisted Cleanup data as untrusted input. The
`progress` object has exactly the fields shown above. Every numeric progress
field is a non-boolean integer greater than or equal to zero; `batch_order` is a
list of lists of string boundary IDs; and `next_batch_index` does not exceed the
number of batches. A missing field, extra field, invalid value type, negative
counter, malformed batch, or out-of-range next index raises
`CleanupDocumentError`.

For a completed document, each blocking quality metric
(`introduced_fusion_count`, `projection_violation_count`,
`invalid_operation_count`, and `unclassified_boundary_count`) is required to be
a non-boolean integer equal to zero. Missing, malformed, boolean, or nonzero
values raise `CleanupDocumentError`; the validator never exposes a conversion
`TypeError`, lookup `KeyError`, or shape-related `AttributeError` to callers.

Project completion evidence treats `CleanupDocumentError` as unavailable
Cleanup completion. Project opening returns through the existing validation
flow with `status="ok"` or `status="repair_required"`, according to whether
the remaining artifact evidence implies a concrete metadata normalization; it
never propagates the Cleanup document-validation exception.

## Deterministic decisions

Precedence is:

1. native paragraph, heading, list, preformatted, and explicit line-break data;
2. protected unit role;
3. deterministic layout/text prior;
4. optional LLM adjudication;
5. deterministic fallback.

Native structure is authoritative. For PDF/TXT, the prior uses indentation,
relative line length, terminal punctuation, font signature, column, body band,
vertical isolation, blank lines, and page transition.

Page artifacts are removable only when they are bounded page numbers or repeat
at a compatible page edge. After removal, the nearest surviving narrative
units receive an explicit boundary decision. Two alphanumeric source slices
may never become newly adjacent.

Verse detection for non-native sources requires at least three consecutive
short lines, stable left alignment (4 pt PDF or two characters TXT), at least
two-thirds without sentence-terminal punctuation, and block isolation by a
blank line, heading, separator, or enlarged vertical gap. Lists, tables,
marked dialogue, and preformatted blocks are excluded. Lines within a stanza
use semantic line breaks; stanza boundaries use paragraph breaks.

Soft hyphen uses `dehyphenate`. A visible source hyphen may use
`join_preserving_hyphen`. Vocabulary frequency is evidence only and cannot
authorize generic no-space joining.

## LLM adjudication

- No usable profile, context below 16K, or absent structured output means
  deterministic-only completion.
- Initial batch sizes are 4 for 16K-31K, 8 for 32K-127K, and 16 for 128K+.
- A batch that exceeds the safe context budget is split recursively to one
  question; an oversized single question falls back locally.
- A failed/invalid batch is retried once, then falls back locally while later
  batches continue.
- Strong deterministic decisions are never submitted.
- Primary agreement retains the prior without a verifier.
- Primary disagreement or no prior triggers a blind verifier.
- The LLM overrides the prior only when primary and verifier return the same
  valid choice.
- Request parameters are emitted only when supported by the backend.

No global question cap is applied. After deterministic analysis, the existing
progress dialog reports question, request, and token estimates and continues
automatically.

## Stop, resume, and publication

`cleanup.json` is written atomically after deterministic analysis, after every
primary/verifier request, on cancellation, and before rendering.

- Exact source, ledger, policy, prompt, and profile: resume the first incomplete
  request.
- The first progress update after an exact resume is reconstructed from the
  persisted completed and estimated request counts. It may not be lower than
  the last checkpointed request percentage.
- Conditional verifier requests that are not needed do not prevent the AI phase
  from reaching its reserved completion percentage before rendering begins.
- Changed model, context, request policy, or prompt: preserve deterministic
  analysis, clear all AI adjudication, and rebuild AI batches.
- Changed policy result: rebuild deterministic analysis and AI adjudication.
- Changed source or ledger: start a new Cleanup document.
- Resume with no AI profile: finalize from deterministic priors.
- `finalizing` with complete decisions: rerender without an LLM call.
- A reusable `completed` checkpoint is returned only when `clean_text.txt`
  exists and its hash matches `output_hash`; otherwise rerender the persisted
  decisions without an LLM call.

`clean_text.txt` is replaced atomically only after validation. Existing text is
not consumable while metadata is non-completed. Same persisted decisions must
render byte-identically.

## Validation and quality

Blocking runtime counts are:

```text
introduced_fusion_count == 0
projection_violation_count == 0
invalid_operation_count == 0
unclassified_boundary_count == 0
```

Authorized source removal is limited to recorded `drop_page_artifact`
operations and validated dehyphenation. User lexical edits are explicitly
outside the automated projection guarantee.

Runtime quality also reports low-confidence boundaries, page transitions,
artifact removals, deterministic/LLM/fallback counts, override count/rate,
failed batches, online fragment count/backend, and token usage. It does not
report F1 or other metrics requiring ground truth.

## Manual edits

Whitespace-only edits update boundary choices, paragraph offsets, and output
hash while retaining unambiguous roles/provenance. Prior roles are realigned by
paragraph content, never by list index:

- the comparison key is the paragraph text normalized with NFKC, collapsed
  whitespace, trimming, and case folding;
- a prior role is eligible only when exactly one prior paragraph has the same
  non-empty comparison key;
- a current paragraph positively classified as an explicit scene separator
  remains `scene_separator`;
- a prior `scene_separator` role is never carried when the current paragraph
  text is not positively classified as a scene separator;
- unmatched or multiply matched content retains the current classifier result,
  so prose falls back to `body`.
- when any retained source unit cannot be located, the edit still persists but
  the component logger warns and `cleanup.json.warnings` contains the stable
  token `user_whitespace_realign_incomplete`.

This rule applies even when a merge before a scene separator and a split after
it preserve the total paragraph count. Lexical edits set `user_modified=true`
and `structure_source="user_edited"`, rebuild minimal paragraph records, mark
unavailable provenance explicitly, and invalidate all downstream operations.
When paragraph records are rebuilt from user-edited text, conservative explicit
scene-separator forms are assigned `role="scene_separator"` instead of the
generic `body` fallback. Ambiguous punctuation and lexical content remain
`body`. This classification does not restore source provenance that was made
unknown by a lexical edit.


## Existing UI

The Text Cleanup page keeps its current selector, Cleanup/Reset buttons, two
previews, Edit/Save/Cancel controls, progress dialog, and status pane. No new
page, table, drill-down, dialog, or button is introduced.

The existing Cleanup action starts a new run or resumes a paused run. The
existing progress-dialog Cancel action persists `paused`. The status pane shows
status, low-confidence count, fallback count, override rate, and validation.

New status copy:

```text
Cleanup analysis: {ambiguous} ambiguous boundaries; estimated {requests} AI requests and {tokens} input tokens.
Cleanup paused after batch {completed}/{total}.
Cleanup resumed from batch {next}/{total}.
Cleanup completed with {low_confidence} low-confidence boundaries.
Cleanup supports Latin and Cyrillic source text only; the document appears to use CJK or Hangul.
```

### Project-open recovery notice

When project opening reports `recovered_operations = ["chunking"]`, Home shows
the existing localized recovery information exactly once:

```text
title key: dialog.project_recovery_title
message key: project.chunking_self_heal_message
```

The notice remains post-hoc: automatic Chunking and downstream reset completes
before the controller receives the project-open result, and no self-heal
confirmation is added.

If the same result has `status = "repair_required"`, Home shows the recovery
information before `confirm_project_repair`. This ordering applies to both
follow-up outcomes:

- Decline: recovery information, then repair question; the project remains
  unopened and `repair_project` is not called.
- Accept: recovery information, then repair question, repair, and activation;
  the recovery information is not repeated after activation.

An ordinary successful recovery without a follow-up repair retains the existing
activation and single-notice behavior. A result that does not report recovered
Chunking data shows no recovery information. No combined dialog, new copy,
additional logging, or service-level recovery change is part of this contract.

## Chunking

Chunking accepts only completed `cleanup.json` with matching `clean_text.txt`.
Candidate cuts are ordered by chapter/heading, scene separator, other structural
boundary, then a sentence-complete paragraph. Heading, separator, list, verse,
and preformatted boundaries do not require sentence-terminal punctuation.

Bare Roman-numeral chapter labels must be uppercase, non-empty, and valid under
the standard subtractive Roman grammar. Values such as `I`, `IV`, `XIV`, and
`MCMXCIV` are headings; lowercase values and invalid Roman-only words such as
`civil`, `mix`, and `did` are ordinary text. This rule is identical in Cleanup
analysis, deterministic Chunking, and the canonical Chunking report projection.

Cleanup paragraph `reason_codes` remain provenance. Runtime and persisted chunk
warning flags contain only the explicit warning reason codes
`deterministic_fallback`, `unknown_line_boundary`, and
`page_transition_repaired`; benign provenance such as `user_edited`,
`llm_verified_override`, and `user_whitespace_realign` is not a warning. The
strict Chunking field set is unchanged.

Every persisted chunk contains the required boolean field
`starts_after_scene_separator`. The field describes the leading boundary, not
the chunk text:

```text
{
  "cleanup_role": "body | heading | list_item | verse | preformatted | footnote",
  "starts_after_scene_separator": boolean
}
```

The first narratable chunk after one or more recognized scene separators uses
`starts_after_scene_separator=true`; all other chunks use `false`. A leading
separator therefore marks the first narratable chunk, consecutive separators
collapse to one leading marker, and a trailing separator with no following
narration emits no chunk. The narratable chunk retains its content role and is
never relabeled `scene_separator`.

The field currently preserves structural truth only. Translation, character
discovery, Speech Blocks, Audio Blocks, and Audio Assembly do not consume it in
this contract. Issue #35 intentionally leaves those runtime behaviors
unchanged. Requirement `REQ-FUNC-bfbe8c95-59a0-47e2-bec7-5847177bc3cf`
keeps that implemented limitation visible in the component contract.
Separately planned runtime requirement
`REQ-FUNC-ca5357e1-f690-4254-981b-d803fe5fb385` defines a configurable
scene-transition pause consumer; it must receive a dedicated owner-approved
design for pause duration and interaction with ordinary inter-chunk silence and
scene ambience before activation.

Manual text edits preserve the selected chunk's leading scene marker. A newly
inserted chunk defaults to `false`. When a chunk whose marker is `true` is
deleted, the marker transfers to the next surviving chunk when one exists so
that deletion does not silently erase the structural boundary.

The Chunking services persist operation state only through the canonical
`chunks_text.json` document API. They do not read, write, rebuild, or migrate
the obsolete checkpoint, report, or state sidecars. Obsolete filenames remain
owned only by Reset Chunking so explicit or automatic recovery can delete
stale derived artifacts without interpreting them.

Deterministic Chunking keeps the canonical document recoverable without
rewriting it after every paragraph:

- write one initial `running` document before processing;
- write a `running` checkpoint after 200 additional processed paragraphs or
  after 2.0 elapsed monotonic seconds, whichever occurs first;
- every running checkpoint stores the chunks produced from exactly the
  processed paragraph prefix and sets `next_paragraph` to the following
  one-based paragraph index, including when the prefix contains omitted
  non-narratable separators;
- emit non-terminal progress no more often than once per 0.1 elapsed monotonic
  seconds;
- on success, write exactly one terminal `completed` document with
  `next_paragraph=null` and final warnings before returning;
- on cancellation or unexpected failure, write exactly one terminal document
  with the matching status and the current resume-consistent checkpoint before
  propagating the exception.

For 1,000 narratable paragraphs under a fixed monotonic clock, persistence is
bounded to the initial running document, five interval checkpoints, and one
completed terminal document. AI-assisted Chunking retains its existing
one-write-per-model-window behavior.

AI descriptor validation is lossless and progress-preserving:

- an exact punctuation-only anchor such as `* * *` is valid when its normalized
  whitespace and case match the complete source paragraph;
- when a descriptor list has a consecutive valid prefix followed by an invalid
  descriptor, Chunking commits the valid prefix and requests the uncommitted
  tail again;
- when no descriptor prefix is valid, deterministic fallback preserves typed
  headings and scene separators as distinct ranges before any whole-window
  fallback;
- user-edited Cleanup structure recognizes the explicit separator form
  for this deterministic fallback even when source provenance and the original
  role are unavailable;
- invalid-provider recovery must neither lose nor duplicate source paragraphs.

Scene separators remain in Cleanup text and AI context as structural evidence,
but they are non-narratable at Chunking materialization:

- an explicit `scene_separator` role is authoritative;
- conservative marker-only forms cover repeated asterisks, dashes, underscores,
  tildes, number signs, equals signs, bullets/diamonds, and common single
  ornamental scene-break glyphs;
- markers split a selected AI or deterministic range into narratable ranges;
- marker text is omitted, and a marker-only range emits no chunk;
- lexical or ambiguous punctuation such as `...`, `…`, a single dash,
- the first narratable chunk after an omitted marker persists
  `starts_after_scene_separator=true`;
  `### Title`, and `x x x` remains narratable unless Cleanup explicitly assigns
  the `scene_separator` role;
- input containing only recognized separators is rejected rather than producing
  an empty completed Chunking document.

## Examples

| Input | Expected result |
| --- | --- |
| `the evacuation\ndropships` | `the evacuation dropships` |
| `civil-\ndefense` | `civil-defense` |
| `inter\u00AD\nnational` | `international` |
| dropped page number between `valid` and `words` | nearest surviving units retain at least one typed separator |
| three aligned short verse lines | semantic line breaks inside one stanza |
| provider batch fails twice | affected boundaries use priors; next batch runs |
| resume with a different 32K model | deterministic analysis retained; all AI answers regenerated |
| `status=paused` with an old output file | Chunking rejects the output |
| lexical manual correction | minimal `user_edited` structure; downstream invalidated |
| completed checkpoint with missing or hash-invalid output | deterministic rerender without an LLM request |
| whitespace-only edit cannot locate one retained source unit | edit persists; logger and Cleanup document record incomplete realignment |
| bare `XIV` / bare `civil` | chapter heading / ordinary text |
| paragraph reasons include `user_edited` and `unknown_line_boundary` | provenance keeps both; warning flags keep only `unknown_line_boundary` |
| `Narrative A\n\n* * *\n\nNarrative B` | two narratable chunks; separator omitted; second chunk has `starts_after_scene_separator=true` |
| merge `A` + `B` before `* * *`, split `C D` after it, count unchanged | only `* * *` is `scene_separator`; deterministic Chunking materializes `A B`, `C`, and `D` |

## Oracle and acceptance corpus

The automated oracle compares canonical text, ledger, expected structure, and
cleaned output. F1 is test-only.

The synthetic corpus contains 20-25 fixtures and covers every supported format,
language, and structural archetype. Mandatory distinct pairs include
PDF/poetry, EPUB/poetry, DOCX/native line break, Markdown/preformatted,
PDF/two-column, PDF/degraded geometry, PDF/footnotes, and TXT/dense dialogue.

Thresholds:

- benchmark: zero remaining measured fusions, 27/27 page transitions, F1 >= 0.97;
- native structure: F1 >= 0.99;
- good PDF geometry: F1 >= 0.95;
- degraded geometry: F1 >= 0.85 plus warnings;
- Chunking text coverage: 1.0.

Real online/offline model verification is manual and includes at least 9B/16K,
20B/16K, 27B/32K, and one online model. Automated tests use provider stubs.
