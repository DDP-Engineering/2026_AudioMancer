<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->

# How To Test AudioMancer

This file describes the automated test suite that ships with the application
and the manual QA pass used to confirm the selective downstream preservation
behavior.

Run every command from `05_Software/AudioMancer/`.

## Test Suite At A Glance

| Property | Value |
| --- | --- |
| Runner | `pytest` 8.x with `pytest-qt` 4.x, `pytest-timeout` 2.x, and `pytest-xdist` 3.x |
| Configuration | `[tool.pytest.ini_options]` in `pyproject.toml` |
| Test root | `tests/` (114 modules, 2 shared support modules, 1 JSON fixture) |
| Collected tests | 1242 |
| Default selection | 1241 (`addopts = "-m 'not performance'"`) |
| Service tier | 923 tests |
| UI tier | 319 tests |
| Performance tier | 1 test, opt-in only |
| Interpreter | Python 3.12-3.13 (`requires-python = ">=3.12,<3.14"`) |

`tests/conftest.py` assigns the tier marker automatically during collection -
no test declares `service` or `ui` by hand:

- a test is `ui` when it requests the `qtbot` fixture, or when its module name
  contains `_page.py`, `_ui_controller.py`, `app_entrypoint`, `main_window`,
  `operation_runner_controller`, or `ui_state`;
- every other test is `service`.

`conftest.py` also provides the shared fixtures `mock_prompt_environment`
(temporary prompt template root), `default_settings_payload` (baseline settings
dictionary), `mock_clean_project` (fresh project root plus manifest), and
`mock_extracted_project` (project with extracted text and a source-document
manifest entry).

Two non-test helper modules are imported by the specification-style tests:
`tests/chunking_test_support.py` builds exact Chunking documents and
`tests/cleanup_test_support.py` builds source-ledger projects and the Cleanup
contract assertions, both without depending on the production services they
verify. `tests/fixtures/cleanup_corpus.json` is the synthetic Cleanup
acceptance corpus.

## Running The Tests

Full regression baseline:

```powershell
uv run pytest -q
```

Fast feedback - service tier only, no Qt widgets:

```powershell
uv run pytest -m service -q
```

Parallel service-tier feedback using four local pytest worker processes:

```powershell
uv run pytest -m service -n 4 --dist loadfile -q
```

Parallel execution is opt-in: the normal pytest command remains serial.
`--dist loadfile` keeps every test module on one worker, and the worker
processes are local test runners rather than additional Codex agents.

UI tier only (Qt widgets, controllers, and main-window shells):

```powershell
uv run pytest -m ui -n 0 -q
```

Keep the UI tier serial until its Qt application state, settings paths, local
ports, and modal-dialog behavior have been proven isolated across processes.

The opt-in performance baseline is deselected by default. Run it explicitly:

```powershell
uv run pytest -m performance -o addopts=
```

Changed-file hygiene during normal feature work:

```powershell
uv run python -m py_compile <changed_files.py>
uv run ruff check <changed_files.py> --fix
uv run ruff format <changed_files.py>
```

Ruff is configured in `pyproject.toml` with a 120-character line length and the
`E`, `W`, `F`, `I`, `UP`, `B`, `C4`, and `SIM` rule sets (`SIM108` disabled).

### Expected Result

Measure the baseline again after any broad change rather than trusting a
remembered number.

Last measured on Windows 11 with Python 3.12.13:

```text
1240 passed, 1 skipped, 1 deselected, 1 warning in 1304.55s (0:21:44)
```

Expect roughly 18-22 minutes of wall clock. The single deselected test is the
performance baseline. Skip and warning counts are environment-dependent, not
failures:

- `tests/test_pcm_codec.py` guards 61 differential-oracle tests (four
  parametrized functions) with `requires_audioop`. On Python 3.12 the stdlib
  `audioop` module still exists, so those tests run and emit the one
  `DeprecationWarning` seen above. On Python 3.13 and newer they skip instead,
  and the expected line becomes `1179 passed, 62 skipped`.
