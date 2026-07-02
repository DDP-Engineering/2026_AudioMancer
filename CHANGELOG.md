<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [1.6.0] - 2026-07-02

### Added

- Added a multilingual Speech Blocks pipeline that builds deterministic atomic
  speech units from source chunks before AI speaker assignment, including
  quoted dialogue, dash-led dialogue, attribution narration, separator-only
  spans, and Romanian/source-language dialogue patterns.
- Added local-model and LM Studio Speech Blocks guidance covering recommended
  model usage, context choices, sampler settings that remain configured in LM
  Studio, and AudioMancer settings that are actually sent to providers.

### Changed

- Speech Blocks narrator-and-character generation now asks models to assign
  speakers and content kinds to existing atomic `unit_ids` only; AudioMancer
  reconstructs persisted `source_text` and spoken `text` from app-owned source
  text instead of trusting model-returned wording.
- Speech Blocks local-model handling now uses operation-specific structured
  output hints when supported, performs one compact repair retry for malformed
  or semantically invalid responses, and falls back deterministically with
  review warnings when model output remains unusable.
- Speech Blocks speaker attribution now uses source-language aliases, compact
  character evidence, nearby attribution hints, and ambiguity warnings to
  improve multilingual books without inventing speakers.
- Adjacent cleanup, translation, and chunking prompts now preserve dialogue
  punctuation, attribution context, paragraph structure, and source-language
  cues needed by downstream Speech Blocks.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.6.0`.
- Offline English and Romanian help bundles were updated to version `1.6.0`.

### Fixed

- Fixed separator-only or whitespace-only Speech Blocks units so they preserve
  source offsets without creating empty persisted narrator rows.
- Fixed same-narrator Speech Blocks boundary selection so normal split
  candidates and AI-selected boundaries do not divide open quoted passages and
  make review text appear to lose opening or closing quotation marks.

## [1.5.9] - 2026-06-17

### Added

- AI Settings now include a default chunking context mode with Balanced, Wide
  scene context, and Maximum context options for AI-assisted chunking prompts.
- AI chunking prompt construction now uses the selected context mode: Balanced
  preserves the existing 64/96/128 paragraph caps, Wide scene context raises
  the caps to 128/192/256, and Maximum context relies on the token budget
  without a local paragraph cap.

### Changed

- Project package metadata and `audiomancer.__version__` were updated to
  `1.5.9`.
- Offline English and Romanian help bundles were updated to version `1.5.9`.

## [1.5.8] - 2026-06-12

### Fixed

- Cleanup, extraction, cleanup metadata, manual cleaned-text edits, and Audio
  Assembly state/report writes now use atomic persistence for the critical
  project artifacts touched by the cleanup safety bundle.
- Malformed or truncated operation-state files now load as no usable state with
  a warning, allowing deterministic cleanup, AI cleanup, extraction, and Audio
  Assembly to restart or follow their normal reset path instead of crashing the
  next run.
- Deterministic and AI cleanup now persist terminal failed state where possible
  while preserving resumable checkpoints for interrupted work.

### Changed

- Deterministic cleanup now uses input-fingerprinted checkpoints, bounded
  checkpoint cadence, and non-PDF pseudo-segments for granular cancel/resume
  progress without changing uninterrupted cleanup output.
- The shared LLM provider now reports cooperative cancellation with a neutral
  cancellation message rather than treating it as provider failure.
- The threaded operation runner now schedules the operation UI bridge for
  deferred Qt deletion after finish cleanup.
- VoiceWeaver operation polling and generated-audio download defaults now use
  `DEFAULT_TTS_OPERATION_TIMEOUT_SECONDS`, an alias for the existing audio
  generation timeout value.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.5.8`.
- Offline English and Romanian help bundles were updated to version `1.5.8`.

## [1.5.7] - 2026-06-11

### Fixed

- Character Voices sample generation now passes cancellation through
  VoiceWeaver polling, preserves previous character samples when generation
  fails or is cancelled, writes Character Voices JSON and WAV artifacts
  atomically, and avoids redundant same-narrator copied-sample writes during
  unchanged page refreshes.

### Changed

