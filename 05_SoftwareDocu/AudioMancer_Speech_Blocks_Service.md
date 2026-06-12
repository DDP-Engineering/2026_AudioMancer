<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Speech Blocks Service

## 1. Purpose

Implements the current approval-driven `Speech Blocks` workflow in
`AudioMancer`.

It converts the chunk text selected through the locked project language into
AI-owned ordered speech blocks, gives the operator a focused review and edit
surface, and persists the approved results as root-level Speech Blocks
artifacts. In `narrator_and_characters` projects the AI owns dialogue and
speaker attribution. In `same_narrator` projects the AI now chooses compact
boundary IDs only, while AudioMancer slices the exact source text and builds
continuous narrator-only blocks under the TTS text budget.

## 2. Responsibilities

- resolve the active source language from the locked `project.json.target_language`
- choose canonical chunking text or approved translated text as the source
- choose the dialogue/speaker prompt or narrator-only boundary prompt from
  `project.json.voice_assignment_mode`
- collect optional operator Speech Blocks rules before fresh full generation or
  selected-chunk re-splitting, append those rules to each user prompt, and
  preserve them in report/state metadata for compatible resumes
- size AI request input from the selected AI profile context window, max output
  tokens, prompt budget, and conservative safety margin
- split oversized source chunks into ordered AI request segments without
  changing the public chunk identity
- include the resolved TTS token budget and conservative word guidance in
  narrator-only requests
- normalize model output into the new persisted speech-block schema; in
  narrator-plus-character mode the model owns final block boundaries, while in
  same-narrator mode the model selects candidate boundary IDs and AudioMancer
  builds exact spans deterministically
- normalize each Scene Ambience model response into individual sound-source
  Speech Blocks and defensively split comma-, semicolon-, `and`-, or
  `plus`-composed ambience prompts before persistence
- assign speech block IDs in `CCCC-BBBBBB` format, for example
  `0001-000001`
- persist only current source span, speaker, content kind, and text values for
  each Speech Block
- preserve exact `source_text` spans for review traceability
- validate model source spans for source coverage, source order, and text edits
  without replacing AI block boundaries in narrator-plus-character mode
- preserve source wording exactly except for stripping dialogue delimiters from
  dialogue audio text in `narrator_and_characters` mode
- preserve quotes, guillemets, dashes, punctuation, and paragraph breaks in
  `same_narrator` mode
- support straight quotes, curly quotes, French guillemets, and dash-led
  dialogue
- fall back to `narrator` when speaker attribution is ambiguous or invalid
- expose speaker choices from `Narrator` plus discovered characters when the
  project uses separate character voices
- expose only `Narrator` and disable speaker reassignment in `same_narrator`
  projects, because the narrator voice plays all speech blocks
- expose content kinds `Narration`, `Dialogue`, `Scene Ambience`, `Pause`,
  and `Indication`
- support selected-block edit and save operations, with generated-audio impact
  confirmation shown when Edit is pressed rather than when Save is pressed
- support manual selected-chunk Speech Block insertion before or after AI
  generation and deletion when a block is selected, with chunk-local sequence
  updates while preserving stable Speech Block IDs
- keep the selected chunk and selected-chunk text scroll during manual review
  edits; inserted blocks become selected immediately, and deleting a block
  selects the next remaining block or the previous/current row when deleting
  the last block
- clear warning indicators as soon as an operator starts editing a block
  without changing approval state or downstream audio inputs
- approve or unapprove the selected speech block, approve all speech blocks,
  and report approval counts
- persist selected approve, unapprove, and warning-clear review changes through
  a compact JSON update path that keeps resume-critical metadata and generation
  fingerprints while avoiding large source-snapshot rewrites
- regenerate one selected chunk and rebuild only that chunk's local sequence
  indexes plus fresh replacement block IDs
- reset Speech Blocks plus downstream Audio Blocks and Audio Assembly artifacts
- reset only exact affected Audio Blocks by stable `speech_block_id` after
  selected-block text, speaker, content-kind, or delete changes