- `tests/test_project_workspace_service.py` skips its symlink test when the
  filesystem or account cannot create file symlinks - the single skip above,
  common on Windows without Developer Mode.

## What The Tests Cover

### Workflow stages

| Area | Modules | Tests | Focus |
| --- | --- | --- | --- |
| Cleanup | 9 | 105 | Quality, adjudication, and chunking-handoff contracts, orchestration, paragraph-offset metadata, the acceptance corpus oracle, and the unified Cleanup page/state/controller |
| Chunking | 7 | 127 | Deterministic chunking, AI chunking and its descriptor contract, the authoritative single-document contract, page state, page, and controller |
| AI Translation | 4 | 28 | Monofile translation service contract, page state, review page, and controller |
| Characters and voices | 15 | 157 | Character discovery, narrator definition and profile generation, Character Voices persistence, voice-sample import validation, Narrator Voice single-document contract, plus the pages and controllers for each |
| Speech Blocks | 9 | 169 | Generation service, same-narrator segmentation, text splitting, normalization, report and state shaping, single-document contract, page, and controller |
| Audio Blocks | 7 | 78 | Generation service, artifact helpers, single-document contract, page state, page, controller, and main-window integration |
| Audio Assembly | 5 | 51 | Assembly service, accepted PCM sample widths, page state, page, and playback controller |

### Platform and shared services

| Area | Representative modules | Focus |
| --- | --- | --- |
| Audio codec | `test_pcm_codec.py` (90 tests) | Internal PCM conversion, resampling, and sample widths, differentially checked against `audioop` where available |
| Project lifecycle | `test_project_workspace_service.py`, `test_import_service.py`, `test_text_extraction_service.py`, `test_project_export_service.py`, `test_project_snapshot_service.py` | Project creation and manifests, source import, text extraction, export projections, ZIP snapshots |
| Operations runtime | `test_operation_runtime_service.py`, `test_operation_runner_controller.py`, `test_operation_progress_dialog.py`, `test_controller_cancellation_wiring.py`, `test_main_window_operation_shutdown.py` | Threaded modal operations, progress reporting, cancellation wiring, shutdown with work in flight |
| Workflow invariants | `test_workflow_impact_service.py`, `test_workflow_controller_service.py`, `test_workflow_order_consistency.py`, `test_project_stage_consistency.py` | Selective downstream invalidation, single-sourced operation order and stage map, monotonic stage high-water mark |
| AI and TTS backends | `test_llm_provider_service.py`, `test_ai_backend_service.py`, `test_ai_budget_service.py`, `test_ai_state_note_service.py`, `test_token_usage_service.py`, `test_tts_budget_service.py`, `test_voiceweaver_runtime_service.py`, `test_prompt_template_service.py` | Provider calls, backend probes, context and generation budgets, token accounting, prompt templates |
| Persistence | `test_persistence_service.py`, `test_atomic_io_contracts.py`, `test_settings_service.py`, `test_config_contract.py`, `test_user_data_location.py`, `test_logging_service.py` | Atomic JSON writes and the artifacts routed through them, settings schema, configuration scaffold, writable data location, log files |
| Shell UI | `test_main_window_lifecycle.py`, `test_main_window_project_flow.py`, `test_main_window_ai_profiles.py`, `test_main_window_home_exports.py`, `test_navigation_sidebar.py`, `test_home_*.py`, `test_settings_page.py`, `test_ai_settings_page.py`, `test_tts_settings_page.py`, `test_misc_ui_controller.py` | Window lifecycle, project flow, navigation, Home presenter and exports, settings pages |
| Presentation services | `test_ui_state_service.py`, `test_ui_theme_service.py`, `test_ui_scroll_service.py`, `test_operator_status_font_role.py`, `test_url_service.py` | Runtime UI state, themes, scrolling, operator status font roles, URL helpers |
| Localization | `test_localization_parity.py`, `test_ui_localization_coverage.py` | Runtime string catalog completeness and English/Romanian binding coverage |
| Repository guards | `test_package_import.py`, `test_app_entrypoint.py`, `test_aegis_workflow_artifacts.py` | Package import smoke test, application bootstrap, AEGIS traceability and source-hygiene contract |
| Performance (opt-in) | `test_blocks_performance_baseline.py` | Times Speech Blocks and Audio Blocks review operations on a synthetic 3,000-block, 150-chunk project |

