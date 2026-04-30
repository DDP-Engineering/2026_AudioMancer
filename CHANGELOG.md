<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# Changelog

All notable changes to this project will be documented in this file.

## [1.1.5] - 2026-04-30

### Changed

- changed interrupted AI-assisted Character Discovery resume to continue
  remaining discovery or synthesis work with the currently selected AI profile
  instead of forcing the original checkpoint profile
- changed Character Discovery checkpoints to persist the next source-chunk
  boundary so remaining request windows can be rebuilt safely when the selected
  model context window or output-token settings change
- changed Character Discovery state and reports to persist concrete model
  settings and model-settings history, including model name, context window,
  max output tokens, and temperature
- package version updated to `1.1.5`

## [1.1.4] - 2026-04-30

### Changed

- changed interrupted AI-assisted chunking resume to continue remaining
  paragraph units with the currently selected AI profile instead of forcing the
  original checkpoint profile
- changed AI chunking checkpoints to persist completed paragraph-unit progress
  so remaining request windows can be rebuilt safely when model context window
  or output-token settings change
- changed AI chunking state and reports to persist concrete model settings and
  model-settings history, including model name, context window, max output
  tokens, and temperature
- package version updated to `1.1.4`

## [1.1.3] - 2026-04-30

### Changed

- changed interrupted AI-assisted cleanup resume to use the currently selected
  model settings for remaining cleanup units instead of forcing the original
  checkpoint profile
- changed AI cleanup state and reports to persist concrete model settings and
  model-settings history, including model name, temperature, context window,
  max output tokens, backend, and base URL
- changed stale AI cleanup checkpoints with a changed extracted-text
  fingerprint to start a clean run instead of carrying old resume history
- package version updated to `1.1.3`

## [1.1.2] - 2026-04-29

### Changed

- extracted shared AI budget, operation-state, token-note, workflow-controller,
  Speech Blocks normalization, Speech Blocks report-state, Speech Blocks text
  splitting, and Audio Blocks artifact helpers from the large workflow services
- changed AI cleanup, chunking, translation, character discovery, Speech Blocks,
  Audio Blocks, Audio Assembly, and workflow controllers to use the shared
  helpers instead of parallel local implementations
- removed unused narrator-definition state helpers and unused narrator/character
  voice runtime-probe wrapper functions
- changed release packaging to write stable `AudioMancer_Windows_x64.zip` and
  `AudioMancer_Linux_x64.zip` archives instead of versioned archive filenames
- package version updated to `1.1.2`

### Fixed

- fixed runtime artifact path handling so persisted project-relative paths are
  resolved through the project-root containment helper before read, delete,
  rename, or open operations
- fixed packaged resource lookup so source-tree, installed, and PyInstaller
  layouts resolve settings, prompts, help, version, and license resources from
  the correct runtime root
- fixed narrator voice-language state shaping after cleanup so available
  language entries and selected narration language follow the original project
  language unless an approved translation is available

## [1.1.1] - 2026-04-29

### Changed

- centralized repeated service helpers for operation progress callbacks, UTC
  timestamp formatting, optional runtime string normalization, operation-state
  JSON loading, project-relative path containment, and endpoint URL joining
  into shared operation, time, and URL utilities
- changed workflow services to reuse the shared helpers across AI chunking,
  cleanup, translation, extraction, workspace repair, export/snapshot, speech,
  audio, narrator, character, and VoiceWeaver runtime paths
- added focused coverage for the shared operation runtime and URL helpers,
  including four-argument progress callbacks, exact operation-state file
  loading, path-escape rejection, and duplicate endpoint/version handling
- added focused test coverage for committed settings secret hygiene, atomic
  JSON persistence routing for manifests/settings/operation artifacts, AI log
  redaction, AI-log snapshot exclusion, and project-open symlink escape
  rejection
- added automatic `service` and `ui` pytest markers so the application test
  suite can be run in faster tiers after full-suite timeouts
- removed obsolete flat-layout workspace repair helpers that had no service or
  test callers and still carried migration-era folder assumptions

### Fixed

- fixed critical JSON persistence so `project.json`, `settings.json`, and
  first-use operation state files are written through same-directory temporary
  files and atomically replaced, preventing partial writes from corrupting the
  previous valid payload
- fixed project-relative path validation so manifest, source replacement,
  cleanup input, completion-healing, and artifact-reference paths reject
  absolute paths, `..` traversal, and symlink escapes before files are trusted
- fixed main-window shutdown while long-running workflow operations are active
  so close now requests cooperative cancellation, waits briefly for threaded
  cleanup, and ignores the close event if the worker remains active
- fixed project switching controls so `New Project` and `Open Project` stay
  disabled while a threaded operation is running
- fixed the committed settings scaffold so AI and TTS runtime secret fields are
  blank example values instead of operator-specific credentials
- fixed AI transaction logging to redact sensitive context fields recursively
  before writing operation-local log files
- fixed project ZIP snapshots to exclude project-local AI transaction logs
- added focused pytest-qt coverage and updated operation-runner documentation
  for active-worker shutdown behavior
- package version updated to `1.1.1`

## [1.1.0] - 2026-04-28

### Changed

- changed AI-assisted cleanup to persist context-budget metadata and validate
  resume checkpoints against the selected model context window, max output
  tokens, prompt budget, and conservative safety margin
- changed AI-assisted chunking to size paragraph request windows from the
  selected model context window, max output tokens, prompt budget, and
  conservative safety margin instead of fixed paragraph counts, with larger
  strategy-specific paragraph caps and budget-aware resume validation
- changed AI translation source segmentation to use the selected model context
  window, max output tokens, prompt budget, and conservative safety margin,
  while persisting budget metadata in translation report and state files
- changed AI-assisted character discovery to use budget-aware chunk windows,
  persist budget metadata in report and state files, validate resume
  checkpoints against model budget settings, and trim synthesis evidence
  payloads before final character-profile generation
- changed AI-assisted Speech Blocks generation and selected-chunk re-splitting
  to size model requests from the selected profile context window, max output
  tokens, prompt budget, and conservative safety margin, split oversized source
  chunks before AI dispatch, persist budget metadata in Speech Blocks report and
  state files, and validate resume checkpoints against that metadata
- reduced the first-pass AI character-discovery JSON schema so the window
  extraction step returns compact speaking-character candidates and evidence,
  leaving rich voice-profile synthesis to the final per-character pass
- fixed delivery packaging so Windows embeds and bundles the AudioMancer icon,
  while Ubuntu archives include the icon asset plus a portable desktop launcher
- package version updated to `1.1.0`

## [1.0.0] - 2026-04-27

### Changed

- changed Audio Assembly generated-output playback to show an inline
  Play/Stop control beside the seek controls instead of in the page header
- changed Audio Assembly generated-output review so double-clicking a file
  stops any active Audio Assembly preview and starts the clicked file from the
  beginning
- added Audio Assembly playback position display, drag-to-seek progress bar,
  and `-10s` / `+10s` quick-seek buttons for long generated audiobook files
- updated Audio Assembly documentation, user guides, and focused page/controller
  tests for the new playback controls
- refreshed the English and Romanian offline help guides with current workflow
  screenshots, AI model recommendations, and VoiceWeaver audio-generation
  requirements
- package version updated to `1.0.0`

### Fixed

- fixed project switching after local audio playback so narrator, character,
  Audio Blocks, and Audio Assembly media players release stale sources and reset
  playback UI state before the next project is activated
- fixed Audio Assembly shutdown cleanup so the final-audiobook player is stopped
  and its media source is cleared when the main window closes
