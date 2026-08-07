<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed

- Resuming Character Discovery now keeps characters added or edited after an
  interruption through later checkpoints, cancellation, provider failure, and
  completion. Manual characters no longer make synthesis skip discovered
  candidates, and deleting an already generated character while interrupted no
  longer causes it to reappear or moves the resume point backward.
- Re-selecting a project's existing source file no longer creates a duplicate
  copy or clears completed work. Changing the app language now keeps the source
  status truthful, and export or snapshot names such as `Dune vol. 2` retain
  their full name when AudioMancer adds `.txt`, `.md`, or `.zip`.
- Cleanup now blocks alphanumeric word fusion introduced across rendered source
  spans, including joins exposed by dropped page artifacts, while keeping valid
  dehyphenation unchanged. Whitespace-only manual edits now retain source,
  page, confidence, reason, and warning provenance only for uniquely matched
  paragraphs; merged, split, duplicate, unmatched, and unprovenanced paragraphs
  are marked unavailable instead of inheriting document-wide source IDs.
- EPUB extraction now ignores hidden HTML content without losing visible text
  after it. Cleanup also warns, without stopping the workflow, when it detects
  a source language outside its supported English, Romanian, German, French,
  Russian, Portuguese, Spanish, and Italian set.
- Resumed AI Cleanup now continues from the exact number of completed provider
  requests instead of counting every answered question as a request. Saved
  batch membership now matches the requests actually run across mixed question
  types, split requests expand the displayed total truthfully, and malformed
  Cleanup checkpoints restart safely instead of leaking internal errors.
- AI providers that return an empty, refused, or reasoning-only response no
  longer trigger a second JSON-repair request, and compatible multipart text
  remains usable. Token totals are now recovered when providers report valid
  input/output counts without a total, provider-specific request fallbacks stay
  active across retries, and transient retries use short cancellation-aware
  backoff instead of firing immediately.
- Failed or cancelled one-chunk AI retranslation attempts now keep the current
  translated text, approvals, and completed downstream availability while
  retaining any token usage already spent. Fresh translation passes now honor
  newly entered rules, resumes keep their stored rules, and one-off chunk rules
  no longer affect later translation runs.
- AI Translation review now keeps the active chunk, editing cursor, selection,
  undo history, scroll position, and selected enabled AI profile through normal
  refreshes. Start/Resume saves the latest pending edit before its worker runs,
  and Re-Translate Selected stays unavailable until translation has started.
- AI Settings now keeps every unsaved profile edit when switching, adding, or
  removing profiles. Connect preserves the last successful model/context
  discovery after a temporary failure, discovers exact-model context limits
  from compatible providers, respects manually entered context values, and
  reports interrupted response reads as normal connection failures.
- Running Cleanup again after completion now truly starts a fresh pass after
  confirmation, removing the old Cleanup and later workflow results instead of
  silently returning the previously completed result. Interrupted Cleanup runs
  remain resumable.
- Unsaved manual Cleanup edits now survive ordinary refreshes and cannot be
  replaced by conflicting Cleanup controls. Switching to a different project
  asks before discarding a changed draft, and cancelling the project picker
  keeps the draft intact.
- PDF import no longer duplicates narrow centered lines such as page numbers,
  footers, or scene ornaments while reconstructing two-column reading order.
  Sparse and unusably sized pages now also keep the same single-column identity
  as other pages, avoiding false page-transition decisions during Cleanup.
- Project creation, source import, and confirmed project repair now keep the
  current Home state intact when the filesystem rejects the operation. The
  existing localized project-error warning shows the original reason instead
  of letting the error escape the UI or reporting a false success.
- Text Extraction now distinguishes Central European, Western European, and
  cp1251 Russian text without first-success mojibake, honors RTF code-page
  declarations, and decodes each EPUB spine document from its BOM or XML/HTML
  charset declaration. Mixed-encoding EPUBs are reported truthfully in the
  source ledger, and a bad declaration identifies the responsible chapter.
- Running Cleanup again or saving a manual cleaned-text correction now resets
  Text Chunking and every later workflow result consistently. Reopening the
  project no longer asks to repair stale completed summaries for files that
  Cleanup already removed.

## [2.0.0] - 2026-07-30

### Added

- New **Narration Block Target (s)** setting under TTS Settings → Runtime Audio
  Limits. It sets the preferred spoken length of one same-narrator block. The
  TTS model budget stays the hard limit, so the setting can only make blocks
  shorter, never longer than the runtime can generate. Leave it at
  *Automatic (model limit)* to keep the previous behaviour.

