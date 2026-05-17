<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

No notable changes yet.

## [1.1.3] - 2026-05-17

### Changed

- Text Chunking now persists smaller chunk artifacts by removing duplicated
  `chapter_label` values from `chunks_text.json`; chapter counts and
  Character Discovery prompt context are derived from ordered chunk text at
  runtime.
- Chunking operation state is now more compact: resume-only AI fields,
  completed-window progress, committed break ids, log path, selected strategy,
  profile id, and extra instruction fingerprints live only in
  `resume_checkpoint` while completed audit data remains in
  `chunking_report.json`.
- Manual chunk edit, insert, and delete operations now update
  `chunks_text.json` and `chunking_report.json` while keeping
  `chunking_state.json` compact after the operation completes.
- `project.json` now stores only compact operation summaries and no longer
  persists extraction shortcut paths or operation folder paths.
- Deterministic and AI cleanup now resolve the canonical root-level
  `extracted_text.txt` artifact directly instead of reading manifest shortcut
  paths.

## [1.1.2] - 2026-05-17

### Changed

- Text Cleanup now treats `clean_text.txt` as the only persisted source of
  cleaned paragraph text. `clean_text_metadata.json` stores paragraph ids,
  line spans, page-break provenance, boundary confidence, and warning flags
  without duplicating paragraph `text`.
- Deterministic cleanup, AI cleanup, and manual cleaned-text edits now refresh
  the compact `project.json.operations.cleanup` summary during running,
  cancelled, completed, and manual-edit transitions so the Home workflow status
  stays current.
- Completed cleanup state is now compact: deterministic cleanup removes
  resume-only `cleaned_pages`, AI cleanup removes resume-only classifications,
  and both persist `resume_checkpoint: null` after success.
- Chunking and narrator profile generation now rebuild cleanup paragraph text
  from `clean_text.txt` when consuming cleanup metadata.

### Fixed

- Cancelled deterministic and AI cleanup runs now persist resumable
  `status="cancelled"` cleanup state while preserving partial progress and
  Home-visible operation status.

## [1.1.1] - 2026-05-17

### Changed

- Audio Blocks now persists a compact `audio_blocks.json` index with nullable
  timestamp `generated` and `approved` fields while keeping runtime, split,
  fingerprint, and resume details in per-block metadata sidecars.
- Audio Blocks page state now joins the compact Audio Blocks index with current
  Speech Blocks metadata and avoids opening WAV files or sidecar metadata during
  normal page loading.
- Play Audiobook preview now treats pause Speech Blocks as timed silence,
  including pauses that are present in current Speech Blocks but not yet present
  in the compact Audio Blocks index.

### Fixed

- Pause blocks are now generated and approved as metadata-only timing entries,
  so they cannot block Audio Assembly approval or generation flow.

## [1.1.0] - 2026-05-16

### Added

- Character Discovery now shows a dedicated bottom `Character Discovery Status`
  window, matching the workflow status pattern used by AI Translation.
- Character Discovery Evidence now uses a vertical splitter between the
  evidence list and source preview, with each pane clamped to at least 20% of
  the available Evidence height.
- Home exports now include ZIP archive rows for Narator Voice samples,
  Character Voices samples, and Audio Assembly outputs. Voice archives include
  each available WAV sample plus a companion text file with the voice definition
  and preview text; Audio Assembly archives include generated WAV outputs plus a
  manifest with composition settings, file list, duration, and size details.

### Changed

- Workflow pages now label operator progress panels as `Status` instead of
  `Notes` where the panel reports pipeline state.
- Character Discovery removes the duplicated summary line under the page title
  because the same details are now shown in the status window.
- Character Discovery places `Age Hint` on the same row as `Gender Hint` and
  sizes the Character List panel to the action-button stack so the Character
  Profile area has more usable vertical space, including with larger UI fonts.
- AI Translation now keeps the `Start Translation`, `Reset Translation`, and
  `Approve All` actions inside the `Chunk List` frame so the button column
  aligns with the list window.
- Home export rows now use the same fixed row height as Workflow Progress rows,
  including blank rows, so export buttons stay aligned with their operation.
- Speech Blocks now allows manual `Insert` on any selected source chunk before
  AI-generated speech blocks exist, enables `Delete` whenever a block is
  selected, and initializes or clears the Speech Blocks report/state so both the
  Speech Blocks page and Home workflow status reflect manual-only edits.
