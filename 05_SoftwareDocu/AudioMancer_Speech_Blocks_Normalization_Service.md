<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Speech Blocks Normalization Service

## 1. Purpose

Provides shared normalization helpers for Speech Blocks identifiers,
content-kind values, operation rows, warning flags, dialogue text,
narrator-plus-character atomic-unit selections, source-span provenance, and
narrator-only TTS budget lookup.

## 2. Responsibilities

- normalize content-kind tokens into supported Speech Blocks values
- identify metadata-only operation block kinds
- build stable operation speaker entries
- normalize warning-flag lists and warning reasons
- parse deterministic `SourceSpan` and `AtomicSpeechUnit` entries from source
  chunks
- log malformed source-span offset payloads with compact chunk/span identifiers
  instead of source text
- validate narrator-plus-character atomic `unit_ids` payloads without trusting
  model-owned text fields
- expose validation results before fallback so orchestration can run one
  compact repair retry for malformed or semantically invalid local-model output
- reconstruct persisted `source_text` and `text` from selected atomic units
- build safe narrator fallback blocks for invalid unit, span, or speaker selections;
  fallback keeps exact `source_text` and removes simple straight-quote dialogue
  delimiters from the narrator audio text
- generate stable `CCCC-BBBBBB` speech block identifiers from chunk ids
- strip only dialogue delimiters that should not be spoken
- resolve cached narrator-only TTS budget metadata

It does not orchestrate AI generation, persist Speech Blocks files, or update
review approval state. It also does not build deterministic source spans or
atomic units before prompting; that construction is owned by
`speech_blocks_text_split_service.build_source_spans(...)` and
`speech_blocks_text_split_service.build_atomic_speech_units(...)`.

## 3. Implementation Overview

Implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_normalization_service.py`

Main entrypoints include:

- `normalize_content_kind(...)`
- `is_operation_content_kind(...)`
- `operation_speaker_entry(...)`
- `speech_block_id(...)`
- `normalize_warning_flags(...)`
- `normalize_chunk_blocks(...)`
- `normalize_source_span_selection_chunk_blocks(...)`
- `validate_source_span_response_payload(...)`
- `source_span_response_requires_confidence(...)`
- `validate_source_span_model_selections(...)`
- `normalize_block_text(...)`
- `resolve_narrator_only_budget(...)`

The Speech Blocks orchestration service imports these helpers to keep
normalization behavior consistent across generation, manual edits, and report
state rebuilding.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config`
- `tts_budget_service`
- `audiomancer.services.logging_service`

External dependencies:

- Python standard library `dataclasses`
- Python standard library `re`

## 5. Inputs And Outputs

Inputs:

- raw content-kind strings
- source chunks with exact `text` and optional deterministic `source_spans`
- model blocks with `unit_ids`, `speaker_id`, `content_kind`, `confidence`,
  and `warnings`
- source chunk ids and sequence indexes
- candidate dialogue text
- persisted warning-flag payloads
- optional settings payload with cached discovered TTS models

Outputs:

- normalized strings and lists
- reconstructed speech-block payloads
- validation warning entries for invalid unit, span, or speaker selections
- compact application log entries for malformed source-span offset payloads
- operation speaker dictionaries
- stable Speech Block identifiers
- TTS budget payloads from cached runtime model metadata

## 6. Data Contracts

Supported content kinds:

- `narration`
- `dialogue`
- `scene_ambience`
- `pause`
- `indication`

Metadata-only operation kinds:

- `scene_ambience`
- `pause`
- `indication`

Speech Block ids use the persisted `CCCC-BBBBBB` shape, where the first token
comes from the numeric chunk order and the second token is the chunk-local
block sequence.

Span-selection normalization uses these internal data types:

- `SourceSpan`: stable `source_span_id`, `start_offset`, `end_offset`, and
  exact `text`
- `AtomicSpeechUnit`: stable `atomic_unit_id`, parent `source_span_id`, offsets,
  exact `text`, and structural kind
- `SpeechBlockModelSelection`: legacy source-span selection parser retained for
  internal fallback fixtures
- `SpeechBlockSelectionValidationResult`: reconstructed AI-block-like payloads
  or the blocking warning flag and validation reason

When model `unit_ids` are present, `normalize_chunk_blocks` uses the atomic-unit
selection path. The narrator-plus-character `blocks` response contract is
strict: each block must include non-empty known selectable `unit_ids`, exact
speaker IDs, supported `content_kind`, and a `confidence` value. Selected units
must be unique across the model response, in source order, and cover every
selectable speakable unit. Separator-only and whitespace-only units remain
source provenance for offset reconstruction but are not selectable and are
rejected with `atomic_unit_selection_invalid` if a model returns them. Dialogue
selections may contain only dialogue units; attribution, narration, or mixed
units are rejected with `atomic_unit_selection_invalid`. Narration selections
may not absorb dialogue units. Unknown speaker IDs are rejected instead of
alias-matched. Persisted `source_text` is the exact concatenated selectable
atomic-unit text, and persisted `text` is derived locally with the existing
dialogue-delimiter cleanup rules. Model-owned `text` or `source_text` fields are
ignored on this path.

Legacy source-span validation helpers remain available for deterministic
fallback and older internal fixtures, but production prompts and structured
output now use atomic `unit_ids`.

## 7. Workflow Integration

Upstream:

- AI Speech Blocks generation
- manual Speech Blocks insert/edit/delete flows
- report-state rebuilding

Downstream:

- `speech_blocks_service`
- `speech_blocks_report_state_service`
- UI pages and controllers through normalized persisted payloads

## 8. Usage

Representative normalization:

```python
content_kind = speech_blocks_normalization_service.normalize_content_kind(raw_kind)
block_id = speech_blocks_normalization_service.speech_block_id(chunk_id, sequence_index)
text = speech_blocks_normalization_service.normalize_block_text(raw_text, content_kind)
```

## 9. Validation And Tests

Focused tests:

- `tests/test_speech_blocks_normalization_service.py`
- `tests/test_speech_blocks_service.py`

Reviewed on 2026-07-02 against the implemented `SourceSpan`,
`AtomicSpeechUnit`, validation-result, fallback, compact parse-failure logging,
and reconstructed-text normalization paths, including strict `blocks`
confidence validation, selectable-unit coverage, and atomic-unit structural
validation.

Validation audit on 2026-07-02 rechecked this document after final formatting
of the atomic-unit implementation.

Minimum validation after changes:

- `uv run python -m py_compile src/audiomancer/services/speech_blocks_normalization_service.py`
- `uv run pytest tests/test_speech_blocks_normalization_service.py`
- `uv run pytest tests/test_speech_blocks_service.py -k "atomic or invalid_span_or_speaker"`

## 10. Limitations And Future Work

- language-specific dialogue delimiter handling is intentionally conservative
- the service owns normalization only; semantic speaker attribution remains in
  the Speech Blocks workflow
- deterministic source-span and atomic-unit construction before prompting is
  owned by `speech_blocks_text_split_service.py`; this service validates and
  consumes the already-built units