- fixed delivery packaging so external AI prompt templates are included in the
  portable Windows and Ubuntu archives under `prompts/`

## [0.34.1] - 2026-04-27

### Changed

- changed Audio Blocks generation reuse to invalidate persisted generated audio
  at block level when text, voice target, language, sample, model budget, or
  split-plan inputs no longer match
- changed Audio Blocks readiness so generation can start when at least one
  Speech Block is approved, matching the service's partial-generation behavior
- changed metadata-only special block persistence to record explicit
  implementation status, with pause implemented and background-noise /
  indication marked as not implemented
- changed Audio Assembly pause handling so explicit pause blocks do not
  double-count adjacent automatic inter-block silence
- updated Audio Blocks and Audio Assembly software documentation for
  generation fingerprints, reset detection, special blocks, WAV validation, and
  pause composition semantics
- package version updated to `0.34.1`

### Fixed

- fixed generated Audio Blocks WAV persistence to reject invalid downloaded WAV
  payloads immediately
- fixed split-part resume so stale, corrupt, or mismatched split checkpoints are
  not reused
- fixed Reset Audio Blocks button enablement so empty generated-audio
  subfolders left after reset no longer keep the reset action active

## [0.34.0] - 2026-04-27

### Added

- added production prompt-contract coverage for Speech Blocks prompt templates
  so runtime placeholder mismatches are caught by tests
- added deterministic post-AI Speech Blocks splitting for over-budget
  non-operation blocks, preferring paragraph and sentence boundaries and
  marking hard fallback splits for review
- added online OpenAI model-profile recommendations for AI Cleanup, AI
  Chunking, AI Translation, and Speech Blocks in SoftwareDocu

### Changed

- changed same-narrator Speech Blocks handling so generated and manually edited
  non-operation blocks are forced to narrator/narration while pause,
  background-noise, and indication operation blocks keep their operation labels
- changed Speech Blocks generation and reset to invalidate downstream Audio
  Blocks and Audio Assembly artifacts, while selected-block edits, resets,
  approvals, inserts, deletes, and selected-chunk re-splits reset only the
  affected chunk's generated audio
- changed Speech Blocks completion semantics so full generation enters
  `review_pending`, disables generation, enables reset, and only marks the
  project/home workflow complete after every Speech Block is approved
- changed same-narrator Speech Blocks editing so the speaker selector exposes
  only Narrator and disables speaker reassignment
- changed Audio Blocks readiness so generation is available only after all
  Speech Blocks are approved
- updated Speech Blocks, Audio Blocks, and TTS budget documentation for the new
  reset, approval, operation-block, and budget-splitting contracts
- package version updated to `0.34.0`

### Fixed

- fixed Speech Blocks prompt placeholder mismatches for TTS budget and speaker
  catalog variables
- fixed null-like Speech Blocks runtime timestamps so review updates no longer
  create `log_ai_speech_blocks_None.log`
- removed unused legacy deterministic source-unit Speech Blocks helpers that
  only handled straight double quotes

## [0.33.5] - 2026-04-27

### Changed

- changed Character Voices state building so first page access synchronizes
  character preview text with the locked project voice language
- changed character voice prompt generation so every character prompt carries
  explicit sex/gender guidance, including neutral guidance when the source does
  not specify a character's sex or gender
- changed Character Discovery voice-definition prompts and profile
  normalization to preserve explicit sex/gender instructions for downstream
  voice generation
- changed cleanup, chunking, translation, and character-discovery resets to
  preserve existing Narator Voice profiles, selected narrator state, and
  selected narrator samples while still invalidating dependent character voice,
  speech, audio, and audiobook artifacts
- updated tests and documentation for localized preview text, explicit
  sex/gender voice prompts, and narrator-preserving upstream reruns
- package version updated to `0.33.5`

## [0.33.4] - 2026-04-27

### Changed

- changed Narator Voice profile listing to visually separate Qwen CustomVoice
  presets from custom profiles
- added live narrator preview-text budget feedback and expanded the existing
  Narator Voice Status area with runtime connection, active-model, and preview
  budget readiness lines
- aligned the Narator Voice Status window height and placement with the shared
  Cleanup Notes and AI Translation Notes layout reference
- increased the Narator Voice Preview Text editor height and reduced the Voice
  Designer Prompt height for better preview-text editing
- package version updated to `0.33.4`

## [0.33.3] - 2026-04-27

### Changed

- changed Narator Voice first-access behavior so narrator profile and selection
  metadata are initialized when the page is opened
- changed narrator sample playback labels to `Play sample` / `Stop play` and
  updated the runtime Romanian translations
- changed narrator sample generation to reject preview text that exceeds the
  runtime-derived TTS word budget before sending the generation request
- changed VoiceWeaver language-field handling so Romanian and languages not
  reported by the active runtime model are omitted from outbound sample
  generation payloads
- package version updated to `0.33.3`

## [0.33.2] - 2026-04-27

### Changed

- changed Character Discovery to use canonical source chunks as the
  authoritative discovery input so translated artifacts cannot reduce dialogue
  character recall or mix source and translated character names
- added language-agnostic dialogue-span evidence, evidence confidence,
  rejected-candidate diagnostics, identity-merge separation, resumable rerun
  internals, and persisted internal review-status metadata for character
  profiles
- updated character discovery prompts to preserve names, role labels, aliases,
  and evidence excerpts in the selected source text form while keeping the
  voice-definition prompt as the English TTS handoff
- updated Character Discovery tests and documentation for source-only
  discovery input, rejected-candidate reporting, and review-status metadata
- package version updated to `0.33.2`

## [0.33.1] - 2026-04-27

### Changed

- changed lazy Characters page state initialization so first access creates
  `characters_state.json` with explicit zero-valued character-discovery
  metadata counters without creating character outputs or reports
- changed manual character add, edit, and delete handling to preserve the
  current Characters output while clearing downstream narrator, character voice,
  speech block, audio block, and audio assembly artifacts and manifest summaries
- updated Character Discovery and project workspace documentation for the
  zero-metadata and downstream invalidation contracts
- updated focused tests for Characters metadata initialization, manual
  maintenance downstream resets, and current flat-project artifact names
- package version updated to `0.33.1`

## [0.33.0] - 2026-04-26

### Changed

- changed AI Translation completion semantics so fully translated chunks enter
  an approval-pending `translated` state and the operation is only completed
  after every translated chunk is approved
- changed translation metadata initialization so first page access creates
  operation metadata from existing chunking output without marking translation
  complete
- changed Reset Translation to clear translation runtime artifacts, downstream
  operation outputs, downstream operation metadata, and downstream manifest
  summaries
- changed translation edits, retranslations, and approval updates to refresh
  operation metadata and invalidate downstream workflow readiness when approval
  is lost
- updated AI Translation UI notes, reset warning text, focused tests, README,
  and software documentation for the approval-gated workflow
- package version updated to `0.33.0`

## [0.32.0] - 2026-04-26

### Added

- added `clean_text_metadata.json` cleanup metadata with stable paragraph IDs,
  source page provenance, page-break repair flags, boundary confidence, and
  warning flags for chunking diagnostics
- added metadata-aware deterministic and AI chunking so both modes prefer
  cleanup paragraph records while remaining compatible with legacy projects
  that only have `clean_text.txt`
- added cleanup UI notes and tests for language-agnostic page-break repair,
  metadata fallback, AI chunking paragraph IDs, cleanup reset, and manual
  cleaned-text edits

### Changed

