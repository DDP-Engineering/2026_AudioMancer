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

# TASK-bf5a9cc2 — Make Character Discovery resume progress and profile selection truthful

stage: done
type: feature
path: full
requirements: REQ-FUNC-32f94a76, REQ-FUNC-d9978521
branch: ddp/character-discovery-resume-profile-truth
opened: 2026-08-07

## Done checklist (current stage)

- [x] `check --strict --run` green, with inherited warnings explained in the log
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and code style
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and linked tests are true
- [x] delivery confirmed by the human before the commit
- [x] journal and report included in the delivery commit and the agreed branch push authorized
- [x] close-out: `stage: done` set and committed only after the delivery push succeeds
- [x] project delivery additions satisfied; this task is not a versioned release

## Log

- 2026-08-07 frame: Implement CD-9 truthful window progress and CD-10 truthful last-used profile selection, excluding CD-7 and CD-8 and all protected planning files.
- 2026-08-07 frame: Full path selected because this changes the strict characters.json contract, runtime persistence, public progress, and page selection behavior.
- 2026-08-07 frame: Proposed focused requirements cover persisted completed-window progress and persisted last-used enabled AI-profile selection.
- 2026-08-07 frame: Autopilot authorized through build; stop before final delivery for supervisor review.
- 2026-08-07 specify: Created REQ-FUNC-32f94a76 for strict persisted completed-window progress and REQ-FUNC-d9978521 for a strict credential-free last-used profile ID.
- 2026-08-07 specify: Wrote the paired format and selection-precedence specs; AEGIS check found no errors and only pre-existing layout/ticket warnings.

## Design

- REQ-FUNC-32f94a76: evolve both exact checkpoint phases with `completed_window_count` and `planned_window_count`; writers and validators carry the true baseline, and restore reads it directly rather than deriving it from a cursor or window size.
- REQ-FUNC-d9978521: evolve the exact root with `character_profile_id_last_used`; writers record only the invocation ID and state resolution accepts an enabled live page value before a valid persisted preference.
- `character_operation_summary` remains the shared projection seam for manifest and page notes; strict validation is the hard-break seam for invalid-document recovery.
- Tests attach to public interrupted/resume runs with real planned windows and to state/MainWindow refresh selection; reject compatibility repair because the document contract requires exact fields.
- Expected files: Character Discovery service/state, MainWindow, focused tests, requirements/specs, and Character Discovery knowledge page.
- 2026-08-07 design: AEGIS check remained error-free with the inherited layout/ticket warnings.
- 2026-08-07 design: Supervisor review added strict persisted planned-window counts for pre-resume manifest/page truth and required the active profile requirement to state its full selector behavior.
- 2026-08-07 build: tests/test_character_discovery_service.py::test_start_discovery_persists_one_authoritative_document and ::test_resume_state_keeps_window_counts_separate_from_chunk_cursor red as expected (missing last-used root ID and cursor returned as window count).
- 2026-08-07 build: tests/test_character_discovery_state_service.py::test_character_state_prefers_live_then_persisted_last_used_profile red as expected (no live-selection interface and strict root rejects persisted ID).
- 2026-08-07 build: Focused Character Discovery service/state/controller/page/MainWindow tests passed: 89 passed in 72.32s.
- 2026-08-07 build: Focused Ruff and Python compilation passed; `git diff --check` passed.
- 2026-08-07 build: AEGIS check reported no errors and only inherited layout/ticket warnings; `aegis test --impacted` produced invalid test paths after its documented `cd` and exited 127, so the explicit focused linked set was run directly instead.
- 2026-08-07 build: Updated strict checkpoint format with completed/planned windows, root last-used profile selection, projections, requirements, specs, and knowledge page; awaiting final independent review and supervisor checkpoint without entering delivery.
- 2026-08-07 build: Strict resume reviewer approved the final schema, persistence, projections, real variable-window interruption, repeated resume, and provider-failure coverage.
- 2026-08-07 build: UI/profile reviewer approved strict last-used profile persistence, live/persisted/default/first selection precedence, invalid recovery, and the corrected cancelled Resume controller test.
- 2026-08-07 build: Final focused Ruff, compilation, and diff-check verification passed; full suite, AEGIS report, staging, commit, and delivery remain intentionally deferred for supervisor review.
- 2026-08-07 build: Supervisor round one found only obsolete seven-field cross-consumer Character Discovery fixtures; updated valid translation-reset, export, and chunking-reset fixtures with the required credential-free last-used profile ID while preserving intentional malformed fixtures.
- 2026-08-07 build: Focused Character Discovery set passed again: 89 passed in 70.91s; specified cross-consumer set passed: 118 passed, 1 skipped in 157.57s.
- 2026-08-07 build: Expanded Ruff, py_compile, diff-check, and AEGIS check passed with only inherited AEGIS warnings; both independent reviewers approved the expanded fixture diff.
- 2026-08-07 build: Awaiting supervisor round-two review without running the full suite, AEGIS report, staging, commit, or delivery.
- 2026-08-07 deliver: Updated the English and Romanian Characters guide sections and the Unreleased changelog without changing a release version.
- 2026-08-07 deliver: The configured full suite passed with 1395 passed, 62 skipped, and 1 deselected in 1564.10 seconds.
- 2026-08-07 deliver: `aegis.py check --full` returned zero errors and 21 known ticket/layout warnings, while focused Ruff, py_compile, and diff-check passed.
- 2026-08-07 deliver: The journal was closed to `stage: done` before staging by supervisor instruction; no commit or push was performed.
- 2026-08-07 deliver: The journal returned to `stage: deliver` so the authorized delivery commit and push precede close-out as required by the current AEGIS contract.
- 2026-08-07 deliver: Delivery commit 284de99 was pushed successfully, so the task is now closed.

## Delivery report (2026-08-07)

- stage: build; type: feature; path: full; branch: ddp/character-discovery-resume-profile-truth
- requirements:
  - REQ-FUNC-32f94a76 - Character Discovery shall persist completed-window progress
  - REQ-FUNC-d9978521 - Character Discovery shall retain last-used enabled AI profile selection
- diff vs merge base: 199 file(s) changed, 20703 line(s) added
- checks: errors=0 warnings=50 notes=0
- checklist: 6/7 done; open: `stage: deliver`

## Delivery report (2026-08-07)

- stage: deliver; type: feature; path: full; branch: ddp/character-discovery-resume-profile-truth
- requirements:
  - REQ-FUNC-32f94a76 - Character Discovery shall persist completed-window progress
  - REQ-FUNC-d9978521 - Character Discovery shall retain last-used enabled AI profile selection
- diff vs merge base: 202 file(s) changed, 20917 line(s) added
- checks: errors=0 warnings=52 notes=0
- checklist: 7/8 done; open: close-out: `stage: done` set and committed only after the delivery push succeeds
