<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Workflow Impact Service

## 1. Purpose

Provides the v2 foundation for selective downstream preservation in
`AudioMancer` projects.

The service centralizes workflow dependency order, stable identity policy,
impact summaries, manifest refresh behavior, and safe generated-artifact
deletion helpers. Later workflow pages can use it to replace scattered broad
reset calls with targeted invalidation.

## 2. Responsibilities

- define the canonical operation order for downstream impact planning
- expose stable identity rules for `chunk_id`, `speech_block_id`, and
  `voice_target_id`
- build UI-neutral full-reset and selective-invalidation summaries
- wrap existing broad reset behavior without changing unmigrated pages
- delete generated Audio Blocks artifacts only for exact affected IDs
- delete Audio Assembly outputs without touching Audio Blocks
- refresh the project manifest from persisted artifacts after impact work

It does not own UI widgets, localized dialog text, AI generation, TTS
generation, or page-specific reconciliation logic.

## 3. Implementation Overview

The component is implemented in:

- `04_Software/AudioMancer/src/audiomancer/services/workflow_impact_service.py`

Main public data models:

- `ArtifactDeletionSummary`
- `WorkflowImpactSummary`

Main public functions:

- `downstream_operation_kinds(...)`
- `stable_identity_fields()`
- `resequence_records(...)`
- `build_full_reset_impact_summary(...)`
- `apply_full_operation_reset(...)`
- `build_selective_invalidation_summary(...)`
- `build_impact_metadata(...)`
- `delete_audio_block_artifacts(...)`
- `reset_audio_assembly_outputs(...)`
- `refresh_manifest_from_artifacts(...)`

High-level flow:

1. A caller asks the service for an impact summary before a destructive or
   partial-destructive action.
2. The UI controller can use the summary to build localized confirmation text.
3. The caller applies either the broad reset wrapper or a later page-specific
   selective reconciliation flow.
4. Generated files are deleted through explicit safe helpers.
5. The manifest is refreshed from actual persisted artifacts.

## 4. Dependencies

Internal dependencies:

- `audiomancer.config`
- `audiomancer.services.operation_runtime_service`
- `audiomancer.services.project_workspace_service`
- `audiomancer.services.time_service`

External dependencies:

- Python standard library only: `dataclasses`, `pathlib`, and
  `collections.abc`

## 5. Inputs And Outputs

Inputs:

- operation kind tokens such as `chunking`, `speech_blocks`, and
  `audio_blocks`
- affected identity lists such as chunk IDs, Speech Block IDs, and voice target
  IDs
- project roots
- persisted Audio Blocks payloads
- project-local artifact paths from existing operation metadata

Outputs:

- JSON-ready impact summaries
- JSON-ready impact metadata notes
- deleted generated Audio Blocks files for exact affected records
- deleted Audio Assembly state/report/output files
- refreshed `project.json` manifest metadata when local artifacts justify it

## 6. Data Contracts

Stable identity fields:

- `chunk_id`
- `speech_block_id`
- `voice_target_id`

Ordering field:

- `sequence_index`

The v2 rule is that local edit, insert, delete, and reorder operations must
preserve stable IDs and update sequence values separately.

`WorkflowImpactSummary` contains:

- `source_operation_kind`
- `impact_kind`
- `reason`
- reset and preserved operation lists
- affected chunk, Speech Block, and voice target IDs
- Audio Assembly reset flag
- artifact deletion summary
- `updated_at`

`ArtifactDeletionSummary` contains:

- deleted paths
- missing paths
- skipped unsafe paths
- preserved paths
- deleted count

## 7. Workflow Integration

Current in-repo usage covers the foundation layer, the v2 Text Chunking
selective-invalidation phase, the v2 Character Discovery manual maintenance
phase, the v2 Character Voices/Narrator voice impact phase, and the v2 Speech
Blocks manual impact phase. Existing full Text Chunking regeneration and full
Character Discovery reset still use broad reset paths, but manual chunk
edit/insert/delete, manual character add/edit/delete, voice-target edits, and
manual Speech Blocks edits now preserve unrelated downstream work.