- The **Play completion beep** setting now does something. It was persisted and
  editable in Settings but had no runtime consumer, so the checkbox was inert.
  A long operation that ends on its own now plays one beep, whether it succeeded
  or failed, so an operator who stepped away is told the run is over. An
  operation the operator cancels stays silent.
- New internal **PCM Codec** component providing the linear PCM conversions
  Audio Assembly and Scene Mix need — sample-width, mono/stereo, and stateful
  sample-rate conversion for 1/2/3/4-byte samples — using only the Python
  standard library, with no third-party dependency.

### Changed

- **Speech Blocks in same-narrator mode is now split deterministically and no
  longer calls the AI model.** Because every block gets the narrator voice, the
  only decision left was where to put the boundaries — a structural question the
  model was being paid to guess at, and often got wrong by cutting mid-sentence.
  Blocks are now packed from whole sentences, sized evenly rather than filled to
  the ceiling, and a quotation spanning several sentences is kept in one block.
  The result is reproducible, instant, and costs no tokens. A sentence too long
  for the TTS budget is kept whole and flagged; TTS Audio Blocks already splits
  it at generation time against the real model budget.
  *Projects mid-run in same-narrator mode restart their Speech Blocks from the
  first chunk, because mixing two segmentations in one document is not safe.
  Existing WAVs are not deleted, but blocks are renumbered, so previously
  generated audio for that project is regenerated.*
- Speech Blocks now carries the Text Cleanup boundary verdict through to the
  operator. A paragraph that cleanup rebuilt across a page break produces blocks
  flagged `weak_source_boundary` / `needs_review` instead of silently discarding
  that uncertainty, which is the case where a sentence split by a page separator
  can still be wrong.
- Same-narrator generation no longer requires an enabled AI profile unless Scene
  Ambience is switched on.

- Audio Assembly no longer accepts 8-bit PCM WAV sources; supported sample
  widths are now 2, 3 and 4 bytes. 8-bit was listed as supported while every
  code path treated it as signed, so gaps and pauses in an 8-bit render would
  have been written as a DC offset rather than silence. The TTS pipeline emits
  16-bit, so no produced audio changes.
- Each run's log file name now includes the process id. Two instances started
  within the same second previously resolved to the same path and, because the
  handler opens with `mode="w"`, the second truncated the first run's log.

- Audio Assembly and Scene Mix no longer depend on the `audioop` standard-library
  module, which was **removed in Python 3.13**. PCM conversion now runs through
  the internal codec. Produced audio is unchanged: the codec reproduces every
  former `audioop` result byte for byte, including the resampler's carry-over
  state across chunk boundaries, verified by a differential test suite that
  compares it against the real `audioop` on Python 3.12 and skips automatically
  on newer interpreters.
- Supported Python interpreters widened from `>=3.12,<3.13` to `>=3.12,<3.14`.
  The full suite passes on both 3.12 (1076 passed) and 3.13 (1015 passed, with
  the 61 `audioop` comparison tests skipped). Python 3.14 stays excluded pending
  its own validation.
- Removed dead duplicates of the shared operation handlers from the Text
  Chunking and Text Cleanup controllers. Nine unreferenced functions went; each
  controller keeps only its cancellation handler, which does manifest work the
  shared runner does not.

### Fixed

- The **Scene Ambience Audio** selector on the Audio Blocks page now follows the
  Scene Ambience Placement setting: it starts **on** whenever TTS Settings asks
  for ambience blocks, and off when placement is *None*. It was reading a
  settings key that had been deprecated and is stripped on every save, so it was
  permanently off no matter what TTS Settings said. It stays a per-run override,
  so it can still be switched off without changing settings.
- Clicking the **Model Name** field in AI Settings now drops down the discovered
  models. The field is editable, and an editable combo box only opens from its
  small arrow, so clicking the text looked like the models found at the endpoint
  were simply not there. Typing a model name the endpoint does not advertise
  still works.
- **AI Settings** now remembers the models discovered at the endpoint. The list
  lived only in memory, so after a restart the Model Name selector offered three
  built-in placeholder names — which a given endpoint may not serve at all —
  while hiding the models that were actually available. A profile that has never
  been probed still shows the built-in suggestions.
- The AI Settings form no longer stretches sideways when an endpoint reports a
  long model identifier. The selector demanded room for its longest entry, so
  the dialog width depended on which models happened to be discovered; the full
  names are still shown in the dropdown list.
- The narration block target and Scene Ambience seed controls in TTS Settings no
  longer clip their text.