- refresh a character's persisted `speaker_display_name` without clearing
  Speech Block approval when only the character voice/profile display data
  changed
- reset only Audio Assembly after Speech Block insert, approval, or order
  changes that do not alter existing Audio Blocks
- persist resumable chunk-based operation state, report data, and AI
  transaction logs
- resume from partially generated review state after operators approve or edit
  already generated blocks
- build page state, notes, speaker catalogs, content-kind labels, generated-run
  button state, reset state, selected-audio preview availability, and
  AI-profile selector entries for the `Speech Blocks` page
- coordinate confirmation popups, modal progress, cancellation, reset,
  re-splitting, downstream audio reconciliation, and manifest updates through
  the page controller

It does not:

- preserve compatibility with old `speech-block-0001` style artifacts
- migrate old Speech Blocks or Audio Blocks artifacts
- own audio generation; selected-block audio preview actions are delegated to
  the Audio Blocks controller and service
- send `Pause` or `Indication` blocks to VoiceWeaver
- own character discovery, narrator selection, or voice sample generation

## 3. Implementation Overview

The workflow is split across:

- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py`
  for source resolution, AI dispatch, normalization, persistence, approval,
  editing, selected-chunk regeneration, ID rebuilding, and resume
  handling
- `04_Software/AudioMancer/src/audiomancer/services/speech_blocks_state_service.py`
  for page-state shaping, AI-profile selection, speaker/content selectors,
  approval counts, selected-audio preview flags, and operator notes
- `04_Software/AudioMancer/src/audiomancer/ui/pages/speech_blocks_page.py`
  for the top chunk list, selected chunk preview, speech block list, selected
  block editor, manual insert/delete buttons, approval toggle button, selected
  text character counter, selected-audio generate/play controls, and
  selected-chunk re-split action
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/speech_blocks_ui_controller.py`
  for prerequisite validation, confirmation popups, modal progress,
  cancellation, explicit reset, approve-all, selected-block approval toggle,
  selected-block edit/save, selected-chunk re-splitting, downstream Audio Blocks reconciliation, and
  manifest synchronization. Selected approve, unapprove, edit-save, and
  warning-clear refreshes update the visible row and review notes in place
  instead of rebuilding the full Speech Blocks page.

High-level flow:

1. The Home page locks the target language and narration mode before source
   import.
2. `speech_blocks_service.resolve_source_chunks(...)` loads canonical chunks
   from `chunks_text.json` or approved translated chunks from
   `translated_text.json`.
3. The controller confirms that the operator wants to start or continue one AI
   run, asks for optional operator Speech Blocks rules on fresh runs, and warns
   about time plus token usage. Scene Ambience generation is enabled only when
   `TTS Settings` stores a `scene_ambience_placement` value other than `none`.
4. `speech_blocks_service.start_or_continue_generation(...)` validates the
   selected prompt files, builds request budget metadata from the selected AI
   profile and prompt shell, restores resumable state when the saved checkpoint
   or partial review state still matches the current source snapshot, source
   language, and operator-rule fingerprint, and processes each remaining chunk
   through one or more budgeted model requests with the currently selected AI
   profile/model.
5. Each response is normalized into new speech-block payloads, including exact
   source spans, current editable values, warning flags, approval fields,
   chunk-local sequence indexes, and `CCCC-BBBBBB` IDs. In
   narrator-plus-character mode, deterministic validation annotates suspicious
   spans with warning flags such as `source_coverage_mismatch`,
   `source_order_mismatch`, and `model_text_modified`. In same-narrator mode,
   the response contains only ordered boundary IDs; AudioMancer slices
   `source_text` from the original chunk and sets narrator/content fields
   deterministically. If the boundary response is unusable, the service falls
   back to deterministic TTS splitting and marks the first generated block with
   `boundary_selection_fallback`. After validation or boundary slicing,
   non-operation blocks that still exceed the safe TTS budget are split locally
   as a safety net, preferring paragraph and sentence boundaries before hard
   word/character splits. Hard fallback splits add `tts_hard_split`; operation
   rows such as `pause`, `scene_ambience`, and `indication` are never split.