### Test styles in use

- **Contract tests** (`*_single_document_contract.py`,
  `test_ai_chunking_descriptor_contract.py`, `test_cleanup_*_contract.py`,
  `test_atomic_io_contracts.py`, `test_config_contract.py`) pin exact document
  shapes and field sets. They were written red-first and are the strongest
  guard against silent schema drift.
- **Consistency guards** (`test_workflow_order_consistency.py`,
  `test_project_stage_consistency.py`, `test_localization_parity.py`,
  `test_aegis_workflow_artifacts.py`) assert repository-wide invariants rather
  than one unit's behavior; they fail when two sources of truth diverge.
- **Service tests** exercise pure logic and persistence against `tmp_path`
  projects with no Qt dependency.
- **UI tests** drive real Qt widgets through `qtbot`; they dominate the wall
  clock of a full run.

## Focused Command Sets

Selective downstream preservation regression set:

```powershell
uv run pytest tests/test_ai_chunking_descriptor_contract.py tests/test_chunking_single_document_contract.py tests/test_text_chunking_state_service.py tests/test_localization_parity.py
uv run pytest tests/test_workflow_impact_service.py
uv run pytest tests/test_text_chunking_state_service.py tests/test_text_chunking_page.py tests/test_text_chunking_ui_controller.py
uv run pytest tests/test_characters_ui_controller.py tests/test_character_discovery_service.py
uv run pytest tests/test_voice_sample_import_service.py tests/test_character_voices_ui_controller.py tests/test_narator_voice_ui_controller.py
uv run pytest tests/test_speech_blocks_service.py tests/test_speech_blocks_ui_controller.py
uv run pytest tests/test_audio_blocks_service.py tests/test_audio_blocks_page.py tests/test_audio_blocks_ui_controller.py
uv run pytest tests/test_audio_assembly_service.py tests/test_audio_assembly_page.py tests/test_audio_assembly_ui_controller.py
```

Cleanup and Chunking work:

```powershell
uv run pytest tests/test_cleanup_quality_contract.py tests/test_cleanup_chunking_contract.py tests/test_cleanup_adjudication_contract.py tests/test_cleanup_service.py tests/test_cleanup_metadata_service.py tests/test_cleanup_acceptance_corpus.py
uv run pytest tests/test_deterministic_chunking_service.py tests/test_ai_chunking_service.py tests/test_ai_chunking_descriptor_contract.py tests/test_chunking_single_document_contract.py
```

Audio pipeline work:

```powershell
uv run pytest tests/test_pcm_codec.py tests/test_audio_assembly_sample_widths.py tests/test_audio_assembly_service.py
```

Settings, backends, and localization:

```powershell
uv run pytest tests/test_settings_service.py tests/test_settings_page.py tests/test_ai_settings_page.py tests/test_tts_settings_page.py tests/test_llm_provider_service.py tests/test_voiceweaver_runtime_service.py tests/test_localization_parity.py tests/test_ui_localization_coverage.py
```

## Regression Matrix

Expected covered behavior:

- AI Chunking counts and persists every no-prefix deterministic fallback window,
  including a final or single-window document, and reports its absolute
  paragraph range plus the completed fallback warning
- Text Chunking page state reads the authoritative document lifecycle: running
  notes are checkpoint-based, failed and cancelled notes remain resumable with
  persisted warnings and AI usage, and completed notes retain their summary
  and rerun warning
- chunk insert preserves unrelated Translation, Speech Blocks, and Audio
  Blocks while adding one untranslated chunk record
- chunk delete removes only affected Translation, Speech Blocks, Audio Blocks,
  and generated audio