- Audio generation no longer crashes with `_persist_split_checkpoint() got
  multiple values for argument 'next_generation_order_index'` partway through a
  run. A block too long for the loaded TTS model is generated in parts, and the
  call that saves progress after each part still passed two arguments that the
  single-document refactor had removed from it. Only long blocks reach that
  path, which is why short-block runs finished normally.

- The sentence-boundary detector used for Speech Blocks segmentation had been
  saved through a double character-encoding at some point, so its punctuation
  set was garbage. `…` had stopped ending a sentence, the CJK and Arabic marks it
  was supposed to contain were gone entirely, and stray letters including the
  Romanian `â` had become sentence terminators. Sentence-aware splitting works
  correctly again in every supported language.
- Sentences in Chinese and Japanese are now detected at all. `。` is written
  flush against the next sentence, and the detector required a following space,
  so an entire CJK paragraph was treated as one sentence.
- The fallback TTS budget used before the VoiceWeaver runtime has been probed was
  2048 codec tokens, but VoiceWeaver caps voice-clone models at 512. AudioMancer
  was planning roughly 139 seconds of speech per block for a model that can
  generate about 42, so blocks were silently truncated. The fallback now matches
  the clone cap, and the split safety factor sits below VoiceWeaver's own
  warning threshold instead of exactly on it.
- Audio Blocks kept its own hardcoded copies of the split safety factor and
  speech-rate constants, so it did not follow the configured values and could
  disagree with the budget Speech Blocks had planned against.
- Text budgeting no longer assumes every language separates words with spaces.
  Chinese, Japanese and Korean are now sized by a per-script character rate;
  previously their blocks were estimated as a handful of "words" and came out
  several times too long.

- Opening a finished project no longer offers **Repair Project** on every open.
  Persisting an operation summary could move `current_stage` backwards while the
  downstream operations stayed `completed`, leaving `project.json` contradicting
  itself; the stage is the highest milestone a project has reached, so it is now
  only ever promoted. A project already carrying the inconsistency needs the
  repair accepted once, after which it stops recurring.
- AudioMancer no longer fails to start when installed into a directory the
  running user cannot write to, such as `C:\Program Files\AudioMancer` on Windows
  or a system-wide prefix on Linux. `settings.json` and the `Logs/` directory
  were both derived from the application root, so creating them failed; because
  logging is initialized before the bootstrap error handler, that failure crashed
  startup with a bare traceback and no log file to diagnose it from. Writable
  data now resolves to a per-user location — `%LOCALAPPDATA%\AudioMancer`,
  `$XDG_DATA_HOME/AudioMancer` or `~/.local/share/AudioMancer`, or
  `~/Library/Application Support/AudioMancer` — whenever the application root
  cannot accept writes. Existing installations are unaffected: a writable
  application root keeps settings and logs exactly where they are, so running
  from source or from a portable folder behaves as before. Set
  `AUDIOMANCER_DATA_DIR` to pin the location explicitly.
- On first run at a new per-user location, settings are seeded from the packaged
  `settings.json` beside the executable, so an installation that is converted to
  the per-user layout keeps its existing configuration instead of resetting to
  defaults. The packaged file is only ever read.
- Logging initialization can no longer abort startup. When the log file cannot be
  created the application keeps running with console output only and records one
  `logging-degraded` warning naming the path and the underlying error. Expired-log
  cleanup likewise no longer propagates filesystem errors.
- The **New project** and **Open project** folder pickers no longer start in the
  application install directory when no project is open. They now start in the
  operator's documents folder, falling back to the home directory. For a build
  installed into `C:\Program Files\AudioMancer`, `/opt`, or `/usr/share`, the
  browser previously opened inside a read-only system directory where any
  project the operator tried to create there failed to write. While a project is
  open both dialogs still start from it, unchanged.

### Known Limitations

- The internal codec is a per-sample Python loop rather than a C extension, so
  conversion is roughly 90-210x slower than `audioop` was: about 0.04s of CPU per
  second of audio resampled. This only affects sources whose WAV parameters
  differ from the target; when parameters already match, frames are copied
  without touching the codec.
- The writable data location is resolved once when the application starts, so
  changing `AUDIOMANCER_DATA_DIR`, or the writability of the application root,
  requires a restart to take effect.
- The project open/create dialogs still offer the application root as their
  default browse directory, which is a poor starting point on a system-wide
  install even though it no longer causes a write failure.

## [1.7.0] - 2026-07-25

### Added

- Two AudioMancer brand themes derived from the product hero art —
  **AudioMancer Dark** (deep teal with a gold accent, now the default) and
  **AudioMancer Parchment** (warm light) — alongside the existing built-in themes.