6. The current `speech_blocks_report.json`, `speech_blocks_state.json`, and
   transaction log metadata are rewritten after every chunk with the current
   budget metadata so cancellation can resume from the next chunk even when the
   operator selects a different AI profile/model before continuing.
7. Finished full generation disables `Generate Speech Blocks`, enables
   `Reset Speech Blocks`, resets downstream Audio Blocks plus Audio Assembly
   data, and leaves Speech Blocks in review until all blocks are approved.
8. `Approve All Speech Blocks` marks every block approved, clears any reviewed
   warning flags, advances the manifest and Home-page operation summary to
   completed `speech_blocks_ready`, and resets Audio Assembly without deleting
   generated Audio Blocks.
9. Pressing Edit on one block asks for confirmation when that exact Speech
   Block already has generated audio, then unlocks the editor only after the
   operator accepts the impact prompt. Save commits the edit without asking
   again, deletes only that block's generated Audio Blocks WAV/metadata
   artifacts, and resets Audio Assembly.
10. Inserting a block rewrites `speech_blocks.json`, appends after the selected
    Speech Block or creates the first/end block when none is selected, updates
    only the selected chunk sequence, leaves the inserted block unapproved,
    preserves existing generated Audio Blocks, selects the inserted block,
    preserves the selected chunk review context, and resets Audio Assembly
    because playback order changed.
11. Re-splitting one chunk uses the Scene Ambience placement from `TTS Settings`,
    asks for optional operator Speech Blocks rules,
    replaces only that chunk's Speech Blocks, rebuilds that chunk's local
    sequence indexes and block IDs, marks new blocks unapproved, rolls Speech
    Blocks back from complete, and asks Audio Blocks to delete/remap only the
    affected downstream records.
12. The Speech Blocks page mirrors Audio Blocks selected-row audio controls:
    `Generate Audio` asks the Audio Blocks controller to generate only the
    selected approved spoken block, and `Play`/`Stop` reuses the selected Audio
    Block local WAV player when a generated file exists.
13. Selected manual review actions refresh the Home summary, the affected
    Speech Blocks row, and the selected detail panel incrementally. Full page
    rebuilds are still used for project open, full generation, reset, and
    selected chunk re-splitting where chunk or row ordering changes broadly.

## 4. Dependencies