- Character Voices page-state refreshes now avoid unchanged manifest and target
  rewrites while preserving full-current-target batch regeneration behavior.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.5.7`.
- Offline English and Romanian help bundles were updated to version `1.5.7`.

## [1.5.6] - 2026-06-11

### Fixed

- Narrator sample generation now passes cancellation through VoiceWeaver
  polling, preserves the previous profile sample when generation fails or is
  cancelled, writes narrator JSON and WAV artifacts atomically, tolerates
  malformed narrator JSON as recoverable missing data, and persists
  `cancelled` / `failed` narrator profile-generation checkpoints.

### Changed

- Project package metadata and `audiomancer.__version__` were updated to
  `1.5.6`.
- Offline English and Romanian help bundles were updated to version `1.5.6`.

## [1.5.5] - 2026-06-11

### Fixed

- Character Discovery now writes profiles and reports atomically, tolerates
  malformed profile/report JSON as recoverable missing data, persists
  `cancelled` / `failed` terminal checkpoints for interrupted runs, avoids
  redundant discovery-span work during Characters page refresh, removes
  duplicate startup window construction, and preserves identity grouping with
  indexed alias lookup.

### Changed

- Project package metadata and `audiomancer.__version__` were updated to
  `1.5.5`.
- Offline English and Romanian help bundles were updated to version `1.5.5`.

## [1.5.4] - 2026-06-11

### Fixed

- AI Translation now writes translated chunks, reports, and operation state
  atomically, avoids duplicate per-chunk and review precondition rewrites,
  keeps unchanged page-state builds read-only, tolerates malformed translation
  JSON as recoverable missing data, and persists `cancelled` / `failed`
  terminal states for interrupted translation runs.

### Changed

- Project package metadata and `audiomancer.__version__` were updated to
  `1.5.4`.
- Offline English and Romanian help bundles were updated to version `1.5.4`.

## [1.5.3] - 2026-06-10

### Changed

- Improved deterministic and AI-assisted text chunking persistence so large
  runs avoid redundant chunk rewrites and full chapter rescans while keeping
  completed chunk artifacts unchanged.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.5.3`.
- Offline English and Romanian help bundles were updated to version `1.5.3`.

### Fixed

- Chunking cancellation, failure, and malformed JSON recovery now persist
  resumable terminal state and use atomic JSON writes for chunking artifacts,
  reports, and state files.

## [1.5.2] - 2026-06-10

### Fixed

- Fixed the Speech Blocks header layout so the page title, AI Profile selector,
  Generate All, Reset, and Approve All controls stay on one startup row without
  overlapping or clipping their labels.
- Fixed `02_Tools/make_synthetic_project.py` so it runs as a standalone offline
  tool without importing the AudioMancer desktop application package or requiring
  PySide6.

### Changed

- Project package metadata and `audiomancer.__version__` were updated to
  `1.5.2`.
- Offline English and Romanian help bundles were updated to version `1.5.2`.

## [1.5.1] - 2026-06-10

### Changed

- Restored the fixed-width vertical workflow-navigation sidebar on the left of
  the page stack with the original full page labels, replacing the horizontal
  top navigation tab strip introduced in `1.5.0`. The compact undecorated
  three-row operator status panes and the other `1.5.0` page-layout
  improvements (Speech Blocks chunk-list alignment, Audio Blocks label removal,
  Audio Assembly Scene Mix button column) are kept; page content scales back
  proportionally through the existing stretch factors and dynamic splitter
  minimum guardrails.
- Narator Voice `Generate Sample` no longer carries an inflated fixed minimum
  width, so it shrinks with the other action-row buttons when the splitter
  narrows the editor pane.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.5.1`.
- Offline English and Romanian help bundles were updated to version `1.5.1`.

## [1.5.0] - 2026-06-09

### Added

- Added a shared `operator_status_pane_height` UI helper that sizes operator
  status panes to a compact, font-aware text-row count.

### Changed

- Replaced the left-hand workflow navigation sidebar with a horizontal
  navigation tab strip under the toolbar, using shortened page labels, so the
  workflow pages occupy the full window width.
- Aligned the navigation tab strip to the workflow pages' left/right margins so
  its ends line up with the page content below it.
- Reworked the operator status panes across all workflow pages into compact,
  undecorated containers without a group-box title or frame, sized to a
  font-aware three-row height to maximize the text and list editors.
- Speech Blocks Chunk List frame height now matches the action-button column so
  their bottom edges align.
- Audio Blocks page removed the "Generated blocks" count label to give the
  source and block panes more vertical space.
- Audio Assembly Scene Mix Previews action buttons moved to the right of the
  previews list and stacked vertically.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.5.0`.