- changed deterministic cleanup to repair uncertain PDF page-break continuations
  before flattening the canonical cleaned text, while avoiding joins into
  headings, page numbers, separators, or complete standalone paragraphs
- changed cleanup reruns and manual cleaned-text edits to clear stale downstream
  state and prevent stale cleanup metadata from driving later chunking
- changed Home-page Project ZIP export so active projects can be archived before
  workflow completion or project-option locking
- changed main-window project refresh to update only the active workflow page,
  preventing passive Audio Blocks and Audio Assembly artifact reads when those
  pages have not been opened
- updated cleanup and chunking documentation for the new metadata sidecar
  contract
- package version updated to `0.32.0`

## [0.31.0] - 2026-04-26

### Added

- added Home-page project option locking for target translation language and
  audio output style before the workflow starts
- added narrator-only Speech Blocks prompt support for `same_narrator` projects,
  using continuous narrator segments under the resolved TTS token budget
- added lazy default operation-state initialization so `<step>_state.json` files
  are created on first page open without creating reports or output artifacts
- added language-agnostic deterministic cleanup coverage for supported-language
  prose, including Unicode-aware chapter detection, script-aware paragraph
  continuation, expanded page-number cleanup, and dash-dialogue formatting
- added a richer AI-assisted cleanup prompt contract with source language and
  script hints, neighboring unit context, separate artifact/action fields, and
  model confidence values

### Changed

- changed new project initialization to create only `project.json`; page-specific
  metadata such as `audio_profiles.json`, `narator.json`, and
  `characters_voice.json` is now initialized only when the matching voice page
  is opened
- changed project activation to return to the Home page before refreshing state,
  preventing previously selected workflow pages from eagerly creating metadata
  for a new or newly opened project
- changed AI Translation to read the locked target language from `project.json`
  and pass through same-language projects without AI rewriting
- changed Speech Blocks prompt selection to use the dialogue/speaker splitter in
  narrator-plus-character mode and the narrator-only segmentation prompt in
  same-narrator mode
- changed Home workflow progress to hide the `Source Selected` row, leaving
  source state in Project Summary and starting the visible workflow at
  `Text Cleanup`
- changed deterministic cleanup to normalize repeated header/footer comparisons
  while preserving conservative text-removal behavior and the existing cleanup
  artifact contract
- changed AI-assisted cleanup to preserve low-confidence removal decisions for
  operator review while staying backward-compatible with legacy `label` output
- package version updated to `0.31.0`

### Fixed

- fixed Home-page layout overflow at large UI text sizes by tightening Project
  Summary spacing and allowing the page body to scroll when content exceeds the
  available height
- fixed Home source replacement before project start so selecting another source
  removes the previously imported source file and preserves the selected target
  language and audio output style
- fixed AI Translation page enablement so `Start Translation` is enabled and
  `Reset Translation` is disabled when no translation operation has completed
- fixed repeated Speech Blocks source-chunk errors during new-project page
  refresh before text chunking has run
- fixed Home workflow progress so active deterministic and AI chunking runs mark
  the Text Chunking row as in progress before the completion manifest refresh
- fixed Speech Blocks page-state refresh so earlier workflow pages no longer
  log translation-approval prerequisite errors during normal cleanup or
  chunking updates
- fixed Audio Blocks source-preview refresh so projects with unapproved
  translated chunks no longer log Speech Blocks prerequisite errors during
  passive page updates

## [0.30.0] - 2026-04-26

### Added

- added AI-first Speech Blocks source-span validation with warning flags for
  source coverage mismatches, source order mismatches, and model text changes
  beyond allowed dialogue delimiter cleanup
- added persisted `source_text` and `ai_source_text` traceability fields to
  Speech Blocks so operators can review the exact source span behind each audio
  text block
- added Speech Blocks test coverage for straight quotes, curly quotes, French
  guillemets, dash-led dialogue, invalid speakers, invalid source spans, and
  French multi-block generation flow

### Changed

- changed Speech Blocks generation so AI output owns the final block boundaries
  while deterministic code normalizes speakers, content kinds, delimiters, IDs,
  and warnings
- changed the Speech Blocks prompt contract to split full chunks directly and
  explicitly support quoted dialogue, French guillemets, and dash-led dialogue
- changed dialogue text cleanup to remove straight quote pairs, curly quote
  pairs, French guillemet pairs, or one leading dialogue dash without rewriting
  source wording
- updated Speech Blocks implementation and component documentation to describe
  the AI-first splitter, source-span validation, and persisted traceability
- package version updated to `0.30.0`

## [0.29.0] - 2026-04-25

### Added

- added artifact-backed project manifest healing during project load, with
  operator confirmation before writing normalized project metadata
- added Project ZIP export progress and cancellation through the shared
  operation progress dialog

### Changed

- package version updated to `0.29.0`
- changed the AI Settings default selector stack to show cleanup, chunking,
  chunking strategy, translation, character extraction, and speech blocks in
  workflow order
- changed Home-page Speech Blocks TXT/Markdown exports so each block renders the
  speaker display name on its own line above the spoken text, with Markdown hard
  line breaks preserving the two-line layout in previewers

### Fixed

- fixed repeated project-load repair prompts when only warning-only stale
  operation state remains after a successful metadata repair
- fixed Audio Assembly playback toggling so Stop halts active playback even
  after selecting another generated output, and Play starts from the selected
  output in multi-part compositions

## [0.28.0] - 2026-04-25

### Added

- added the Romanian offline end-user guide under `05_SoftwareDocu/UserGuide_ro/`,
  including Romanian UI screenshots and visible version plus creator information

### Changed

- changed the toolbar Help action to open Romanian help when the application UI
  language is Romanian, with English help fallback when localized help is missing
- bundled both English and Romanian offline help into Windows and Ubuntu release
  archives under `help/en/` and `help/ro/`

### Fixed

- fixed Character Voices prompt editing so downstream Audio Blocks invalidation
  no longer relocks the voice prompt or preview text editors
- fixed Character Voices language switching so choosing the approved translated
  language is preserved while downstream Speech Blocks and Audio Blocks are reset
- fixed Audio Blocks continuation for Romanian output so reusable clone prompts
  are matched and created with the reference sample language instead of the
  selected synthesis language

## [0.27.0] - 2026-04-25

### Added

- added the English offline end-user guide under `05_SoftwareDocu/UserGuide/`,
  including visible version plus creator information, expanded page-by-page
  operator instructions, HTML, and real UI screenshots
- bundled the user guide into Windows and Ubuntu release archives under
  `help/en/`

### Changed

- changed the toolbar Help action from a placeholder message to opening the
  packaged offline HTML user guide
- package version updated to `0.27.0`

### Fixed

- fixed selected narrator sample metadata so `narator.json` remains only the
  selected-profile state while `narator_sample.json` carries preview metadata
  for Audio Blocks and Character Voices, with fallback for existing projects

## [0.26.0] - 2026-04-25

### Added

- added the packaged AudioMancer application icon as PNG and multi-size Windows
  `.ico` assets
- wired the application icon into the Qt application and main window

### Changed

- package version updated to `0.26.0`

### Fixed

- improved Speech Blocks selected-chunk scroll restoration by restoring the
  preview scrollbar again on the next Qt event cycle after refresh

## [0.25.0] - 2026-04-25

### Added

- added manual Speech Blocks insertion and deletion on the Speech Blocks page,
  including chunk-local renumbering, automatic edit mode for inserted blocks,
  localized controls, and downstream Audio Blocks plus Audio Assembly reset
