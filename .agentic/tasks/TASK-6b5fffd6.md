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

# TASK-6b5fffd6 — Synchronized Cleanup downstream invalidation

stage: done
type: fix
path: full
requirements: REQ-FUNC-2ab78634
branch: bugfix/improvements
opened: 2026-08-03

## Done checklist (current stage)

- [x] `check --strict --run` green with evidence in the log
- [x] diff reviewed against scope, requirements, design, error paths,
      portability, security, and unrequested changes
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] delivery endpoint confirmed by the user: stop before commit or push
- [x] journal and report prepared without committing or pushing
- [x] close-out: `stage: done` set and committed only after the outcome succeeds
- [x] code follows `01_Documentation/Code_Style.md`
- [x] release version workflow not applicable because this task is not a release

## Log

- 2026-08-03 frame: Scope is synchronized Chunking-and-downstream artifact and compact-summary invalidation after automatic or manual canonical Cleanup publication, including coherent reopen and surfaced persistence failures; downstream algorithms and commit/push are excluded.
- 2026-08-03 frame: Full path selected because the fix changes externally observable persisted workflow state and requires an ownership-and-ordering contract.
- 2026-08-03 frame: Current code reverification found both Cleanup publication paths call the centralized artifact reset but then use the promote-only single-summary sync, leaving completed downstream summaries and a higher stage in project.json.
- 2026-08-03 frame: Update existing REQ-FUNC-2ab78634 and its cleanup_chunking specification; do not create a duplicate requirement.
- 2026-08-03 frame: Autonomous delivery requested, so the frame checkpoint is logged and work continues without pausing.
- 2026-08-03 specify: Expanded REQ-FUNC-2ab78634 into a self-contained automatic-and-manual publication requirement with concrete regressions and documented the shared ownership and persistence ordering in cleanup_chunking.spec.md.
- 2026-08-03 specify: Advisory check reported no errors; the existing ticket reference in unrelated REQ-UX-4753a4bf and the user-owned untracked planning-analysis directory account for all 17 warnings and are outside this task's mutation scope.
- 2026-08-03 design: Chose one Cleanup-owned publication helper backed by a Project Lifecycle manifest-reset builder, with centralized artifact deletion retained and a single final manifest save; tests attach at both Cleanup service entry paths and the manifest persistence boundary.
- 2026-08-03 build: Automatic and manual synchronized-publication regressions red as expected because downstream files were removed while every seeded compact summary remained completed; both persistence-failure cases already propagated without a 100-percent report.
- 2026-08-03 build: The implemented shared publication transition passed 121 focused tests with 1 skip, including Cleanup, manifest healing, reset ownership, Home-controller, and reopen coverage.
- 2026-08-03 build: `aegis.py test --impacted` could not launch its 115 selected node IDs because the generated Windows command line exceeded the platform limit; the same focused areas passed directly and the delivery full suite remains mandatory.
- 2026-08-03 build: Advisory check reported no errors; accepted the unrelated existing ticket reference in REQ-UX-4753a4bf and all 16 outside-layout warnings for the user-owned untracked planning-analysis directory because neither belongs to this task's mutation scope.
- 2026-08-03 deliver: `check --strict --run` exited 0 after the complete configured pytest suite passed in 1310.7 seconds; collection reports 1210 selected tests and 1 deselected.
- 2026-08-03 deliver: Accepted strict uncovered-source warnings for import_service.py, operation_runtime_service.py, and home_ui_controller.py because they are unchanged pre-existing branch work outside this task's diff.
- 2026-08-03 deliver: Accepted the unrelated existing REQ-UX-4753a4bf ticket-reference warning and 16 outside-layout warnings for the untouched user-owned planning-analysis directory.
- 2026-08-03 deliver: `ruff check src tests`, py_compile for every changed Python file, and `git diff --check` all passed.
- 2026-08-03 deliver: Semantic diff review confirmed centralized artifact ownership, synchronized manifest reset, propagated failure paths, cross-platform path handling, no secret exposure, and no changes to downstream algorithms.
- 2026-08-03 deliver: Updated Text Cleanup, Project Lifecycle, and Operation Orchestration knowledge and Files sections, plus Unreleased user-facing changelog and both language guides.
- 2026-08-03 deliver: `check --full` reported zero errors and 21 warnings; accepted the two guide and changelog outside-layout warnings as intentional delivery documentation, the 16 planning warnings as untouched user-owned inputs, the unrelated ticket-reference warning, and the current unticked-deliver warning because no commit or close-out is authorized.
- 2026-08-03 deliver: No version bump was applied because this fix is not a release; the existing 2.0.0 identifiers remain synchronized.
- 2026-08-03 deliver: Delivery report prepared; its merge-base total includes earlier branch work and the user-owned planning inventory, while this task's scoped worktree changes are the 12 reviewed tracked files plus this journal.
- 2026-08-03 deliver: Final `check --full` after report preparation retained zero errors and reduced to 20 explained warnings; `git diff --check` passed and HEAD remained f2c71ab with no commit or push performed.
- 2026-08-03 deliver: Corrected the close-out checklist item to remain unticked because the requested pre-commit delivery endpoint does not authorize setting `stage: done`.
- 2026-08-03 deliver: The user manually tested TC-2 successfully and authorized the implementation commit, with no push requested.
- 2026-08-03 done: Implementation commit 0e8467f succeeded, so the AEGIS journal is closed without pushing.

## Design

- Components: Text Cleanup owns publication, Operation Orchestration retains centralized artifact deletion, and Project Lifecycle owns compact-manifest reset construction (REQ-FUNC-2ab78634).
- Interface: expose `project_workspace_service.build_manifest_after_operation_reset`, with existing Text Cleanup state helpers delegating for compatibility, and add one private Cleanup publication helper shared by automatic and manual paths (REQ-FUNC-2ab78634).
- Storage: after in-memory validation, reset Chunking and downstream files, atomically persist cleaned text and Cleanup metadata, then reload and atomically save one manifest containing both the completed Cleanup summary and reset downstream summaries at `text_chunking_ready` (REQ-FUNC-2ab78634).
- Failure: manifest or artifact persistence exceptions propagate before automatic progress reaches 100 percent or either service call returns success (REQ-FUNC-2ab78634).
- Rejected alternative: importing `text_cleanup_state_service` into `text_cleanup_service` would create a dependency cycle, while duplicating summary reset logic would split ownership and drift from the artifact registry (REQ-FUNC-2ab78634).
- Test seams: service-level automatic publication and manual-edit tests seed completed summaries plus representative real artifacts for every downstream operation and reopen through `project_workspace_service.open_project`; a parameterized save-manifest failure test covers both publication paths (REQ-FUNC-2ab78634).
- Expected implementation files: `project_workspace_service.py`, `text_cleanup_state_service.py`, `text_cleanup_service.py`, and `test_cleanup_service.py`; delivery also updates the three affected knowledge pages, release files, requirement/spec, and this journal.

## Delivery report (2026-08-03)

- stage: deliver; type: fix; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-2ab78634 - Cleanup publication shall invalidate every downstream operation coherently
- diff vs merge base: 37 file(s) changed, 4708 line(s) added
- checks: errors=0 warnings=24 notes=0
- checklist: 8/9 done; open: journal and report prepared without committing or pushing
