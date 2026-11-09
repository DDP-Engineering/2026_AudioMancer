# TASK-b87d0a4d - Make Character Voices drafts and sample updates recoverable

stage: done
type: change
path: full
interaction: autopilot
requirements: REQ-FUNC-beaae82d, REQ-FUNC-d15dae2c, REQ-REL-9b792ec3, REQ-FUNC-efab6267, REQ-FUNC-b8d5f669, REQ-FUNC-86edfc26
parent:
branch: master
base: 825f14989ea223905056173c0b51f9433c1544bf
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

Problem: OBSERVED Edit clears samples immediately, display names can collide, WAV and metadata writes can diverge, and an interrupted batch can leave stale generated blocks.
Desired outcome: STATED Use an editable draft, publish WAV and transcript together under a stable target ID, and invalidate only completed targets when a batch stops.
Actors: Character Voices operator.
Primary scenario: Edit and cancel or save a character prompt, then generate or import a sample.
Examples: OBSERVED Ana-Maria and Ana Maria can share a filename today. INFERRED Separate ID-based filenames let each keep its own transcript.
Counterexamples: INFERRED An unchanged Save or a batch that stores zero samples preserves downstream audio.
In scope: STATED Edit/Cancel/Save, character sample naming and paired writes, interrupted-batch invalidation.
Out of scope: INFERRED Changes to character assignment, provider selection, and other operations.
Constraints: STATED Keep the solution simple, use autopilot, run focused tests, and leave work uncommitted.
Success signals: Cancel preserves sample and audio; changed Save invalidates the selected target; failed publication restores the prior pair; partial batch invalidates only published IDs.
Evidence: OBSERVED character_voices_service, character_voices_page and character_voices_ui_controller implement the existing flow.
Assumptions: INFERRED Reuse the existing recoverable publisher and support stored sample paths when reading.
Unknowns: UNKNOWN Live provider latency and audio quality are outside focused local validation.
Decision-blocking questions: None.
Proposed behaviors: Record completed IDs after each successful publication; keep unchanged Save as an exit from edit.
Path and reason: full

| Criterion | Holds? | Evidence |
|---|---|---|
| no new externally observable behavior | no | Cancel and selective invalidation |
| no new interface or data format | no | new WAV names |
| no new dependency | yes | existing persistence helper |
| an existing requirement already covers the behavior | no | edit and batch contracts need revision |
| no security or data-handling change | no | paired sample publication |

## Requirement coverage

| Behavior | Requirement | Design | Evidence |
|---|---|---|---|
| Edit and cancel | REQ-FUNC-beaae82d | Page owns original values and draft | Focused regression |
| New sample filenames | REQ-FUNC-d15dae2c | Canonical filename in character_voice_samples | Focused regression |
| Paired sample publication | REQ-REL-9b792ec3 | Shared project file replacement and rollback | Focused regression |
| Batch completion | REQ-FUNC-efab6267 | Record only successfully published IDs | Focused regression |
| Changed Save | REQ-FUNC-b8d5f669 | Compare saved prompt and preview | Focused regression |
| Unchanged Save | REQ-FUNC-86edfc26 | Compare saved prompt and preview | Focused regression |

## Design

**Approach**
- CharacterVoicesPage owns the draft and restores its initial payload on Cancel.
- The controller enters Edit without writing. Save compares the two fields and confirms destructive changes.
- The service keeps stored paths readable and uses target IDs for new files.
- The batch worker records each target ID after storing its sample. Terminal callbacks use the recorded IDs.

**Interfaces and data**
- Keep the existing voice plan and metadata schema. WAV paths are project relative.
- Stage sample writes or deletion and the revised JSON using the existing replace_project_files helper.
- Publication errors keep the draft open and trigger no downstream invalidation.

**Files and test seams**
- Exercise page draft cancellation and controller dispatch for Save, cancel and failure.
- Service tests cover equal normalized display names and injected publication failure.

**Risks and open decisions**
- Retain existing stored sample paths for reading. Only replace or remove files owned by the target.
- Reuse existing project recovery behavior if rollback fails. Invalidate the saved prefix through the Audio Blocks controller with project-state refresh disabled. Preserve the backup location in the warning if reconciliation also fails.

**Requirement map**
- REQ-FUNC-beaae82d: nonmutating Edit and Cancel.
- REQ-FUNC-b8d5f669 and REQ-FUNC-86edfc26: changed and unchanged Save.
- REQ-FUNC-d15dae2c: ID-based WAV names for published samples.
- REQ-REL-9b792ec3: recoverable paired publication.
- REQ-FUNC-efab6267: completed IDs drive batch invalidation.

Diagrams: [diagram_TASK-b87d0a4d.md](diagram_TASK-b87d0a4d.md).


## Log

