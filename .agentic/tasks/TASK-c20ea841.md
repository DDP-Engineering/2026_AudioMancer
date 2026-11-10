# TASK-c20ea841 - Select VoiceWeaver models by operation and language

stage: done
type: change
path: full
interaction: autopilot
requirements: REQ-FUNC-295f2eb9, REQ-FUNC-b8a50984, REQ-FUNC-09110e87, REQ-FUNC-1562fca1
parent:
branch: master
base: 751629db24c112ac2e8434945ab377b3cad706c4
opened: 2026-11-10

Edit Frame, Requirement coverage and Design directly. Write State, Log and
Rulings with `python .agentic/aegis.py` (advance, pause, log, ruling, verdict);
end each session with `advance` or `pause`.

## Done checklist (current stage)

- [x] diff reviewed against scope, requirements, design, error paths,
      portability, security and unrequested work
- [x] knowledge pages of changed components current with the reviewed code
- [x] project and environment context reconciled with the candidate
- [x] requirements re-read: status, prose, verification, paths and links true
- [x] manual or inspection verification recorded where applicable
- [x] explicit review approved, when enabled
- [x] final focused verification and structural check logged after the last candidate edit
- [x] remaining warnings and pre-existing failures explained
- [x] `report` appended

## Frame

Problem: OBSERVED in voiceweaver_runtime_service, voice profile services and Audio Blocks: healthy capabilities are discovered, yet spoken operations require Qwen and always map Romanian to Italian.
Desired outcome: STATED: choose a model by operation and language. Prefer explicit Romanian support. Keep Italian as a Qwen-specific fallback.
Actors: Audiobook operator, AudioMancer, configured VoiceWeaver runtime.
Primary scenario: AudioMancer generates a voice sample or approved spoken block using the model advertising the required operation and selected language. A project with imported samples can use a clone-only model.
Examples: A Romanian-capable design model handles a Romanian preview. A clone-capable Romanian model reads a Romanian block with language ro. A Qwen-only runtime continues using it for Romanian.
Counterexamples: A sound model cannot generate narration. A model listing only English is not selected for Romanian; Qwen with Italian is the specific fallback.
In scope: One capability-based selector shared by design, clone, speech budgeting and scene sounds. Keep the existing Qwen reusable prompt path and use the existing direct clone route for other clone-capable adapters.
Out of scope: STATED: stage one only. New adapters or model installs, TTS Settings model selectors, sound parameter changes and REST schema changes belong to later stages.
Constraints: STATED: AEGIS autopilot, focused tests, no commit. OBSERVED: current checkout master is the default branch. Preserve project text, sample metadata and existing persistence.
Success signals: Exact language beats fallback; design and clone work independently; Qwen fallback still works; planning uses the selected clone model; direct clone receives the existing sample and correct synthesis language.
Evidence: OBSERVED: VoiceWeaver ModelSummary exposes supported_generation_modes and supported_languages. POST /voice/clone accepts reference WAV and transcript; its reusable profile schema is Qwen-specific.
Assumptions: INFERRED: Existing Qwen requests and artifact fingerprints should remain compatible whenever effective generation inputs are identical.
Unknowns: Quality and availability of any additional model on a real runtime. Synthetic tests prove selection and wire behavior.
Decision-blocking questions: None.
Proposed behaviors: None beyond the accepted first stage.
Path and reason:
| Quick criterion | Holds | Evidence |
| --- | --- | --- |
| No new observable behavior | No | Operations select compatible model families |
| No new interface or format | Yes | Existing VoiceWeaver endpoints and artifacts |
| No new dependency | Yes | No model installation |
| Existing requirement covers behavior | No | Qwen-specific requirements need revision |
| No security or data-handling change | Yes | Same configured runtime receives existing reference inputs |

## Requirement coverage

| Behavior | Requirement | Design | Verification |
| --- | --- | --- | --- |
| Select by capability and language | REQ-FUNC-295f2eb9 | Shared runtime selector; budget the selected clone | Inventory and planning tests |
| Gate previews by design only | REQ-FUNC-b8a50984 | Preview request builders | Design-only and incompatible inventories |
| Show readiness | REQ-FUNC-09110e87 | Derive from selected-language design | Narrator state test |
| Send correct wire language and clone route | REQ-FUNC-1562fca1 | Resolve language once per target; direct clone for non-Qwen | Wire and Audio Blocks tests |

## Design

**Approach**
- REQ-FUNC-295f2eb9: select a healthy model with the requested mode. Rank declared language first, then the Qwen Romanian fallback, then a compatible inventory entry without language metadata. Keep the existing Qwen Base preference among equal clone matches. Sound selection is independent of narration language.
- REQ-FUNC-b8a50984 and REQ-FUNC-09110e87: narrator and character requests and readiness use the design selection for the requested language. A design-only runtime can produce a preview.
- REQ-FUNC-1562fca1: pass the resolved language explicitly to the existing VoiceWeaver routes. Preserve the project's language in samples and generation state. Qwen keeps reusable prompts. Non-Qwen models use direct cloning with the WAV and transcript already on disk.