- added `Indication` as a Speech Blocks content kind; Audio Blocks stores it as
  metadata-only and skips VoiceWeaver generation for now
- added pause-duration parsing for Speech Blocks and Audio Blocks, with Audio
  Assembly converting metadata-only pause blocks into generated WAV silence
- added Home-page `Export Project ZIP` snapshots that archive the full active
  project folder to an external `.zip` destination and block while long-running
  operations are active

### Changed

- changed metadata-only Speech Blocks so pause, background-noise, and
  indication blocks persist and display their operation name instead of a
  narrator or character name
- package version updated to `0.25.0`

### Fixed

- preserved the selected chunk text scroll position after saving or resetting
  an edited Speech Block on the Speech Blocks page
- fixed split Audio Blocks generation so part WAV file names use chunk-local
  identity and no longer call the audio artifact stem helper with the old
  global-sequence argument list
- fixed Audio Blocks generation in same-narrator mode so character dialogue
  uses the selected narrator sample and reusable narrator clone prompt instead
  of requiring separate character samples

## [0.24.0] - 2026-04-25

### Changed

- changed Speech Blocks and Audio Blocks identity to chunk-local numbering:
  `speech_block_id` remains `CCCC-BBBBBB`, but `BBBBBB` now resets to
  `000001` for each source chunk
- changed Speech Blocks re-splitting so only the selected chunk's local
  sequence values and IDs are rebuilt, preparing later insert/delete work
- changed Audio Blocks generation, merge, approval, playback, and Audio
  Assembly ordering to use source chunk order plus chunk-local `sequence_index`
- changed generated Audio Blocks file stems to include both chunk order and
  chunk-local sequence, for example `0002_000001_alice.wav`
- package version updated to `0.24.0`

### Fixed

- stale legacy Speech Blocks or Audio Blocks artifacts that still contain
  global-sequence schema fields are now rejected and must be reset/regenerated
  instead of being silently normalized

## [0.23.0] - 2026-04-25

### Added

- added the implemented `Audio Assembly` workflow with WAV-only composition
  from approved Audio Blocks, per-project assembly settings, resumable
  state/report artifacts, generated `audiobook/` outputs, playback controls,
  localized UI text, and focused service/page/controller coverage
- documented the Audio Assembly control gating: generation is available only
  after all Audio Blocks exist and are approved, reset is available only after
  assembly artifacts exist, and playback is available only after output files
  are generated

### Fixed

- fixed Home workflow progress so Character Voices and later workflow rows are
  shown as finished when their ready stage has been reached, and unfinished
  downstream operation summaries are shown as in progress instead of not
  started

## [0.22.0] - 2026-04-25

### Changed

- changed Audio Blocks generation to run only for approved Speech Blocks, leaving
  unapproved blocks pending and keeping the operation `in_progress` until all
  blocks are generated and approved

### Fixed

- fixed Audio Blocks narrator validation when `narator.json` stores only the
  selected profile state by falling back to the selected narrator profile sample
  metadata for `preview_text`

## [0.21.0] - 2026-04-25

### Added

- added Qwen3 TTS target-language options for Japanese, Korean, Russian,
  Portuguese, Italian, plus Romanian while continuing to exclude Chinese
- added configurable narrator preview-text character limit with a default of
  512 characters and a TTS Settings control
- added always-visible scrollbars for narrator Voice Designer Prompt and
  Preview Text editors
- added per-profile narrator sample preservation so generated narrator profile
  audio can be previewed again without regenerating after switching profiles
- added code-style prologue cleanup for modified Python test files

### Changed

- flattened project runtime artifact storage so operation reports, state files,
  canonical text/JSON outputs, AI transaction logs, narrator samples, and
  character voice samples are written directly in the project root
- removed numbered workflow-folder creation and validation for new projects;
  existing numbered-layout projects are treated as unsupported legacy layouts
- renamed operation artifacts to the flat-layout names such as
  `extracted_text.txt`, `clean_text.txt`, `chunks_text.json`,
  `translated_text.json`, `characters_profile.json`, `audio_profiles.json`,
  `characters_voice.json`, `speech_blocks.json`, and `audio_blocks.json`
- changed reset behavior to delete only known root-level runtime artifacts and
  generated `audio_blocks/` content instead of clearing workflow directories
- changed Romanian Qwen3 TTS requests to omit the outbound language field so the
  runtime can infer pronunciation from the text
- changed Narrator Voice, Text Chunking, and TTS Settings page layouts for more
  compact operator-facing panels and clearer action spacing
- changed Narrator Voice edit mode so `Save Profile` is enabled immediately
- package version updated to `0.21.0`

### Fixed

- fixed narrator sample generation clearing previously generated samples for
  other narrator profiles
- fixed narrator sample lookup after profile renames by honoring the stored
  `sample_audio_path`

## [0.20.0] - 2026-04-25

### Added

- added a shared threaded modal-operation runner for long-running UI workflows, with `QThread`/`QObject` worker execution, Qt-signal progress delivery, and cooperative `threading.Event` cancellation
- added focused runner tests for success, failure, cancellation, active-operation guarding, and cleanup of thread/worker state
- added software documentation for the shared operation runner controller

### Changed

- changed modal long-running workflows to run service calls off the Qt UI thread while keeping progress dialogs, busy states, warnings, status messages, manifest refreshes, and page updates on the UI thread
- migrated text extraction, deterministic and AI cleanup, deterministic and AI chunking, AI translation and retranslation, Character Discovery, Speech Blocks, Audio Blocks, narrator sample generation, and character-voice sample generation to the shared threaded runner
- changed narrator and character voice sample generation so worker code uses explicit payloads and worker-safe runtime helpers instead of touching `MainWindow` or Qt widgets
- changed transient shell messages so they no longer create stale central tooltip popups or bottom status-bar UI
- changed AI chunking paragraph-window sizes to be shared `config.py` parameters instead of service-local hardcoded values
- changed the main shell to remove the bottom status bar and use a smaller default/minimum window size
- package version updated to `0.20.0`

### Fixed

- fixed the app appearing stuck or intermittently responsive during Character Discovery and other modal long operations by moving those operations out of the UI thread
- fixed modal operation progress/result callbacks so worker-thread signals are delivered through a UI-thread bridge before updating Qt widgets
- fixed selected narrator sample metadata so selected samples include `selected_profile_id`

## [0.19.1] - 2026-04-24

### Added

- added right-click `Find` and `Find Next` search actions to the `Characters` page evidence preview

## [0.19.0] - 2026-04-24

### Added

- added manual editing and saving for Text Cleanup cleaned-text output, with downstream workflow reset after saved edits
- added right-click `Find` and `Find Next` search actions to Text Cleanup extracted/cleaned previews and Text Chunking cleaned/chunk previews
- added manual editing and saving for the selected Text Chunking chunk, with persisted `20_chunking/output_chunks.json` updates

### Changed

- changed Text Cleanup and Text Chunking save refreshes to preserve relevant preview/list scroll positions after project-state reloads
- package version updated to `0.19.0`

### Fixed

- fixed Text Cleanup search not-found handling so translated messages are formatted after lookup instead of passing unsupported keyword arguments to the translation helper
- fixed Text Chunking selected-chunk edits so downstream workflow data is reset from translation onward while preserving the chunking artifact

## [0.18.1] - 2026-04-22

### Added

- added shared cleanup-text analysis helpers so deterministic and AI cleanup paths reuse one analysis implementation
- added shared VoiceWeaver runtime UI support helpers reused by the `Character Voices` and `Narator Voice` controllers

