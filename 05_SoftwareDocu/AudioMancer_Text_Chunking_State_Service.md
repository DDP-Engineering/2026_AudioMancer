<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Text Chunking State Service

## 1. Purpose

Provides Text Chunking page-state helpers and the v2 manual chunk maintenance
path for `AudioMancer`.

The service keeps the page aligned with cleaned text, persisted chunk artifacts,
AI chunking notes, profile selectors, and manual selected-chunk operations. Its
v2 responsibility is to preserve expensive downstream work whenever a local
chunk edit, insert, or delete affects only specific stable `chunk_id` values.

## 2. Responsibilities

- build Text Chunking page state from the active project, manifest, settings,
  cleaned text, chunk output, chunking report, and operation state
- build deterministic and AI-assisted chunking notes, including persisted token
  usage when the backend reported it
- expose enabled AI chunking profiles and selected semantic strategy
- persist manual selected-chunk text edits
- insert one empty chunk after the selected chunk
- delete one selected chunk while requiring at least one chunk to remain
- preserve stable `chunk_id` values and resequence `sequence_index`
- synchronize Translation records by stable `chunk_id`
- remove Speech Blocks and Audio Blocks only for affected chunks
- delete generated audio files only for affected chunks
- drop Character Discovery evidence anchored to affected chunks while
  preserving character profiles
- reset Audio Assembly outputs after chunk-local changes
- refresh chunking metadata, operation state, impact metadata, and manifest
  summaries

It does not own deterministic chunk generation, AI chunk generation, actual AI
translation, character profile synthesis, speech-block generation, TTS
generation, or Audio Assembly composition.

## 3. Implementation Overview

The component is implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/text_chunking_state_service.py`

Main public entrypoints:

- `build_text_chunking_state(...)`
- `build_ai_chunking_profile_state(...)`
- `build_text_chunking_notes(...)`
- `save_chunk_text_edit(...)`
- `insert_chunk_after_selected(...)`
- `delete_selected_chunk(...)`
- `build_manifest_after_chunk_edit(...)`

High-level manual-change flow:

1. The controller confirms the operator action with localized impact text.
2. The service loads the canonical chunk artifact.
3. The selected chunk is edited, a new empty chunk is inserted after the
   selected chunk, or the selected chunk is removed.
4. The full chunk list is resequenced while preserving existing stable
   `chunk_id` values.
5. Translation is synchronized by `chunk_id`: changed or inserted chunks become
   untranslated and unapproved; deleted chunks are removed; unaffected chunks
   keep their translation and review state.
6. Character Discovery evidence for affected chunks is removed without deleting
   the character profile list.
7. Speech Blocks and Audio Blocks for affected chunks are removed; generated
   audio files for those Audio Blocks are deleted through the workflow impact
   safe-artifact helper.
8. Audio Assembly state, report, and generated audiobook output are reset.
9. Chunking report and operation-state metadata record the manual adjustment
   plus the latest v2 impact summary.
10. `project.json` summaries are refreshed from the actual persisted artifacts.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config`
- `audiomancer.services.ai_state_note_service`
- `audiomancer.services.ai_translation_service`
- `audiomancer.services.audio_blocks_service`
- `audiomancer.services.character_discovery_service`
- `audiomancer.services.deterministic_chunking_service`
- `audiomancer.services.home_presenter_service`
- `audiomancer.services.operation_runtime_service`
- `audiomancer.services.project_workspace_service`
- `audiomancer.services.speech_blocks_service`
- `audiomancer.services.text_cleanup_state_service`
- `audiomancer.services.ui_state_service`
- `audiomancer.services.workflow_impact_service`

External dependencies:

- Python standard library only: `json` and `pathlib`

## 5. Inputs And Outputs

Inputs:

- active project root and manifest
- settings payload with AI profile selectors
- `clean_text.txt`
- `chunks_text.json`
- `chunking_report.json`
- `chunking_state.json`
- selected `chunk_id`

Outputs updated by manual chunk changes:

- `chunks_text.json`
- `chunking_report.json`
- `chunking_state.json`
- `translated_text.json`
- `translation_report.json`
- `translation_state.json`
- `characters_profile.json` evidence metadata
- `speech_blocks.json`
- `speech_blocks_report.json`
- `speech_blocks_state.json`
- `audio_blocks.json`
- `audio_blocks_report.json`
- `audio_blocks_state.json`
- generated files under `audio_blocks/` for affected chunks
- Audio Assembly state, report, and generated files under `audiobook/`
- `project.json` operation summaries

