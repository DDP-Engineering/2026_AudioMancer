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

# TASK-f4d812b8 — Character Discovery log and diagnostics truth

stage: done
type: change
path: full
requirements: REQ-FUNC-f5d9667f, REQ-FUNC-9b951004
branch: ddp/character-discovery-log-diagnostics-truth
opened: 2026-08-07

## Done checklist (current stage)

- [x] `check --strict --run` green, with inherited warnings explained in the log
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and code style
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links are true
- [x] delivery report generated and read; task remains `stage: deliver` with close-out unticked
- [x] exact requested files staged; no protected planning file is staged
- [x] project delivery additions satisfied; this task is not a versioned release
- [x] close-out: `stage: done` only after an authorized commit and push

## Log

- 2026-08-07 frame: Implement Character Discovery log-family lifecycle truth and durable rejected-candidate diagnostics, excluding unrelated logging refactors, the five protected planning files, and any commit or push.
- 2026-08-07 frame: Full path selected because both changes alter strict persisted data and user-visible operational projections.
- 2026-08-07 frame: The detached requested baseline was 285cd4f, so this work uses the dedicated ddp/character-discovery-log-diagnostics-truth branch at that exact commit without altering the occupied source branch.
- 2026-08-07 frame: The directive authorizes completion through reviewed staging without a commit; proposed requirements independently cover the Character Discovery log lifecycle and credential-free persisted rejected-candidate diagnostics.
- 2026-08-07 specify: Created REQ-FUNC-f5d9667f for the Character Discovery-only transaction-log family and REQ-FUNC-9b951004 for strict persisted rejected-candidate diagnostics.
- 2026-08-07 specify: Wrote the diagnostic format spec with explicit uniqueness, merge, ordering, count bounds, and cross-projection rules required for repeated-resume truth.
- 2026-08-07 specify: AEGIS check reported zero errors; the accepted inherited warnings are one historical ticket reference and twenty outside-layout paths, including protected planning and existing help/changelog files.

## Design

