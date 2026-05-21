<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Speech Blocks Normalization Service

## 1. Purpose

Provides shared normalization helpers for Speech Blocks identifiers,
content-kind values, operation rows, warning flags, dialogue text, and
narrator-only TTS budget lookup.

## 2. Responsibilities

- normalize content-kind tokens into supported Speech Blocks values
- identify metadata-only operation block kinds
- build stable operation speaker entries
- normalize warning-flag lists and warning reasons
- generate stable `CCCC-BBBBBB` speech block identifiers from chunk ids
- strip only dialogue delimiters that should not be spoken
- resolve cached narrator-only TTS budget metadata

It does not orchestrate AI generation, persist Speech Blocks files, or update
review approval state.

## 3. Implementation Overview

Implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_normalization_service.py`

Main entrypoints include:

- `normalize_content_kind(...)`
- `is_operation_content_kind(...)`
- `operation_speaker_entry(...)`
- `speech_block_id(...)`
- `normalize_warning_flags(...)`
- `normalize_block_text(...)`
- `resolve_narrator_only_budget(...)`

The Speech Blocks orchestration service imports these helpers to keep
normalization behavior consistent across generation, manual edits, and report
state rebuilding.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config`
- `tts_budget_service`

External dependencies:

- Python standard library `re`

## 5. Inputs And Outputs

Inputs:

- raw content-kind strings
- source chunk ids and sequence indexes
- candidate dialogue text
- persisted warning-flag payloads
- optional settings payload with cached discovered TTS models

Outputs:

- normalized strings and lists
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

Minimum validation after changes:

- `uv run python -m py_compile src/audiomancer/services/speech_blocks_normalization_service.py`
- `uv run pytest tests/test_speech_blocks_normalization_service.py`

## 10. Limitations And Future Work

- language-specific dialogue delimiter handling is intentionally conservative
- the service owns normalization only; semantic speaker attribution remains in
  the Speech Blocks workflow