- chunk edit resets only affected chunk downstream records and Audio Assembly
- character add preserves existing Speech Blocks, Audio Blocks, and Assembly
- character edit unapproves only assigned Speech Blocks and resets only their
  Audio Blocks
- character delete moves affected Speech Blocks to Narrator, unapproves them,
  and resets only their Audio Blocks
- character voice edit, sample import, and sample regeneration reset only Audio
  Blocks using the affected `voice_target_id`
- narrator voice edit resets narrator-driven Audio Blocks only
- Speech Block edit/reset/delete resets only that block's Audio Block
- Speech Block insert and approval preserve generated Audio Blocks and reset
  Assembly only
- Speech Blocks generation with Scene Ambience disabled preserves the existing
  narration/dialogue workflow
- Speech Blocks generation with Scene Ambience enabled creates opener, closer,
  and scene-change metadata blocks according to the selected policy and resumes
  from the next unfinished chunk after cancellation
- Audio Block selected reset/regeneration preserves unrelated Audio Blocks and
  resets Assembly
- Audio Blocks generation skips Scene Ambience when ambience audio is disabled
  and generates approved Scene Ambience WAV files through a sound-capable
  VoiceWeaver model when enabled
- Audio Block approval/unapproval preserves generated audio and resets Assembly
  only
- Audio Assembly settings changes preserve approved Audio Blocks and reset only
  assembly outputs/state/report
- Audio Assembly groups generated Scene Ambience prompt WAVs into on-demand
  Scene Mix previews and uses the same mixed segments in final assembly

Known broad reset that remains documented:

- AI Translation approval loss after a manual translation edit still broad
  resets downstream operation data through the current AI Translation
  controller. This is intentionally documented as a remaining broad reset for
  the hard-break release rather than claimed as selective behavior.

## Coverage Gaps To Keep In Mind

The automated suite mocks every external dependency. It never proves that a
real LLM endpoint, a real VoiceWeaver TTS runtime, or real audio playback
works. The manual QA pass below is the only check for those, and for
end-to-end audio quality.

## Manual QA

Use a small sample book and an offline or local AI/TTS setup when available.

1. Create a project, import a source file, extract text, clean text, chunk text,
   translate when needed, discover characters, prepare voices, generate Speech
   Blocks, generate Audio Blocks, approve them, and assemble audio.
2. Edit one Text Chunking chunk. Confirm that unrelated Translation, Speech
   Blocks, generated Audio Blocks, and audio files remain.
3. Insert one Text Chunking chunk. Confirm existing `chunk_id` values and
   existing audio survive, and only the new chunk needs translation/review.
4. Delete one character assigned to some Speech Blocks. Confirm those Speech
   Blocks become Narrator, become unapproved, and only their Audio Blocks are
   reset.
5. Import a WAV sample for one narrator profile. Enter the exact spoken sample
   text, select the profile, and confirm the sample previews and can be used by
   later Audio Blocks.
6. Import a WAV sample for one character voice. Confirm samples shorter than
   three seconds, silent files, and non-WAV files are rejected. Confirm imported
   samples reset only Audio Blocks using that character `voice_target_id`.
7. Change one character voice prompt or regenerate one character sample.
   Confirm unrelated character audio remains.
8. Edit one Speech Block. Confirm only that block's Audio Block is reset.
9. Enable Scene Ambience in Speech Blocks, accept the confirmation, generate a
   small chunk set, and confirm Scene Ambience opener/closer/scene-change
   blocks can be reviewed and approved.
10. Enable Scene Ambience Audio in Audio Blocks, accept the confirmation, and
   confirm spoken audio is generated before Scene Ambience audio for the same
   chunk when a sound-capable VoiceWeaver model is available.
11. Unapprove one Audio Block. Confirm generated audio remains and only Audio
   Assembly resets.
12. Change one Audio Assembly setting. Confirm approved Audio Blocks remain and
   only assembly outputs/state/report are reset.
13. On Audio Assembly, select a Scene Mix Preview, generate it, play it, then
    assemble audio and confirm the final audiobook uses one mixed ambience
    segment for that scene.