The broad reset wrapper delegates to
`operation_runtime_service.reset_operation_data(...)`, then refreshes manifest
metadata through `project_workspace_service`.

Manual Text Chunking changes:

- preserve existing chunk IDs and resequence only `sequence_index`
- insert new chunks with the next unused `chunk-####` id
- synchronize Translation records by stable `chunk_id`
- reset only the changed or inserted chunk translation record
- remove deleted chunk translation records
- remove Character Discovery evidence anchored to affected chunks while
  preserving character profiles
- remove Speech Blocks and Audio Blocks only for affected chunks
- delete generated audio files only for affected Audio Blocks
- reset Audio Assembly outputs and manifest summary

Manual Character Discovery changes:

- add a character without resetting Speech Blocks, Audio Blocks, or Audio
  Assembly
- synchronize Character Voices targets after add so the new character has a
  voice target while existing generated work is preserved
- edit a character by stable `character_id`, mark only Speech Blocks currently
  assigned to that character unapproved, and refresh their speaker display name
  when the canonical name changes
- mark the matching Character Voices target stale and clear its sample when
  voice-definition source fields change
- remove only Audio Blocks tied to affected Speech Blocks or the affected
  `voice_target_id`
- delete a character without deleting Speech Blocks: assigned blocks fall back
  to Narrator, become unapproved, and keep their text/order
- reset Audio Assembly outputs whenever affected speech/audio/voice inputs
  change

Character Voices and Narrator voice changes:

- edit, reset, or regenerate one character voice target without resetting
  Speech Blocks or unrelated generated audio
- remove only Audio Blocks whose `voice_target_id` matches the changed
  character target
- remove only the matching reusable clone prompt metadata for that voice target
- edit, delete, select, save, or regenerate the active Narrator voice without
  resetting Speech Blocks
- remove only Audio Blocks whose `voice_target_id` is `narrator`; in
  same-narrator projects this naturally covers all spoken blocks while
  metadata-only pause/indication blocks are preserved when they do not use the
  narrator voice target
- reset all generated Audio Blocks and reusable clone prompts when a global
  voice language or active runtime model change affects generation assumptions
- reset Audio Assembly outputs whenever affected Audio Blocks or voice inputs
  change

Manual Speech Blocks changes:

- preserve existing `speech_block_id` values when manual insert/delete only
  changes chunk-local sequence indexes
- allocate inserted blocks from the next unused chunk-local `CCCC-BBBBBB` id
- clear selected-block warnings without unapproving or invalidating audio
- edit, reset, or delete one Speech Block by stable `speech_block_id` and
  remove only the matching Audio Blocks record plus generated files
- preserve all unrelated Audio Blocks when one Speech Block changes
- preserve generated Audio Blocks when a block is approved or inserted, then
  reset Audio Assembly because approval/order can change assembly readiness
- reset Audio Assembly outputs whenever Speech Block order, approval state, or
  affected audio inputs change
- keep selected-chunk re-split as chunk-scoped invalidation because that
  operation replaces the Speech Blocks inside the chunk

Audio Blocks and Audio Assembly manual operations:

- selected Audio Block reset removes only the exact `speech_block_id` record and
  generated files, then resets Audio Assembly outputs
- selected Audio Block regeneration replaces only that Audio Block and resets
  Audio Assembly outputs after success
- Audio Block approval/unapproval preserves generated WAV files and resets only
  Audio Assembly outputs when assembly data exists
- Audio Assembly settings changes reset only assembly state, report, and
  generated audiobook files while preserving approved Audio Blocks
- Audio Assembly reruns replace only assembly outputs/state/report and leave
  upstream operations untouched

## 8. Usage

Build a confirmation-ready summary:

```python
summary = workflow_impact_service.build_selective_invalidation_summary(
    "chunking",
    reason="Chunk edited.",
    affected_chunk_ids=("chunk-0002",),
    reset_operation_kinds=("translation", "speech_blocks", "audio_blocks"),
    audio_assembly_reset=True,
)
```

Delete generated audio for exact affected Speech Blocks:

```python
summary = workflow_impact_service.delete_audio_block_artifacts(
    project_root,
    audio_blocks,
    speech_block_ids=("0001-000001",),
)
```