- Offline English and Romanian help bundles were updated to version `1.5.0`.

## [1.4.2] - 2026-06-08

### Added

- Added a Settings control for application-wide mouse-wheel scroll steps with
  validated values from `1` to `5` and default `1`.
- Added a shared UI scroll-step service so text editors, lists, and scroll
  areas use the configured wheel-step count at startup and after Settings
  Apply/OK.

### Changed

- Speech Blocks operations now preserve the selected-chunk text cursor,
  highlighted range, horizontal scroll, and vertical scroll after edit, save,
  insert, delete, approve/unapprove, generation refreshes, and selected-chunk
  re-splitting.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.4.2`.
- Offline English and Romanian help bundles were updated to version `1.4.2`.

## [1.4.1] - 2026-06-08

### Added

- Added modal progress and cancellation support while generating Audio Assembly
  Scene Mix previews.

### Changed

- Character voice-definition and sample changes now preserve existing Speech
  Blocks and Audio Block rows, clearing only generated audio for Audio Blocks
  that use the changed voice target.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.4.1`.
- Offline English and Romanian help bundles were updated to version `1.4.1`.

### Fixed

- Fixed selected Audio Block regeneration after one character voice sample is
  regenerated so a stale Audio Blocks run fingerprint does not force a full
  Audio Blocks reset when the selected row has already been invalidated.
- Fixed Audio Assembly with Scene Ambience enabled when sound-model WAVs and
  TTS WAVs use different channel counts or sample rates, such as stereo
  44.1 kHz ambience beside mono 24 kHz narration.

## [1.4.0] - 2026-05-25

### Added

- Added Audio Assembly Scene Mix previews for Scene Ambience groups so operators
  can generate, refresh, and play a mixed ambience bed before creating final
  audiobook output.
- Added reusable Audio Assembly service support for listing Scene Ambience mix
  groups, checking preview readiness, generating deterministic preview WAV
  files, and reusing the same mixer for final assembly.
- Added focused service, page, controller, Audio Blocks, and Speech Blocks tests
  for fixed Scene Ambience duration, preview availability, preview playback, and
  final mixed Scene Ambience assembly.

### Changed

- Scene Ambience prompt WAVs now use the fixed Scene Ambience duration from TTS
  Settings, and related ambience prompt WAVs are overlaid into one mixed segment
  per scene group during final Audio Assembly.
- Audio Assembly now inserts mixed Scene Ambience segments when
  `Include Scene Ambience` is enabled, while keeping narration, dialogue,
  pauses, and indications in the existing sequential composition flow.
- Scene Ambience prompt instructions now describe the configured duration
  contract instead of showing a hardcoded `10.0` duration example.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.4.0`.
- Offline English and Romanian help bundles were updated to version `1.4.0`.

## [1.3.2] - 2026-05-25

### Changed

- Speech Blocks speaker and content-kind selectors now expand with the
  available window width so longer speaker labels remain visible.
- Speech Blocks editing, saving, approval, insertion, deletion, and generation
  actions now preserve the selected-chunk text cursor, selection, and scroll
  position instead of moving the operator's reading position.
- Speech Blocks edit and save handling now avoids unnecessary status rewrites
  and duplicate manifest summary refreshes.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.3.2`.
- Offline English and Romanian help bundles were updated to version `1.3.2`.

### Fixed

- Fixed the local development environment metadata so `uv run pytest` can start
  normally again after the local pytest installation became inconsistent.

## [1.3.1] - 2026-05-23

### Changed

- Text Chunking, AI Translation, and Speech Blocks chunk lists now use
  full-width one-line row previews with edge elision instead of hard-truncated
  preview text.
- Characters profile controls were tightened so labels and fields remain
  aligned when the application window is expanded.
- Narator Voice controls were shortened, the profile wording was removed from
  the action buttons, and the vertical splitter range was widened.
- Character Voices now shows an AI Profile selector beside Generate Character
  Samples for consistency with the narrator and character workflows.