### Changed

- refactored operation runtime path resolution so read-only operation lookups no longer create workflow folders as a side effect
- improved AI backend and VoiceWeaver URL normalization and validation, including support for already-complete chat-completions endpoints
- changed AI transaction logging to append new entries instead of rewriting the full transaction-log payload on every write
- package version updated to `0.18.1`

### Fixed

- fixed OpenAI-compatible retry handling so permanent provider failures are no longer retried as transient request errors
- fixed AI Translation workflow progression so `character_discovery_ready` is reached only after all translated chunks are approved
- fixed duplicated cleanup-analysis and VoiceWeaver controller helper logic drifting independently by centralizing the shared behavior

## [0.18.0] - 2026-04-21

### Added

- added the implemented `Speech Blocks` workflow with persisted `70_speech_blocks` output, AI prompt templates, page/controller/state/service coverage, and software documentation
- added AI prompt guidance for recurring unnamed or role-based speakers so character discovery can include speakers such as agents, guards, or captains without language-specific deterministic scans

### Changed

- changed Speech Blocks generation to pre-split source chunks into quote and narration source units before AI speaker attribution, preserving text boundaries before model classification
- changed Speech Blocks speaker matching to accept unique suffix aliases such as `Drenthe` for `Ottmar Drenthe`
- package version updated to `0.18.0`

### Fixed

- fixed Speech Blocks boundary handling so dialogue attribution text such as `"Sure, absolutely," his agent said.` is split into separate dialogue and narrator blocks
- fixed missing narrator follow-up text after quoted dialogue, including cases like `"Different how?" Drenthe snapped.`

## [0.17.2] - 2026-04-21

### Added

- added explicit `Speech Blocks`, `Audio Blocks`, and `Audio Assembly` placeholder pages plus workflow folders `70_speech_blocks`, `80_audio_blocks`, and `90_audio_assembly`
- added repair coverage for missing support folders and downstream-stage preservation when older projects are opened after the workflow expansion

### Changed

- renamed the former `Narration Plan` implementation surface to `Character Voices`, including module filenames, tests, README references, software documentation, runtime translations, persisted folder names, and the stored target file name `voice_targets.json`
- changed project repair so missing downstream workflow folders now preserve the highest valid upstream stage instead of resetting older projects all the way back to `project_created`
- package version updated to `0.17.2`

### Fixed

- fixed stale Character Voices UI strings that still described the page as a narration plan after the rename
- fixed translation-stage gating for Character Voices so approved translated languages remain available through the new placeholder stages

## [0.17.1] - 2026-04-21

### Added

- added Windows and Ubuntu release packaging scripts that assemble self-contained zip archives under `07_Delivery/` with operating-system and version naming
- added release documentation for the packaging scripts and delivery-folder artifact contract

### Changed

- renamed the former narrator page surface to `Narator Voice`, including page id, page class, UI controller, translation keys, user-facing labels, tests, README references, and software documentation
- updated Narration Plan narrator-target labels and missing-sample guidance to point operators to the `Narator Voice` page
- changed packaging scripts to read the release version from `04_Software/AudioMancer/pyproject.toml` and to skip application test execution during package assembly
- package version updated to `0.17.1`

### Fixed

- fixed stale Narrator page references in application docs, component docs, focused UI tests, and narration-plan warnings after the page rename

## [0.17.0] - 2026-04-21

### Added

- added focused shared test fixtures and split the oversized main-window coverage into lifecycle, AI-profile, and project-flow modules
- added the complete `Narration Plan` workflow with narrator-plus-character target listing, explicit voice-language selection, deterministic character voice-prompt derivation, per-character sample persistence, same-narrator sample copy mode, and focused service/page/controller coverage
- added `60_narration_plan` project storage, the `narration_plan_ready` workflow stage, the narration-plan implementation plan in `0_Planning/`, and dedicated software documentation for the new page contract
- added structured Qwen-oriented character voice-definition fields, one persisted final `voice_definition_prompt`, and explicit `Regenerate Voice Definition` support on the `Characters` page so character voice design is authored upstream and handed off cleanly to `Narration Plan`

### Changed

- refactored AI cleanup and text-cleanup controller tests to remove repeated setup while preserving the covered scenarios
- updated workflow repair/reset handling, home-stage rendering, narrator-stage compatibility, and runtime UI translations so the new narration-plan step behaves as a first-class workflow page
- updated the application README and software-component documentation to describe narration-plan persistence, language-selection rules, and `same_narrator` behavior
- updated the Narration Plan page so each character now has a dedicated two-line preview-text editor, and the saved preview text is used during sample generation and stored in sample metadata for later voice-cloning workflows
- updated Character Discovery prompt templates and persisted character profiles so they now request, store, and preserve voice-design-ready Qwen brief fields and so Narration Plan prefers the character-owned `voice_definition_prompt` with legacy fallback only for older projects
- changed the new-project default `voice_assignment_mode` to `narrator_and_characters`, so separate narrator and character voices are now the default TTS plan
- package version reserved in changelog as `0.17.0`

### Fixed

- fixed narration-plan same-narrator sample synchronization so copied character samples always recreate the required `60_narration_plan/audio_samples` output folder before writing artifacts
- fixed Windows file-lock failures when Narration Plan or Narrator samples were previewed and then immediately edited or regenerated, by stopping playback and clearing the media source before deleting the old WAV

## [0.16.1] - 2026-04-11

### Added

- added focused shared test fixtures and split the oversized main-window coverage into lifecycle, AI-profile, and project-flow modules

### Changed

- refactored AI cleanup and text-cleanup controller tests to remove repeated setup while preserving the covered scenarios
- package version updated to `0.16.1`

### Fixed

## [0.16.0] - 2026-04-11

### Added

- added shared backend-agnostic token-usage normalization and cumulative merge helpers for OpenAI-compatible AI workflows
- added live AI token counters in the modal progress dialog plus persisted token-usage notes in cleanup, chunking, translation, and character-discovery page state
- added provider-service and workflow regression coverage for normalized usage extraction and persisted token summaries
- added `AudioMancer_LLM_Provider_Service.md` software documentation for the shared provider contract and token-usage behavior

### Changed

- changed the shared OpenAI-compatible provider contract so `chat_json(...)` now returns parsed payload data plus normalized `usage`
- changed AI cleanup, AI chunking, AI translation, and character discovery to accumulate provider-reported input, output, and total tokens in step-local reports, state files, and transaction logs
- package version updated to `0.16.0`

### Fixed

## [0.15.1] - 2026-04-11

### Added

### Changed

- added scoped ignore rules for `09_Others/Test*/` folders
- package version updated to `0.15.1`

### Fixed

## [0.15.0] - 2026-04-11

### Added

- added focused provider-service regression coverage for malformed backslash escapes, follow-up JSON repair requests, and parse-failure raw-content logging

### Changed

- hardened shared OpenAI-compatible provider parsing so malformed JSON responses can be repaired conservatively, with one follow-up JSON-repair request when the original assistant content is not parseable
- expanded provider transaction logging to retain raw assistant message content for JSON parse failures and repair attempts
- package version updated to `0.15.0`

### Fixed

- fixed AI translation and other AI workflows aborting on some malformed model JSON outputs that contained invalid backslash escapes or otherwise broken JSON formatting

## [0.14.0] - 2026-04-11

### Added

- added focused regression coverage for compact `project.json` operation summaries and for deterministic chunking with compact cleanup manifests

### Changed