## 6. Data Contracts

Stable identity fields:

- `chunk_id`
- downstream `speech_block_id` values tied to affected chunks

Ordering field:

- `sequence_index`

Manual insert rules:

- new chunks receive the next unused `chunk-####` identifier
- inserted chunks start with empty text and `chunking_mode = "manual"`
- inserted chunks inherit source-position hints from the selected anchor chunk
  only as placeholders until the operator edits the text
- existing chunks keep their `chunk_id`

Manual edit rules:

- a changed chunk keeps its `chunk_id`
- only the changed chunk's Translation, Speech Blocks, Audio Blocks, generated
  audio, and assembly output are invalidated

Manual delete rules:

- deleted chunks are removed from Translation and from chunk-scoped Speech
  Blocks and Audio Blocks
- at least one chunk must remain
- existing non-deleted chunks keep their `chunk_id`

Metadata rules:

- `chunking_report.json` and `chunking_state.json` set `manual_adjusted = true`
- `last_workflow_impact` records affected chunks, reset operation kinds,
  assembly reset, deleted generated files, and timestamp
- no complex v1 metadata migration is attempted

## 7. Workflow Integration

Upstream:

- Text Cleanup produces `clean_text.txt`.
- Deterministic or AI-assisted chunking produces the canonical chunk artifact.

Downstream:

- AI Translation is synchronized by stable `chunk_id`.
- Character Discovery profiles are preserved; only evidence entries from
  affected chunks are removed.
- Character Voices and Narator Voice are preserved.
- Speech Blocks and Audio Blocks are removed only for affected chunks.
- Audio Assembly is always reset after manual chunk edit, insert, or delete
  because final sequence, approval readiness, or audio inputs may have changed.

Broad resets that remain intentional:

- Text extraction reruns clear all follow-up data and metadata.
- Text cleanup reruns clear regenerated text, Speech Blocks, Audio Blocks, and
  Audio Assembly data while preserving completed Character Discovery, Narator
  Voice, and Character Voices artifacts.
- Full deterministic or AI Text Chunking regeneration clears downstream data
  from generated text onward because the full canonical chunk set is replaced,
  but preserves completed Character Discovery, Narator Voice, and Character
  Voices artifacts.

## 8. Usage

Representative calls:

```python
state = text_chunking_state_service.build_text_chunking_state(
    project_root,
    manifest,
    "en",
    settings_payload,
)

updated_manifest = text_chunking_state_service.insert_chunk_after_selected(
    project_root,
    manifest,
    "chunk-0002",
)
```

Operator path:

- open Text Chunking after cleanup
- select one chunk
- confirm the downstream impact message before editing selected text, inserting
  a new chunk after it, or deleting it
- save selected text edits after the editor is already unlocked
- continue downstream review only for the affected chunks

## 9. Validation And Tests

Focused automated coverage includes:

- `04_Software/AudioMancer/tests/test_text_chunking_state_service.py`
- `04_Software/AudioMancer/tests/test_text_chunking_page.py`
- `04_Software/AudioMancer/tests/test_text_chunking_ui_controller.py`
- related selective-impact coverage in
  `04_Software/AudioMancer/tests/test_workflow_impact_service.py`,
  `04_Software/AudioMancer/tests/test_audio_blocks_service.py`, and
  `04_Software/AudioMancer/tests/test_speech_blocks_service.py`

Minimum validation after changes:

```powershell
uv run python -m py_compile src/audiomancer/services/text_chunking_state_service.py
uv run ruff check src/audiomancer/services/text_chunking_state_service.py tests/test_text_chunking_state_service.py --fix
uv run ruff format src/audiomancer/services/text_chunking_state_service.py tests/test_text_chunking_state_service.py
uv run pytest tests/test_text_chunking_state_service.py tests/test_text_chunking_page.py tests/test_text_chunking_ui_controller.py
```

## 10. Limitations And Future Work

- Manual insert creates an empty chunk; it does not ask AI to rebalance
  neighboring chunk boundaries.
- Character Discovery evidence cleanup is chunk-scoped and does not re-run
  character synthesis.
- Full chunk regeneration remains a broad downstream reset because the whole
  canonical chunk list may change.
- Translation manual edits are documented in the AI Translation component; that
  controller still performs a broad downstream reset when approval is lost.