- Speech Blocks and Audio Blocks splitter and header layouts were retuned so
  panes, selectors, and progress controls resize more predictably on wide
  windows.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.3.1`.
- Offline English and Romanian help bundles were updated to version `1.3.1`.

### Fixed

- Fixed repeated project-repair prompts caused by Character Voices activation
  syncing manifest metadata before persisted voice targets had been loaded.
- Fixed Audio Blocks progress and Scene Ambience selector sizing so they stay
  anchored and expand correctly when the window is maximized.

## [1.3.0] - 2026-05-21

### Added

- Added Scene Ambience Speech Blocks as the replacement for the old
  `background_noise` concept, including opener, closer, and scene-change
  placement support with `sound_prompt`, `negative_prompt`, per-block
  duration, and ambience-position metadata.
- Added Speech Blocks and TTS Settings controls for enabling Scene Ambience
  analysis, selecting placement policy, setting a soft maximum sequence
  duration, and limiting the maximum number of ambience blocks per sequence.
- Added Audio Blocks support for optional Scene Ambience sound generation
  through VoiceWeaver `sound_prompt` models, with runtime capability discovery,
  confirmation prompts, and generated WAV download support.
- Added an Audio Assembly `Include Scene Ambience` option so final sequential
  audiobook composition can include or skip generated ambience WAV blocks.

### Changed

- Speech Blocks generation now performs a second per-chunk ambience pass only
  when Scene Ambience is enabled, and ambience blocks participate in approval
  and review like other generated Speech Blocks.
- Scene Ambience LLM prompts now request concrete layered Foley-style sound
  prompts with timing variation and anti-beep negative prompts, and
  normalization defensively splits composed ambience prompts into individual
  sound-source blocks before persistence.
- Scene Ambience Speech Blocks now omit the old sound-type field; the prompt,
  negative prompt, duration, and sequence order are the editable contract.
- TTS Settings now stores Scene Ambience sound-model parameters
  `scene_ambience_guidance_scale`, `scene_ambience_num_inference_steps`, and
  `scene_ambience_seed`, and Audio Blocks forwards them to VoiceWeaver
  `/v1/sound/prompt`.
- Scene Ambience duration now starts from the TTS Settings sequence limit during
  Speech Blocks creation, then each generated ambience block carries its own
  duration into VoiceWeaver sound generation.
- Audio Assembly settings are now arranged in two columns and persist the
  Scene Ambience inclusion policy in `project.json.audio_assembly_settings`.
- Audio Blocks and Speech Blocks header/control layouts were tightened so long
  labels and larger UI fonts fit better across the workflow pages.
- TTS Settings runtime audio limit controls now use a compact two-column
  layout with better-sized numeric inputs.
- Removed duplicate Scene Ambience enable toggles from TTS Settings; Speech
  Blocks and Audio Blocks keep their workflow-local enable selectors.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.3.0`.
- Offline English and Romanian help bundles were updated to version `1.3.0`
  with refreshed TTS Settings, Speech Blocks, and Audio Blocks screenshots.

### Fixed

- Fixed VoiceWeaver Stable Audio WAV serialization for `float16` generated
  audio by converting it to a supported WAV dtype before writing.
- Fixed Speech Blocks metadata-row sizing so Speaker and Content Kind controls
  stay inside the Speech Blocks panel without overlapping adjacent panes.
- Fixed Speech Blocks selected-block audio controls so approved Scene Ambience
  blocks can generate and play audio from the Speech Blocks page.
- Fixed duplicate `Scene Ambience` labels in the Speech Blocks list so each
  ambience row shows the content type only once.

## [1.2.2] - 2026-05-19

### Changed

- Audio Blocks now stores per-block generation metadata directly in
  `audio_blocks.json` instead of writing separate WAV-adjacent JSON sidecars,
  reducing duplicated metadata while preserving generated-audio playback,
  approval state, prompt reuse, split-part resume, and operation resumability.
- `audio_blocks_state.json` now keeps only resume-critical operation metadata;
  prompt counts, generated counts, selected model names, and block totals are
  derived from canonical Audio Blocks/report data instead of duplicated into
  state metadata.