- Speech Blocks manual `Insert` now adds the new block after the selected block,
  or creates/appends the block when nothing is selected in the current chunk,
  matching manual top-to-bottom authoring.
- Character Voices now synchronizes its compact `project.json` operation
  summary whenever readiness changes, so the Home workflow row shows completed
  when the selected narrator sample and every character sample are present.
  Project-open metadata repair now recognizes current Character Voices artifacts
  where narrator sample data lives in `narator_sample.json`.
- Speech Blocks now preserves the selected chunk, selected Speech Block, and
  review-list scroll positions after the selected `Generate Audio` action
  refreshes Audio Blocks and Audio Assembly state.
- Speech Blocks now uses a tighter top offset for the chunk action button
  column so the `Insert`, `Delete`, edit, approval, audio generation, and
  playback actions sit closer to the Chunk List content line.
- Audio Blocks now measures generated WAV files when building the Speech Blocks
  list, so manually generated speech-block audio shows its duration instead of
  the unknown-duration placeholder.
- Audio Blocks now refreshes the compact Home workflow progress summary at each
  persisted generation checkpoint, including selected/manual generation from
  the Speech Blocks page.

## [1.0.16] - 2026-05-16

### Changed

- Narator Voice now uses only the current custom-profile model by removing old
  default/preset/protected-profile compatibility paths and their dead API
  wrappers.
- Character Voices now uses only the current read-only project voice-language
  model, drops obsolete `sample_mode` and `source_profile_id` target fields,
  and removes dead selected-language reset helpers so character preview text is
  preserved until explicitly edited.
- Speech Blocks now drops older `chunk_sequence_index` global-sequence schema
  compatibility, removes dead inserted-block and chunk-audio confirmation
  helpers, and no longer resumes from `metadata["source_chunks"]` length.
- Audio Blocks now requires current `narator_sample.json` selected narrator
  metadata, drops older `chunk_sequence_index` global-sequence compatibility,
  and removes dead chunk-level audio inspection and rerun-confirmation helpers.
- Audio Assembly now drops write-only resume metadata, requires non-default
  persisted state to carry the current input fingerprint, uses only current
  `pause_duration_ms` metadata for pause silence, and resolves playback output
  paths through the safe project-relative resolver.

## [1.0.15] - 2026-05-15

### Added

- Character Discovery now persists an editable `age_hint` for each speaking
  character and requires downstream Qwen voice-designer prompts to include an
  explicit `Age Domain:` instruction, preventing older characters from silently
  defaulting to younger generated voices when the source age is unclear.
- AI Settings and TTS Settings now use the same `Cancel`, `Save`, and `OK`
  dialog flow as Settings: `Save` persists changes without closing the dialog,
  while `OK` persists changes and closes it.
- Offline English and Romanian help screenshots for AI Settings and TTS
  Settings were regenerated with the new Windows dialog button rows.

### Changed

- Character dossiers and Character Voices synchronization now carry the new
  age handoff contract alongside sex/gender guidance.
- AI-assisted Text Cleanup now requires the current
  `artifact_type`/`action`/`confidence` JSON result schema and no longer treats
  legacy label-only cleanup items as valid removal instructions.
- AI-assisted Text Chunking now resumes only from current-version checkpoints
  with `completed_unit_count`; older checkpoint fallback by last unit id or
  window/budget inference was removed.
- AI Translation now uses only the current `approved` review-complete stage and
  no longer normalizes older `completed` report stages or passive pass-through
  artifacts.
- Character Discovery now requires current-version resume checkpoints with
  `next_discovery_start_chunk_index`, uses only canonical chunk input metadata,
  and no longer accepts legacy discovery-window `name`, `gender_hint`, or
  `voice_definition_prompt` fields.
- Runtime UI translation coverage now includes the new AI Settings and TTS
  Settings `OK` labels.

### Fixed

- Speech Blocks aligns selected-block `Generate Audio` and `Play` actions on
  the same row.
- Audio Assembly status text now refreshes with the UI-control font role, like
  Audio Blocks status text.
- Narator Voice gives the profile-list pane a wider minimum so `Import Sample`
  fits beside `Select`.

## [1.0.14] - 2026-05-15