- Global, theme-independent font-size steps with seven levels (Extra small →
  Huge), applied independently to the interface controls and to the text-editor
  windows, both adjustable from Settings.
- The Home dashboard now shows a horizontal workflow pipeline stepper with
  per-stage status (done / in progress / pending) and a serif project title.
- The navigation sidebar now shows a per-page icon, an "AudioMancer" wordmark,
  and a gold accent on the active page; each entry carries its full label as a
  tooltip so long labels stay readable.
- Workflow pages and the Settings, AI Settings, and TTS Settings dialogs are
  wrapped in scroll areas so content stays reachable at large font sizes or the
  minimum window resolution.

### Changed

- Settings was simplified into an **Appearance** panel: choose a built-in theme
  and set the interface and text-window font sizes, with a live preview. The
  default UI theme is now AudioMancer Dark.
- The theme stylesheet was refined across the app: rounded card group boxes,
  rounded controls, gold-accented buttons and active states, themed scrollbars
  and combo/menu popups, and accent-coloured progress bars. Top toolbar labels
  are now legible on dark themes.
- Characters demographic fields (Gender/Age Hint and Confidence) now align to
  the same width as the other Character Profile fields instead of overflowing
  the panel at the default window size.
- Speech Blocks source selection now matches Character Discovery: once the AI
  translation is complete and every chunk is approved, Speech Blocks uses the
  translated (repair-normalized) text as its source regardless of the selected
  Character Voices language; otherwise it uses the original chunking text.
  Selecting a translated voice language no longer raises when the translation is
  absent or only partially approved — it falls back to the original text.
- Speech Blocks now persists a single authoritative `speech_blocks.json`
  document (fixed top-level field set: status, source, ai_profile_id,
  instructions, scene_ambience, response_contract, token_usage,
  budget_metadata, checkpoint, failure, blocks). The separate
  `speech_blocks_report.json` and `speech_blocks_state.json` artifacts are no
  longer written; the legacy report and operation-state shapes are
  compatibility projections recomputed from the single document, so
  `load_speech_blocks_report()` and `load_operation_state()` keep their
  signatures. The artifact no longer stores a copy of the source-chunk text
  (only `source.fingerprint`); source chunks are re-resolved from upstream.
  **Breaking (persistence):** existing projects with the old Speech Blocks
  artifacts read as not-started and must re-run Speech Blocks; reset now clears
  the single document and any residual legacy report/state files.

- Text Extraction now persists exactly `extracted_text.txt` and the strict
  authoritative `extraction_metadata.json` document. Status, progress,
  warnings, PDF page count, and final text statistics are read from that
  document, including rerun/resume and Text Cleanup availability decisions.
- Extraction reset and project-open repair now reject legacy or mixed
  extraction artifacts and destructively clear Extraction plus downstream
  outputs while preserving the imported source document.
- Narrator Voice now persists its complete strict metadata contract in
  `narrator_voice.json`; selection stores only the profile ID and downstream
  services resolve the selected profile-owned WAV at read time.
- AI narrator profile generation now checkpoints resume state atomically in the
  authoritative document and appends validated profiles only on success.
- Narrator export, project recovery, snapshots, reset, and preservation now use
  the authoritative document, canonical `audio_narator_<profile_id>.wav`
  samples, and the actual narrator AI log pattern.

### Removed

- Removed the Settings colour/custom-theme editor, the per-theme font-family and
  font-size controls, and theme import/export. Appearance is now the curated
  built-in themes plus the interface/text font-size steps.
- Removed the deprecated global `ui_text_scale` setting; existing values are
  migrated into the new interface/text font-size steps.
- Removed `extraction_report.json`, `extraction_state.json`,
  `extraction_warning_count`, and `operations.extraction` from active
  persistence contracts. Legacy sidecar names remain reset-only and are not
  migrated or used as fallback data.
- Removed the fragmented narrator profile, selection, selected-sample,
  generation-report, and generation-state contracts. No compatibility reader,
  automatic migration, or selected-sample copy remains.

## [1.6.7] - 2026-07-16

### Changed

- AI Chunking now requests ordered absolute-paragraph chunk descriptors and
  validates their structure, range, and source anchors before committing them.
- Start-anchor validation now accepts five consecutive normalized matching
  words, while keeping short paragraph anchors fully matched and all descriptor
  ordering checks strict.
- Project package metadata, `audiomancer.__version__`, the lockfile, release
  smoke test, and offline English and Romanian help bundles were updated to
  `1.6.7`.

### Fixed

- AI Chunking no longer discards otherwise valid model boundaries merely
  because a copied start anchor is shorter than eight words or differs only in
  harmless casing, punctuation, whitespace, or Unicode compatibility form.