- reduced the root `project.json` contract to compact per-operation summaries instead of duplicating detailed operation payloads already stored in workflow-local files
- updated workspace, cleanup, chunking, translation, and character-discovery synchronization paths so detailed state remains authoritative in step-local `state_operation.json`, report, and output artifacts
- updated workflow prerequisite checks to read canonical step-local artifacts instead of relying on manifest `output_paths`
- package version updated to `0.14.0`

### Fixed

- fixed root-manifest growth caused by duplicated nested operation metadata such as translated chunks, warning details, and chunk-boundary internals

## [0.13.1] - 2026-04-11

### Added

- added focused provider-service regression coverage for OpenAI-compatible compatibility fallback when one API rejects `max_tokens` and requires `max_completion_tokens`

### Changed

- updated OpenAI-compatible provider requests so local backends still receive the original `max_tokens` chat-completions payload while remote APIs can retry once with `max_completion_tokens` after an explicit compatibility rejection
- updated the application README and AI cleanup component documentation to describe the new mixed local-plus-OpenAI compatibility behavior
- package version updated to `0.13.1`

### Fixed

- fixed OpenAI API compatibility for newer models that reject `max_tokens` in `/v1/chat/completions` requests, while preserving the existing local-provider behavior

## [0.13.0] - 2026-04-08

### Added

- added explicit manual character maintenance in the `Characters` page with `Add Character`, `Edit Character`, `Save Character`, and `Delete Character` actions, synthetic evidence for manual entries, and guarded unsaved-change prompts
- added focused regression coverage for the guarded character manual-edit workflow across the character page, controller, state service, and persistence service

### Changed

- changed character profiles to be read-only by default and require explicit edit mode before any field changes can be saved
- updated the character-discovery README and component documentation to describe the explicit save flow, manual profile management, and current discovery artifact naming
- restored the callable-level Doxygen headers and local `@version` tags in the touched character-discovery page, controller, and service modules for repository documentation compliance
- package version updated to `0.13.0`

### Fixed

- fixed character manual-edit persistence so added and deleted profiles keep the discovery operation `character_count` metadata synchronized
- fixed character page selection handling so switching characters during an unsaved add or edit draft now prompts to save, discard, or cancel instead of silently losing changes

## [0.12.0] - 2026-04-08

### Added

- added the complete AI-assisted character-discovery workflow with canonical `40_character_discovery` artifacts, resumable state, editable discovered profiles, source-evidence preview, prompt templates, and focused service/controller/page coverage
- added dedicated character-discovery software documentation and README updates for the new workflow

### Changed

- centralized workflow folder names in `config.py` and updated the affected runtime, workspace, cleanup-state, chunking, translation, and character-discovery services to consume the shared definitions instead of hardcoded folder strings
- translation and character-discovery input snapshots now preserve the imported source-document base name in `input_<book_name>` style artifact files
- package version updated to `0.12.0`

### Fixed

- fixed downstream reset-stage handling so clearing character discovery returns the project to `translation_ready` instead of falling back to an earlier stage
- fixed translation and character-discovery runtime path handling so persisted operation metadata stays aligned with the configured workflow folder names

## [0.11.1] - 2026-04-08

### Added

- added focused regression coverage for persisted default AI translation profile selection in the settings and translation-state services

### Changed

- the `AI Settings` dialog now loads, saves, and localizes a dedicated default translation profile selection alongside the existing cleanup, chunking, and character-extraction defaults
- package version updated to `0.11.1`

### Fixed

- fixed AI Translation profile selection so it prefers the persisted default translation profile instead of always falling back to the first enabled profile

## [0.11.0] - 2026-04-07

### Added

- added the complete AI-assisted translation workflow with canonical `30_translation` artifacts, resumable operation state, editable translated chunks, per-chunk retranslation, manual approval controls, and focused service/controller/page coverage

### Changed

- refined the Text Cleanup, Text Chunking, and AI Translation page layouts so note panels stay anchored at the bottom and the main text preview/edit areas use more of the vertical workspace
- increased the AI Translation chunk-list height so at least three chunk rows remain visible in the review workflow
- expanded the left navigation sidebar to better use the full shell height
- normalized the new AI Translation service, state-service, controller, and page modules to the repository Doxygen/comment style
- package version updated to `0.11.0`

### Fixed

- removed the remaining implicit bottom status bar recreation by changing shell messages to avoid `QStatusBar` creation

## [0.10.0] - 2026-04-07

### Added

- added AI-assisted text chunking with canonical `20_chunking` outputs, resumable state, AI prompts, transaction logging, and focused service/controller/page coverage
- added focused regression coverage for AI cleanup reliability and chunking-note state handling

### Changed

- hardened AI-assisted cleanup to split long requests into smaller windows, validate risky `page_number` and `separator` labels conservatively, and persist operator-visible warning details
- updated chunking-page notes so active AI-assisted chunking shows an in-progress note instead of a misleading ready note
- added Doxygen-style constant descriptions across the touched services and UI modules for documentation consistency
- package version updated to `0.10.0`

### Fixed

- fixed AI-assisted cleanup so suspicious late-window label drift no longer silently removes valid story text without warning

## [0.9.0] - 2026-04-07

### Added

- added a complete deterministic Text Chunking workflow with dedicated runtime state, resumable progress, output artifacts, and one-chunk-per-paragraph processing
- added a dedicated Text Chunking UI controller plus main-window wiring for start, resume, rerun confirmation, downstream reset handling, and manifest synchronization
- added focused tests for deterministic chunking service behavior, chunking page behavior, chunking controller behavior, and main-window integration

### Changed

- upgraded the `Text Chunking` page to render cleaned-text preview, chunk list, selected chunk preview, localized notes, and deterministic action state
- updated the chunking header layout so the `Deterministic Chunking` button appears before the AI-related controls
- package version updated to `0.9.0`

### Fixed

## [0.8.0] - 2026-04-06

### Added

- added AI-assisted cleanup from the `Text Cleanup` page using the selected enabled AI profile from `AI Settings`
- added prompt-template loading from the app-root `prompts/` folder plus OpenAI-compatible provider requests, JSON normalization, retry handling, and per-run AI transaction logs in `10_cleanup`
- added focused tests and software documentation for AI cleanup, prompt loading, and provider-request handling

### Changed

- the `Text Cleanup` page now keeps the AI profile selector active by default and refreshes it from saved AI Settings profiles
- AI-assisted cleanup now supports resumable cleanup state, shared progress-popup integration, and canonical cleanup artifacts in the existing `10_cleanup` workflow folder
- package version updated to `0.8.0`

### Fixed

- fixed AI-assisted cleanup cancel handling so the progress popup remains responsive while waiting for model responses
- fixed AI-assisted cleanup line-healing so more soft wraps and page-split continuations are merged back into one sentence

## [0.7.0] - 2026-04-06

### Added

- added deterministic text cleanup with project-local `10_cleanup` artifacts, resumable state, and cleanup output/report generation
- added focused cleanup, page-controller, presenter-service, and runtime-reset test coverage plus matching software documentation updates

### Changed

- simplified and reused the modal progress flow for extraction and cleanup operations
- improved extraction progress granularity for `pdf`, `rtf`, and `epub` processing so long-running work advances in visible steps
- refactored the application shell toward page-oriented UI controllers and related presenter/state services
- improved cleanup heuristics to better remove separator noise, preserve dialogue structure, and keep paragraph/newline structure more faithfully
- package version updated to `0.7.0`

### Fixed

- fixed workflow progress so `text_chunking_ready` no longer marks `Text Chunking` as already completed

