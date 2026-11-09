# TASK-08add324 - Make Narrator Voice edits and sample saves recoverable

stage: done
type: change
path: full
interaction: autopilot
requirements: REQ-FUNC-3fc66fe1, REQ-FUNC-666a26b5, REQ-REL-d20719d9, REQ-FUNC-907e0468, REQ-FUNC-ebc2e9e7
parent:
branch: master
base: 90b250e1e624c9f97614d10d66dd607e2b5c7107
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

Problem: OBSERVED entering Edit deletes narrator sample and selection before Save. Sample replacement writes WAV before its transcript. AI suggestions discard valid profiles on minor variations; rendered prompts can exceed the estimate.
Desired outcome: STATED draft editing and recoverable sample publication first, then usable AI profiles and rendered prompt budgets with simple code.
Actors: AudioMancer narrator operator.
Primary scenario: Edit and save a narrator, replace its sample, and generate more editable narrator profiles.
Examples: A rename preserves the selected voice and WAV. Failure replacing narrator_voice.json preserves the old WAV and transcript. Duplicate AI names receive suffixes.
Counterexamples: A real voice edit invalidates the stale sample on Save. An entirely unusable response leaves the inventory intact.
In scope: Narrator Voice service/controller, narrator AI generation, targeted tests and bilingual guides.
Out of scope: Other voice workflows, migration, architecture rewrite, VoiceWeaver language adapter change, and commit.
Constraints: STATED autopilot and focused tests; OBSERVED current master and separate local Romanian workaround changes. Preserve sample format, project text rules, and preview duration contract.
Success signals: Edit and discard are non-destructive; only relevant successful saves invalidate; sample replacement recovers; usable AI suggestions survive; rendered prompt fits the estimated budget.
Evidence: narrator_definition_service.py, narator_voice_ui_controller.py, narrator_profile_generation_service.py, and the prior read-only simulations.
Assumptions: A change to prompt, preview or language makes a profile sample stale. Keep existing selection clearing for that change at Save. A plain rename preserves audio.
Unknowns: Live provider quality is outside focused verification.
Decision-blocking questions: None.
Proposed behaviors: Reuse the existing file replacement helper, profile-name suffixer and token estimator.
Path and reason: Full. Observable behavior changes, existing requirements need revision, JSON format and dependencies are stable.

## Requirement coverage

| Behavior | Requirement | Design |
|---|---|---|
| Save narrator draft changes before invalidating the sample | REQ-FUNC-3fc66fe1 | Read-only entry, save-time voice comparison |
| Keep Narrator Voice selection and editor state explicit | REQ-FUNC-666a26b5 | Existing draft UI and post-save refresh |
| Publish narrator WAV with its transcript recoverably | REQ-REL-d20719d9 | Existing staged file replacement |
| Keep usable narrator profile suggestions from partial responses | REQ-FUNC-907e0468 | Use profile name suffixer and report shortfall |
| Bound the rendered narrator analysis and synthesis requests | REQ-FUNC-ebc2e9e7 | Estimate actual request text |

## Design

### Approach
Begin edit loads a snapshot. Save compares the effective voice fields in the
service, preserves a rename, or clears the stale sample and selected ID together.
The controller owns confirmation, playback release, and the existing selective
downstream refresh after success.

### Interfaces and data
Stage WAV and the validated narrator document in the project. Reuse
replace_project_files with the original narrator document as the comparison
snapshot; use the same operation to retire a stale sample on a voice edit.
Keep the current profile shape, selected ID and filename conventions.

### Files and test seams
Update narrator_definition_service, narrator page/controller, and
narrator_profile_generation_service. Inject file replacement failures in
service tests and test draft preservation and invalidation in the controller.

### Risks and open decisions
Match prompt, preview and language when assessing sample validity. Preserve the
existing preview duration policy and downstream reset boundary. An entirely
invalid AI response retains the prior profiles and resumable style checkpoint.

### Requirement map
REQ-FUNC-3fc66fe1 and REQ-FUNC-666a26b5: draft and selective save.
REQ-REL-d20719d9: staged sample publication and rollback.
REQ-FUNC-907e0468: append usable profiles and reuse unique names.
REQ-FUNC-ebc2e9e7: assembled window estimates and compact final prompt.

Diagrams: [diagram_TASK-08add324.md](diagram_TASK-08add324.md)

## Log