### Added

- Narator Voice profiles and Character Voices character targets can now import
  WAV voice samples with operator-entered sample text for Qwen TTS Base voice
  cloning.
- Imported voice samples validate WAV readability, minimum 3-second duration,
  and non-silent audio before being copied into project sample storage.

### Changed

- Character Voices replaces the reset-prompt action with `Import Sample` for
  editable character targets while keeping the Narator Voice row read-only.
- Imported voice samples are treated as runtime-ready even without a source
  model id, while generated samples keep the existing model-readiness checks.
- Operator notes and bottom status panels now use the UI-control font instead
  of the book/text-window font.

## [1.0.13] - 2026-05-14

### Added

- Settings now supports separate theme font controls for UI labels/controls and
  multi-line text windows, so book-text editors can use a larger or different
  reading font without enlarging the whole interface.
- Settings now includes `Default Dark` and `Dark Contrast` built-in themes.

### Changed

- Settings theme editing now uses direct font-size values only; the previous
  UI/text scale controls were removed from the dialog, while legacy scale fields
  remain import-compatible.
- Settings theme font-size fields are now always editable for custom themes;
  the `Use default UI font size` and `Use default text font size` checkboxes
  were removed.
- The Settings dialog layout is more compact, with the preview area reduced and
  the color-selector column given more room.

### Fixed

- Text Chunking now enables the Insert action before generated chunks exist,
  allowing operators to start a fully manual chunking pass from cleaned text.

## [1.0.12] - 2026-05-13

### Added

- Text Cleanup, Text Chunking, AI Translation, Character Discovery, Narator
  profile generation, and Speech Blocks AI-assisted runs now ask for optional
  operator-supplied prompt rules in a word-wrapped text box before a fresh run,
  append those rules to each AI request, persist the rules with the report/state,
  and resume unfinished AI work with the original saved rules.

### Fixed

- AI prompt rendering no longer rejects source text containing literal brace
  markers such as Gutenberg index references (`{ix}`, `{x}`, `{xi}`) as
  unresolved template placeholders.
- Character Voices no longer enables batch character sample generation in
  same-narrator mode, preventing cancelled or refreshed batch runs from
  replacing character samples with copied Narator Voice audio.

## [1.0.11] - 2026-05-12

### Added

- AI-assisted Character Discovery now stores a `preview_text` field extracted
  from each character's spoken dialogue when enough evidence exists for an
  estimated 6-second Qwen TTS reference sample, and Character Voices seeds new
  character targets from that discovered preview text.

### Changed

- AI-assisted Narator Voice profile generation now requires preview text long
  enough for an estimated 6-second Qwen TTS reference sample instead of the
  previous 3-second minimum.
- AI-assisted Narator Voice profile generation now compacts repeated
  first-pass style observations into a deterministic frequency summary before
  the final profile-synthesis request, avoiding oversized second-pass prompts
  on large books.

## [1.0.10] - 2026-05-12

### Changed

- Text Cleanup reruns, manual cleaned-text edits, and full Text Chunking
  regeneration now preserve completed Character Discovery, Narator Voice, and
  Character Voices artifacts while resetting regenerated text, Speech Blocks,
  Audio Blocks, and Audio Assembly data.

## [1.0.9] - 2026-05-12

### Changed

- Same-narrator Speech Blocks now ask the AI model for compact boundary IDs
  instead of full copied Speech Block JSON, then build exact narrator
  `source_text`, `text`, speaker, and content-kind fields deterministically
  from the original source chunk.

### Fixed

- Same-narrator Speech Blocks now fall back to deterministic TTS splitting
  with a review warning when a local model returns malformed JSON or unusable
  boundary IDs, reducing run-stopping JSON parse failures and source-copy
  mismatch warnings from offline models.

## [1.0.8] - 2026-05-11

### Added

- Narator Voice now supports AI-assisted text-only narrator profile generation
  with an AI profile selector, token/cost confirmation, requested profile
  count, gender allocation, generated voice-designer prompts, preview text, and
  append-only editable profiles without generating audio or selecting a
  narrator.
- AI narrator profile generation now persists resumable checkpoints with
  completed style observations, token usage, model settings, and the AI
  transaction log path so interrupted runs can continue compatible unfinished
  work instead of restarting from the first source window.