## 0.6.0 - 2026-04-06

- added deterministic text extraction from the `Text Cleanup` page with project-local `00_extraction` artifacts and resumable `state_operation.json`
- added support for `.txt`, `.pdf`, `.rtf`, `.docx`, `.odt`, `.md`, and `.epub` text extraction using copied operation-local inputs
- changed extraction manifest persistence to store extracted-text/report paths, warning counts, and per-step `operations` state in `project.json`
- added destructive extraction rerun confirmation, downstream-folder reset behavior, and workflow-progress updates that mark `Text Cleanup` as in progress after extraction starts
- fixed RTF validation to reject misnamed legacy `.doc` containers instead of generating corrupted output
- added extraction-service, cleanup-page, main-window, and config/workspace test coverage plus component documentation for the extraction workflow

## 0.5.0 - 2026-04-06

- added source-file import from the Home page and locked the project to one imported source
- changed `project.json` to persist structured `source_document` metadata
- added support for `.txt`, `.pdf`, `.rtf`, `.docx`, `.odt`, `.md`, and `.epub` source import
- added import-service coverage and main-window/workspace tests for source locking and manifest persistence
- updated project workspace documentation and README to reflect the new import workflow

## [0.4.1] - 2026-04-06

### Added

### Changed

- refactored `audiomancer.services.ai_backend_service` to use fully functional dictionary payloads instead of dataclass-based result objects
- updated the AI settings page, main-window connect popup flow, and focused AI tests to consume the new functional probe-result contract
- package version updated to `0.4.1`

### Fixed

## [0.4.0] - 2026-04-06

### Added

- added the first persisted project-workspace flow for `AudioMancer` with `New Project` and `Open Project` support
- added cross-platform exact project-name validation for Windows and Linux folder rules
- added a minimal root-level `project.json` contract and a dedicated functional `project_workspace_service`
- added focused tests for project creation, project open, repair handling, and the project-aware main-window shell
- added `05_SoftwareDocu/AudioMancer_Project_Workspace.md` for the new project-workspace component

### Changed

- the main window now enables workflow pages only after one project is created or opened
- the Home / Project workflow-progress list is now driven from `config.PROJECT_WORKFLOW_STAGES` and displays rows as `Step | Progress`
- replaced the earlier custom new-project dialog with a simpler 2-popup flow using one folder picker and one name-input popup
- removed the thin project controller layer and kept the project workflow direct and functional from `main_window.py` to `project_workspace_service.py`
- refactored project manifest handling to validated dictionary payloads instead of a manifest class
- package version updated to `0.4.0`

### Fixed

- fixed project open so recoverable corruption now offers a repair confirmation instead of failing generically
- fixed project repair so the corrupted step and all downstream step folders are recreated/reset and the manifest stage is repaired consistently
- fixed repaired-project workflow progress so empty downstream steps do not appear completed after repair

## [0.3.3] - 2026-04-05

### Added

- added Windows and Linux release packaging scripts (`package_windows_release.ps1`, `package_linux_release.sh`) and entrypoint/spec helpers under `02_Tools/`
- added VS Code workspace configuration (`2026_Audiomancer.code-workspace`)

### Changed

- removed legacy build scripts (`build_linux.sh`, `build_windows.ps1`, and `02_Tools/AudioMancer/README.MD`) in favor of the new packaging flow
- updated tool, software, documentation, and delivery READMEs to reflect the new packaging structure
- refreshed `settings.json` and `uv.lock` to stay in sync with the current dependency set
- updated `05_SoftwareDocu/AudioMancer_App_Shell.md` to match the current application state
- package version updated to `0.3.3`

### Fixed

## [0.3.2] - 2026-04-05

### Added

### Changed

- added the missing callable-level Doxygen-style docstrings across the recent AI settings, localization, startup, logging, and main-window test changes so the codebase matches the repository documentation rules
- updated the affected Python module `@version` tags for the documentation-compliance pass
- package version updated to `0.3.2`

### Fixed

- fixed the remaining `AGENTS.md` and `Code_Style.md` compliance gaps for file and function documentation in the recently changed Python files

## [0.3.1] - 2026-04-05

### Added

- added `audiomancer.services.ai_backend_service` with normalized backend probing and model-discovery support for `lmstudio`, `ollama`, and `openai_compatible` AI profiles
- added focused automated coverage for backend probing, discovered-model normalization, AI Settings profile discovery updates, and translated connect popup feedback

### Changed

- the `AI Settings` dialog now supports real `Connect` probing, discovered-model refresh, popup feedback with discovered-model counts, and persisted discovery state for saved profiles
- AI backend probing now uses a dedicated short connect timeout from `config.py` instead of the longer workflow request timeout
- refined the `AI Settings` layout by removing the inline connect-status message, aligning the default-profile selectors with the main form rows, and moving `Structured output supported` under `Temperature`
- completed the connect-result translation path so localized popup messages no longer mix English success text into Romanian UI sessions
- updated application and shell documentation to describe the functional AI Settings connect flow
- package version updated to `0.3.1`

### Fixed

- fixed the AI Settings connect popup so operator-facing success feedback is fully translated for the active UI language

## [0.3.0] - 2026-04-05

### Added

- added `ui_state_service` as a dedicated runtime UI-state component for applying persisted UI language and text-size changes
- added focused test coverage for runtime UI translation lookup, text-scale application, and translated About-dialog license loading
- added Romanian app-root companion license files for the About dialog: `LICENSE_ro.txt` and `LICENSE_NC_ro.txt`
- added a repository rule requiring every operator-facing UI text change to update the translation mechanism in the same change

### Changed

- `Settings` save now applies the selected UI language and text-size immediately across the running shell instead of waiting for restart
- extended runtime English/Romanian translation coverage across the main toolbar, sidebar, status bar, settings dialogs, and current page shell labels
- updated the Home / Project page layout so the source-selection button sits in the project summary block and the workflow-progress area regains vertical space at large UI text sizes
- the About dialog now loads localized license text based on the current UI language, with fallback to the English license files when no localized pair exists
- `ui_state_service` now emits backend-service logging for translation and runtime UI-apply actions
- updated software and shell documentation to describe runtime UI apply behavior and localized license assets
- package version updated to `0.3.0`

### Fixed

- fixed the Home / Project page so the workflow-progress panel fits better at the maximum interface text size

## [0.2.0] - 2026-04-05

### Added

- added real save/load integration for the `Settings` and `AI Settings` dialogs through the shared settings service
- added focused page tests for `Settings` and `AI Settings` load/build behavior plus dialog-integration coverage in the main window

### Changed

- `Settings` and `AI Settings` now reload persisted values when opened, discard unsaved edits on cancel, and save merged settings back into the shared `settings.json` payload
- expanded the persisted settings schema to include AI default cleanup, chunking, and character-extraction profile selections alongside the simplified operator-facing settings
- updated startup so the main window receives the validated settings payload at bootstrap and keeps one in-memory source of truth for dialog coordination
- updated shell documentation to describe the now-wired settings persistence flow
- package version updated to `0.2.0`

### Fixed

## [0.1.13] - 2026-04-05

### Added

- added a static `Settings` dialog with language, interface text size, completion-beep, and save/cancel controls
- extended focused UI and settings-service coverage for the simplified settings dialog and reduced persisted settings schema

### Changed