- Internal dependencies:
  `04_Software/AudioMancer/src/audiomancer/config.py`
  `04_Software/AudioMancer/src/audiomancer/services/audio_blocks_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/character_voices_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/narrator_definition_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/deterministic_chunking_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/ai_translation_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/character_discovery_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/llm_provider_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/prompt_template_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/token_usage_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/project_workspace_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/tts_budget_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/text_cleanup_state_service.py`
  `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
  `04_Software/AudioMancer/src/audiomancer/ui/controllers/misc_ui_controller.py`
  `04_Software/AudioMancer/src/audiomancer/ui/main_window.py`
- External dependencies:
  `PySide6`
  one configured OpenAI-compatible LLM backend reachable through the shared
  provider layer

## 5. Inputs And Outputs

Inputs:

- active project root and manifest
- locked target and selected voice language from `project.json`
- locked voice assignment mode from `project.json`
- canonical chunking output in `chunks_text.json`
- approved translated chunks and `translation_report.json` when the selected
  voice language is translated
- discovered character profiles from `characters_profile.json`
- selected enabled AI profile from `settings.json`
- prompt templates:
  `04_Software/AudioMancer/prompts/speech_blocks_system.txt`
  `04_Software/AudioMancer/prompts/speech_blocks_user.txt`
- narrator-only prompt templates:
  `04_Software/AudioMancer/prompts/speech_blocks_narrator_only_system.txt`
  `04_Software/AudioMancer/prompts/speech_blocks_narrator_only_user.txt`
- cached VoiceWeaver discovered-model payloads from `settings.json`, used to
  resolve narrator-only TTS budget metadata

Outputs:

- `speech_blocks.json`
- `speech_blocks_report.json`
- `speech_blocks_state.json`
- `log_ai_speech_blocks_<timestamp>.log`
- updated manifest summary for `operations["speech_blocks"]`
- updated manifest stage `speech_blocks_ready` only after approval is complete
- reset downstream Audio Blocks and Audio Assembly artifacts after full
  generation or Speech Blocks reset
- selective removal of affected Audio Blocks and generated files for exact
  `speech_block_id` values after local Speech Block audio-input changes
- display-name refresh for character-owned Speech Blocks without review-state
  reset after character profile edits
- assembly-only reset after local order or approval changes

## 6. Data Contracts

Persisted speech-block payloads use:

- `speech_block_id`
- `sequence_index`
- `chunk_id`
- `source_language`
- `speaker_kind`
- `speaker_id`
- `speaker_display_name`
- `content_kind`
- `source_text`
- `text`
- `warning_flags`
- `approved`
- `approved_at`

Current invariants:

- each source chunk is processed through one or more AI requests sized to the
  computed context budget
- oversized source chunks are split before AI dispatch, preferring paragraph,
  sentence, and word boundaries before hard character spans
- `sequence_index` is 1-based and local within the source chunk
- `speech_block_id` is always `CCCC-BBBBBB`
- `CCCC` is derived from the numeric chunk id
- `BBBBBB` is allocated from the chunk-local Speech Block id space and is not
  rewritten only because `sequence_index` changes
- canonical book order is source chunk order, then chunk-local
  `sequence_index`
- manual insert appends after the selected block, and manual insert/delete
  updates `sequence_index` but preserves existing `speech_block_id` values for
  unchanged blocks
- inserted blocks get the next unused chunk-local `speech_block_id`
- AI output is the primary Speech Block list in narrator-plus-character mode;
  deterministic helpers validate and annotate the model result but do not force
  quote-based boundaries
- AI output is only a boundary-id list in same-narrator mode; exact
  `source_text`, `text`, `speaker_id`, and `content_kind` fields are built by
  AudioMancer from the original source chunk
- `speaker_id` must be `narrator` or one discovered `character_id`
- for metadata-only operation kinds, `speaker_kind` is `operation`,
  `speaker_id` is the content-kind token, and `speaker_display_name` is the
  operation name shown in the Speech Blocks list
- unrecognized or ambiguous speakers fall back to narrator and add
  `ambiguous_speaker`
- `source_text` stores the exact chunk span represented by the block
- narration text is stored as model audio text after validation against
  `source_text`
- dialogue text strips only dialogue delimiters: one outer straight quote pair,
  one outer curly quote pair, one French guillemet pair, or one leading dialogue
  dash
- in `same_narrator` mode every generated block is normalized to
  `speaker_id = "narrator"` and `content_kind = "narration"`
- in `same_narrator` mode block text preserves the source span exactly except
  harmless outer whitespace cleanup
- same-narrator malformed JSON, missing boundary IDs, unknown boundary IDs, or
  out-of-order boundary IDs trigger deterministic TTS splitting instead of
  stopping the entire Speech Blocks run
- narrator-only blocks that exceed the resolved safe TTS budget are retained and
  flagged with `tts_budget_exceeded`
- `scene_ambience`, `pause`, and `indication` are operation content kinds
  for Audio Blocks
- Scene Ambience second-pass prompts ask the LLM for ordered individual
  sound-design blocks; each persisted `scene_ambience` block stores one prompt,
  negative prompt, and duration, with sequence order carried by the normal
  `sequence_index`
- Scene Ambience duration settings are treated as a soft maximum for one
  ambience sequence, while `scene_ambience_max_blocks_per_sequence` limits how
  many individual sound blocks the LLM may create for that sequence
- pause text may include a millisecond duration; when no valid duration exists,
  downstream audio composition uses `1000 ms`
- block ordering never crosses chunk boundaries
- manual insert creates an unapproved narrator narration block with empty text,
  initializing Speech Blocks report and operation state from current source
  chunks when no generated Speech Blocks pass exists yet
- manual delete removes only the selected block and leaves the source chunk in
  the chunk list even when no Speech Blocks remain for that chunk
- warning flags are cleared when the operator starts editing a block, without
  unapproving the block
- selected-block text, speaker, content-kind, Scene Ambience prompt fields,
  duration, and delete changes reset generated Audio Blocks data for the
  affected `speech_block_id` only
- selected-block approval, unapproval, and manual insert preserve generated
  Audio Blocks and reset only Audio Assembly
- selected-chunk re-splits reset generated Audio Blocks data for the affected
  chunk because the Speech Blocks in that chunk are replaced
- generation creates unapproved blocks
- partial generated blocks remain committed progress after approval or review
  edits; pressing `Generate Speech Blocks` continues with the next unprocessed
  source chunk
- Speech Blocks is complete only when every block is approved; generated but
  unapproved full output is persisted as `review_pending` in `project.json`
  operation metadata
- deleting the last remaining manual block returns Speech Blocks operation
  status to `not_started` while keeping the source chunks available for another
  manual insert or generation run

Report and operation-state metadata include:

- `source_language`
- `source_kind`
- `ai_profile_id`
- `processed_chunk_count`
- `total_chunk_count`
- `speech_block_count`
- `approved_block_count`
- `total_block_count`
- `warning_count`
- `warnings`
- normalized `token_usage`
- `budget_metadata`, with `context_window`, `max_output_tokens`,
  `prompt_budget_tokens`, `text_budget_tokens`, and `safety_margin_tokens`
- `additional_speech_block_instructions`
- `additional_speech_block_instructions_fingerprint`
- one current-version resume checkpoint with `next_chunk_index`,
  `run_token`, `log_relative_path`, `source_snapshot_fingerprint`,
  `source_language`, `ai_profile_id`, and `budget_metadata`; resume validation
  uses the source snapshot, language, and saved operator-rule fingerprint,
  while the stored profile and budget describe the last saved run settings
- when approval or review updates clear the explicit resume checkpoint, the
  service restores the next chunk only from current `processed_chunk_count`
  values in the report or operation metadata
- operation audit timestamps and generic input/output/artifact path arrays are
  not stored in current Speech Blocks state or report payloads

## 7. Workflow Integration

This workflow sits immediately after `Character Voices`.

Upstream integrations:

- canonical chunk output from `chunks_text.json`
- approved translation output from `translated_text.json` when the selected voice
  language is translated
- discovered character speaker catalog from `characters_profile.json`
- locked project target language and narration mode from `project.json`

Downstream integrations:

- `project.json.current_stage = "speech_blocks_ready"` only after every Speech
  Block is approved
- `Audio Blocks` consumes speech blocks and skips VoiceWeaver for metadata-only
  blocks
- `Reset Speech Blocks` clears speech-block, audio-block, and audio-assembly
  runtime artifacts
- selected-block edits invalidate affected downstream Audio Blocks data
- selected-block audio generation and playback shortcuts delegate to Audio
  Blocks without changing Speech Blocks artifacts
- selected-chunk re-splitting asks Audio Blocks to delete audio for the
  re-split chunk, preserve earlier chunk audio, remap later records to rebuilt
  IDs, rename order-based artifacts when needed, and rebuild report/state
- project language changes are not part of the normal workflow after Home-page
  locking

Runtime gating:

- one project must be open
- chunking output must exist
- the locked target language must resolve to either the original language or a
  fully approved translation target
- at least one enabled AI profile must be configured

## 8. Usage

Representative service calls:

```python
source_resolution = speech_blocks_service.resolve_source_chunks(
    project_root,
    manifest,
)

