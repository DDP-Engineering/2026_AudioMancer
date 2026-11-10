# TASK-8ba293c9 - Make Audio Assembly complete, recoverable and easier to maintain

stage: done
type: change
path: full
interaction: autopilot
requirements: REQ-FUNC-7c32fd5e, REQ-FUNC-f58d731e, REQ-REL-f3f965de, REQ-REL-65c19765, REQ-FUNC-51afdd49
parent:
branch: master
base: 3b4f3e8cd5f3a5cad36ffbe6ff77783d5f2290d5
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
- [x] final `check --strict --run` result logged truthfully after the last edit
- [x] remaining warnings and pre-existing failures explained
- [x] `report` appended

## Frame

Problem: OBSERVED Assembly can omit an approved block with a missing WAV or accept a truncated WAV. Scene-change anchors are dropped in the Audio Blocks projection. Preview and final mix durations can differ. Replacement can delete a previously published WAV and resume trusts path existence.
Desired outcome: STATED Implement the Audio Assembly proposals, starting with source validation and ambience anchors.
Actors: AudioMancer operator.
Primary scenario: Assemble the full approved book, audition separate scene groups, then cancel or resume a multi-output run.
Examples: OBSERVED In-memory probes planned one of two approved WAVs, read six of eight declared frames, merged distinct scene anchors, and used different preview and final durations.
Counterexamples: INFERRED Pauses and indications do not need WAVs. Disabled ambience stays outside composition.
In scope: STATED Source validation, scene anchors and common preview/final mix, safe WAV replacement, file-level resume, pause units and streaming, separate planning and WAV processing.
Out of scope: INFERRED Mid-file checkpoints, new export formats or a different mixing policy, live listening, releases and commits.
Constraints: STATED Current default branch master, autopilot, focused tests, no commit. Existing PCM codec and output modes remain in use.
Success signals: Invalid required WAV identifies its block before output changes. Anchors remain distinct. Preview and final mix agree. Failed replacement keeps the previous WAV. Resume rebuilds only invalid or absent outputs. Explicit pauses use their units.
Evidence: OBSERVED Prior source inspection and in-memory probes. Existing tests cover 4 GB preflight, disabled ambience, PCM conversion, timestamps and output-level resume.
Assumptions: INFERRED Reuse existing report/state and confirmed reset for incompatible inputs. Preserve preview duration rule and use it for final output.
Unknowns: UNKNOWN Audible quality with real project input, outside automated verification.
Decision-blocking questions: None.
Proposed behaviors: Validate only required sources, share the ambience plan, atomically replace rendered files and resume by validated planned output.

Path and reason: full

| Criterion | Holds? | Evidence |
|---|---|---|
| no new externally observable behavior | no | diagnostics and corrected timing |
| no new interface or data format | no | new internal module interfaces |
| no new dependency | yes | stdlib and existing PCM codec |
| an existing requirement already covers the behavior | no | preview parity and resume validity need explicit coverage |
| no security or data-handling change | no | guarded WAV publication |

## Requirement coverage

| Behavior | Requirement | Design | Evidence |
|---|---|---|---|
| Complete WAV sources | REQ-FUNC-7c32fd5e | Shared frame validation | Missing/truncated WAV |
| Scene parity | REQ-FUNC-f58d731e | Anchored groups and shared duration | Distinct scenes and output parity |
| Safe publish | REQ-REL-f3f965de | Single staged writer | Replace failure and cancellation |
| Resume outputs | REQ-REL-65c19765 | Match report, plan and WAV | Corrupt output selectively rebuilt |
| Pause timing | REQ-FUNC-51afdd49 | Shared parser and streamed silence | Milliseconds, seconds and cancellation |


## Design

**Approach**
- Validate playable source headers and last frames before planning. Missing approved spoken audio is an error. Keep the existing pause, indication and ambience inclusion rules. Check Scene Mix layout and planned output channel conversion in preflight.
- Project scene-change anchors from Speech Blocks and group by chunk, position and anchor. Preserve the preview duration rule for final output and use the deterministic group WAV when it is valid.
- Move sequential output grouping and gap policy to audio_assembly_plan. Move PCM streaming, mixing and single-WAV publication to audio_assembly_wav. Reuse pcm_codec.

