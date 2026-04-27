<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# AudioMancer Application

This folder contains the current Python application implementation for
`AudioMancer`. It includes a project-aware main-window shell copied from
`DDP_Audiomancer` and adapted to the local package.

## Structure

- `pyproject.toml` defines the package metadata and dependencies.
- `settings.json` provides the current persisted app-settings scaffold.
- `src/audiomancer/` contains the Python package.
- `src/audiomancer/config.py` defines the current developer-owned defaults and root-level runtime artifact file names.
- `src/audiomancer/assets/icons/` stores the packaged AudioMancer application icon source PNG and Windows `.ico`.
- the toolbar `Help` action opens the packaged offline HTML user guide for the current UI language, with source content maintained under `../../05_SoftwareDocu/UserGuide/` and `../../05_SoftwareDocu/UserGuide_ro/`.
- `src/audiomancer/services/logging_service.py` provides per-run app logging and optional trace helpers.
- `src/audiomancer/services/settings_service.py` provides load, validate, self-heal, and save behavior for `settings.json`.
- `src/audiomancer/services/ai_backend_service.py` provides backend probe and model-discovery helpers for AI provider profiles.
- `src/audiomancer/services/project_workspace_service.py` provides new/open project creation, flat-layout validation, manifest persistence, and Home-page locking for `target_language`, mirrored `selected_voice_language`, and `voice_assignment_mode`.
- `src/audiomancer/services/import_service.py` provides source-file validation, copy-into-project behavior, and source metadata creation.
- `src/audiomancer/services/text_extraction_service.py` provides deterministic raw-text extraction, self-contained extraction artifacts, resumable extraction state, and cancelable progress updates.
- `src/audiomancer/services/deterministic_cleanup_service.py` provides deterministic cleanup, cleanup artifacts, page-break-aware paragraph metadata, and resumable cleanup state.
- `src/audiomancer/services/cleanup_metadata_service.py` provides cleaned-text paragraph metadata persistence and fallback record loading for chunking.
- `src/audiomancer/services/deterministic_chunking_service.py` provides deterministic chunking, chunk artifacts, and resumable chunking state.
- `src/audiomancer/services/ai_cleanup_service.py` provides AI-assisted cleanup, resumable AI cleanup state, and operation-local AI transaction logging.
- `src/audiomancer/services/cleanup_text_analysis_service.py` provides shared chapter detection, language detection, and dialogue formatting used by both cleanup pipelines.
- `src/audiomancer/services/ai_translation_service.py` provides AI-assisted translation, translated chunk review records, and resumable translation state.
- `src/audiomancer/services/character_discovery_service.py` provides AI-assisted character discovery, resumable character-profile synthesis, persisted Qwen-oriented voice-definition brief fields plus one final `voice_definition_prompt` with explicit sex/gender guidance, and root-level discovery artifacts.
- `src/audiomancer/services/narrator_definition_service.py` provides project-local narrator profile persistence, explicit selected-narrator state, locked selected voice-language helpers, localized narrator preview text, and root-level narrator sample storage with metadata recorded in `audio_profiles.json`.
- `src/audiomancer/services/character_voices_service.py` provides project-local Character Voices target persistence, character-owned voice-prompt handoff from `Characters` with mandatory sex/gender guidance and legacy fallback derivation, localized per-character preview text, root-level per-character sample storage, and same-narrator sample-copy helpers.
- `src/audiomancer/services/voiceweaver_runtime_service.py` provides VoiceWeaver runtime probing, normalized REST endpoint wrappers that tolerate operator-entered `/v1` bases, capability-matrix derivation, model-load or unload helpers, direct clone-generation helpers for the documented `/v1/voice/clone` contract, generation status polling, and generated-audio download helpers for TTS Settings, narrator sample generation, and Audio Blocks.
- `src/audiomancer/services/token_usage_service.py` provides shared normalization and cumulative merge helpers for provider-reported token usage.
- `src/audiomancer/services/tts_budget_service.py` resolves conservative TTS text budgets from cached VoiceWeaver discovered-model metadata for narrator-only Speech Blocks prompting and validation.
- `src/audiomancer/services/text_chunking_state_service.py` provides Text Chunking page state shaping plus persisted chunk preview loading.
- `src/audiomancer/services/ai_translation_state_service.py` provides AI Translation page state shaping plus persisted translated chunk and review loading.
- `src/audiomancer/services/character_discovery_state_service.py` provides Characters page state shaping plus persisted discovery profile and evidence loading.
- `src/audiomancer/services/narrator_definition_state_service.py` provides Narator Voice page state shaping plus persisted narrator profile and selection loading, locked voice-language display, and localized preview text.
- `src/audiomancer/services/character_voices_state_service.py` provides Character Voices page state shaping plus a read-only selected voice-language indicator, narrator-plus-character target ordering, and sample-status loading.
- `src/audiomancer/services/speech_blocks_service.py` provides mode-aware AI-first speech-block generation, source-language resolution from the locked project voice language, source-span validation for quoted/guillemet/dash dialogue, narrator-only TTS-budget segmentation for same-narrator projects, approval-gated review state, selected-block editing/reset, manual insert/delete with chunk-local renumbering, selected-chunk re-splitting, continuous `CCCC-BBBBBB` ID rebuilds, and root-level Speech Blocks artifacts.
- `src/audiomancer/services/speech_blocks_state_service.py` provides Speech Blocks page state shaping plus persisted block, report, approval-count, speaker-catalog, content-kind, and resumable note loading.
- `src/audiomancer/services/audio_blocks_service.py` provides resumable Audio Blocks reusable clone-prompt preparation, selected narrator sample metadata from `narator_sample.json` with selected-profile fallback for older projects, same-narrator voice assignment for all spoken blocks when configured, preferred `Qwen3-TTS-12Hz-1.7B-Base` clone-model selection when available, ordered approved-speech-block WAV generation in `audio_blocks/`, metadata-only handling for `Pause`, `Background Noise`, and `Indication`, selective upstream invalidation/remapping, approval updates, regeneration, and root-level Audio Blocks reports/state.
- `src/audiomancer/services/audio_blocks_state_service.py` provides Audio Blocks page state shaping plus persisted generated-block, report, and resumable note loading.
- `src/audiomancer/services/audio_assembly_service.py` provides final WAV audiobook composition from approved Audio Blocks, metadata-only pause-to-silence composition, per-project assembly settings persistence, root-level state/report artifacts, completed-output resume, and generated deliverables under `audiobook/`.
- `src/audiomancer/services/audio_assembly_state_service.py` provides Audio Assembly page state shaping plus persisted generated-output, progress, status, and readiness loading.
- `src/audiomancer/services/llm_provider_service.py` provides OpenAI-compatible chat-completion requests, transient-only retry handling, conservative malformed-JSON repair, responsive cooperative cancellation during model waits, normalized token-usage extraction, append-only AI transaction logging, and endpoint normalization for complete or base-only chat URLs.
- `src/audiomancer/services/prompt_template_service.py` provides strict prompt loading and placeholder rendering from the app-root `prompts/` folder.
- `src/audiomancer/services/operation_runtime_service.py` provides shared runtime helpers for root-level operation artifacts, side-effect-free read-path resolution, known-artifact resets, narrator-definition preservation during upstream reruns, and progress conversion.
- `src/audiomancer/services/home_presenter_service.py` provides pure manifest-to-view shaping for the Home page workflow progress and source summary.
- Home workflow progress now combines `project.json.current_stage` with persisted operation summaries so reached ready stages and unfinished downstream operations are displayed consistently.
- `src/audiomancer/services/project_export_service.py` provides Home-page export readiness and UTF-8 TXT/Markdown document projections for cleaned text, text chunks, AI translations, character dossiers, and Speech Blocks without registering deliverables in `project.json`; Speech Blocks exports render the speaker name on its own line above the spoken text, and AI-generated exports include the persisted model request parameters from the operation-local transaction log without exporting prompts or API-key-like values.
- `src/audiomancer/services/project_snapshot_service.py` provides complete external ZIP snapshots of active project folders, including root-level artifacts, generated audio, reports, state files, logs, and final outputs under one archive top-level project folder.
- `src/audiomancer/services/text_cleanup_state_service.py` provides Text Cleanup page state shaping plus extraction/cleanup manifest reset helpers.
- `src/audiomancer/ui/` provides the copied toolbar, sidebar, page, and status-bar shell used by the first desktop window.
- `src/audiomancer/ui/controllers/` provides page/window-oriented Qt controllers for Home, Text Cleanup, Settings, AI Settings, and shared shell UI helpers.
- `src/audiomancer/ui/controllers/operation_runner_controller.py` provides the shared `QThread`/`QObject` runner used by modal long-running workflows so service calls execute off the Qt UI thread while progress, cancellation, busy state, and final UI refreshes remain on the UI thread.
- `src/audiomancer/ui/controllers/` now also includes a dedicated Text Chunking page controller for deterministic chunking actions and rerun/reset handling.
- `src/audiomancer/ui/controllers/characters_ui_controller.py` provides the Character Discovery page controller for start, resume, reset, guarded manual add/edit/save/delete actions, and explicit unsaved-change handling.
- `src/audiomancer/ui/controllers/narator_voice_ui_controller.py` provides the Narator Voice page controller for inspected-vs-selected profile handling, destructive edit confirmation, locked voice-language display, Qwen3-backed VoiceWeaver sample generation with one configurable preview timeout, load-then-poll runtime sequencing before generation, explicit narrator selection, and local WAV preview playback.
- `src/audiomancer/ui/controllers/character_voices_ui_controller.py` provides the Character Voices page controller for target inspection, destructive character prompt edits, Qwen3-backed character sample generation, and local narrator-or-character preview playback.
- `src/audiomancer/ui/controllers/tts_runtime_ui_support.py` provides shared runtime-probe, timeout, and status-cache helpers reused by the Narator Voice and Character Voices controllers.
- `src/audiomancer/ui/controllers/speech_blocks_ui_controller.py` provides the Speech Blocks page controller for prerequisite validation, confirmation popups, explicit resets, approve-all, selected-block edits/resets, selected-chunk re-splitting, modal progress handling, cancellation, downstream Audio Blocks reconciliation, and manifest synchronization.
- `src/audiomancer/ui/controllers/audio_blocks_ui_controller.py` provides the Audio Blocks page controller for VoiceWeaver runtime probing, generation confirmations, modal progress handling, per-block approvals, rerun or reset behavior, manifest synchronization, and upstream invalidation resets.
- `src/audiomancer/ui/controllers/audio_assembly_ui_controller.py` provides the Audio Assembly page controller for settings persistence, long-running composition confirmation, modal progress handling, generated-output playback with double-click restart plus seek/skip controls, reset behavior, and manifest synchronization.
- `src/audiomancer/ui/controllers/tts_settings_ui_controller.py` provides the TTS Settings dialog controller for VoiceWeaver connection tests plus persistence for runtime cache fields and preview/generation timeouts.
- `src/audiomancer/ui/operation_progress_dialog.py` provides the reusable modal progress popup created on demand for threaded long-running operations.
- `prompts/` stores AI prompt templates loaded by AI-assisted cleanup, translation, character discovery, Speech Blocks generation, and future AI workflows.
- the main toolbar now supports `New Project` and `Open Project`.
- new projects create only one project root plus `project.json`; runtime workflow artifacts are stored directly in that root.
- the runtime artifact subfolders are `audio_blocks/` for generated Audio Blocks media and `audiobook/` for final Audio Assembly WAV deliverables.
- opening a project now expects the project root; numbered workflow-folder projects are treated as unsupported legacy layouts and are not migrated.
- `project.json` now keeps only compact workflow summaries under `operations`, while detailed runtime state remains authoritative in operation-specific root files such as `extraction_state.json`, `cleanup_state.json`, `chunking_state.json`, and related report/output artifacts.
- the Home page now stacks `Translation language`, `Audio output style`, `Select Source File`, `Start Project`, and `Export Project ZIP` on the right side of Project Summary; it lets the operator select the source file before Start Project, then locks the source, target language, and narration mode together before ZIP export, storing `project_options_locked`, `target_language`, mirrored `selected_voice_language`, and `voice_assignment_mode` in `project.json`.
- the Home page `Select Source File` action imports one source file into the project root before Start Project, stores structured source metadata in `project.json`, and allows replacement until Start Project; selecting another file deletes the previous imported source copy first.
- the Home page now places Workflow Progress on the left as one read-only row box per operation stage after source selection and a compact `Exports` panel on the right with export controls aligned to their matching workflow rows; the panel enables Cleaned Text, Text Chunks, AI Translation, Characters, and Speech Blocks export buttons only when the matching completed operation has a usable artifact, and exports are saved through an external save-file dialog as UTF-8 `.txt` or `.md` files outside the active project root.
- the Home page Project Summary now includes `Export Project ZIP`, which writes a complete ZIP snapshot to a user-selected external path, blocks destinations inside the project root, and stays disabled while long-running workflow operations are active.
- supported source import formats are `.txt`, `.pdf`, `.rtf`, `.docx`, `.odt`, `.md`, and `.epub`.
- the `Text Cleanup` page now runs deterministic text extraction for the imported source and writes root-level extraction artifacts.
- the `Text Cleanup` page now also runs deterministic cleanup into root-level cleanup artifacts, using conservative script-aware cleanup after extraction so supported-language prose is handled more consistently across Latin, Cyrillic, CJK, and Korean text.
- the `Text Cleanup` page now also supports AI-assisted cleanup using the selected enabled AI profile from `AI Settings`.
- AI-assisted cleanup now splits long inputs into smaller request windows, includes source-language, script, and neighboring-unit context in the prompt, accepts separate artifact/action/confidence result fields with legacy-label compatibility, validates risky page-number and separator labels conservatively, and surfaces review warnings when the AI result looks suspicious.
- the `Text Chunking` page now runs deterministic chunking into root-level chunking artifacts, renders the current chunk list plus selected chunk preview, and resumes interrupted deterministic chunking runs.
- the `Text Chunking` page now also supports AI-assisted chunking using the selected enabled AI profile plus the selected semantic strategy.
- the `AI Translation` page now translates canonical chunks into the locked project target language, displays original and target language indicators instead of a selector, creates a completed pass-through translation state when source and target languages match, preserves per-chunk review state in root-level translation artifacts, treats generated-but-unapproved translations as approval-pending, resets downstream character/speech/audio data when approved translation text changes while preserving existing Narator Voice profiles and samples, and advances the workflow to `character_discovery_ready` only after every translated chunk is approved.
- the `Characters` page now discovers speaking characters from canonical chunking output, persists editable character profiles in root-level character-discovery artifacts, generates and stores one structured Qwen-oriented voice-definition brief plus one final `voice_definition_prompt` per character, supports explicit `Regenerate Voice Definition`, supports resumable AI runs, and shows source-evidence previews with right-click Find and Find Next actions for each discovered character.
- the `Speech Blocks` page now consumes the locked project voice language and narration mode, resolves either canonical chunking text or approved translated text, sends one AI request per chunk, uses the dialogue/speaker prompt for narrator-plus-character projects, uses the narrator-only TTS-budget prompt for same-narrator projects, persists AI-owned ordered speech blocks with exact `source_text` traceability, validates source coverage/order and model text edits, deterministically splits oversized non-operation AI blocks against the safe TTS budget, supports straight quotes, curly quotes, French guillemets, and dash-led dialogue, shows a top chunk list plus selected chunk preview and selected-block editor, supports manual insert/delete inside the selected chunk, disables generation and enables reset after all chunks have generated Speech Blocks, resets downstream Audio Blocks and Audio Assembly after full generation/reset, resets only the affected chunk's generated audio after selected-block changes, supports cancellation plus continuation from saved state, and advances the manifest/home workflow to completed `speech_blocks_ready` only after all generated blocks are approved.
- extraction artifacts currently use `extracted_text.txt`, `extraction_report.json`, and `extraction_state.json`; the original imported source remains the input instead of an operation-local snapshot.
- cleanup artifacts currently use `clean_text.txt`, `clean_text_metadata.json`, `cleanup_report.json`, `cleanup_state.json`, and `log_ai_cleanup_<timestamp>.log` for AI cleanup; deterministic cleanup is format-independent after text extraction and is strongest when extraction preserved page boundaries.
- deterministic and AI chunking prefer `clean_text_metadata.json` paragraph records when present, then fall back to blank-line splitting of `clean_text.txt` for older projects.
- chunking artifacts currently use `chunks_text.json`, `chunking_report.json`, `chunking_state.json`, and `log_ai_chunking_<timestamp>.log`, with deterministic and AI-assisted chunking updating the same canonical chunk output.
- translation artifacts currently use `translated_text.json`, `translation_report.json`, `translation_state.json`, and `log_ai_translation_<timestamp>.log`, while leaving the canonical chunking output unchanged.
- character-discovery artifacts currently use `characters_profile.json`, `characters_report.json`, `characters_state.json`, and `log_ai_characters_<timestamp>.log`.
- Narator Voice artifacts currently use `audio_profiles.json`, `audio_narator_<normalized_profile>.wav`, selected narrator state in `narator.json`, selected narrator sample audio in `narator.wav`, and selected narrator sample metadata in `narator_sample.json`.
- Character Voices artifacts currently use `characters_voice.json` and root-level `audio_<normalized_character_name>.wav` files; the selected voice language is stored in `project.json.selected_voice_language` and mirrored from the Home-locked `project.json.target_language`.
- Speech Blocks artifacts currently use `speech_blocks.json`, `speech_blocks_report.json`, `speech_blocks_state.json`, and one per-run `log_ai_speech_blocks_<timestamp>.log`; persisted speech block IDs use `CCCC-BBBBBB`, such as `0001-000001`, with AI-extracted baseline source span, speaker, type, and text stored beside the current editable values.
- pressing `Extract Text` after a completed extraction now asks for confirmation before clearing extraction data and all downstream runtime artifacts.
- pressing `Deterministic Cleanup` after a completed cleanup now asks for confirmation before clearing cleanup data plus chunking and all following runtime artifacts except existing Narator Voice profiles and samples.
- pressing `AI-Assisted Cleanup` now first warns that AI operations can take longer, then asks for confirmation before clearing completed cleanup data plus chunking and all following runtime artifacts except existing Narator Voice profiles and samples when a rerun is required.
- pressing `Deterministic Chunking` after a completed chunking run now asks for confirmation before clearing chunking data plus all following runtime artifacts.
- pressing `Extract Text` after an unfinished extraction now continues from saved state when possible, or restarts safely from the copied extraction input snapshot.
- pressing `Deterministic Cleanup` after an unfinished cleanup now continues from saved state when possible.
- pressing `AI-Assisted Cleanup` after an unfinished AI cleanup now resumes from the saved cleanup checkpoint and AI transaction log.
- pressing `Deterministic Chunking` after an unfinished chunking run now resumes from the saved chunking checkpoint.
- pressing `AI-Assisted Chunking` after an unfinished AI chunking run now resumes from the saved chunking checkpoint and AI transaction log.
- pressing `Start Translation` after an unfinished translation run now continues from the persisted translated chunk state and translates only the remaining chunks.
- pressing `Reset Translation` now asks for confirmation and clears known translation artifacts plus downstream character, character-voice, speech, audio, and audiobook outputs while preserving existing Narator Voice profiles and samples; the target language remains the locked project target.
- pressing selected-row approval in AI Translation, Speech Blocks, or Audio Blocks now moves the corresponding review list to the next row when one exists and keeps the last row selected at the end.
- pressing `Start Discovery` now shows one first-run information popup for long AI work, resumes interrupted discovery when possible, and stays disabled after successful completion until reset.
- pressing `Reset Discovery` now clears known character-discovery artifacts plus downstream character-voice, speech, audio, and audiobook data without extra confirmation, preserves existing Narator Voice profiles and samples, and returns the workflow to `translation_ready`.
- discovered character profiles are now read-only by default, require explicit `Edit Character` before changes, and are saved only when `Save Character` is pressed.
- the `Characters` page now also supports `Add Character` and `Delete Character`, guarded unsaved-change prompts, and one synthetic manual-evidence note for manually added profiles.
- changing the selected voice language is no longer part of the normal project workflow; the audiobook language is fixed by Home-page project locking.
- long-running modal workflows now run through one reusable threaded operation runner and modal progress dialog, keeping the Qt UI thread available for repainting, progress updates, and cancel clicks while the worker service call runs on a `QThread`.
- AI-assisted cleanup and the other migrated long workflows keep the progress popup responsive while waiting for provider or VoiceWeaver responses, so the cancel button is recorded immediately and honored at cooperative cancellation checkpoints.
- OpenAI-compatible provider requests now retry automatically with `max_completion_tokens` when one remote API rejects `max_tokens`, while preserving the original payload shape for local providers that still expect `max_tokens`.
- OpenAI-compatible provider requests now also retain raw assistant message content in the AI transaction log, append new transaction records without rewriting the existing log, avoid retrying permanent HTTP failures, and can issue one follow-up JSON-repair request when a model returns malformed JSON text.
- AI-assisted cleanup, AI-assisted chunking, AI translation, and character discovery now accumulate provider-reported input, output, and total tokens when the backend exposes a standard `usage` object.
- the shared modal progress dialog now shows live token counters for AI workflows and falls back to one localized “not reported by the backend” message when usage is unavailable.
- AI workflow reports, operation-specific state files, transaction logs, and page notes now persist or display normalized token usage without copying those counters into the compact root `project.json`.
- project names are stored exactly as entered but are rejected when invalid for Windows or Linux folder creation.
- the `Settings` dialog now loads and saves `language`, `interface text size`, and `play completion beep` through the shared settings service.
- saving `Settings` now applies the selected UI language and global text size to the running shell.
- the current shell supports runtime English/Romanian UI switching through one centralized UI-state service.
- the `AI Settings` dialog now loads and saves AI profiles plus the default cleanup, chunking, translation, Speech Blocks, and character-extraction selections through the shared settings service.
- the `AI Settings` dialog now supports backend connection probing, discovered model refresh, and popup feedback with discovered-model counts.
- invalid persisted AI profile base URLs and invalid VoiceWeaver runtime base URLs are now self-healed back to their defaults during settings validation instead of being left for downstream HTTP failures.
- the `TTS Settings` dialog now persists one global VoiceWeaver runtime connection cache in `settings.json`, one narrator preview timeout, and one long-form audio generation timeout; project voice assignment is locked on the Home page instead.
- the `TTS Settings` dialog now shows equally wide runtime connection and discovered-model columns, keeps the discovered-model list height close to the runtime controls height, and exposes runtime audio limit settings below the runtime area.
- the VoiceWeaver runtime capability matrix now classifies fixed Qwen3 `base`, `voice_designer`, and `custom_voice` readiness from the current REST generation modes (`clone`, `definition`, `custom_voice`) while still tolerating older alias values in cached data.
- the `Narator Voice` page now seeds each project with built-in editable Qwen3 preset profiles for `vivian`, `serena`, and `anna`, restores those presets automatically when they are missing from one project, syncs any additional Qwen3 CustomVoice presets reported by the current runtime into the project profile catalog as runtime presets instead of protected built-ins, migrates legacy `qwen3_tts_customvoice_seed` prompt-seed entries into editable custom narrator profiles, keeps no narrator selected by default, stores narrator language values internally as VoiceWeaver language codes, and stores `preview_text` plus `is_selected` in `audio_profiles.json`.
- the `Narator Voice` page now supports explicit `Create Profile`, `Edit Profile`, `Save Profile`, `Delete Profile`, `Generate Sample`, `Preview`, and `Select` actions for project-local Narator Voices, with no `Add Model Profiles` workflow.
- editing a narrator profile now shows a destructive confirmation, clears the stored sample immediately, clears selection when the edited profile was selected, and requires a new sample before the profile can be selected again.
- narrator profile selection in the left list now refreshes button enablement for the newly inspected profile, so Delete, Generate Sample, Select, and Preview follow the currently highlighted profile instead of the previously inspected one.
- narrator sample generation now re-tests fixed Qwen3 capability readiness from the current runtime probe, waits for model-load completion before submitting generation, sends VoiceWeaver language codes instead of UI labels, uses the saved narrator preview timeout from `TTS Settings`, clears older root-level narrator sample files before storing the newly generated sample, and records selected state in `audio_profiles.json` plus `narator.json` while selected sample metadata is stored separately in `narator_sample.json`.
- the Narator Voice page now shows read-only original, translated, and locked voice-language indicators, localizes the narrator preview text for the selected voice language, and shows a bottom status window summarizing profile counts, sample counts, selected-count state, and current Qwen3 readiness notes.
- the `Character Voices` page now lists the selected narrator plus all discovered characters, displays the locked selected voice language as a read-only indicator, uses the character-owned `voice_definition_prompt` from `Characters` as the default character voice-designer prompt with one legacy fallback builder for older projects, includes one separate two-line preview-text editor like the Narator Voice page, localizes that preview text from the locked project language, uses that preview text for character sample generation, stores it alongside each generated sample for later voice-cloning work, supports reset or edit or save or generate or preview for character targets in narrator-plus-character projects, and shows a bottom status window with total targets plus targets with samples.
- the `Character Voices` page now disables character prompt editing and sample generation when `voice_assignment_mode` is `same_narrator`, automatically copies the selected narrator sample into each character sample slot, and warns on page entry when the selected narrator still lacks a generated sample.
- the `Speech Blocks`, `Audio Blocks`, and `Audio Assembly` pages are now real localized workflow surfaces.
- the `Speech Blocks` page supports `Generate Speech Blocks`, `Reset Speech Blocks`, `Approve All Speech Blocks`, `Insert Speech Block`, `Delete Speech Block`, selected-block `Edit`/`Save`/`Reset`, warning clearing on edit, speaker and content-kind selectors including `Indication`, and `Re-Split Selected Chunk`; same-narrator projects expose only the Narrator speaker and disable speaker reassignment while editing; generation stays available for partial resumable runs, is disabled after all chunks have generated Speech Blocks, and only all-block approval marks the persisted operation summary completed; narration/dialogue blocks persist and display narrator or character names, while pause/background/indication blocks persist and display the operation name; Speech Block IDs now use chunk-local numbering (`CCCC-BBBBBB`), so re-splitting or manually changing one chunk rebuilds that chunk's local IDs and rolls downstream Audio Blocks plus Audio Assembly back from stale state.
- the `Audio Blocks` page now consumes approved persisted `Speech Blocks`, the selected narrator sample, character voice samples when the project uses narrator-plus-character assignment, and the selected project voice language; prepares reusable client-owned Qwen3 voice clone prompts through VoiceWeaver; resolves the loaded clone model's effective `max_new_tokens` budget; generates one ordered final WAV per approved speech block under `audio_blocks/` using chunk-plus-local file stems such as `0002_000001_alice.wav`; skips unapproved speech blocks until they are approved and generation is continued; skips VoiceWeaver generation for metadata-only `Pause`, `Background Noise`, and `Indication` blocks; internally splits and stitches over-budget blocks; supports selected-block and sequential audiobook playback for review; supports responsive cancellation plus resume from saved state; and requires explicit per-block approval before the workflow advances to `audio_blocks_ready`.
- Audio Blocks artifacts currently use `audio_blocks.json`, `audio_blocks_report.json`, `audio_blocks_state.json`, `voice_clone_profiles.json`, one WAV plus JSON metadata pair per generated speech block under `audio_blocks/`, and split part WAVs under `audio_blocks/parts/` when long blocks require internal splitting.
- the `Audio Assembly` page now consumes approved generated Audio Blocks, converts metadata-only pause blocks into silence, supports `Per text chunk`, `Time limit`, and `Whole audiobook` WAV output modes, persists `audio_assembly_settings` in `project.json`, writes final deliverables under `audiobook/`, stores `audio_assembly_report.json` plus `audio_assembly_state.json`, and provides generated-output playback with row double-click restart, an inline Play/Stop button, a progress slider, `-10s`/`+10s` seek buttons, plus reset controls.
- Audio Assembly supports configurable silence gaps only; MP3 encoding, silence trimming, normalization, pitch changes, chapter metadata, and cover-art embedding remain deferred.
- changing selected narrator or character-voice inputs that affect generation now confirms and invalidates persisted Audio Blocks data before the upstream mutation proceeds.
- `LICENSE.txt`, `LICENSE_NC.txt`, `LICENSE_ro.txt`, and `LICENSE_NC_ro.txt` are stored in the app root so the About dialog can display English or Romanian license text and the delivered app keeps the license set at the app-root level.
- the About dialog now includes the main license text and the non-commercial addendum in a scrollable read-only text area, localized to the current UI language when a companion translation file exists.
- `tests/` contains focused automated tests for the scaffold.