report = speech_blocks_service.start_or_continue_generation(
    project_root,
    manifest,
    selected_profile_payload,
    progress_callback=progress_callback,
    cancel_requested=cancel_requested,
)

report = speech_blocks_service.approve_all_speech_blocks(project_root)

report = speech_blocks_service.approve_speech_block(
    project_root,
    speech_block_id,
)

report = speech_blocks_service.update_speech_block(
    project_root,
    speech_block_id,
    speaker_id,
    content_kind,
    text,
)

report = speech_blocks_service.regenerate_chunk_speech_blocks(
    project_root,
    manifest,
    chunk_id,
    selected_profile_payload,
    progress_callback=progress_callback,
    cancel_requested=cancel_requested,
)
```

Operator path:

- open one project that has completed `Character Voices`
- open `Speech Blocks`
- select the AI profile
- press `Generate Speech Blocks`
- confirm the generation popup
- inspect chunks in the top list
- inspect or edit selected Speech Blocks in the lower-right editor
- press `Save` after block edits
- read the selected-block character counter beside the approval button to
  compare current text length against the active TTS model budget
- press `Approve` to approve only the selected Speech Block; on approved rows
  the same button becomes `Unapprove` and clears approval for that block
- after selected-block approval, the page advances the visible Speech Blocks
  list to the next row when one exists and keeps the final row selected at the
  end
- after selected-block unapproval, the page keeps the same Speech Block selected
- press `Generate Audio` on an approved selected Speech Block to generate or
  replace only that block's Audio Block from the Speech Blocks page
- press `Play` or `Stop` on a selected Speech Block with generated audio to
  preview the exact Audio Block without leaving Speech Blocks review
- press `Split Chunk` when only the selected chunk needs a new AI
  split
- press `Approve All Speech Blocks` after review
- if interrupted, start generation again to continue from the saved checkpoint
- if only part of the book is generated and reviewed, start generation again to
  continue from the next unprocessed chunk without discarding approved blocks

## 9. Validation And Tests

Focused automated coverage exists in:

- `04_Software/AudioMancer/tests/test_speech_blocks_service.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_state_service.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_page.py`
- `04_Software/AudioMancer/tests/test_speech_blocks_ui_controller.py`
- related invalidation, Audio Blocks, and repair coverage in
  `test_audio_blocks_service.py`, `test_audio_blocks_state_service.py`,
  `test_audio_blocks_page.py`, `test_audio_blocks_ui_controller.py`,
  `test_audio_blocks_main_window.py`,
  `test_audio_blocks_upstream_invalidation.py`,
  `test_character_voices_ui_controller.py`, and
  `test_project_workspace_service.py`

Minimum validation after a change:

```powershell
uv run python -m py_compile <changed_python_files>
uv run pytest tests/test_speech_blocks_service.py
uv run pytest tests/test_speech_blocks_state_service.py
uv run pytest tests/test_speech_blocks_page.py
uv run pytest tests/test_speech_blocks_ui_controller.py
uv run pytest tests/test_audio_blocks_service.py
uv run pytest tests/test_audio_blocks_state_service.py
uv run pytest tests/test_audio_blocks_page.py
uv run pytest tests/test_audio_blocks_ui_controller.py
uv run pytest tests/test_audio_blocks_main_window.py
uv run pytest tests/test_audio_blocks_upstream_invalidation.py
uv run ruff check <changed_python_files> --fix
uv run ruff format <changed_python_files>
```

## 10. Limitations And Future Work

- source-span validation is deterministic and warning-based; suspicious AI
  splits remain editable instead of being automatically replaced
- speaker attribution uses only the discovered-character catalog plus narrator
- prosody and detailed delivery hints are not stored
- `Pause` blocks are metadata-only in Speech Blocks and are rendered as silence
  by Audio Assembly; invalid or missing durations fall back to `1000 ms`
- `Scene Ambience` blocks are sequential sound cues ordered by `sequence_index`;
  they are not grouped by a separate ambience identifier, mixed under
  narration, or ducked as ambience-bed automation
- `Indication` blocks remain metadata-only markers skipped by generated speech
  audio until a richer non-spoken instruction layer is implemented
- Audio Assembly is implemented as the next downstream WAV composition stage