- 2026-11-09 frame: journal opened
- 2026-11-09 frame: completed; next specify
- 2026-11-09 specify: completed; next design
- 2026-11-09 design: completed; next build
- 2026-11-09 build: red: focused Character Voices regressions exit 1, five failures prove draft, naming, and paired rollback gaps
- 2026-11-09 build: red: pytest -k batch_invalidates_only_saved_targets exit 1; cancellation and failure omit the completed ID
- 2026-11-09 build: green: uv run pytest -q tests/test_character_voices_service.py tests/test_character_voices_page.py tests/test_character_voices_state_service.py tests/test_character_voices_ui_controller.py exit 0 (71 passed); 21 selected consumer tests exit 0. Ruff, both delta audits and diff check exit 0.
- 2026-11-09 build: Evolution matches the design and required documentation. Strict check exit 0 with 15 baseline repository warnings and three help/changelog paths outside layout globs.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Validation reconciliation: reviewed draft and batch flows, project-local publication, focused regressions, bilingual help, component knowledge and context against requirements.
- 2026-11-09 validate: DEVIATION validate: full check --run omitted at user request. Final proof uses focused Character Voices and consumer pytest selectors, Ruff, baseline-delta audits, diff check and strict AEGIS check.
- 2026-11-09 validate: Review 1: preserve selective invalidation of the saved prefix when rollback of a later sample cannot finish. Avoid reloading a potentially missing voice plan while the backup is available.
- 2026-11-09 validate: returned to build - Invalidate saved IDs after rollback failure without loading the damaged voice plan
- 2026-11-09 build: red review 1: pytest -k batch_invalidates_only_saved_targets and recovery_failed exits 1, because rollback failure suppresses invalidation for already published Alice
- 2026-11-09 build: green review 1: pytest Character Voices batch and Audio Blocks voice-target invalidation selectors exit 0 (8 passed), including saved-prefix rollback failure with backup intact and no voice plan reload. Ruff and both delta audits pass.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Validate reconciliation: shared Audio Blocks invalidation now supports deferring the project refresh in the exceptional recovery path. Default behavior and unrelated audio preserved.
- 2026-11-09 validate: Review 2: secondary I/O failure while invalidating the saved IDs can mask the original recovery message with the backup location.
- 2026-11-09 validate: returned to build - Always report the voice-plan backup path even when Audio Blocks reconciliation fails
- 2026-11-09 build: red review 2: pytest -k recovery_invalidation_failed exits 1; the secondary locked Audio Blocks write prevents displaying the original recovery error
- 2026-11-09 build: green review 2: pytest Character Voices batch and Audio Blocks voice-target invalidation selectors exit 0 (9 passed); locked secondary write stays in the warning alongside the backup location. Ruff, delta audits, strict check and diff check pass.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Validate reconciliation: a secondary reconciliation I/O or value error is appended to the original failure; no backup message is lost.
- 2026-11-09 validate: final: uv run pytest -q tests/test_character_voices_service.py tests/test_character_voices_page.py tests/test_character_voices_ui_controller.py tests/test_audio_blocks_ui_controller.py -k 'edit_prompt_preserves_sample or edit_mode_disables_list or save_prompt_persists_preview_text or names_follow_ids or publication_restores_pair or batch_invalidates_only_saved_targets or cancelled_character_sample_batch or voice_target_invalidation' --tb=line --show-capture=no exit 0 (19 passed, 63 deselected). Earlier build ran 71 Character Voices and 21 related consumer tests. Ruff, both baseline-delta audits, git diff --check and AEGIS check --strict passed. AEGIS has 15 baseline warnings and 3 expected help/changelog layout notices. VoiceWeaver calls were simulated.
- 2026-11-09 validate: completed; next done
- 2026-11-09 done: Operator confirmed manual checks for Edit/Cancel/Save, sample replacement and batch interruption after the first sample was saved.

## Rulings


## State

status: done
reported: validate - completed
next: implementation guidance complete; commit, push and integration belong to the developer
must_read: .agentic/tasks/TASK-b87d0a4d.md
changed: Character Voices draft, ID-based sample pairs, selective batch invalidation, and bilingual help.
evidence: 19 final targeted tests passed. Ruff, audits, diff and AEGIS strict checks passed.
issues: Full suite omitted as requested. VoiceWeaver simulated. Advisory warnings recorded.
spec_compliance: approved
implementation_quality: approved
review_round: 3

## Delivery report (2026-11-09)

- stage: validate; type: change; path: full; branch: master
- requirements:
  - REQ-FUNC-beaae82d - The Character Voices controller shall expose an explicit edit/save flow
  - REQ-FUNC-d15dae2c - Character sample filenames derive from target IDs
  - REQ-REL-9b792ec3 - Character sample publication preserves the WAV and transcript pair
  - REQ-FUNC-efab6267 - Interrupted character sample batches reconcile persisted progress
  - REQ-FUNC-b8d5f669 - Saving a changed character voice draft clears its sample
  - REQ-FUNC-86edfc26 - Saving an unchanged character voice draft preserves its sample
- deviations: 1 recorded
  - validate: full check --run omitted at user request. Final proof uses focused Character Voices and consumer pytest selectors, Ruff, baseline-delta audits, diff check and strict AEGIS check.
- explicit review: enabled; spec_compliance=approved; implementation_quality=approved; review_round=3
- diff vs task base 825f149: 23 file(s) changed, 844 line(s) added
- checks: errors=0 warnings=18 notes=2
- checklist: 9/9 done
