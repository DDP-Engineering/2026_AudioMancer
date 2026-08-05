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

# TASK-9bccaaba — Preserve translation review state and instruction intent

stage: done
type: fix
path: full
requirements: REQ-FUNC-a0ab9df4, REQ-FUNC-9889967c, REQ-FUNC-d911e006
branch: bugfix/improvements
opened: 2026-08-05

## Done checklist (current stage)

- [x] `check --strict --run` green, with warnings fixed or explained and evidence in the log
- [x] diff reviewed against scope, requirements, design, error paths, portability, and security
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, links all true
- [x] delivery confirmed by the initiating autopilot brief; commit and push intentionally omitted
- [x] journal report generated and read; exact task files staged
- [x] close-out: `stage: done` set after the requested staged-only outcome succeeds
- [x] changed code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` Unreleased section written in user language
- [x] non-release task: no version bump or help-file version update

## Log

- 2026-08-05 frame: Scope covers preserving unchanged review state and accrued usage when selected-chunk retranslation fails or is cancelled, retaining successful retranslation behavior, preserving main-batch resumable interruption statuses, and selecting normalized caller instructions only for new or existing non-resumable translation documents.
- 2026-08-05 frame: Exclusions are the read-only planning analysis, resolved findings, review-page and prompt-content redesign, general persistence changes, unrelated downstream components, release/version work, commits, pushes, and unrelated cleanup.
- 2026-08-05 frame: Full path selected because the fixes change persisted translation status and instruction semantics at a data-handling boundary and require independently verifiable contracts.
- 2026-08-05 frame: Proposed requirements are a distinct selected-retranslation interruption-state requirement and a distinct start/resume instruction-selection requirement, while the existing interruption requirement will be narrowed to the main batch contract.
- 2026-08-05 frame: Autopilot-to-deliver mode suppresses the scope checkpoint, so work continues autonomously on the existing bugfix/improvements branch.
- 2026-08-05 specify: Created separate functional requirements REQ-FUNC-a0ab9df4 for interrupted selected retranslation and REQ-FUNC-9889967c for state-aware instruction selection, each with a behavior matrix specification.
- 2026-08-05 specify: Narrowed REQ-FUNC-d911e006 to its distinct main-batch interruption contract and removed the selected-retranslation test link so batch failed/cancelled status remains independently protected.
- 2026-08-05 specify: Advisory check reported zero errors and 21 pre-existing warnings: one unrelated ticket reference plus configured help, changelog, test-guide, and read-only planning paths outside source/test globs.

## Design

- REQ-FUNC-a0ab9df4: In each `retranslate_chunk` exception handler, persist the local accrued token usage and `_review_status(document["chunks"])` without mutating chunks, general instructions, or budget metadata, then re-raise the original exception.
- REQ-FUNC-a0ab9df4: Keep successful retranslation mutation after the protected provider call so segment accumulation cannot leak partial text and only success replaces the selected text and clears its approval.
- REQ-FUNC-d911e006: Leave `start_or_continue_translation` exception handlers unchanged so main-batch failures and cancellations retain explicit resumable statuses.
- REQ-FUNC-9889967c: Select instructions once before prompt budgeting: persisted value for resumable documents or absent non-resumable input, otherwise the normalized caller value; write and pass that single value through existing code paths.
- REQ-FUNC-9889967c: Keep `retranslate_chunk` one-off instructions local and leave controller prompt behavior and persisted schema unchanged.
- REQ-FUNC-a0ab9df4: Test seams are service-level persisted documents across completed, review-pending, and in-progress states; provider cancellation/failure and segmented failure doubles; `translation_is_completed`; and successful retranslation regression coverage.
- REQ-FUNC-9889967c: Test seams are parameterized existing-document statuses, captured budget arguments and provider prompts, new-document normalization, durable instruction values, and one-off retranslation isolation.
- REQ-FUNC-d911e006: Existing batch interruption tests remain the seam proving `failed` and `cancelled` resumability is distinct.
- Rejected alternative: snapshot and restore the entire document on retranslation error because no chunk mutation occurs before success and rewriting a snapshot could discard legitimately accrued usage (REQ-FUNC-a0ab9df4).
- Expected implementation files are `ai_translation_service.py` and `test_ai_translation_service.py`; contracts, knowledge, changelog, and this journal complete delivery evidence for all three requirements.
- 2026-08-05 design: Advisory check reported zero errors and the same 21 pre-existing warnings dispositioned during specify; design is complete and the task advances to build.
- 2026-08-05 build: REQ-FUNC-9889967c instruction-selection regressions were red as expected because both non-resumable statuses sent stored instructions to budget calculation instead of the normalized new caller value, while all resumable and new-document characterization cases passed.
- 2026-08-05 build: REQ-FUNC-a0ab9df4 interruption regressions were red as expected because provider failure and cancellation stamped completed, review-pending, and in-progress documents with failed or cancelled despite unchanged chunks; the successful-retranslation characterization passed.
- 2026-08-05 build: The focused service module passed 25 tests, and the impacted AI Translation service, state, controller, page, and main-window selection set passed 52 tests in 22.77 seconds.
- 2026-08-05 build: `aegis.py test --impacted` selected 406 references but exited 127 before pytest because the existing app-directory command received repository-root selectors; the direct 52-test impacted selection passed instead.
- 2026-08-05 build: Changed-file Ruff and Python compilation checks passed, and the advisory check reported zero errors with the same 21 pre-existing warnings previously dispositioned.
- 2026-08-05 deliver: Updated AI Translation knowledge, both user guides because they document instruction entry and selected retranslation, and the Unreleased changelog without assigning a release version.
- 2026-08-05 deliver: `check --task TASK-9bccaaba --strict --run` exited 0; its configured full test command passed in 1569.0 seconds and strict reported zero errors.
- 2026-08-05 deliver: Read all 44 warnings: one unrelated existing ticket reference, one expected unticked-delivery marker, 22 inherited uncovered-source paths not changed by this task, and 20 configured outside-layout paths including required guides/changelog and the untouched planning analysis.
- 2026-08-05 deliver: Semantic review confirmed the source diff changes only state-aware instruction selection and selected-retranslation exception status derivation, leaves main-batch resumable status handling intact, and introduces no schema, controller, prompt-template, portability, security, or secret-handling change.
- 2026-08-05 deliver: Reviewed the test diff against every requested edge case and re-read all three requirements and both specifications; active status, prose, affected paths, and linked selectors match the implementation and passing tests.
- 2026-08-05 deliver: The initiating autopilot brief authorizes a staged-only close-out and explicitly forbids commit and push, which overrides the generic publish outcome for this task.
- 2026-08-05 deliver: Read the generated report; its 136-file merge-base comparison includes inherited branch history, while this task's staged diff is exactly 12 files with 765 insertions and 37 deletions.
- 2026-08-05 close-out: Staged the exact task-owned requirements, specifications, journal, knowledge, service, tests, bilingual guides, and changelog; the read-only planning-analysis directory is the only unstaged worktree path, and no commit or push was performed.

## Delivery report (2026-08-05)

- stage: deliver; type: fix; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-a0ab9df4 - Preserve review state when selected-chunk retranslation is interrupted
  - REQ-FUNC-9889967c - Honor caller instructions for non-resumable translation starts
  - REQ-FUNC-d911e006 - Preserve completed chunks during interrupted batch translation
- diff vs merge base: 136 file(s) changed, 13227 line(s) added
- checks: errors=0 warnings=44 notes=0
- checklist: 8/10 done; open: journal report generated and read; exact task files staged; close-out: `stage: done` set after the requested staged-only outcome succeeds

## Delivery report (2026-08-05)

- stage: done; type: fix; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-a0ab9df4 - Preserve review state when selected-chunk retranslation is interrupted
  - REQ-FUNC-9889967c - Honor caller instructions for non-resumable translation starts
  - REQ-FUNC-d911e006 - Preserve completed chunks during interrupted batch translation
- diff vs merge base: 136 file(s) changed, 13240 line(s) added
- checks: errors=0 warnings=43 notes=0
- checklist: 10/10 done
