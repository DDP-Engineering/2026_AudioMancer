<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Character Discovery Service

## 1. Purpose

Provides the Character Discovery workflow used by the `Characters` page in
`AudioMancer`.

It analyzes canonical chunking output as the authoritative source for character
identity and dialogue evidence. It produces one persisted set of compact
speaking-character profiles with identity, aliases, sex or gender guidance,
evidence, confidence, and one final `voice_definition_prompt` per character.
It exposes resumable operation state and keeps the page state and UI
controller aligned with the project manifest.

## 2. Responsibilities

- resolve the discovery input from `chunks_text.json`
- use root-level cleanup and chunking artifacts as the discovery source
- split chunk input into overlapping, budget-aware AI analysis windows
- call the configured AI profile for window extraction and profile synthesis
- detect language-agnostic dialogue spans from quotation and dash-style direct
  speech markers
- normalize, score, merge, filter, and persist discovered speaking characters
- retain rejected non-speaking or weak-evidence candidates in the report for
  diagnostics
- derive and persist one final voice-definition prompt for each character
  profile
- persist `characters_state.json`, `characters_report.json`, one
  `characters_profile.json` output, and one per-run AI transaction log
- expose Character Discovery page state, notes, and default AI-profile
  selection
- handle page-level start, resume, reset, guarded manual add or edit or save
  or delete behavior, and unsaved-change prompts

It does not own chunk creation, translation approval, narrator-definition
editing, or AI profile persistence.

## 3. Implementation Overview

Main implementation files:

- `04_Software/AudioMancer/src/audiomancer/services/character_discovery_service.py`
- `04_Software/AudioMancer/src/audiomancer/services/character_discovery_state_service.py`
- `04_Software/AudioMancer/src/audiomancer/ui/controllers/characters_ui_controller.py`
- `04_Software/AudioMancer/src/audiomancer/ui/pages/characters_page.py`
- `04_Software/AudioMancer/src/audiomancer/ui/main_window.py`

Prompt files:

- `04_Software/AudioMancer/prompts/character_discovery_system.txt`
- `04_Software/AudioMancer/prompts/character_discovery_window_user.txt`
- `04_Software/AudioMancer/prompts/character_profile_synthesis_user.txt`

Main public service entrypoints:

- `start_or_continue_discovery(...)`
- `load_operation_state(...)`
- `load_character_profiles(...)`
- `load_character_discovery_report(...)`
- `load_input_chunks(...)`
- `add_character_profile(...)`
- `validate_manual_character_name(...)`
- `update_character_profile(...)`
- `delete_character_profile(...)`
- `reset_character_discovery(...)`

High-level runtime flow:

1. `CharactersPage` emits `start_discovery_requested(profile_id)`.
2. `characters_ui_controller.handle_start_discovery_requested(...)` validates
   the active project, chunking output, and selected enabled AI profile.
3. On first start only, the controller shows one informational popup about
   long-running AI work.
4. `character_discovery_service.start_or_continue_discovery(...)` resolves
   canonical chunking output as the discovery input, derives request budgets
   from the selected profile context window and max output tokens, and restores
   resumable state when fingerprints, profile ids, window counts, and budget
   metadata still match.
5. The service detects direct-dialogue spans in each chunk using punctuation
   structure rather than English-only speech verbs, analyzes budgeted chunk
   windows using eight chunks as a maximum cap, normalizes candidate evidence
   against known chunk ids and optional `dialogue_span_id` values, merges
   character candidates by canonical or alias identity, filters to speaking
   characters, records rejected candidates, trims synthesis evidence payloads
   when needed, and runs one synthesis pass per merged character.
6. The service writes `characters_profile.json`, `characters_report.json`,
   `characters_state.json`, and one `log_ai_characters_<timestamp>.log`
   transaction log at the project root.
7. The controller syncs `operations["character_discovery"]` into
   `project.json`, sets `current_stage` to `character_discovery_ready`, and
   reloads the window state.
8. The page keeps character fields read-only by default and only enters edit
   mode after `Edit Character`.
9. Manual add or edit changes are saved only through explicit
   `Save Character`, while selection changes and destructive actions are
   guarded by one `Save / Discard / Cancel` prompt when the current draft is
   dirty.
10. The page exposes compact editable character identity fields plus one final
    `voice_definition_prompt`. The final prompt always includes explicit
    `Sex/Gender:` guidance, using the stored `gender_hint` when available and
    a neutral non-male-default instruction when the source does not specify sex
    or gender.