## Environment Setup

This project uses `uv` for environment and dependency management.

Example workflow:

```powershell
uv sync --extra dev
```

This installs the application runtime plus the current developer tools, including
`pytest`, `pytest-qt`, `PyInstaller`, and `ruff`.

## Run The Application

From this folder:

```powershell
uv run audiomancer
```

You can also run:

```powershell
uv run python -m audiomancer
```

## Runtime Logging

- Each app launch creates a new log file under `Logs/` in the app root.
- Log files use the pattern `AudioMancer_YYYYMMDD_HHMMSS.log`.
- Runtime logging writes to both the log file and stdout.
- Supported log output formats are `text` and `json`.
- Logging defaults and per-component overrides are currently defined in `src/audiomancer/config.py`.

## Settings Lifecycle

- The app settings file is stored at `settings.json` in the app root.
- Missing `settings.json` is created automatically from service-owned defaults.
- Persisted settings are validated and self-healed at startup.
- Updated settings can be saved back through the shared settings service from both `Settings` and `AI Settings`.
- Saved language and text-size changes are applied immediately to the running UI shell.
- Saved AI provider settings now include persisted connection-discovery state for each configured profile.
- Saved TTS runtime settings now include persisted VoiceWeaver discovery state, active-model identity, normalized device diagnostics, narrator preview timeout, and long-form audio generation timeout.