- REQ-FUNC-f5d9667f: the strict Character Discovery document never stores a log path and every resume-restoration return is `None`, so remove the unreachable reuse parameter/branch and create each invocation's log with the existing `character_discovery` operation token; retain the reset service's exact operation-family glob to preserve unrelated logs.
- REQ-FUNC-9b951004: add one exact root `rejected_candidates` array with a compact name/reason/count schema, restore it only from compatible state, and preserve it through all state writes and manual profile writes; project `len()` through the summary, localized note groups, and export parameter.
- REQ-FUNC-9b951004: normalize writer diagnostics by Unicode identity/reason, retaining the first display name and maximum counts before deterministic name/reason ordering; reject malformed or duplicate persisted entries rather than repairing the hard-break document.
- The rejected alternative is a checkpoint-only diagnostic list: completed documents have no checkpoint, so it cannot truthfully support UI, manifest, or export after completion.
- Test seams are public start/cancel/repeated-resume/reset runs in the service test, strict document fixtures, state notes and manifest summary, and the Character export parameter; expected files are the two services, export service, their focused tests, help, changelog, knowledge, requirements/spec, and this journal.
- 2026-08-07 build: New CD-7 and CD-8 tests were red as expected because Character Discovery still used the characters log token and rejected diagnostics were absent from the strict root and projections.
- 2026-08-07 build: Implemented the character_discovery log family, removed the unreachable resume-log path branch after confirming every restore return was None, and added strict compact rejected-candidate persistence with deterministic unique identity/reason ordering.
- 2026-08-07 build: Focused linked service/state/export tests, strict duplicate and out-of-order fixtures, Ruff, compilation, and diff check passed; the broader affected Character Discovery and cross-consumer set passed with 134 tests in 106.13 seconds.
- 2026-08-07 build: Updated the English and Romanian Character Discovery help, Character Discovery knowledge page, and Unreleased changelog without a version change.
- 2026-08-07 deliver: The configured full suite passed with 1408 passed, 62 skipped, and 1 deselected in 1736.30 seconds.
- 2026-08-07 deliver: A subsequent `check --strict --run` invoked the configured suite but the five-minute command wrapper timed out before output; this is not claimed as a test failure because the completed full suite above ran after implementation and the later change only corrected wording and a test variable name.
- 2026-08-07 deliver: `check --full` reported zero errors and 22 warnings: the current journal's unticked delivery checklist, one inherited ticket reference, and twenty-one established outside-layout paths including protected planning, help, changelog, and HowToTest files.
- 2026-08-07 deliver: Independent persisted-diagnostics/resume review found missing resumable-page notes; added a failing state regression, then projected the same strict diagnostics before completion and reran the 175-pass affected consumer set.
- 2026-08-07 deliver: Independent logging-lifecycle/UI-export review corrected reset wording to the established current-and-downstream scope, confirmed upstream Translation logs remain, and added the direct persisted-manifest warning-count assertion; the strengthened linked test passed.
- 2026-08-07 deliver: Re-read REQ-FUNC-f5d9667f and REQ-FUNC-9b951004: both are active, self-contained, linked to existing tests, and match the final strict document, resume, logging, UI, manifest, and export behavior.
- 2026-08-07 deliver: `check --task TASK-f4d812b8 --strict --run` completed with exit 0 after 1781.6 seconds; its configured full suite passed, and 50 advisory warnings are accepted only where inherited or expected for the open deliver checklist.
- 2026-08-07 deliver: Added ui_state_service.py to REQ-FUNC-9b951004 affected paths to resolve the task-introduced localization traceability warning before final report generation.
- 2026-08-07 deliver: The earlier design wording about preserving unrelated logs is superseded: Reset Discovery retains its established current-and-downstream scope; CD-7 only aligns the owned Character Discovery log family and verifies upstream Translation-log preservation.
- 2026-08-07 deliver: Accepted the final 49 warnings: one inherited ticket reference, twenty-seven inherited uncovered-source records outside this task, two expected current deliver checklist items before report/staging, and nineteen established protected-planning/layout paths plus the intentional help, changelog, and HowToTest outside-layout notices.
- 2026-08-07 deliver: Warning-category recount corrected the layout total to twenty (sixteen protected planning files, two help files, CHANGELOG.md, and HowToTest.md); the final pre-staging check has 49 warnings because only the staging checklist item remains unticked.
- 2026-08-07 deliver: Staged the exact CD-7/CD-8 implementation, tests, requirements/spec, knowledge, English/Romanian help, changelog, and journal; all five protected planning files remain untouched and unstaged, and close-out remains intentionally unticked because no commit or push was authorized.
- 2026-08-07 deliver: Delivery commit 4115ad0 was pushed successfully to origin, so the task is now closed.

## Delivery report (2026-08-07)

- stage: deliver; type: change; path: full; branch: ddp/character-discovery-log-diagnostics-truth
- requirements:
  - REQ-FUNC-f5d9667f - Character Discovery logs shall use the operation log family
  - REQ-FUNC-9b951004 - Character Discovery shall persist rejected-candidate diagnostics
- diff vs merge base: 206 file(s) changed, 21093 line(s) added
- checks: errors=0 warnings=49 notes=0
- checklist: 5/7 done; open: delivery report generated and read; task remains `stage: deliver` with close-out unticked; exact requested files staged; no protected planning file is staged

## Delivery report (2026-08-07)

- stage: deliver; type: change; path: full; branch: ddp/character-discovery-log-diagnostics-truth
- requirements:
  - REQ-FUNC-f5d9667f - Character Discovery logs shall use the operation log family
  - REQ-FUNC-9b951004 - Character Discovery shall persist rejected-candidate diagnostics
- diff vs merge base: 206 file(s) changed, 21105 line(s) added
- checks: errors=0 warnings=49 notes=0
- checklist: 6/7 done; open: exact requested files staged; no protected planning file is staged

## Delivery report (2026-08-07)

- stage: deliver; type: change; path: full; branch: ddp/character-discovery-log-diagnostics-truth
- requirements:
  - REQ-FUNC-f5d9667f - Character Discovery logs shall use the operation log family
  - REQ-FUNC-9b951004 - Character Discovery shall persist rejected-candidate diagnostics
- diff vs merge base: 206 file(s) changed, 21118 line(s) added
- checks: errors=0 warnings=49 notes=0
- checklist: 7/8 done; open: close-out: `stage: done` only after an authorized commit and push
