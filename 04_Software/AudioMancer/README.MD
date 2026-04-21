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
- `src/audiomancer/config.py` defines the current developer-owned defaults and file names.
- `src/audiomancer/services/logging_service.py` provides per-run app logging and optional trace helpers.
- `src/audiomancer/services/settings_service.py` provides load, validate, self-heal, and save behavior for `settings.json`.
- `src/audiomancer/services/ai_backend_service.py` provides backend probe and model-discovery helpers for AI provider profiles.
- `src/audiomancer/services/project_workspace_service.py` provides new/open project creation, validation, and manifest persistence, including the optional `project.json.original_language` field used by the Narator Voice page and the project-local `voice_assignment_mode` field used by `TTS Settings`.
- `src/audiomancer/services/import_service.py` provides source-file validation, copy-into-project behavior, and source metadata creation.
- `src/audiomancer/services/text_extraction_service.py` provides deterministic raw-text extraction, self-contained extraction artifacts, resumable extraction state, and cancelable progress updates.
- `src/audiomancer/services/deterministic_cleanup_service.py` provides deterministic cleanup, cleanup artifacts, and resumable cleanup state.
- `src/audiomancer/services/deterministic_chunking_service.py` provides deterministic chunking, chunk artifacts, and resumable chunking state.
- `src/audiomancer/services/ai_cleanup_service.py` provides AI-assisted cleanup, resumable AI cleanup state, and operation-local AI transaction logging.
- `src/audiomancer/services/ai_translation_service.py` provides AI-assisted translation, translated chunk review records, and resumable translation state.
- `src/audiomancer/services/character_discovery_service.py` provides AI-assisted character discovery, resumable character-profile synthesis, persisted Qwen-oriented voice-definition brief fields plus one final `voice_definition_prompt`, and persisted discovery artifacts under `40_character_discovery`.
- `src/audiomancer/services/narrator_definition_service.py` provides project-local narrator profile persistence, explicit selected-narrator state, `project.json`-backed TTS plan helpers, per-profile sample artifact storage, and selected narrator audio-copy helpers under `50_narrator_definition` plus the project-root `audio_samples` folder.
- `src/audiomancer/services/narration_plan_service.py` provides project-local narration-plan target persistence, character-owned voice-prompt handoff from `Characters` with legacy fallback derivation, selected voice-language persistence, per-character sample storage, and same-narrator sample-copy helpers under `60_narration_plan`.
- `src/audiomancer/services/voiceweaver_runtime_service.py` provides VoiceWeaver runtime probing, full current REST endpoint wrappers, capability-matrix derivation, model-load or unload helpers, generation status polling, and generated-audio download helpers for TTS Settings and narrator sample generation.
- `src/audiomancer/services/token_usage_service.py` provides shared normalization and cumulative merge helpers for provider-reported token usage.
- `src/audiomancer/services/text_chunking_state_service.py` provides Text Chunking page state shaping plus persisted chunk preview loading.
- `src/audiomancer/services/ai_translation_state_service.py` provides AI Translation page state shaping plus persisted translated chunk and review loading.
- `src/audiomancer/services/character_discovery_state_service.py` provides Characters page state shaping plus persisted discovery profile and evidence loading.
- `src/audiomancer/services/narrator_definition_state_service.py` provides Narator Voice page state shaping plus persisted narrator profile and selection loading.
- `src/audiomancer/services/narration_plan_state_service.py` provides Narration Plan page state shaping plus selected voice-language, narrator-plus-character target ordering, translation-language gating, and sample-status loading.
- `src/audiomancer/services/llm_provider_service.py` provides OpenAI-compatible chat-completion requests, transient retry handling, conservative malformed-JSON repair, responsive cooperative cancellation during model waits, JSON normalization, normalized token-usage extraction, and optional AI transaction logging.
- `src/audiomancer/services/prompt_template_service.py` provides strict prompt loading and placeholder rendering from the app-root `prompts/` folder.
- `src/audiomancer/services/operation_runtime_service.py` provides shared runtime helpers for long-running operation folders, resets, and progress conversion.
- `src/audiomancer/services/home_presenter_service.py` provides pure manifest-to-view shaping for the Home page workflow progress and source summary.
- `src/audiomancer/services/text_cleanup_state_service.py` provides Text Cleanup page state shaping plus extraction/cleanup manifest reset helpers.
- `src/audiomancer/ui/` provides the copied toolbar, sidebar, page, and status-bar shell used by the first desktop window.
- `src/audiomancer/ui/controllers/` provides page/window-oriented Qt controllers for Home, Text Cleanup, Settings, AI Settings, and shared shell UI helpers.
- `src/audiomancer/ui/controllers/` now also includes a dedicated Text Chunking page controller for deterministic chunking actions and rerun/reset handling.
- `src/audiomancer/ui/controllers/characters_ui_controller.py` provides the Character Discovery page controller for start, resume, reset, guarded manual add/edit/save/delete actions, and explicit unsaved-change handling.
- `src/audiomancer/ui/controllers/narator_voice_ui_controller.py` provides the Narator Voice page controller for inspected-vs-selected profile handling, destructive edit confirmation, Qwen3-backed VoiceWeaver sample generation with one configurable preview timeout, load-then-poll runtime sequencing before generation, explicit narrator selection, and local WAV preview playback.
- `src/audiomancer/ui/controllers/narration_plan_ui_controller.py` provides the Narration Plan page controller for target inspection, destructive character prompt edits, Qwen3-backed character sample generation, explicit voice-language persistence, and local narrator-or-character preview playback.
- `src/audiomancer/ui/controllers/tts_settings_ui_controller.py` provides the TTS Settings dialog controller for VoiceWeaver connection tests plus persistence for runtime cache fields, preview/generation timeouts, and the simplified project-local `voice_assignment_mode`.
- `src/audiomancer/ui/operation_progress_dialog.py` provides the reusable modal progress popup created on demand for synchronous blocking operations.
- `prompts/` stores AI prompt templates loaded by AI-assisted cleanup, translation, character discovery, and future AI workflows.
- the main toolbar now supports `New Project` and `Open Project`.
- new projects create `00_extraction`, `10_cleanup`, `20_chunking`, `30_translation`, `40_character_discovery`, `50_narrator_definition`, `60_narration_plan`, `temp`, and one root `project.json`.
- opening a project now works from the project root or one selected child workflow folder.
- opening a recoverably corrupted project now offers a repair confirmation and can recreate/reset the corrupted step plus all downstream step folders while updating the manifest stage.
- `project.json` now keeps only compact workflow summaries under `operations`, while detailed per-step runtime state remains authoritative in each workflow folder `state_operation.json` and related artifact files.
- the Home page `Select Source File` action now imports exactly one source file into the project root, stores structured source metadata in `project.json`, and locks the source for that project.
- supported source import formats are `.txt`, `.pdf`, `.rtf`, `.docx`, `.odt`, `.md`, and `.epub`.
- the `Text Cleanup` page now runs deterministic text extraction for the imported source and writes self-contained artifacts into `00_extraction`.
- the `Text Cleanup` page now also runs deterministic cleanup into `10_cleanup` while preserving the original source file name for the cleanup input snapshot.
- the `Text Cleanup` page now also supports AI-assisted cleanup using the selected enabled AI profile from `AI Settings`.
- AI-assisted cleanup now splits long inputs into smaller request windows, validates risky page-number and separator labels conservatively, and surfaces review warnings when the AI result looks suspicious.
- the `Text Chunking` page now runs deterministic chunking into `20_chunking`, renders the current chunk list plus selected chunk preview, and resumes interrupted deterministic chunking runs.
- the `Text Chunking` page now also supports AI-assisted chunking using the selected enabled AI profile plus the selected semantic strategy.
- the `AI Translation` page now translates canonical chunks into one selected target language, preserves per-chunk review state in `30_translation`, and supports chunk editing plus approval.
- the `Characters` page now discovers speaking characters from canonical chunking output, persists editable character profiles in `40_character_discovery`, generates and stores one structured Qwen-oriented voice-definition brief plus one final `voice_definition_prompt` per character, supports explicit `Regenerate Voice Definition`, supports resumable AI runs, and shows source-evidence previews for each discovered character.
- extraction artifacts currently use `input_<original_name>`, `output_raw_text.txt`, `extraction_report.json`, and `state_operation.json`.
- cleanup artifacts currently use `input_<original_name>`, `output_clean_text.txt`, `artifact_cleanup_report.json`, and `state_operation.json`, with the cleanup output/report names defined centrally in `src/audiomancer/config.py`.
- chunking artifacts currently use `input_<original_name>`, `output_chunks.json`, `chunking_report.json`, and `state_operation.json`, with both deterministic and AI-assisted chunking updating the same canonical chunk output.
- translation artifacts currently use `input_<original_name>.json`, `output_translated_chunks.json`, `artifact_translation_report.json`, and `state_operation.json`, while leaving the canonical chunking output unchanged.
- character-discovery artifacts currently use `input_<original_name>.json`, `input_<original_name>.txt`, `output_character_profiles.json`, `artifact_character_discovery_report.json`, and `state_operation.json`.
- narration-plan artifacts currently use `voice_plan.json`, `selected_voice_language.json`, and one per-target WAV plus JSON pair under `60_narration_plan/audio_samples/`.
- AI-assisted cleanup writes one project-local transaction log per run in `10_cleanup` using `log_ai_transactions_<timestamp>.log`.
- pressing `Extract Text` after a completed extraction now asks for confirmation before clearing extraction data and all downstream workflow folders.
- pressing `Deterministic Cleanup` after a completed cleanup now asks for confirmation before clearing cleanup data plus chunking and all following workflow folders.
- pressing `AI-Assisted Cleanup` now first warns that AI operations can take longer, then asks for confirmation before clearing completed cleanup data plus chunking and all following workflow folders when a rerun is required.
- pressing `Deterministic Chunking` after a completed chunking run now asks for confirmation before clearing chunking data plus all following workflow folders.
- pressing `Extract Text` after an unfinished extraction now continues from saved state when possible, or restarts safely from the copied extraction input snapshot.
- pressing `Deterministic Cleanup` after an unfinished cleanup now continues from saved state when possible.
- pressing `AI-Assisted Cleanup` after an unfinished AI cleanup now resumes from the saved cleanup checkpoint and AI transaction log.
- pressing `Deterministic Chunking` after an unfinished chunking run now resumes from the saved chunking checkpoint.
- pressing `AI-Assisted Chunking` after an unfinished AI chunking run now resumes from the saved chunking checkpoint and AI transaction log.
- pressing `Start Translation` after an unfinished translation run now continues from the persisted translated chunk state and translates only the remaining chunks.
- pressing `Reset Translation` now asks for confirmation, clears only `30_translation`, and unlocks the target-language selector for a fresh translation run.
- pressing `Start Discovery` now shows one first-run information popup for long AI work, resumes interrupted discovery when possible, and stays disabled after successful completion until reset.
- pressing `Reset Discovery` now clears `40_character_discovery` plus downstream narrator-definition data without extra confirmation and returns the workflow to `translation_ready`.
- discovered character profiles are now read-only by default, require explicit `Edit Character` before changes, and are saved only when `Save Character` is pressed.
- the `Characters` page now also supports `Add Character` and `Delete Character`, guarded unsaved-change prompts, and one synthetic manual-evidence note for manually added profiles.
- long-running extraction and cleanup now run through one reusable modal progress dialog with a cancel button that blocks the main window while the operation is active.
- AI-assisted cleanup keeps the progress popup responsive while waiting for provider responses, so the cancel button is honored during long model calls.
- OpenAI-compatible provider requests now retry automatically with `max_completion_tokens` when one remote API rejects `max_tokens`, while preserving the original payload shape for local providers that still expect `max_tokens`.
- OpenAI-compatible provider requests now also retain raw assistant message content in the AI transaction log and can issue one follow-up JSON-repair request when a model returns malformed JSON text.
- AI-assisted cleanup, AI-assisted chunking, AI translation, and character discovery now accumulate provider-reported input, output, and total tokens when the backend exposes a standard `usage` object.
- the shared modal progress dialog now shows live token counters for AI workflows and falls back to one localized “not reported by the backend” message when usage is unavailable.
- AI workflow reports, `state_operation.json`, transaction logs, and page notes now persist or display normalized token usage without copying those counters into the compact root `project.json`.
- project names are stored exactly as entered but are rejected when invalid for Windows or Linux folder creation.
- the `Settings` dialog now loads and saves `language`, `interface text size`, and `play completion beep` through the shared settings service.
- saving `Settings` now applies the selected UI language and global text size to the running shell.
- the current shell supports runtime English/Romanian UI switching through one centralized UI-state service.
- the `AI Settings` dialog now loads and saves AI profiles plus the default cleanup, chunking, translation, and character-extraction selections through the shared settings service.
- the `AI Settings` dialog now supports backend connection probing, discovered model refresh, and popup feedback with discovered-model counts.
- the `TTS Settings` dialog now persists one global VoiceWeaver runtime connection cache in `settings.json`, one narrator preview timeout, one long-form audio generation timeout, and one simplified project-local `voice_assignment_mode` field in `project.json`, with new projects defaulting to separate narrator plus character voices.
- the `TTS Settings` dialog now shows equally wide runtime connection and discovered-model columns, keeps the discovered-model list height close to the runtime controls height, and exposes `Voice Assignment Mode` plus the two TTS timeout settings below the runtime area.
- the VoiceWeaver runtime capability matrix now classifies fixed Qwen3 `base`, `voice_designer`, and `custom_voice` readiness from the current REST generation modes (`clone`, `definition`, `custom_voice`) while still tolerating older alias values in cached data.
- the `Narator Voice` page now seeds each project with built-in editable Qwen3 preset profiles for `vivian`, `serena`, and `anna`, restores those presets automatically when they are missing from one project, syncs any additional Qwen3 CustomVoice presets reported by the current runtime into the project profile catalog as runtime presets instead of protected built-ins, migrates legacy `qwen3_tts_customvoice_seed` prompt-seed entries into editable custom narrator profiles, keeps no narrator selected by default, stores narrator language values internally as VoiceWeaver language codes, and stores `preview_text` plus `is_selected` in `50_narrator_definition/profiles.json`.
- the `Narator Voice` page now supports explicit `Create Profile`, `Edit Profile`, `Save Profile`, `Delete Profile`, `Generate Sample`, `Preview`, and `Select` actions for project-local Narator Voices, with no `Add Model Profiles` workflow.
- editing a narrator profile now shows a destructive confirmation, clears the stored sample immediately, clears selection when the edited profile was selected, and requires a new sample before the profile can be selected again.
- narrator profile selection in the left list now refreshes button enablement for the newly inspected profile, so Delete, Generate Sample, Select, and Preview follow the currently highlighted profile instead of the previously inspected one.
- narrator sample generation now re-tests fixed Qwen3 capability readiness from the current runtime probe, waits for model-load completion before submitting generation, sends VoiceWeaver language codes instead of UI labels, uses the saved narrator preview timeout from `TTS Settings`, stores one per-profile WAV plus metadata under `50_narrator_definition/audio_samples`, and refreshes the selected narrator copy under the project-root `audio_samples` folder only when the generated profile is already selected.
- the Narator Voice page now shows read-only original and translated book languages plus a bottom status window summarizing profile counts, sample counts, selected-count state, and current Qwen3 readiness notes.
- the `Narration Plan` page now lists the selected narrator plus all discovered characters, persists one selected voice language under `60_narration_plan`, uses the character-owned `voice_definition_prompt` from `Characters` as the default character voice-designer prompt with one legacy fallback builder for older projects, includes one separate two-line preview-text editor like the Narator Voice page, uses that preview text for character sample generation, stores it alongside each generated sample for later voice-cloning work, supports reset or edit or save or generate or preview for character targets, and shows a bottom status window with total targets plus targets with samples.
- the `Narration Plan` page now disables character prompt editing and sample generation when `voice_assignment_mode` is `same_narrator`, automatically copies the selected narrator sample into each character sample slot, and warns on page entry when the selected narrator still lacks a generated sample.
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

Focused validation used for the current narration-plan implementation:

```powershell
uv run pytest tests/test_narration_plan_service.py
uv run pytest tests/test_narration_plan_state_service.py
uv run pytest tests/test_narration_plan_page.py
uv run pytest tests/test_narration_plan_ui_controller.py
uv run pytest tests/test_project_workspace_service.py
uv run pytest tests/test_main_window_project_flow.py -k "narration or Narration"
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

## Packaging

Windows packaging automation is stored under:

- `../../02_Tools/package_windows_release.ps1`
- `../../02_Tools/audiomancer_windows.spec`
- `../../02_Tools/package_linux_release.sh`

The Windows release script builds a portable `PyInstaller` bundle, stages the
app together with `settings.json` and the four license files, writes a
versioned delivery archive into `../../07_Delivery/`, and removes temporary
build artifacts after a successful zip.