Apply the existing broad reset behavior through the v2 wrapper:

```python
workflow_impact_service.apply_full_operation_reset(
    project_root,
    "cleanup",
    include_current=True,
    reason="Cleanup rerun.",
)
```

## 9. Validation And Tests

Automated tests:

- `04_Software/AudioMancer/tests/test_workflow_impact_service.py`
- `04_Software/AudioMancer/tests/test_text_chunking_state_service.py`
- `04_Software/AudioMancer/tests/test_text_chunking_page.py`
- `04_Software/AudioMancer/tests/test_text_chunking_ui_controller.py`
- `04_Software/AudioMancer/tests/test_characters_ui_controller.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_service.py`
- `04_Software/AudioMancer/tests/test_audio_blocks_service.py`

Covered behaviors:

- operation dependency ordering
- unsupported operation rejection
- full reset summary generation
- selective invalidation summary generation
- stable identity preservation during resequencing
- selective Audio Blocks artifact deletion
- unsafe artifact path rejection
- assembly-only output reset
- manifest refresh from completed artifacts
- broad reset wrapper delegation
- Text Chunking edit/insert/delete preservation by stable chunk id
- Text Chunking page insert/delete signals and button states
- Text Chunking controller confirmations and status refresh
- Character Discovery add preserves existing Speech Blocks and Audio Blocks
- Character Discovery edit unapproves only assigned Speech Blocks, stales the
  matching voice target, removes only affected Audio Blocks, and resets Audio
  Assembly
- Character Discovery delete moves assigned Speech Blocks to Narrator without
  deleting their text, removes the matching voice target, preserves unrelated
  Audio Blocks, and resets Audio Assembly
- Character Voices prompt edits, prompt resets, sample regeneration, and batch
  character sample generation remove only matching voice-target Audio Blocks and
  clone prompts
- Narrator profile edits, sample regeneration, selection changes, and deletion
  remove only Narrator-target Audio Blocks and clone prompts
- global voice-language and runtime-model changes preserve Speech Blocks while
  resetting all generated Audio Blocks and Audio Assembly
- Speech Blocks manual insert/delete preserves stable `speech_block_id` values
  while updating sequence indexes
- Speech Blocks selected-block edit/delete removes only exact matching
  Audio Blocks and generated files
- Speech Blocks approval and insert preserve Audio Blocks and reset Audio
  Assembly only
- Audio Blocks selected reset and regeneration preserve unrelated generated
  audio and reset Audio Assembly only
- Audio Blocks approval/unapproval preserves generated audio and resets Audio
  Assembly only
- Audio Assembly settings changes and reruns preserve Audio Blocks and upstream
  workflow data

Minimum validation after a change:

- `uv run python -m py_compile src/audiomancer/services/workflow_impact_service.py`
- `uv run python -m py_compile src/audiomancer/services/text_chunking_state_service.py src/audiomancer/services/ai_translation_service.py`
- `uv run ruff check src/audiomancer/services/workflow_impact_service.py tests/test_workflow_impact_service.py --fix`
- `uv run ruff format src/audiomancer/services/workflow_impact_service.py tests/test_workflow_impact_service.py`
- `uv run pytest tests/test_workflow_impact_service.py`
- `uv run pytest tests/test_text_chunking_state_service.py tests/test_text_chunking_page.py tests/test_text_chunking_ui_controller.py`
- `uv run pytest tests/test_characters_ui_controller.py tests/test_speech_blocks_service.py tests/test_audio_blocks_service.py`
- `uv run pytest tests/test_speech_blocks_ui_controller.py tests/test_speech_blocks_service.py tests/test_audio_blocks_service.py`

## 10. Limitations And Future Work

- Selective invalidation currently covers Text Chunking manual changes,
  Character Discovery manual add/edit/delete, Character Voices/Narrator target
  changes, Speech Blocks manual review operations, Audio Blocks selected
  operations, and Audio Assembly settings/output reset operations.
- Full reset summaries do not list every file deleted by the legacy broad reset
  helper.
- The service does not create operator-facing confirmation text directly; UI
  controllers remain responsible for localization.