- Audio Blocks, operation-runtime, and software documentation were updated to
  describe the compact metadata contract and current resume data boundaries.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.2.2`.
- Offline English and Romanian help bundles were updated to version `1.2.2`.

## [1.2.1] - 2026-05-19

### Changed

- AI Translation now always uses the configured AI profile when Start
  Translation is pressed, including when the source and target languages match.
  Same-language translation is now an AI-assisted rewrite/adaptation path
  instead of a source-text pass-through.
- Removed the same-language pass-through helper and `pass_through` translation
  operation mode.
- Translation chunk records no longer persist `translated_at` or `approved_at`;
  resume continues to use chunk text/status plus `translation_state.json`
  checkpoints, token usage, prompt-rule fingerprints, and AI log metadata.
- `translation_state.json` no longer duplicates the per-chunk translated text
  records stored in `translated_text.json`.
- LLM JSON parsing now fails fast on empty assistant content instead of sending
  an empty malformed-JSON repair request back to the model.
- Character Discovery now persists separate `gender_confidence` and
  `age_confidence` fields while preserving existing evidence records and using
  `confidence` only for speaking-character identity confidence.
- Character Discovery prompts now instruct the LLM to estimate age and
  sex/gender from direct evidence first and conservative local book context
  when direct evidence is missing.
- Characters page editing now shows and saves the new demographic confidence
  fields with English and Romanian runtime labels.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.2.1`.
- Offline English and Romanian help bundles were updated to version `1.2.1`.

## [1.2.0] - 2026-05-18

### Changed

- Operation state payloads now use the compact shared envelope only:
  `status`, progress fields, `mode`, `warning_count`, `metadata`, and
  `resume_checkpoint`.
- Extraction, cleanup, chunking, character discovery, narrator profile
  generation, speech blocks, audio blocks, and audio assembly reports no
  longer persist operation audit timestamps or fixed path mirrors.
- Resume behavior is preserved through checkpoints, input and prompt-rule
  fingerprints, token usage metadata, partial output artifacts, and explicit
  AI log path metadata.
- Narrator profiles, narrator samples, character profiles, and character voice
  targets no longer persist audit timestamp fields or `stale`; `editable`
  remains in character voice targets to protect read-only narrator behavior.
- Project-open and manifest healing now validate completion from status,
  counters, reports, and existing artifacts instead of audit timestamps or
  generic path arrays.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.2.0`.
- Offline English and Romanian help bundles were updated to version `1.2.0`.

## [1.1.6] - 2026-05-18

### Changed

- Narator Voice now persists compact narrator profile and sample metadata,
  removing duplicated profile-kind, origin, provider, selection, sample-path,
  validation, runtime-summary, and generation metadata fields while preserving
  selected narrator behavior.
- AI narrator profile generation keeps resume checkpoints, reports, token
  usage, and AI transaction logs in the operation sidecars instead of
  duplicating provenance into each generated profile.
- Legacy narrator profile samples, selected-sample metadata, and existing
  display-name-based narrator WAV files remain readable and normalize into the
  compact sample contract on load.
- Same-narrator Character Voices, project-open operation evidence, Audio
  Blocks, and export readiness now consume the compact narrator sample
  contract with legacy fallbacks where needed.
- Narator Voice now gives the profile-list pane a slightly smaller initial
  width and protects the `Generate Sample` button label from clipping.
- Repository agent instructions now forbid writing the current application
  version in README files; version-sensitive references belong in the
  changelog, project metadata, and synchronized help files.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.1.6`.
- Offline English and Romanian help bundles were updated to version `1.1.6`.

## [1.1.5] - 2026-05-18

### Changed

- AI Translation now persists compact operation state by removing duplicated
  path-list, source-count, and pass-through operator metadata while preserving
  chunk-record resume, AI log reuse, token usage, and saved operator prompt
  rules.
- Speech Blocks export source chunk counts now fall back to current
  `translated_text.json` or `chunks_text.json` artifacts instead of removed
  operation-state metadata.
- Offline English and Romanian help bundles were updated to version `1.1.5`.

## [1.1.4] - 2026-05-17

### Changed

- Character Discovery now persists compact operation state with a top-level
  `checkpoint` and root-level `log_relative_path`, removing duplicated path,
  metadata, and synthesis-progress fields while preserving resumable AI logs.

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
