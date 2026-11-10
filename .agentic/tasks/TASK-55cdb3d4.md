# TASK-55cdb3d4 - Make Audio Blocks regeneration recoverable and resume by block ID

stage: done
type: change
path: full
interaction: autopilot
requirements: REQ-REL-3a5d2962, REQ-FUNC-e9a6688e, REQ-FUNC-168e8717, REQ-FUNC-880f7fda, REQ-FUNC-39994b8e, REQ-UX-1e583d8c, REQ-FUNC-dedd5cbf
parent:
branch: master
base: 72362e7771ccec1360d5fe791140721f9b839598
opened: 2026-11-09

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
- [x] final `check --strict --run` result logged truthfully after the last edit
- [x] remaining warnings and pre-existing failures explained
- [x] `report` appended

## Frame

Problem: OBSERVED Regeneration can delete the existing WAV before a replacement is ready. A second interruption or unrelated review can erase a split cursor. Complete WAVs can inherit new fingerprints without regeneration, clone reuse ignores transcript changes, and UI readiness relies on generated flags.
Desired outcome: STATED Implement the Audio Blocks proposals, starting with recoverable WAV replacement and ID-based resume.
Actors: AudioMancer operator.
Primary scenario: Resume an interrupted multi-part block, or regenerate an existing reviewed block and recover if the provider or publication fails.
Examples: OBSERVED Temporary probes lost a previous WAV after provider failure and reset a saved two-part cursor when model loading was cancelled.
Counterexamples: STATED Keep the valid WAV and allow operator review while replacement is pending.
In scope: STATED WAV validation and publication, ID-based resume and cursor retention, correct reuse identity, missing-WAV retry, shared generation of one block and scoped prerequisites.
Out of scope: INFERRED Changes to audio mixing, new providers, live synthesis verification, releases and commits.
Constraints: STATED Current branch, autopilot, only relevant tests, simple changes.
Success signals: Failure leaves previous WAV and approval intact, a second interruption keeps saved parts, changed inputs are identified without stamping old audio, and local metadata or selected block operations use only their required resources.
Evidence: OBSERVED Prior source inspection and temporary-project probes in Audio Blocks.
Assumptions: INFERRED Reuse the current WAV paths and document, with optional metadata and the current recoverable file publisher.
Unknowns: UNKNOWN Live provider quality.
Decision-blocking questions: None.
Proposed behaviors: Stage replacement before publishing. Recover a saved prefix by block ID and matched synthesis inputs. Retain old playable WAVs for review.

Path and reason: full

| Criterion | Holds? | Evidence |
|---|---|---|
| no new externally observable behavior | no | replacement failure and retry behavior |
| no new interface or data format | no | stale output evidence and checkpoint semantics |
| no new dependency | yes | shared file publication |
| an existing requirement already covers the behavior | no | amended resume and reuse |
| no security or data-handling change | no | paired artifact publication |

## Requirement coverage

| Behavior | Requirement | Design | Evidence |
|---|---|---|---|
| Recoverable WAV | REQ-REL-3a5d2962 | Recoverable WAV | Focused regression |
| Resume identity | REQ-FUNC-e9a6688e | Resume identity | Focused regression |
| Honest WAV reuse | REQ-FUNC-168e8717 | Honest WAV reuse | Focused regression |
| Clone prompt identity | REQ-FUNC-880f7fda | Clone prompt identity | Focused regression |
| Valid WAV frames | REQ-FUNC-39994b8e | Valid WAV frames | Focused regression |
| Missing WAV retry | REQ-UX-1e583d8c | Missing WAV retry | Focused regression |
| Scoped prerequisites | REQ-FUNC-dedd5cbf | Scoped prerequisites | Focused regression |

## Design

**Approach**
- REQ-REL-3a5d2962: render completed WAVs in project-local staging. Replace WAV, audio_blocks.json, clone cache and the project summary with the shared recoverable publisher. Clear part files after that publication succeeds.
- REQ-FUNC-e9a6688e: use current_block_id with the split plan and synthesis fingerprint. Load or cancel without dropping the old cursor. Keep it when reviewing other rows. Resume the saved active block first.
- Keep project orchestration, checkpoint and review updates in audio_blocks_service. Extract VoiceWeaver submission, polling, download and WAV rendering into audio_blocks_generation_service.

**Interfaces and data**
- Keep canonical WAV and part paths. Build separate staged parts when regenerating an existing selected block.
- REQ-FUNC-168e8717: completed playable WAVs keep their original fingerprint. Compare locally available configured synthesis inputs for review without activating VoiceWeaver. Keep the effective runtime budget in the exact generation fingerprint used for split resume. Record a stale indicator when generation detects a changed synthesis identity, and allow selected regeneration.
- REQ-FUNC-880f7fda: require matching sample bytes, exact transcript, reference language and clone model for prompt reuse.
- REQ-FUNC-39994b8e: validate actual WAV frames, including downloaded and resumed files.
- REQ-UX-1e583d8c and REQ-FUNC-dedd5cbf: use real artifact availability to plan work and scope models and references to requested audio.

