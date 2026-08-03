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

# TASK-bbb0ac2a — Transaction-safe source replacement

stage: done
type: fix
path: full
requirements: REQ-FUNC-b1f49831
branch: bugfix/improvements
opened: 2026-08-03

## Done checklist (current stage)

- [x] full suite and `check --full` completed with every warning explained and evidence logged
- [x] diff reviewed against scope, requirements, design, error paths, portability, and security with no unrequested changes
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read with status, prose, verification, and links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report inside the delivery commit and agreed outcome delivered
- [x] close-out stage set and committed only after the outcome succeeded
- [x] code follows `01_Documentation/Code_Style.md`
- [x] release-only changelog and four-place version workflow completed or recorded as not applicable

## Log

- 2026-08-03 frame: Scope is transaction-safe replacement of an unlocked project's stored source, including copy-first storage, reserved-name avoidance, centralized Extraction-and-downstream invalidation, manifest-summary reset, stage reset, and preservation of source registration and project options.
- 2026-08-03 frame: Character Discovery, Narrator Voice, Speech Blocks, Audio Blocks, Audio Assembly, and every unrelated review finding are excluded except for deleting their stale artifacts and resetting their compact summaries through existing centralized helpers.
- 2026-08-03 frame: The full path is required because source replacement changes externally observable persisted-data behavior and coordinates multiple failure-sensitive filesystem mutations.
- 2026-08-03 frame: Update existing durable requirement REQ-FUNC-b1f49831 and add a companion spec because transaction ordering and rollback boundaries are non-obvious.
- 2026-08-03 frame: Autopilot scope was accepted from the prompt without a frame checkpoint.
- 2026-08-03 verification: PL-1, PL-3, and PL-5 were reproduced against master commit db3ca666d22d2a38441e1ea29865c6a6f70ec60e before framing.
- 2026-08-03 specify: Expanded REQ-FUNC-b1f49831 instead of creating a semantic duplicate and added its companion transaction-ordering spec.
- 2026-08-03 specify: AEGIS check reported zero errors, one pre-existing non-layout ticket-reference warning, and sixteen user-owned planning-report layout warnings.
- 2026-08-03 test: test exit 0 (1369.8s)

## Design

- Components: source import, Home project lifecycle orchestration, and centralized operation artifact ownership are touched for REQ-FUNC-b1f49831.
- Interface: `import_source` retains its signature and return shape, while operation runtime exposes the exact reserved root-artifact names already owned by its reset registry for REQ-FUNC-b1f49831.
- Storage: source copying uses a same-project temporary file followed by atomic promotion, and failed copies remove that temporary file before the previous source can be unlinked for REQ-FUNC-b1f49831.
- Storage: replacement resets artifacts through `reset_extraction_and_downstream` and summaries through `build_manifest_after_extraction_reset`, then registers the safe new source without rewriting option fields for REQ-FUNC-b1f49831.
- Alternative rejected: duplicating generated-artifact names or downstream deletion lists in `import_service` or the Home controller was rejected because the centralized operation registry is the authoritative ownership boundary for REQ-FUNC-b1f49831.
- Test seam: `test_import_service.py` injects a partial copy failure and imports reserved names, while `test_home_ui_controller.py` replaces a processed source and observes artifacts, summaries, registration, stage, and options for REQ-FUNC-b1f49831.
- Expected source files: `import_service.py`, `operation_runtime_service.py`, and `home_ui_controller.py`; expected regression files: `test_import_service.py` and `test_home_ui_controller.py`.
- 2026-08-03 design: AEGIS check reported zero errors with the same one pre-existing ticket-reference warning and sixteen user-owned planning-report layout warnings.
- 2026-08-03 build: The new reserved-name, partial-copy-failure, and processed-project replacement regressions were red as expected because master used reserved destinations, deleted the old source before copying, retained completed summaries and stale artifacts, and rewrote unlocked options.
- 2026-08-03 build: The exact 55-test impacted selection passed as 63 passed and 1 skipped after removing the duplicated application-path prefix produced by the configured AEGIS command.
- 2026-08-03 build: The AEGIS impacted wrapper itself exited 4 because `.agentic/aegis.toml` changes into the application directory while linked selectors retain repository-root prefixes, so this pre-existing workflow configuration defect remains out of scope.
- 2026-08-03 build: Full focused service and controller files passed 66 tests, and Ruff plus Python compilation passed on every changed Python file.
- 2026-08-03 build: Accepted the pre-existing ticket-ref warning in REQ-UX-4753a4bf and sixteen outside-layout warnings for the user's untracked planning-analysis directory because none belongs to this task's changes.
- 2026-08-03 deliver: The full configured suite exited 0 with 1205 passed, 1 skipped, 1 deselected, and the pre-existing Python audioop deprecation warning in 1368.40 seconds.
- 2026-08-03 deliver: The requested `check --full` exited 0 with zero errors and eighteen warnings comprising one pre-existing ticket reference, the expected unticked delivery checkpoint, and sixteen user-owned planning-report layout warnings.
- 2026-08-03 deliver: Accepted ticket-ref on REQ-UX-4753a4bf because the unchanged requirement's issue reference predates and is unrelated to source replacement.
- 2026-08-03 deliver: Accepted unticked-deliver on TASK-bbb0ac2a because human approval, commit, and close-out must remain unticked at this pre-commit checkpoint.
- 2026-08-03 deliver: Accepted sixteen outside-layout findings because `0_Planning/Analysis_2026-08-02/` is user-owned untracked input explicitly supplied for this task and was not modified.
- 2026-08-03 deliver: Updated Project Lifecycle and Operation Orchestration knowledge for copy ordering, reserved artifact names, centralized reset integration, summary reset, and option preservation.
- 2026-08-03 deliver: Re-read REQ-FUNC-b1f49831 and its spec and confirmed the active status, prose, affected paths, verification, and four linked selectors match the implementation.
- 2026-08-03 deliver: Semantic diff review found no changes outside source import, centralized artifact-name exposure, Home replacement orchestration, regression coverage, and required AEGIS documentation.
- 2026-08-03 deliver: Post-suite test-only strengthening proved that a reserved-name replacement is stored as extracted_text_1.txt and survives the reset, with its direct selector and Ruff both passing.
- 2026-08-03 deliver: This task is not a release, so CHANGELOG, version files, and bilingual help version workflow are not applicable and remain unchanged.
- 2026-08-03 deliver: Dan Pasare approved the delivery commit after manually testing the application, with no push authorized.
- 2026-08-03 deliver: The agreed outcome is one signed-off local commit on bugfix/improvements; PR, push, and close-out remain pending separate authorization.
- 2026-08-03 close-out: The owner accepted the local delivery and requested task closure; the planning-analysis documents remain untracked and excluded, and no push is authorized.

## Delivery report (2026-08-03)

- stage: deliver; type: fix; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-b1f49831 - Source replacement shall preserve one consistent project state
- diff vs merge base: 10 delivery file(s) changed, 485 line(s) added, 32 line(s) deleted; user-owned planning inputs excluded
- checks: errors=0 warnings=18 notes=0
- checklist: 8/9 done; open: close-out stage set and committed only after the outcome succeeded