- AI narrator profile generation now folds the Qwen3-TTS Voice Designer guide
  into generated prompt instructions, including prompt length, structure,
  acoustic/emotional layering, stability, and anti-exaggeration guidance.
- AI narrator profile generation now requires generated preview text to be long
  enough for an estimated 3-second Qwen TTS reference sample.

### Changed

- Narator Voice no longer shows the Original language, Translated language, and
  Voice language indicator row; the project language remains visible on Home
  and is used internally by narrator operations.
- AI Settings now labels the narrator-generation default selector as
  `Default Narator Generation Profile`.
- AI Settings now places Context Window, Max Output Tokens, Timeout, and
  Temperature into a compact two-column profile-options grid to leave more
  vertical room for default-profile selectors.
- AI Settings now places the shortened `Structured output` checkbox beside
  Model Name to free another row in the profile editor.

## [1.0.7] - 2026-05-11

### Fixed

- Project opening no longer shows a repair prompt for narrator-definition
  timestamp-only metadata drift when the selected narrator identity and
  downstream non-completed workflow statuses are already consistent.

## [1.0.6] - 2026-05-11

### Changed

- Windows and Linux packaging scripts now include `CHANGELOG.md` in portable
  release bundles.

## [1.0.5] - 2026-05-11

### Changed

- Narator Voice changes now show a synchronous modal progress dialog while
  affected Audio Blocks and Audio Assembly state is refreshed, using the same
  faster affected-audio cleanup path as Characters saves.

## [1.0.4] - 2026-05-11

### Changed

- Characters page saves now show a synchronous modal progress dialog while
  downstream Speech Blocks, Audio Blocks, and Audio Assembly state are
  refreshed, and affected Audio Blocks cleanup skips unnecessary preserved-file
  checks for faster large-project saves.

## [1.0.3] - 2026-05-10

### Changed

- Audio Blocks page opening is faster on large projects because page-state
  construction no longer opens every generated WAV to compute row durations,
  and the page batches list-row refreshes while avoiding unchanged source-text
  rewrites.

## [1.0.2] - 2026-05-10

### Fixed

- Backend workflow services now persist compact operation status summaries and
  workflow-stage transitions directly to `project.json` after operation
  completion or review updates, instead of relying on the UI shell to mirror
  backend state.
- Audio Blocks completion and approval refreshes now promote stale
  `audio_blocks_state.json` metadata to `completed` when the completed report
  and generated output artifacts prove the operation finished.
- Project-open metadata normalization now treats persisted string values such
  as `"None"` and `"null"` as missing values, preventing repeat repair prompts
  caused by stale null-like text.
- Narrator completion evidence now prefers selected-sample timestamps so valid
  narrator selections no longer require repeated summary normalization.

## [1.0.1] - 2026-05-10

### Changed

- JSON-producing AI requests now choose the structured-output
  `response_format` by backend: general OpenAI-compatible profiles use
  `json_object`, while LM Studio and Ollama profiles use permissive
  `json_schema` mode. Providers that reject `response_format` still get a
  one-time compatibility retry without the field.
- AI workflow prompts have been refreshed for literary/audiobook production,
  with stronger preservation rules for cleanup, semantic chunking, translation,
  character discovery, character voice synthesis, Speech Blocks, and
  narrator-only Speech Blocks.
- Speech Blocks prompts now preserve the improved v2 dialogue and attribution
  guidance while staying aligned with the current application JSON contract.
- Speech Blocks generation now resumes from partially generated, reviewed, or
  approved chunks instead of treating review state as a fresh run.
- AI cleanup, AI-assisted chunking, character discovery, and Speech Blocks now
  size OpenAI-compatible request text windows from 30% of the selected model
  context window, without applying the local LM Studio/Ollama request caps.
- Narrator profile selection now updates the project manifest's narrator
  operation summary immediately, avoiding a repair prompt after restarting the
  app with a valid selected narrator.
- Home workflow progress now trusts explicit operation summaries over the
  linear `current_stage`, so independently completed Narator Voice work no
  longer makes Translation, Characters, or Character Voices appear finished.

## [1.0.0] - 2026-05-06

### Added

- first AudioMancer release with the complete desktop audiobook production
  workflow, offline English and Romanian help, packaging metadata, and release
  documentation aligned to version `1.0.0`
