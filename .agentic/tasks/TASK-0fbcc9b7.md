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

# TASK-0fbcc9b7 — Preserve Speech Block edit integrity

stage: deliver
type: fix
path: full
requirements: REQ-UX-6d27b63d, REQ-FUNC-35098598
branch: ddp/sbu5-sbu6-edit-integrity
opened: 2026-08-09

## Done checklist (current stage)

- [x] focused/affected tests and strict static check complete; full suite explicitly deferred by the user
- [x] diff reviewed against scope, requirements, design, error paths, portability, and security
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report prepared inside the delivery commit
- [ ] close-out: `stage: done` set and committed only after the outcome succeeded
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` Unreleased entry written in user language

## Log

- 2026-08-09 frame: Scope confirmed by the delegated prompt covers edit-mode control locking and language-safe draft preservation plus persistence-free edit entry and commit-owned warning cleanup; planning files, public or persisted formats, confirmation behavior, and unrelated Speech Blocks behavior are excluded.
- 2026-08-09 frame: Full path chosen because the fixes change externally observable review behavior across the Qt page and controller, with REQ-UX-6d27b63d created and REQ-FUNC-35098598 updated.
- 2026-08-09 specify: REQ-UX-6d27b63d defines active-editor integrity and REQ-FUNC-35098598 now makes warning cleanup conditional on a successful authoritative save.
- 2026-08-09 specify: AEGIS check reported no errors and only the repository's existing 80 advisory warnings.

## Design

- Components: change only the Speech Blocks Qt page for edit-state gating and the Speech Blocks controller for edit-entry persistence behavior.
- Interface: preserve all public signals and controller signatures; REQ-UX-6d27b63d changes only widget enablement and localization refresh internals.
- Data: introduce no schema or storage changes; REQ-FUNC-35098598 keeps warning flags in the authoritative document until `update_speech_block` succeeds.
- Language refresh: while editing, relabel visible UI and list rows but skip `_show_selected_block`, then reapply control state so editor documents, caret, and selection remain untouched (REQ-UX-6d27b63d).
- Control gate: disable the profile, chunk, split, generate, approve-all, and reset controls through the existing `_editing` state while preserving every non-editing predicate (REQ-UX-6d27b63d).
- Edit entry: remove the warning-clear persistence and review-summary projection refresh; retain the existing audio-reset confirmation before the editor unlocks (REQ-FUNC-35098598).
- Rejected alternative: confirmation prompts on every conflicting control would duplicate controller flows and still leave programmatic language refresh vulnerable.
- Test seams: real Qt page tests cover dialogue and Scene Ambience drafts plus selection, while controller service spies cover warned Edit, declined Edit, successful Save, and failed Save.
- Expected source/tests: `speech_blocks_page.py`, `speech_blocks_ui_controller.py`, `test_speech_blocks_page.py`, and `test_speech_blocks_ui_controller.py`.
- 2026-08-09 build: REQ-UX-6d27b63d page selectors were red as expected because edit mode left the profile and workflow controls enabled and language application replaced typed dialogue and Scene Ambience payloads.
- 2026-08-09 build: REQ-FUNC-35098598 controller selector was red as expected because entering Edit called `clear_speech_block_warning_flags` for a warned block.
- 2026-08-09 build: Nine linked dialogue, ambience, controller, and authoritative-service selectors passed after the minimal page and controller fixes.
- 2026-08-09 build: The configured `test --impacted` command was not invoked because it requires prohibited `uv`; the equivalent linked selectors ran directly with the mandated interpreter and explicit worktree `PYTHONPATH`.
- 2026-08-09 build: Complete page/controller/service validation produced 130 passes plus the two known base-lineage offscreen-font Qt failures for header geometry and source-scroll restoration.
- 2026-08-09 build: The remaining six Speech Blocks modules passed 70 tests, Ruff and py_compile passed on all changed Python files, and strict static AEGIS reported no errors with 79 repository advisory warnings.
- 2026-08-09 deliver: The earlier two Qt failures were caused by an invalid explicit `QT_QPA_PLATFORM=offscreen` override, not base debt; the normal Windows platform passed both selectors alone and in both new-test orderings, followed by 132 complete page/controller/service passes.
- 2026-08-09 deliver: Per the authoritative workflow update, the repository full suite and settings bootstrap are deferred to the root task after all remaining plan batches are integrated; this delivery runs only focused and affected Speech Blocks plus static validation.
- 2026-08-09 deliver: Relevant Speech Blocks validation totals 202 passes across the complete page/controller/service modules and the remaining six Speech Blocks modules, with nine linked selectors separately green after their red evidence.
- 2026-08-09 deliver: Ruff, py_compile, and diff whitespace checks passed; static AEGIS strict check reported no errors and 80 repository advisory warnings, including the expected open-delivery checkpoint warning.
- 2026-08-09 deliver: Semantic diff review found only the requested UI/controller behavior, focused tests, AEGIS traceability, Speech Blocks knowledge, and Unreleased changelog changes, with no planning, format, schema, dependency, version, help, or unrelated edits.
- 2026-08-09 deliver: Human approval confirmed staged fingerprint `bd91c47a8a2e47ce9cce313ab4e788cdd35bfa92`, the exact 10-file scope, and all recorded validation evidence before commit.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: full; branch: ddp/sbu5-sbu6-edit-integrity
- requirements:
  - REQ-UX-6d27b63d - Preserve active Speech Block editor state
  - REQ-FUNC-35098598 - Persist Speech Block warning cleanup only on successful save
- approved checkpoint diff: 10 file(s) changed, 474 insertion(s), 26 deletion(s); fingerprint `bd91c47a8a2e47ce9cce313ab4e788cdd35bfa92`
- validation: 4 intended red failures before source edits; 9 linked selectors green; 202 affected Speech Blocks tests passed; Ruff, py_compile, and diff whitespace checks passed
- Qt isolation: the two existing selectors passed alone, after the new page selectors, and before them on the normal Windows platform; the complete page/controller/service run passed 132 tests
- checks: static AEGIS strict result errors=0 warnings=80 notes=0; full suite and settings bootstrap explicitly deferred by the user to the root integration task
- exclusions: no planning, persisted/public format, dependency, version, help, settings, push, merge, or unrelated changes
- checklist: 8/9 done; open: close-out `stage: done` after the delivery commit succeeds