11. Saving a manual add, edit, or delete uses the v2 selective impact path.
    Manual add synchronizes Character Voices targets and preserves existing
    Speech Blocks, Audio Blocks, and Audio Assembly outputs. Manual edit keeps
    unrelated characters and blocks, marks only assigned Speech Blocks
    unapproved, refreshes their speaker display name when needed, resets only
    affected Audio Blocks, and resets Audio Assembly. Manual delete does not
    delete Speech Blocks; assigned blocks fall back to Narrator, become
    unapproved, lose only their generated Audio Blocks, and reset Audio
    Assembly. Existing Narator Voice profiles, selected narrator state, and
    narrator sample files are preserved. The project returns to
    `character_discovery_ready`.
12. Reset clears character-discovery artifacts plus downstream character-voice,
   speech-block, audio-block, and audio-assembly runtime artifacts while
   preserving existing narrator-definition data, resets manifest state through
   `build_manifest_after_operation_reset(...)`, and returns the project to
   `translation_ready`.

## 4. Dependencies

- Internal dependencies:
  `audiomancer.config`, `deterministic_chunking_service`,
  `text_cleanup_state_service`, `prompt_template_service`,
  `llm_provider_service`, `operation_runtime_service`,
  `project_workspace_service`, `ui_state_service`, and the main-window shell
- External dependencies:
  Python standard library, `PySide6`, and one OpenAI-compatible AI backend
  reached through the configured profile

## 5. Inputs And Outputs

Inputs:

- active project root and manifest
- enabled AI profile payload from `settings.json`
- canonical chunking output at `chunks_text.json`
- optional cleaned text from `clean_text.txt`
- prompt templates from the app-root `prompts/` directory
- optional resumable `characters_state.json`

Outputs:

- `characters_profile.json`
- `characters_report.json`
- `characters_state.json`
- `log_ai_characters_<timestamp>.log`
- updated `project.json` operation state and workflow stage

## 6. Data Contracts

Persisted character profile fields:

- `character_id`
- `canonical_name`
- `aliases`
- `gender_hint`
- `voice_definition_prompt`
- `confidence`
- `review_status`
- `evidence`
- `updated_at`

Internal review statuses are persisted without adding controls to the AI
Translation page:

- `discovered`: produced by AI-assisted discovery
- `manual`: added by the operator from the Characters page
- `edited`: originally discovered and then edited by the operator

Voice-definition rules:

- `voice_definition_prompt` is the final handoff prompt later consumed by
  `Character Voices` and includes explicit `Sex/Gender:` guidance
- manual edits to the final prompt are preserved as the current character
  voice-design source

Evidence items currently store:

- `chunk_id`
- `sequence_index`
- `dialogue_span_id`
- `source_excerpt`
- `reason`
- `confidence`

Manual profiles use one synthetic evidence entry with:

- `chunk_id = "manual"`
- `sequence_index = 0`
- `source_excerpt = "Added manually by the operator."`
- `reason = "Added manually by the operator."`

Report fields currently include:

- `input_chunk_count`
- `input_source`
- `analyzed_window_count`
- `merged_candidate_count`
- `rejected_candidate_count`
- `rejected_candidates`
- `character_count`
- `review_status_summary`
- `character_discovery_mode`
- `character_profile_id_last_used`
- `model_settings`
- `window_size`
- `window_overlap`
- `budget_metadata`
- `model_settings_history`
- `warning_count`
- `warnings`
- `generated_at`

Operation-state invariants:

- opening the Characters page before discovery lazily creates
  `characters_state.json` with `not_started` progress and zero-valued
  character-discovery metadata counters; it does not create
  `characters_profile.json` or `characters_report.json`
- `mode` is `ai_assisted`
- resume checkpoints are reused when the chunk fingerprint still matches; the
  remaining discovery or synthesis work uses the currently selected enabled AI
  profile and records the current model name, context window, max output tokens,
  and temperature in `model_settings` plus `model_settings_history`
- discovery-window checkpoints store `next_discovery_start_chunk_index` so
  remaining windows can be rebuilt from the current profile budget after a
  cancellation; older checkpoints derive that boundary from the saved window
  budget when possible
- completed discovery disables the page start action until reset
- reset preserves upstream translation artifacts and existing narrator profiles
  or samples, then clears dependent character voice, speech, audio block, and
  assembly data
- manual add, edit, or delete operations update the persisted operation-state
  `metadata.character_count` when a state file already exists
- manual add preserves downstream Speech Blocks, Audio Blocks, and Audio
  Assembly while adding or refreshing the matching Character Voices target
- manual edit unapproves only Speech Blocks assigned to the edited character,
  marks the matching voice target stale when voice-definition source fields
  change, resets only affected Audio Blocks, and resets Audio Assembly
- manual delete removes the matching Character Voices target, moves assigned
  Speech Blocks to Narrator without deleting them, unapproves those blocks,
  resets only their Audio Blocks, and resets Audio Assembly

Relevant config values in `src/audiomancer/config.py`:

- `CHARACTER_PROFILE_FILE_NAME`
- `CHARACTER_DISCOVERY_REPORT_FILE_NAME`
- `DEFAULT_CHARACTER_DISCOVERY_WINDOW_SIZE`
- `DEFAULT_CHARACTER_DISCOVERY_WINDOW_OVERLAP`
- `DEFAULT_CHARACTER_DISCOVERY_MIN_TEXT_BUDGET_TOKENS`
- `DEFAULT_CHARACTER_DISCOVERY_MIN_SAFETY_MARGIN_TOKENS`
- `DEFAULT_CHARACTER_DISCOVERY_SAFETY_MARGIN_CONTEXT_FRACTION`
- `DEFAULT_CHARACTER_DISCOVERY_TEXT_CONTEXT_FRACTION`
- `DEFAULT_CHARACTER_DISCOVERY_SYNTHESIS_MAX_EVIDENCE_ITEMS`
- `AI_TRANSACTION_LOG_FILE_PREFIX`

## 7. Workflow Integration

Upstream:

- `Text Chunking` provides the canonical chunk set consumed by discovery
- `AI Settings` provides enabled profiles and
  `default_character_extraction_profile_id`
- `MainWindow.show_project_state(...)` rebuilds the Characters page state after
  every project refresh

Downstream:

- `CharactersPage` displays the discovered profiles and evidence, including
  right-click Find and Find Next actions on the selected evidence preview
- narrator-definition profiles and samples are preserved when discovery is reset
  or character profiles are manually changed
- manual character maintenance preserves unrelated characters, Speech Blocks,
  Audio Blocks, and voice targets
- projects with partially reviewed translation output remain at
  `translation_ready` until the translation chunk set is fully approved
- reset logic returns the project to `translation_ready`

Current in-repo usage:

- `MainWindow` wires the page signals to `characters_ui_controller`
- `ui_state_service` owns all operator-facing strings for the page, popup, and
  status messages
- `project_workspace_service` and `text_cleanup_state_service` preserve later
  workflow stages correctly during repair and reset

## 8. Usage

Controller-driven usage pattern:

```python
from audiomancer.services import character_discovery_service

report = character_discovery_service.start_or_continue_discovery(
    project_root,
    manifest,
    ai_profile_payload,
    progress_callback=progress_callback,
    cancel_requested=cancel_requested,
)
```

Page integration points:

- `CharactersPage.start_discovery_requested(str)`
- `CharactersPage.reset_discovery_requested()`
- `CharactersPage.add_character_requested()`
- `CharactersPage.edit_character_requested(str)`
- `CharactersPage.save_character_requested(dict)`
- `CharactersPage.delete_character_requested(str)`
- `CharactersPage.selection_change_requested(str | None)`

Required conditions:

- an active project must exist
- chunking output must already exist
- at least one enabled AI profile must be configured
- required character-discovery prompt templates must be present

## 9. Validation And Tests

Automated tests:

- `04_Software/AudioMancer/tests/test_character_discovery_service.py`
- `04_Software/AudioMancer/tests/test_character_discovery_state_service.py`
- `04_Software/AudioMancer/tests/test_characters_page.py`
- `04_Software/AudioMancer/tests/test_characters_ui_controller.py`
- `04_Software/AudioMancer/tests/test_main_window.py`
- `04_Software/AudioMancer/tests/test_text_cleanup_state_service.py`
- `04_Software/AudioMancer/tests/test_project_workspace_service.py`

Covered behaviors:

- initial discovery output persistence
- resumable synthesis checkpoints
- manual add or save or delete persistence
- duplicate and invalid manual-name validation
- explicit edit-mode enablement and save-button activation
- compact voice-definition prompt normalization
- guarded selection changes with unsaved drafts
- reset behavior and stage rollback
- profile-selector default resolution
- page button enablement, evidence preview, and evidence-preview search
- first-run popup and resume behavior in the controller
- main-window page refresh from persisted discovery artifacts

Minimum validation after a change:

- `python -m py_compile` for every changed Python file
- focused `pytest` runs for character discovery, state shaping, page,
  controller, main-window, and affected reset or repair tests

## 10. Limitations And Future Work

- the current spoken-dialogue heuristic is intentionally simple and relies on
  direct quotes, leading dashes, or dialogue-oriented reasoning text
- merged-character resolution is alias-based and does not yet use a stronger
  cross-window entity-linking strategy
- warnings are persisted structurally, but the current implementation does not
  yet generate many discovery-specific warning classes
- the AI prompts now request voice-design-ready fields, but quality still
  depends on how much direct textual evidence exists for each character
- the final voice-definition prompt is generated locally and deterministically;
  there is no second AI refinement pass dedicated only to voice design