**Files and test seams**
- Exercise batch and selected public entry points, file rollback after staged WAV publication, second cancellation, unrelated approval, stale output, transcript-only correction and local work.
- Document retry, regeneration and stale output in both guides and Unreleased changelog.

**Risks and open decisions**
- A fingerprint that cannot establish synthesis compatibility safely can restart that incomplete block. Complete playable WAVs stay available.
- VoiceWeaver is simulated in focused tests.

**Requirement map**
- REQ-REL-3a5d2962: recoverable publication of the WAV and document.
- REQ-FUNC-e9a6688e: checkpoint resume by ID and matching part inputs.
- REQ-FUNC-168e8717 and REQ-FUNC-880f7fda: preserve actual output identity and key the clone cache accurately.
- REQ-FUNC-39994b8e: readable declared WAV frames.
- REQ-UX-1e583d8c and REQ-FUNC-dedd5cbf: artifact-aware work and prerequisite selection.

Diagrams: [diagram_TASK-55cdb3d4.md](diagram_TASK-55cdb3d4.md).


## Log

- 2026-11-09 frame: journal opened
- 2026-11-09 frame: completed; next specify
- 2026-11-09 specify: completed; next design
- 2026-11-09 design: completed; next build
- 2026-11-09 build: red: five targeted tests fail for provider error and cancellation losing an approved WAV, missing publication rollback, second cancellation losing the split cursor, and a truncated WAV accepted by the header check.
- 2026-11-09 build: green: regeneration rollback and truncated WAV regressions pass. Red: five focused tests fail for stale fingerprint restamping, transcript-only clone reuse, missing-WAV retry, local pause generation and unrelated sample gating.
- 2026-11-09 build: Red: the continuation test reproduces restamping through the public batch entry point. Green: the Audio Blocks service, artifact, document, state and page modules passed 109 tests; 5 selected controller tests passed. Prior WAV, document and manifest bytes survive injected publication failures. Ruff and focused style/logging audits report no new findings.
- 2026-11-09 build: Evolution reviewed 15 product, test and help paths. Strict metadata check passed with 15 baseline warnings and 3 outside-layout warnings for the required guides and CHANGELOG.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: DEVIATION validate: omit the full check --run suite - user requested focused tests only; run strict metadata, focused Audio Blocks pytest, Ruff and changed-file audits with simulated VoiceWeaver.
- 2026-11-09 validate: Inspection: matched both help sections against start eligibility, selected regeneration, stale label and split resume. Reviewed candidate paths and recoverable publication order. Audio Assembly consumes the unchanged canonical WAV names.
- 2026-11-09 validate: Round 1: compare completed audio against cached synthesis inputs without loading a model, make optional reference inspection nonblocking, respect cancellation at batch publication, and share effective sound inputs between request and fingerprint.
- 2026-11-09 validate: returned to build - Fix explicit review findings for cached stale comparison, optional reference errors, late cancellation and effective ambience identity.
- 2026-11-09 build: DEVIATION build: continue after the review return under the user-approved autopilot interaction - the review loop authorizes bounded fixes before the next verdict.
- 2026-11-09 build: Round 1 corrections verified: 112 focused service/artifact/document/state/page tests plus 5 selected controllers. Cached completed-state comparison stays local; metadata-only continuation works with a cached clone model; unreadable optional reference is bypassed; final download cancellation keeps the checkpoint; ambience cue and explicit override produce equivalent fingerprints when the provider settings match.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Round 2: cached defaults and live effective token budgets can differ without any operator input change. Separate locally comparable settings identity from the exact synthesis fingerprint used for resume.
- 2026-11-09 validate: returned to build - Prevent false stale badges from cached default versus live token budget.
- 2026-11-09 build: Red: the actual public generation and page regression reports stale with live 128 versus cached 512. Green: the configured fingerprint keeps the newly generated WAV current in that case, and exact resume still uses the effective budget. Focused proof: 113 Audio Blocks service/artifact/document/state/page tests and 5 selected controller tests passed. Ruff, diff and changed-file audits passed.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Round 3: the live/default budget regression passes, but a stale marker saved during metadata-only work remains when the operator restores the original synthesis setting. Distinguish persisted live-budget evidence from a fresh configured-input comparison. Source inspection also found that split cleanup should skip a redirected parts directory.
- 2026-11-10 validate: returned to build - Correct sticky cached review marker and constrain split-part cleanup within the project, per user ruling.
- 2026-11-10 build: Red before fix: uv run pytest -q tests/test_audio_blocks_service.py -k checks_completed_wavs_with_cached_inputs-or-removes_only_local_published_parts (pytest -k expression) exited 1: two failures reproduced the sticky configured marker and deletion through a real Windows junction. The local-only control passed.
- 2026-11-10 build: Green: 116 Audio Blocks service/artifact/document/state/page tests and five selected controller tests exited 0. Both original regressions pass. Restored settings clear the projected marker after local and live batches. A confirmed live-only mismatch survives cached review. A real Windows junction is skipped, and the normal cleanup deletes only the published block parts. Ruff and git diff --check passed.
- 2026-11-10 build: Evolution still covers the 15 authorized product, test and help paths. Updated the single-document spec, TTS Audio Blocks knowledge, project context and both help sections for this round.
- 2026-11-10 build: completed; next validate
- 2026-11-10 validate: Round 4 approved independently for specification compliance and implementation quality under RULING-001. DEVIATION validate: one additional review round - user approved a task-specific exception. The bound was overridden in memory for this verdict only. The unchanged repository config makes the strict metadata check report the expected round-limit warning.
- 2026-11-10 validate: DEVIATION validate: one additional explicit review round - the user approved this task-only exception in RULING-001. The verdict override was in memory and project policy was not edited.
- 2026-11-10 validate: final: uv run pytest -q tests/test_audio_blocks_service.py tests/test_audio_blocks_artifact_service.py tests/test_audio_blocks_single_document_contract.py tests/test_audio_blocks_state_service.py tests/test_audio_blocks_page.py --tb=line --show-capture=no exit 0 (116 passed); uv run pytest -q tests/test_audio_blocks_ui_controller.py -k 'start_request or completed_start or confirmation_before_starting or corrupt_document or selected_block_after_regeneration_refresh' --tb=line --show-capture=no exit 0 (5 passed, 11 deselected), both QT_QPA_PLATFORM=offscreen. AEGIS check --task TASK-55cdb3d4 --strict, Ruff, git diff --check, and changed-file style and logging delta audits exited 0. AEGIS reported 15 baseline warnings, 3 outside-layout notices for the help files and changelog, and 1 expected task review-limit warning under RULING-001. VoiceWeaver was simulated; full suite excluded by user instruction.
- 2026-11-10 validate: completed; next done
- 2026-11-10 done: Operator confirmed manual Audio Blocks checks: cancelling regeneration preserves the previous WAV, and an interrupted block resumes successfully.