## Run Tests

From this folder:

```powershell
uv run pytest
```

For routine Python hygiene, prefer `ruff` on the files you actually changed:

```powershell
uv run ruff check src/audiomancer/app.py tests/test_app_entrypoint.py --fix
uv run ruff format src/audiomancer/app.py tests/test_app_entrypoint.py
```

Focused validation used for the current project-workspace implementation:

```powershell
uv run pytest tests/test_project_workspace_service.py
uv run pytest tests/test_import_service.py
uv run pytest tests/test_main_window_project_flow.py
```

Focused validation used for the current extraction implementation:

```powershell
uv run pytest tests/test_text_extraction_service.py
uv run pytest tests/test_text_cleanup_page.py
uv run pytest tests/test_main_window_project_flow.py
uv run pytest tests/test_project_workspace_service.py
```

Focused validation used for the current cleanup and operation-progress implementation:

```powershell
uv run pytest tests/test_operation_runtime_service.py
uv run pytest tests/test_deterministic_cleanup_service.py
uv run pytest tests/test_text_cleanup_page.py
uv run pytest tests/test_main_window_project_flow.py
```

Focused validation used for the current AI-assisted cleanup implementation:

```powershell
uv run pytest tests/test_prompt_template_service.py
uv run pytest tests/test_llm_provider_service.py
uv run pytest tests/test_ai_cleanup_service.py
uv run pytest tests/test_text_cleanup_page.py
uv run pytest tests/test_text_cleanup_ui_controller.py
```