- replaced the `Settings` placeholder dialog with the new presentational settings dialog and wired `Cancel` to close the dialog shell
- simplified the `Settings` dialog by removing unused provider, project-root, notification, and recent-project controls and aligning the remaining selectors on one row
- reduced the persisted settings schema and implementation to keep only the active operator-facing fields still used by the project
- updated shell documentation to describe the simplified settings dialog and settings payload
- package version updated to `0.1.13`

### Fixed

## [0.1.12] - 2026-04-05

### Added

- added a static `AI Settings` dialog with AI profile listing, provider configuration fields, default-profile selectors, and save/cancel actions
- extended the focused UI test to verify the cloned AI Settings controls are present in the main shell

### Changed

- replaced the `AI Settings` placeholder dialog with the new presentational cloned dialog
- refined the AI Settings layout by moving `Connect` beside `Backend Kind`, moving profile add/remove controls below the profile list, aligning the default-profile selectors with the main form rows, and centering the bottom actions
- updated the AI Settings form labels and control widths for closer visual fit, and wired the `Cancel` button to close the dialog shell
- updated shell documentation to describe the cloned AI Settings dialog
- package version updated to `0.1.12`

### Fixed

## [0.1.11] - 2026-04-05

### Added

- added a static `Narrator` page with a profile list, narrator-language selector, prompt-based profile editor, preview text area, and profile-management actions
- extended the focused UI test to verify the narrator profile-management controls are present in the main shell

### Changed

- replaced the earlier simple narrator placeholder with a fuller operator-facing narrator profile manager
- simplified the narrator page by removing delivery-direction, linked-role, model-source, and technical voice-source selectors so the UI stays focused on profile management only
- updated shell documentation to describe the narrator profile manager layout
- package version updated to `0.1.11`

### Fixed

## [0.1.10] - 2026-04-05

### Added

- added a static `Characters` page with discovery controls, character list, editable profile form, and evidence panels
- extended the focused UI test to verify the cloned characters controls are present in the main shell

### Changed

- replaced the `Characters` placeholder page in the application shell with the new presentational page
- reduced the static `Character Profile` panel height so the page fits the window better
- package version updated to `0.1.10`

### Fixed

## [0.1.9] - 2026-04-05

### Added

- added a static `AI Translation` page with target-language selection, translation-profile selection, chunk list, progress display, source/translation editors, and review action layout
- extended the focused UI test to verify the cloned translation controls are present in the main shell

### Changed

- replaced the `AI Translation` placeholder page in the application shell with the new presentational page
- reduced the static `Chunk List` section height on the AI Translation page by about 20 percent for closer visual fit
- repository validation guidance now prefers `uv run ...` for Python validation and tests in `04_Software/AudioMancer/`
- package version updated to `0.1.9`

### Fixed

## [0.1.8] - 2026-04-05

### Added

- added a static `Text Chunking` page with deterministic chunking, AI chunking, cleaned-text reference, chunk list, selected-chunk preview, and notes layout
- extended the focused UI test to verify the cloned chunking controls are present in the main shell

### Changed

- replaced the `Text Chunking` placeholder page in the application shell with the new presentational page
- package version updated to `0.1.8`

### Fixed

## [0.1.7] - 2026-04-05

### Added

- added a static `Text Cleanup` page with extraction, deterministic cleanup, AI cleanup, preview, and notes layout
- added focused UI-test coverage to verify the cloned cleanup controls are present in the main shell

### Changed

- replaced the `Text Cleanup` placeholder page in the application shell with the new presentational page
- package version updated to `0.1.7`

### Fixed

## [0.1.6] - 2026-04-05

### Added

- added a real About dialog with a scrollable read-only license text area
- added app-root `LICENSE.txt` and `LICENSE_NC.txt` files for About dialog display and delivery packaging
- added focused test coverage for the About dialog license content and updated subtitle/layout expectations

### Changed

- narrowed the About dialog, increased the `@2026` mark size, centered the `Ok` button, and updated the subtitle to `Transform written words into real audio experience!`
- changed the About dialog license source to the `04_Software/AudioMancer/` app root so delivered builds can keep the license files beside the application
- updated application and shell documentation to describe the About dialog and app-root license-file placement
- package version updated to `0.1.6`

### Fixed

## [0.1.5] - 2026-04-05

### Added

- added the main-window shell structure for `AudioMancer` with a toolbar, navigation sidebar, stacked pages, status bar, and placeholder dialogs
- added presentational UI support modules for navigation, status display, the home/project page, generic placeholder pages, and a new static narrator page
- inserted a `Narrator` workflow page between `Characters` and `Narration Plan` with profile selection, description entry, preview controls, and a reserved blank workspace area

### Changed

- replaced the earlier custom placeholder main window with the current `AudioMancer` application shell
- adjusted the Home / Project workflow-progress panel sizing and default empty project-stage text to better match the intended initial state and layout
- removed UI logging from the main window in line with the rule that logging is reserved for backend implementation only
- updated package, test, and shell documentation to describe the copied UI structure
- package version updated to `0.1.5`

### Fixed

## [0.1.4] - 2026-04-04

### Added

- shared `settings_service` for `settings.json` creation, loading, validation, self-healing, saving, and startup integration
- focused tests for settings lifecycle behavior and a dedicated `05_SoftwareDocu/AudioMancer_Settings_Service.md` component document

### Changed

- settings defaults now start with no seeded LLM profiles and no selected LLM profile-id fields
- settings validation now emits more detailed repair/load/save lifecycle logs and uses decorator-based trace logging on the public settings-service API
- package version updated to `0.1.4`

### Fixed

## [0.1.3] - 2026-04-04

### Added

- dedicated `05_SoftwareDocu/AudioMancer_Logging_Service.md` component documentation for the runtime logging service
- repo-local Codex skill under `.codex/skills/write-component-documentation/` for creating and updating `05_SoftwareDocu/` component documents using the repository template and established style

### Changed

- `05_SoftwareDocu/README.md` now lists the logging service document
- package version updated to `0.1.3`

### Fixed

## [0.1.2] - 2026-04-04

### Added

- shared runtime logging service for the AudioMancer desktop app with per-run log files, component loggers, and optional decorator tracing
- focused tests for logging initialization, cleanup, structured output, and trace logging

### Changed

- app bootstrap now initializes logging at startup and shuts it down on exit or bootstrap failure
- main window initialization now emits a component log message
- software and application documentation now describe the logging service behavior and configuration ownership
- package version updated to `0.1.2`

### Fixed

- repository ignore rules now exclude generated runtime logs under `04_Software/AudioMancer/Logs/`

## [0.1.1] - 2026-04-04

### Added

- adapted `config.py` baseline and configuration/settings component documentation
- focused configuration contract test for the config and settings scaffold
- adapted the `settings.json` baseline for the local application scaffold

### Changed

- application scaffold documentation and tests to reflect the preserved config/settings contract
- main window setup to use the shared configuration values for title and dimensions
- callable Doxygen docstrings to match the stricter repository documentation format

### Fixed

- `pyproject.toml` encoding so `uv sync --extra dev` parses and resolves correctly

## [0.1.0] - 2026-04-04

### Added

- initial repository scaffold with planning, documentation, tools, software, delivery, and support folders
- repository rules in `AGENTS.md` and code/documentation style guidance in `01_Documentation/Code_Style.md`
- initial planning overview for the `AudioMancer` desktop application
- Python 3.12 application scaffold under `04_Software/AudioMancer/`
- `uv`-based environment and dependency setup
- minimal `PySide6` desktop app shell with package entrypoints and focused tests
- packaging placeholders for future `PyInstaller`-based build flow
- setup documentation for repository bootstrap and dependency installation

### Changed

### Fixed