- 2026-11-09 frame: journal opened
- 2026-11-09 frame: completed; next specify
- 2026-11-09 specify: completed; next design
- 2026-11-09 design: completed; next build
- 2026-11-09 build: red: six focused service/controller cases fail as expected. Edit deletes the sample and selection before Save, and both sample paths lack paired publication (REQ-FUNC-3fc66fe1, REQ-FUNC-666a26b5, REQ-REL-d20719d9). pytest exit 1.
- 2026-11-09 build: green: 28 narrator definition/document tests and 6 relevant Qt controller tests passed after draft and paired publication implementation.
- 2026-11-09 build: red: three focused AI tests fail on duplicate-name rejection, a separator-sensitive window overflow and an oversized final summary (REQ-FUNC-907e0468, REQ-FUNC-ebc2e9e7); pytest exit 1.
- 2026-11-09 build: red: existing page edit regression now verifies visible name edit and Cancel restoring the draft; it fails at the currently hidden name field. The list is disabled in edit mode so explicit Cancel is part of the existing draft design (REQ-FUNC-666a26b5).
- 2026-11-09 build: green: seven Narrator Voice page/localization tests pass, including a visible name field and Cancel restoring the draft. The draft UI uses the original editor snapshot; no additional confirmation on discard.
- 2026-11-09 build: green: 57 narrator service/document/profile-generation tests, 19 targeted controller tests, and seven narrator-page/localization tests passed. Ruff and strict AEGIS check pass. Reviewed 12 changed product paths against the pre-fix anchor, with the Romanian workaround retained as baseline.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Validate inspection: reviewed draft/save flow, paired WAV and document rollback, partial AI suggestions, and budgeted rendered prompts. Updated bilingual help, voice knowledge and context. Final candidate Ruff and baseline-delta audits across 11 Python paths report no findings. Separate Romanian workaround remains present.
- 2026-11-09 validate: Review 1: online analysis windows use a direct fraction that ignores prompt, output reserve and safety. Keep the existing online fraction and unlimited unit count, and bound the actual remaining style input budget.
- 2026-11-09 validate: returned to build - Respect remaining context for online style windows
- 2026-11-09 build: red review 1: captured online style request test fails because both units are packed into one request despite prompt and reserve overhead; pytest exit 1.
- 2026-11-09 build: green review 1: 30 narrator profile generation tests exit 0, including an online run split into two within-budget rendered requests; Ruff and diff checks pass. No UI, persistence or source rule changes in this review correction.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Validate reconciliation after review: online profiles keep their context fraction and uncapped unit count, with the shell and reserves applied. The regression inspects actual system plus user prompt estimates; all earlier design seams remain unchanged.
- 2026-11-09 validate: Review 2: the style shell loses its source separators when rendered with empty input, so the exact boundary can still overflow by one estimated token. Preserve separators with a nonempty placeholder, including rounding headroom.
- 2026-11-09 validate: returned to build - Preserve real style prompt delimiters in the shell estimate
- 2026-11-09 build: red review 2: exact shipped-template probe measures a 1640-token request against 1639 available and shows the old planner still accepts it; focused pytest exit 1.
- 2026-11-09 build: green review 2: 31 narrator profile tests pass, including the shipped-template one-token overflow. Source placeholder retains delimiters and the actual style dispatch is checked against the same input limit used for final synthesis. Ruff and diff --check pass.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Validate reconciliation after round 2: only source delimiters and full style-request estimate changed; regression is pinned to the shipped template edge. Existing voice profile, publication and draft behavior remains the reviewed candidate.
- 2026-11-09 validate: DEVIATION validate: full check --run omitted at user request. Prove with focused narrator service, AI, controller, page, localization and help-version tests, Ruff, baseline-delta audits and strict AEGIS check.
- 2026-11-09 validate: final: uv run pytest on narrator generation, definition, document contract, state, page, localization and package metadata exit 0 (74 passed). Controller pytest -k edit_preserves_sample or edit_missing_profile or save_blocks or shortfall or generate_sample_failure or shared_runtime_keeps_profile exit 0 (9 passed, 29 deselected). Ruff and both baseline-delta audits across 11 Python files show zero issues. git diff --check and AEGIS check --strict exit 0 (15 baseline warnings, three docs paths, one prior VoiceWeaver workaround path outside task requirements). No live AI or TTS calls.
- 2026-11-09 validate: completed; next done

## Rulings


## State

status: done
reported: validate - completed
next: implementation guidance complete; commit, push and integration belong to the developer
must_read: .agentic/tasks/TASK-08add324.md
changed: Narrator draft, recoverable WAV and transcript, usable AI profiles, and bounded rendered prompts.
evidence: 83 focused tests passed; Ruff, audits, diff and AEGIS strict checks passed.
issues: Full suite omitted as requested; AI and VoiceWeaver calls simulated.
spec_compliance: approved
implementation_quality: approved
review_round: 3

## Delivery report (2026-11-09)

- stage: validate; type: change; path: full; branch: master
- requirements:
  - REQ-FUNC-3fc66fe1 - Save narrator draft changes before invalidating the sample
  - REQ-FUNC-666a26b5 - Keep Narrator Voice selection and editor state explicit
  - REQ-REL-d20719d9 - Publish narrator WAV with its transcript recoverably
  - REQ-FUNC-907e0468 - Keep usable narrator profile suggestions from partial responses
  - REQ-FUNC-ebc2e9e7 - Bound the rendered narrator analysis and synthesis requests
- deviations: 1 recorded
  - validate: full check --run omitted at user request. Prove with focused narrator service, AI, controller, page, localization and help-version tests, Ruff, baseline-delta audits and strict AEGIS check.
- explicit review: enabled; spec_compliance=approved; implementation_quality=approved; review_round=3
- diff vs task base 90b250e: 26 file(s) changed, 993 line(s) added
- checks: errors=0 warnings=19 notes=2
- checklist: 8/9 done; open: `report` appended
