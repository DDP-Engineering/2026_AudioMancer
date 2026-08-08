<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->

<!--
Task journal. One file per task, at .agentic/tasks/TASK-<id>.md, kept
after delivery as the task's historical record.

The header is the block of "key: value" lines directly under the title.
Keep it exactly in that form — one key per line, no blank lines inside
the block, no comments between the lines — so it stays machine-readable.

  stage         frame | specify | design | build | deliver | done
                (adoption journals: survey | components | close | done)
  type          feature | fix | change | adopt
  path          full | quick
  requirements  comma-separated requirement IDs, empty until specify
  branch        the branch this task is delivered on
  opened        YYYY-MM-DD

Header lines are edited in place; log lines are only ever appended.
Keep each log line to one sentence.
-->

# TASK-9ac2174d — Correct narrator profile retry prompts and resume count

stage: done
type: fix
path: full
requirements: REQ-FUNC-77887760, REQ-FUNC-e0f33d10
branch: ddp/nv3-nv4-narrator-retry-resume
opened: 2026-08-08

## Done checklist (current stage)

- [x] `check --strict --run` green or only accepted inherited findings remain
- [x] diff reviewed against scope, requirements, design, error paths, portability, and security
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report prepared for the delivery commit without committing
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` Unreleased section written in user language
- [x] non-release version remains unchanged and both help files describe visible behavior
- [x] close-out: set `stage: done` and commit only after the outcome succeeds

## Log

- 2026-08-08 frame: Correct only narrator-generation retry instructions and checkpoint count defaults, excluding NV-5 and later findings, service compatibility changes, duplicate state, releases, commits, pushes, merges, PRs, and task close-out.
- 2026-08-08 frame: Full path selected because both fixes change operator-visible retry behavior and require two new independently verifiable functional requirements.
- 2026-08-08 frame: Current 2a38c5b code still suppresses all unfinished-state instruction prompts and seeds every count dialog from configuration, while the service already owns the complete source/profile/model/budget/count/instruction fingerprint.
- 2026-08-08 frame: The analysis suggestion to conditionally skip the prompt when a checkpoint is reusable is superseded by the requested behavior to prompt on every attempt and pass every accepted value explicitly.
- 2026-08-08 frame: Proposed REQ-FUNC-77887760 covers retry instruction prompting, prefill, explicit edit/clear propagation, and pre-worker cancellation.
- 2026-08-08 frame: Proposed REQ-FUNC-e0f33d10 covers bounded resume-count defaults with safe configuration fallback for completed, missing, invalid, or malformed state.
- 2026-08-08 specify: Created REQ-FUNC-77887760 and REQ-FUNC-e0f33d10 as the two independently testable behaviors; no separate specs are needed because their requirements and verification cases fully define the controller contract.
- 2026-08-08 specify: Advisory check reported no errors; inherited ticket-reference and repository layout warnings remain for delivery review.

## Design

- Components: the Narrator Voice controller owns both dialog defaults; the generation service remains authoritative for checkpoint compatibility and token accounting (REQ-FUNC-77887760, REQ-FUNC-e0f33d10).
- Interface: extend the internal instructions prompt helper with an initial-text argument and replace the misleading resume predicate with defensive dialog-state/default helpers (REQ-FUNC-77887760, REQ-FUNC-e0f33d10).
- Data: read the existing derived operation state once, persist nothing new, accept only unfinished AI checkpoints with integer counts inside the Qt range, and pass every accepted instruction value as a string (REQ-FUNC-77887760, REQ-FUNC-e0f33d10).
- Error path: unreadable or contract-invalid narrator state yields the configuration count and blank instructions without starting from an invalid Qt default (REQ-FUNC-e0f33d10).
- Rejected alternative: predicting full checkpoint compatibility in the UI would duplicate and risk weakening the service fingerprint, so the UI only restores truthful inputs and lets the service decide reuse (REQ-FUNC-77887760, REQ-FUNC-e0f33d10).
- Test seams: controller tests capture multiline prefill, explicit worker arguments, cancellation, and QInputDialog defaults; service tests exercise unchanged versus changed count/instruction fingerprints and token-preserving observations (REQ-FUNC-77887760, REQ-FUNC-e0f33d10).
- Expected files: controller and controller/service tests, both requirements, task journal, Voice Profiles knowledge, changelog, and English/Romanian narrator help.
- 2026-08-08 design: Design recorded without a separate spec, affected paths remain limited to the existing controller/service contracts, and advisory check had no format errors.
- 2026-08-08 build: tests/test_narator_voice_ui_controller.py retry instruction regressions red as expected because failed/cancelled attempts skipped the prompt, edited/cleared values remained None, and instruction cancellation still started the worker.
- 2026-08-08 build: tests/test_narator_voice_ui_controller.py::test_narator_voice_generate_profiles_unfinished_checkpoint_seeds_saved_count red as expected because QInputDialog received 6 instead of the checkpointed 12.
- 2026-08-08 build: Focused narrator controller, generation, definition, page, single-document, and operation-runner regressions passed with 87 tests.
- 2026-08-08 review-1: Fingerprint/checkpoint/token-cost review found the full service fingerprint unchanged and confirmed unchanged explicit inputs preserve observations and token usage; added the missing cleared-instruction incompatibility case, which passed with changed count and edited-instruction cases.
- 2026-08-08 build: `test --impacted` could not execute because the inherited Windows command expands 606 repo-relative selectors beyond the shell command limit; focused linked coverage passed manually and the full configured suite remains required at delivery.
- 2026-08-08 build: Advisory check had no errors; accepted inherited ticket-reference warning belongs to REQ-UX-4753a4bf and outside-layout warnings reflect configured repository layout for help, changelog, HowToTest, and untouched planning evidence.
- 2026-08-08 review-2: Dialog/default/cancellation/UI/docs/error review corrected ambiguous count-clearing wording in both help files and added direct proof that persisted text reaches the multiline dialog; 16 generation UI and 11 localization/help tests passed.
- 2026-08-08 deliver: Initial configured full-suite attempt timed out at 30 minutes with exit 124 after reaching 52 percent and showing no failures, so it was not counted as completed evidence.
- 2026-08-08 deliver: A second outer 70-minute attempt confirmed the inherited AEGIS command timeout itself stops the suite at 1,800 seconds, so the configured timeout was temporarily raised to 4,200 seconds for complete delivery verification and will be restored before staging.
- 2026-08-08 deliver: Complete configured suite passed with 1434 passed, 62 skipped, and 1 deselected in 1834.83 seconds.
- 2026-08-08 deliver: `check --task TASK-9ac2174d --strict --run` exited 0 with the configured test command successful in 1842.2 seconds and `strict: ok`.
- 2026-08-08 deliver: Accepted inherited ticket-reference, merge-base uncovered-source, and planning/HowToTest outside-layout warnings because they are unchanged at the required 2a38c5b base; required help/changelog outside-layout warnings reflect project-owned delivery files.
- 2026-08-08 deliver: The temporary AEGIS timeout override was restored, both active requirements and every linked selector were re-read as true, and this remains a non-release delivery with version 2.0.0 unchanged.
- 2026-08-08 close-out: Delivery commit 7da7080 succeeded; the task is now complete.

## Delivery report (2026-08-08)

- stage: deliver; type: fix; path: full; branch: ddp/nv3-nv4-narrator-retry-resume
- requirements:
  - REQ-FUNC-77887760 - Reprompt narrator profile instructions on every generation attempt
  - REQ-FUNC-e0f33d10 - Seed narrator profile count from a valid unfinished checkpoint
- diff vs merge base: 221 file(s) changed, 22490 line(s) added
- checks: errors=0 warnings=56 notes=0
- checklist: 9/10 done; open: close-out: set `stage: done` and commit only after the outcome succeeds

## Report review

- 2026-08-08 deliver: Read the generated report; its 221-file merge-base diff includes inherited bugfix/improvements work already present at required base 2a38c5b, while this task stages only the explicitly listed NV-3/NV-4 files.
