<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details. SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

# AudioMancer Repository Discovery

Run: `adoption-2026-07-18T145821Z-782116f8`

Discovery date: 2026-07-18

## Scope And Method

This report records read-only discovery of `04_Software/AudioMancer` for an
existing-project adoption. It distinguishes observed repository behavior from
the component map proposed for the next gate. No application source, tests, or
runtime behavior were changed during discovery.

Evidence reviewed:

- `AGENTS.md`, `.agentic/workflow.toml`, and the adoption workflow skill.
- Package metadata, README, entry points, module briefs, imports, and workflow
  ordering under `04_Software/AudioMancer`.
- Existing tests under `04_Software/AudioMancer/tests`.
- Existing implementation documentation under `05_SoftwareDocu`.
- Empty AEGIS component knowledge and durable requirement registers under
  `.agentic/knowledge/components` and `.agentic/requirements`.
- AEGIS traceability and coverage audits.

The operator-local `04_Software/AudioMancer/settings.json` and runtime `Logs/`
were intentionally not read because they may contain local endpoints, API
keys, or machine-specific data.

## Repository Shape

- Runtime: Python `>=3.12,<3.13` desktop application using PySide6.
- Package: `04_Software/AudioMancer/src/audiomancer`.
- Console entry point: `audiomancer = "audiomancer.app:main"`.
- Module entry point: `python -m audiomancer` via `audiomancer.__main__`.
- Main coordinator: `audiomancer.ui.main_window.MainWindow`.
- Source inventory: 88 non-`__init__.py` Python modules.
- Test inventory: 93 Python test/support files with 872 discovered `test_*`
  function definitions.
- Prompt resources: `04_Software/AudioMancer/prompts`.
- Human-facing implementation documentation: 39 focused Markdown documents
  plus English and Romanian offline user guides under `05_SoftwareDocu`.
- AEGIS gates: `uv run --project 04_Software/AudioMancer pytest -q` and
  `uv run --project 04_Software/AudioMancer ruff check .`.
- Workflow adapters present: Claude Code, Codex, OpenCode, Pi, and Qwen Code.

## Observed Product Flow

`MainWindow.PAGE_ORDER` defines the operator workflow as:

1. Home / Project
2. Text Cleanup
3. Text Chunking
4. AI Translation
5. Characters
6. Narator Voice
7. Character Voices
8. Speech Blocks
9. Audio Blocks
10. Audio Assembly

The main window is a thin-but-central coordinator. It composes domain pages,
delegates actions to UI controllers, and reads page state from services. This
supports domain-oriented components, but `main_window.py` remains a shared
integration boundary for every workflow stage.

## External Dependencies And Runtime Boundaries

- PySide6 provides widgets, multimedia playback, threading, and application
  lifecycle.
- PyMuPDF, python-docx, striprtf, odfpy, EbookLib, and langdetect support source
  extraction and cleanup analysis.
- OpenAI-compatible, LM Studio/Ollama-compatible, and VoiceWeaver endpoints are
  contacted through standard-library HTTP helpers.
- WAV processing uses the standard-library `wave` module; project snapshots and
  exports use `zipfile`.
- Application settings and project artifacts are local files. The committed
  settings example contains placeholders; the operator-local settings file is
  gitignored and may contain credentials.
- Prompt templates are runtime resources outside the Python package and are
  shared by several AI workflow stages.

## Ownership Evidence

Source module headers consistently name `Eng. Dan Dumitru Pasare`, and project
copyright notices name DDP Engineering. No separate `CODEOWNERS`-style file or
per-component owner registry was found. The proposed map should therefore use
DDP Engineering / Eng. Dan Dumitru Pasare as discovered ownership evidence and
mark component-level ownership as needing confirmation.

## Likely Component Boundaries

These are discovery recommendations, not yet approved manifest entries.