Focused validation used for the current narrator and TTS settings refactor:

```powershell
uv run pytest tests/test_narrator_definition_service.py
uv run pytest tests/test_narrator_definition_state_service.py
uv run pytest tests/test_narator_voice_page.py
uv run pytest tests/test_narator_voice_ui_controller.py
uv run pytest tests/test_tts_settings_page.py
uv run pytest tests/test_voiceweaver_runtime_service.py
uv run pytest tests/test_main_window_project_flow.py -k narrator
```

Focused validation used for the current Character Voices implementation:

```powershell
uv run pytest tests/test_character_voices_service.py
uv run pytest tests/test_character_voices_state_service.py
uv run pytest tests/test_character_voices_page.py
uv run pytest tests/test_character_voices_ui_controller.py
uv run pytest tests/test_project_workspace_service.py
uv run pytest tests/test_main_window_project_flow.py -k "character_voices or repair"
```

Focused validation used for the current Speech Blocks implementation:

```powershell
uv run pytest tests/test_speech_blocks_service.py
uv run pytest tests/test_speech_blocks_state_service.py
uv run pytest tests/test_speech_blocks_page.py
uv run pytest tests/test_speech_blocks_ui_controller.py
uv run pytest tests/test_character_voices_ui_controller.py -k language_change
uv run pytest tests/test_project_workspace_service.py -k speech_blocks
```