**Interfaces and data**
- Keep existing service entry points, report and operation-state formats. Use one staged writer with a unique sibling candidate per render for the audiobook and Scene Mix. Preserve previous bytes until the completed candidate replaces them. Validate publication paths.
- Match both persisted fingerprints, canonical filename and complete WAV to planned output keys. Preserve run token, rebuild individual files, and report outputs in plan order.
- Parse explicit seconds or milliseconds in the shared Speech Blocks pause parser. Stream silence in bounded chunks with cancellation.

**Files and test seams**
- Extend existing Audio Assembly service tests for missing/truncated WAV, separate anchors and preview/final duration, replacement faults and selective resume. Verify pause units and cancellation in existing source/PCM tests.
- Update EN/RO guides and Unreleased changelog.

**Risks and open decisions**
- Source ordering and cue metadata are part of input identity. A run with incompatible identity uses existing confirmed reset. Resume stays file-granular.
- No live listening is required for the automated proof.

**Requirement map**
- REQ-FUNC-7c32fd5e: complete source frames and block-specific diagnostic.
- REQ-FUNC-f58d731e: shared anchored Scene Mix definition.
- REQ-REL-f3f965de: staged single-WAV replacement.
- REQ-REL-65c19765: validated file-level reuse.
- REQ-FUNC-51afdd49: shared pause parse and streamed silence.

Diagrams: [diagram_TASK-8ba293c9.md](diagram_TASK-8ba293c9.md).


## Log

- 2026-11-10 frame: journal opened
- 2026-11-10 frame: completed; next specify
- 2026-11-10 specify: completed; next design
- 2026-11-10 design: completed; next build
- 2026-11-10 build: Red: focused Audio Assembly pytest exited 1, four expected failures. Missing, unrecorded and truncated required WAVs were composed, and two distinct scene anchors collapsed (REQ-FUNC-7c32fd5e, REQ-FUNC-f58d731e).
- 2026-11-10 build: Green: 10 focused source/scene/PCM tests passed, including missing and truncated sources, anchor identity and mix parity.
- 2026-11-10 build: Red: targeted pytest exited 1. Replacement lost the prior WAV in both writers, preview cancellation left a temporary file, resume misplaced or reused damaged output, and seconds parsed as milliseconds.
- 2026-11-10 build: Green: 183 Audio Assembly, UI, codec and WAV artifact tests and 17 affected Speech Blocks and Audio Blocks tests passed. Fault tests preserve prior audiobook and Scene Mix WAVs on replacement errors, remove a cancelled mix candidate, and rebuild only missing/truncated output in plan order. Long silence can be cancelled after one bounded chunk.
- 2026-11-10 build: Evolution reviewed 13 scoped product, test and help paths. Ruff, git diff --check, delta audits and strict metadata passed. The expected 15 baseline and 3 guide/changelog layout warnings remain.
- 2026-11-10 build: completed; next validate
- 2026-11-10 validate: DEVIATION validate: omit the full check --run test suite - operator requested only relevant tests. Run strict metadata, focused Assembly and affected source/PCM selectors, Ruff and delta audits.
- 2026-11-10 validate: Inspection: both guides agree with output-granular resume, pause examples and anchored Scene Mix grouping. Retained current report/state schemas and output modes. Audited diff for path containment, approved source rules and recovery behavior.
- 2026-11-10 validate: Round 1: preflight group compatibility and output channel conversion before any file publication; preview must retain required missing generated cues; isolate concurrent WAV candidates and support leading-decimal pause units.
- 2026-11-10 validate: returned to build - Address round 1 compatibility preflight, preview source completeness, staging isolation and pause units.
- 2026-11-10 build: Autopilot authorizes the bounded explicit-review fix cycle.
- 2026-11-10 build: Red round 1: five targeted failures reproduced invalid early publication, omitted required preview cue, shared temporary candidate, and the leading-decimal unit bug.
- 2026-11-10 build: Green round 1: 9 correction-specific tests passed. Full focused selection 186 Assembly/PCM/artifact, 17 Speech/Audio Blocks and 4 direct consumer regressions passed, 207 total. Both incompatible source cases fail before creating the earlier output, preview rejects the missing generated cue, interleaved renders preserve their own candidates, and leading decimals resolve to 500 ms. Ruff, diff, delta audits and strict metadata passed.
- 2026-11-10 build: completed; next validate
- 2026-11-10 validate: Inspection and focused cache probe: replaced a generated preview first with a same-duration three-channel WAV, then a shorter mono WAV. Both were excluded from preview playback. Final per-chunk assembly rebuilt the cache as mono at 2400 frames and produced both planned outputs.
- 2026-11-10 validate: Round 2: both independent reviews approved the unchanged candidate. The specification reviewer withdrew an obsolete cache finding after rereading the shared validation and reproducing the probe.
- 2026-11-10 validate: final: uv run pytest -q tests/test_audio_assembly_service.py tests/test_audio_assembly_sample_widths.py tests/test_audio_assembly_state_service.py tests/test_audio_assembly_ui_controller.py tests/test_audio_assembly_page.py tests/test_pcm_codec.py tests/test_audio_blocks_artifact_service.py --tb=line --show-capture=no exit 0 (186 passed); uv run pytest -q tests/test_speech_blocks_service.py tests/test_audio_blocks_service.py -k 'pause or scene_ambience or translated_speech' --tb=line --show-capture=no exit 0 (17 passed, 156 deselected); uv run pytest -q tests/test_atomic_io_contracts.py::test_audio_assembly_state_uses_atomic_json_writer tests/test_ai_translation_service.py::test_stale_translated_speech_cannot_generate_new_output[audio_assembly] tests/test_project_workspace_service.py::test_project_workspace_calls_audio_assembly_settings_contract tests/test_project_workspace_service.py::test_audio_assembly_and_project_workspace_import_without_cycle --tb=line --show-capture=no exit 0 (4 passed). QT_QPA_PLATFORM=offscreen. Ruff, git diff --check, focused style and logging delta audits, and AEGIS check --task TASK-8ba293c9 --strict exited 0. Fifteen baseline and three expected guide/changelog layout warnings remain. PCM tests emitted the baseline audioop deprecation warning. No full suite or manual listening.
- 2026-11-10 validate: completed; next done
- 2026-11-10 done: Operator confirmed manual Audio Assembly checks for pause timing, Scene Mix playback, and resuming after interruption.