**Interfaces and data**
- Keep the existing runtime and document schemas. Speech planning uses the selected clone metadata. For a clone adapter that supplies no token budget, use the existing conservative split estimate internally and let the adapter choose generation parameters.
- Clone requests use the target speech language; Qwen prompt preparation uses the sample language. Model IDs and actual inputs continue to scope cached audio and split resume.
- Keep VoiceWeaver endpoints and the one-active-model workflow. Leave the backend and dependency changes outside this iteration.

**Files and test seams**
- Selector and wire behavior in voiceweaver_runtime_service and its tests. Narrator and Character Voices state and request builders check independent preview readiness.
- Speech Blocks consumes the selected clone budget. Audio Blocks tests cover Qwen reuse and direct clone through batch and regeneration.

**Risks and open decisions**
- UNKNOWN: candidate quality and actual adapter availability. Tests use the existing HTTP contract and simulated model inventories.
- Existing runtimes may omit language metadata. Treat that as unspecified support after explicit choices.

**Requirement map**
- REQ-FUNC-295f2eb9: model and budget selection.
- REQ-FUNC-b8a50984 and REQ-FUNC-09110e87: design-only generation and readiness.
- REQ-FUNC-1562fca1: exact language and existing request routes.

Diagrams: [diagram_TASK-c20ea841.md](diagram_TASK-c20ea841.md)

## Log

- 2026-11-10 frame: journal opened
- 2026-11-10 frame: completed; next specify
- 2026-11-10 specify: completed; next design
- 2026-11-10 design: completed; next build
- 2026-11-10 build: red: pytest test_voiceweaver_runtime_service.py -k resolve_tts_model exit 1, no shared selector (REQ-FUNC-295f2eb9)
- 2026-11-10 build: green: focused selector pytest exit 0 (REQ-FUNC-295f2eb9)
- 2026-11-10 build: red: three scoped preview/state/native-clone tests exit 1; Qwen-only preview and model routing still active (REQ-FUNC-b8a50984, REQ-FUNC-09110e87, REQ-FUNC-1562fca1)
- 2026-11-10 build: green: focused VoiceWeaver, narrator, character voice and Audio Blocks pytest exit 0 (161 passed); targeted narrator controller retest exit 0 (4 passed). Ruff and git diff --check pass; scoped structural warnings are baseline and required guides/changelog layout.
- 2026-11-10 build: completed; next validate
- 2026-11-10 validate: Round 1 independent reviews found non-Qwen backend IDs can accidentally select Qwen routes, and audio fingerprints need to distinguish a native Romanian hint from the previous Italian fallback.
- 2026-11-10 validate: returned to build - Respect backend identity and distinguish native Romanian audio fingerprints
- 2026-11-10 build: red: Audio Blocks targeted review regressions exit 1 (two expected failures on adapter identity and language fingerprint).
- 2026-11-10 build: green: three targeted review regressions passed, including direct clone with misleading model ID and distinct resume/review fingerprints while preserving the prior Italian hint fingerprint.
- 2026-11-10 build: completed; next validate
- 2026-11-10 validate: DEVIATION validate: focused pytest and strict structural check instead of check --run - operator requested relevant tests only; the full repository suite is outside this proof.
- 2026-11-10 validate: final: QT_QPA_PLATFORM=offscreen uv run pytest -q on 12 VoiceWeaver, TTS budget, settings, narrator, character, Speech Blocks and Audio Blocks suites exit 0 (321 passed); selected narrator and character voice controller pytest exit 0 (7 passed). python .agentic/aegis.py check --task TASK-c20ea841 --strict exit 0 (18 baseline and guide/changelog layout warnings). Ruff, code-style audit and git diff --check exit 0. Model routing verified against simulated inventories and REST calls.
- 2026-11-10 validate: completed; next done

## Rulings


## State

status: done
reported: validate - completed
next: implementation guidance complete; commit, push and integration belong to the developer
must_read: .agentic/tasks/TASK-c20ea841.md
changed: Capability-based VoiceWeaver selection, native Romanian and Qwen fallback, direct cloning and EN/RO guides
evidence: 328 focused pytest cases passed; strict structural check, Ruff and code-style passed
issues: New model adapters and live Romanian inference are outside this stage
spec_compliance: approved
implementation_quality: approved
review_round: 2

## Delivery report (2026-11-10)

- stage: validate; type: change; path: full; branch: master
- requirements:
  - REQ-FUNC-295f2eb9 - Choose a healthy VoiceWeaver model by operation and language
  - REQ-FUNC-b8a50984 - Enable voice previews with a compatible design model
  - REQ-FUNC-09110e87 - Show narrator profile counts and voice-design readiness
  - REQ-FUNC-1562fca1 - Send generation requests using the simplified VoiceWeaver contract
- deviations: 1 recorded
  - validate: focused pytest and strict structural check instead of check --run - operator requested relevant tests only; the full repository suite is outside this proof.
- explicit review: enabled; spec_compliance=approved; implementation_quality=approved; review_round=2
- diff vs task base 751629d: 40 file(s) changed, 661 line(s) added
- checks: errors=0 warnings=18 notes=2
- checklist: 8/9 done; open: `report` appended