Focused validation used for the current Audio Blocks implementation:

```powershell
uv run pytest tests/test_audio_blocks_service.py
uv run pytest tests/test_audio_blocks_state_service.py
uv run pytest tests/test_audio_blocks_page.py
uv run pytest tests/test_audio_blocks_ui_controller.py
uv run pytest tests/test_audio_blocks_main_window.py
uv run pytest tests/test_audio_blocks_upstream_invalidation.py
uv run pytest tests/test_character_voices_ui_controller.py
```

Focused validation used for the current deterministic chunking implementation:

```powershell
uv run pytest tests/test_deterministic_chunking_service.py
uv run pytest tests/test_text_chunking_page.py
uv run pytest tests/test_text_chunking_ui_controller.py
uv run pytest tests/test_main_window_project_flow.py
```

Focused validation used for the current page-oriented UI controller split:

```powershell
uv run pytest tests/test_main_window_lifecycle.py
uv run pytest tests/test_main_window_ai_profiles.py
uv run pytest tests/test_main_window_project_flow.py
uv run pytest tests/test_home_presenter_service.py
uv run pytest tests/test_text_cleanup_state_service.py
uv run pytest tests/test_home_ui_controller.py
uv run pytest tests/test_text_cleanup_ui_controller.py
```

Focused validation used for the current Home export panel:

```powershell
uv run pytest tests/test_project_export_service.py
uv run pytest tests/test_home_page.py
uv run pytest tests/test_home_ui_controller.py
uv run pytest tests/test_main_window_home_exports.py
```

## Packaging

Windows packaging automation is stored under:

- `../../02_Tools/package_windows_release.ps1`
- `../../02_Tools/audiomancer_windows.spec`
- `../../02_Tools/package_linux_release.sh`

The Windows release script builds a portable `PyInstaller` bundle, stages the
app together with `settings.json` and the four license files, writes a
versioned delivery archive into `../../07_Delivery/`, and removes temporary
build artifacts after a successful zip.