## Rulings


## State

status: done
reported: validate - completed
next: implementation guidance complete; commit, push and integration belong to the developer
must_read: .agentic/tasks/TASK-8ba293c9.md
changed: WAV preflight, anchored Scene Mix parity, safe publication, file-level resume, pause units, separated plan/PCM modules and EN/RO help
evidence: 207 focused tests passed. Both reviews approved. Ruff, delta audits, diff and strict AEGIS passed.
issues: Full suite omitted as requested. Synthetic WAVs used; audible review remains manual. Earlier ambience runs may require reset before resuming.
spec_compliance: approved
implementation_quality: approved
review_round: 2

## Delivery report (2026-11-10)

- stage: validate; type: change; path: full; branch: master
- requirements:
  - REQ-FUNC-7c32fd5e - Validate every opened Audio Assembly source
  - REQ-FUNC-f58d731e - Share anchored Scene Mix planning between preview and assembly
  - REQ-REL-f3f965de - Remove failed Audio Assembly temporary outputs
  - REQ-REL-65c19765 - Resume only validated WAV outputs from the current Assembly plan
  - REQ-FUNC-51afdd49 - Apply explicit pause duration units and stream silence
- deviations: 1 recorded
  - validate: omit the full check --run test suite - operator requested only relevant tests. Run strict metadata, focused Assembly and affected source/PCM selectors, Ruff and delta audits.
- explicit review: enabled; spec_compliance=approved; implementation_quality=approved; review_round=2
- diff vs task base 3b4f3e8: 29 file(s) changed, 1576 line(s) added
- checks: errors=0 warnings=18 notes=2
- checklist: 9/9 done