## [1.6.6] - 2026-07-16

### Changed

- Project package metadata, `audiomancer.__version__`, the lockfile, and the
  release-version smoke test were updated to `1.6.6`.
- Offline English and Romanian help bundles were updated to version `1.6.6`.

### Fixed

- AI Cleanup now accepts provider-modified Story text when unique normalized
  edge anchors identify exactly one original source span, while keeping exact
  matching mandatory for non-Story blocks.
- AI Cleanup now preserves source text omitted between uniquely bounded exact
  response blocks instead of repeatedly failing with an unexplained source-gap
  error; ambiguous, leading, and trailing omissions still fail closed.
- Compatible partial AI Cleanup checkpoints now resume from the first
  unprocessed canonical source offset when model budget changes repartition
  request windows, avoiding reprocessing of already validated text.

## [1.6.5] - 2026-07-15

### Added

- Added independently selectable `Heading`, `Separator`, `Noise`, `Header`,
  and `Footer` newline-spacing controls beneath Cleaned Text Preview. Operators
  can apply one or multiple categories without another AI provider request;
  `Story` remains exact and is never selectable.

### Changed

- AI Cleanup now retains validated exact-source block decisions so spacing can
  be reapplied deterministically, with `Heading` and `Separator` selected by
  default.
- Project package metadata, `audiomancer.__version__`, the lockfile, and the
  release-version smoke test were updated to `1.6.5`.
- Offline English and Romanian help bundles were updated to version `1.6.5`
  and document the selectable AI Cleanup spacing workflow.

### Fixed

- Deselecting every spacing category now removes all controllable inter-block
  blank lines while preserving exact Story text and source order.
- Cancelling the optional AI Cleanup instructions prompt no longer leaves the
  AI-assisted cleanup button disabled.
- Cleaned-preview spacing controls now occupy exactly two rows, with Edit and
  Save vertically aligned at the right for a usable desktop layout.

## [1.6.4] - 2026-07-08

### Changed

- Project package metadata and `audiomancer.__version__` were updated to
  `1.6.4`.
- Offline English and Romanian help bundles were updated to version `1.6.4`.

### Fixed

- Audio Assembly final composition now chooses output WAV parameters from the
  first non-Scene-Ambience source WAV when one exists, preventing a leading
  stereo 44.1 kHz Scene Ambience bed from upsampling the whole audiobook and
  pushing large whole-book WAV output toward the classic RIFF size limit.

## [1.6.3] - 2026-07-07

### Changed

- Replaced narrator-and-character Speech Blocks generation with the direct LLM
  block contract: models now return ordered `text`, `speaker_id`,
  `content_kind`, `confidence`, and `warning_flags` blocks, while AudioMancer
  aligns returned text back to the source before persistence.
- Speech Blocks generation now saves segment-level progress and resumes from
  the next unfinished segment, while old atomic/source-span checkpoints restart
  instead of being migrated.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.6.3`.
- Offline English and Romanian help bundles were updated to version `1.6.3`.

### Fixed

- Malformed or unusable narrator-and-character Speech Blocks responses now
  fall back only the failed segment as narrator `needs_review` text, instead of
  collapsing an entire chunk to one narrator block.
- Direct Speech Blocks normalization now preserves source gaps as reviewable
  narrator blocks and rejects unmatched model-invented text as trusted
  audiobook content.

### Changed

- Synced the embedded agentic workflow integration with the latest template,
  adding Intent Alignment, adoption-stage support, OpenCode default-agent
  routing, Qwen Code adapter support, updated workflow docs, and adapter parity
  tests while preserving AudioMancer-specific gates and documentation paths.

## [1.6.2] - 2026-07-03

### Changed

- Removed the unused Character Voices AI Profile selector and its page-state
  wiring; character sample generation continues to use the configured
  VoiceWeaver/Qwen TTS runtime.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.6.2`.
- Offline English and Romanian help bundles were updated to version `1.6.2`.

## [1.6.1] - 2026-07-03

### Changed

- Narrator profile generation prompt and component documentation now describe
  the `15..24` spoken-word preview target with bounded tolerance up to 30
  estimated words, keeping validation language-agnostic and provider-agnostic.
- Project package metadata and `audiomancer.__version__` were updated to
  `1.6.1`.
- Offline English and Romanian help bundles were updated to version `1.6.1`.

### Fixed

- AI-assisted Narator Voice profile generation now accepts compact single-line
  preview text with a bounded word-count overage, preventing near-valid narrator
  suggestions from failing only because they are one or a few words over the
  prompt target.

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