| Candidate | Primary boundary | Representative tests | Existing documentation |
| --- | --- | --- | --- |
| `app-shell` | `app.py`, `__main__.py`, `ui/main_window.py`, navigation, shell helpers, package assets | app entry point, package import, main-window lifecycle/project-flow/shutdown tests | `AudioMancer_App_Shell.md` |
| `platform-settings-ui` | `config.py`; settings, logging, UI state/theme/scroll, URL and time services; Settings/AI Settings/TTS Settings dialogs where not owned by a runtime domain | config, settings, logging, UI state/theme/scroll, localization tests | config/settings, UI, and logging documents |
| `project-lifecycle` | project workspace, import, export, snapshot, persistence, Home presenter/page/controller | project workspace/export/snapshot, import, persistence, home, atomic-I/O tests | project workspace/runtime/export/snapshot/persistence documents |
| `operation-orchestration` | operation runtime, workflow impact, threaded runner, workflow controller, progress dialog | operation runtime/runner, workflow impact/order/controller tests | operation runner and workflow impact documents |
| `ai-runtime` | LLM provider/backend, AI budgets, token usage, prompt loading, AI state notes, AI settings integration | LLM provider, backend, budget, prompt-template, AI settings/state-note tests | LLM provider and AI runtime support documents |
| `text-cleanup` | text extraction, deterministic and AI cleanup, cleanup analysis/metadata, cleanup state/page/controller | extraction, deterministic cleanup, AI cleanup/contract, cleanup metadata/page/controller tests | text extraction and cleanup documents |
| `text-chunking` | deterministic and AI chunking, chunking state/page/controller | deterministic/AI chunking, descriptor contract, state/page/controller tests | text chunking state and text-pipeline documents |
| `ai-translation` | translation service, state, page, controller, and translation prompts | translation service/state/page/controller tests | `AudioMancer_AI_Translation_Service.md` |
| `character-discovery` | character discovery service/state/page/controller and discovery prompts | character discovery service/state and Characters page/controller tests | `AudioMancer_Character_Discovery_Service.md` |
| `voice-profiles` | narrator definition/state/profile generation, character voices/state, voice sample import, Narator Voice and Character Voices UI | narrator, character voices, voice sample import, and related UI tests | narrator, character voices, and voice sample documents |
| `speech-blocks` | speech block generation, normalization, splitting, report/state, page/controller, and speech/ambience prompts | speech block service/state/report/normalization/splitting/page/controller tests | speech block service/state/normalization documents |
| `tts-audio-blocks` | VoiceWeaver runtime, TTS budgets/runtime UI support, audio block generation/artifacts/state/page/controller | VoiceWeaver, TTS settings/budget, audio block service/artifact/state/page/controller tests | TTS/VoiceWeaver and audio block documents |
| `audio-assembly` | WAV assembly service/state/page/controller | audio assembly service/state/page/controller tests | `AudioMancer_Audio_Assembly_Service.md` |

## Boundary Risks And Unknowns

1. `main_window.py` imports every workflow domain and is the principal
   integration seam. It should belong to `app-shell`; domain changes that also
   modify it will be multi-component changes rather than evidence that the
   shell and every domain are one component.
2. `config.py` and `ui_state_service.py` are large cross-cutting modules. Their
   ownership should remain with `platform-settings-ui`, with explicit
   dependencies from domain components.
3. `prompts/` contains both shared AI templates and domain-specific templates.
   The component map should use exact prompt paths instead of assigning the
   entire directory to every AI component.
4. The three settings dialogs cross platform, AI runtime, and TTS runtime
   concerns. Exact file ownership should be assigned once; integration
   dependencies should describe the other concerns.
5. No durable requirement rows exist, so existing test coverage is not yet
   traceable through AEGIS even though the pytest suite is extensive.
6. Existing component documents live under `05_SoftwareDocu`, outside the
   configured AEGIS component-documentation root. Adoption should link or
   summarize them under `.agentic/knowledge/components` one component at a
   time instead of duplicating all documents in one gate.
7. Component-level ownership has not been explicitly confirmed by a human.

## Audit Results

### Traceability

`aegis audit traceability` reported `OK: no audit issues`. This is structurally
correct but not evidence of adopted traceability because all durable
requirement registers are empty.

### Coverage

`aegis audit coverage` reported 2,388 missing file-level requirement mappings:

- 2,207 files under the project-local `.venv`.
- 88 application source modules under `src/audiomancer`.
- 93 files under `tests`.

The configured `coverable_roots = ["04_Software/AudioMancer"]` is too broad.
Before coverage can become meaningful, the component-map/adoption work should
propose `04_Software/AudioMancer/src/audiomancer` as the coverable root and
exclude generated/vendor/cache/runtime paths. After that configuration repair,
the remaining 88 source modules need durable requirement coverage or explicit
legacy waivers established one approved component at a time.

## Recommended Component-Map Gate Actions

1. Draft the 13 candidates above in `.agentic/components.toml` with status
   below `baseline-usable` until each component has confirmed paths, tests,
   ownership, documentation, and traceability.
2. Assign every source/UI/prompt path to one primary component; represent
   cross-component use as dependencies rather than overlapping ownership.
3. Leave bundles empty unless the human explicitly approves a named bundle.
4. Propose the `coverable_roots` correction separately in
   `.agentic/workflow.toml` because the current audit includes `.venv` and
   tests.
5. Ask the human to approve the component map and select one component for the
   first `component-adoption` slice.