## Rulings

- RULING-001 | date=2026-11-10 | decision=Allow one additional correction and explicit review round for this task. | reason=The operator explicitly approved correcting stale review markers and constraining split cleanup, with focused tests and no commit. | source=user | supersedes=none


## State

status: done
reported: validate - completed
next: implementation guidance complete; commit, push and integration belong to the developer
must_read: .agentic/tasks/TASK-55cdb3d4.md
changed: Recoverable WAV replacement, checkpoint resume by ID, correct review markers, safe split cleanup and EN/RO guides
evidence: 121 focused tests passed. Both independent reviews approved. Ruff, delta audits, git diff and AEGIS strict passed.
issues: VoiceWeaver simulated. Full suite omitted as requested. Review-limit warning reflects the authorized fourth round.
spec_compliance: approved
implementation_quality: approved
review_round: 4

## Delivery report (2026-11-10)

- stage: validate; type: change; path: full; branch: master
- requirements:
  - REQ-REL-3a5d2962 - Audio Blocks preserves the previous WAV and review if replacement fails
  - REQ-FUNC-e9a6688e - Audio Blocks resumes saved split parts by block ID
  - REQ-FUNC-168e8717 - Audio Blocks retains the actual synthesis identity of a playable WAV
  - REQ-FUNC-880f7fda - Audio Blocks keys clone prompts to the exact reference
  - REQ-FUNC-39994b8e - Audio Blocks synthesizes approved audio rows and validates complete WAVs
  - REQ-UX-1e583d8c - Audio Blocks can retry a missing or unreadable generated WAV
  - REQ-FUNC-dedd5cbf - Audio Blocks validates only prerequisites for requested audio
- deviations: 4 recorded
  - validate: omit the full check --run suite - user requested focused tests only; run strict metadata, focused Audio Blocks pytest, Ruff and changed-file audits with simulated VoiceWeaver.
  - build: continue after the review return under the user-approved autopilot interaction - the review loop authorizes bounded fixes before the next verdict.
  - validate: one additional review round - user approved a task-specific exception. The bound was overridden in memory for this verdict only. The unchanged repository config makes the strict metadata check report the expected round-limit warning.
  - validate: one additional explicit review round - the user approved this task-only exception in RULING-001. The verdict override was in memory and project policy was not edited.
- explicit review: enabled; spec_compliance=approved; implementation_quality=approved; review_round=4
- diff vs task base 72362e7: 29 file(s) changed, 1790 line(s) added
- checks: errors=0 warnings=19 notes=2
- checklist: 9/9 done
