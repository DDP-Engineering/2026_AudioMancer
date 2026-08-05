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

# TASK-fa71d059 — Stabilize AI translation review UI

stage: done
type: fix
path: full
requirements: REQ-FUNC-9a7e98c9, REQ-UX-7e8fb80a, REQ-UX-31620904, REQ-UX-1373b3b5, REQ-UX-eb55be5b, REQ-UX-3dae2eb0, REQ-FUNC-ee95beb7
branch: bugfix/improvements
opened: 2026-08-05

## Done checklist (current stage)

- [x] `check --strict --run` green - where "green" means: no errors, no
      failures the diff introduced, warnings fixed or explained, and any
      pre-existing base-branch failures logged as out-of-scope future
      tasks; the evidence line is in the log
- [x] diff reviewed against scope, requirements, design, error paths,
      portability, security - no unrequested changes
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report inside the delivery commit; agreed outcome
      delivered (PR by default)
- [x] close-out: `stage: done` set and committed only after the outcome
      succeeded
- [x] the project items from `.agentic/PROJECT.md` ("Delivery checklist
      additions") - code style, and for a release the four-place version
      workflow

## Log

- 2026-08-05 frame: Scope covers preserving translation-editor state and selected profile across refreshes, flushing pending edits before worker start, and gating selected-chunk retranslation until translation has started.
- 2026-08-05 frame: Exclusions are analysis-file edits, translation semantics and prompts, retranslation failure status, broader persistence redesign, downstream workflow changes, release/version work, commits, pushes, and unrelated cleanup.
- 2026-08-05 frame: Full path selected because the fixes change observable UI state, debounced persistence ordering, and worker-start safety across page, state, window, and controller boundaries.
- 2026-08-05 frame: Existing debounce/flush requirement will cover pre-start persistence ordering; separate requirements are proposed for same-content editor refresh preservation, live profile preservation with fallback, and unavailable retranslation gating.
- 2026-08-05 frame: The prompt's autonomous delivery-preparation direction is treated as autopilot, so the scope checkpoint is logged and work continues without a pause.
- 2026-08-05 specify: Updated REQ-FUNC-9a7e98c9 for exact edit-before-worker ordering and added its signal-ordering specification.
- 2026-08-05 specify: Added separate editor-preservation, authoritative-refresh, stable-chunk-selection, live-profile-selection, action-availability, and defensive-retranslation requirements so each behavior remains independently verifiable.
- 2026-08-05 specify: Added focused specifications for editor document preservation, profile fallback propagation, and the pre-translation controller boundary.
- 2026-08-05 specify: Advisory check reported zero errors; 21 warnings were read and are pre-existing unrelated ticket/layout findings or expected planning/help/changelog paths outside configured source globs.
- 2026-08-05 design: Design check reported zero errors and the same 21 previously dispositioned warnings.
- 2026-08-05 build: `test_ai_translation_page.py::test_same_content_refresh_preserves_editor_state_and_continued_typing` red as expected because list reconstruction cleared both editors and reset source state to cursor/anchor/scroll zero.
- 2026-08-05 build: `test_ai_translation_page.py::test_start_translation_flushes_pending_edit_before_signal_and_stops_timer` red as expected because Start emitted before the pending edit and left the debounce timer active.
- 2026-08-05 build: profile state/main-window selection tests red as expected because the state builder accepted no live profile candidate and refresh reset `profile_b` to configured default `profile_a`.
- 2026-08-05 build: `test_ai_translation_page.py::test_retranslate_selected_requires_started_idle_translation_state` red as expected because a selected chunk enabled Re-Translate Selected while status was `not_started`.
- 2026-08-05 build: `test_ai_translation_ui_controller.py::test_retranslate_before_translation_start_is_inert` red as expected because the controller prompted and prepared a worker without an authoritative translation document.
- 2026-08-05 build: controller integration now proves the mocked worker observes `Latest exact edit` from authoritative storage before dispatch completes.
- 2026-08-05 build: authoritative-content and stable-chunk-ID regression tests passed as characterization coverage after the shared editor refresh change; both behaviors already existed and were retained rather than reimplemented.
- 2026-08-05 build: Focused AI Translation page, state, service, controller, and main-window profile set passed 39 tests in 30.70 seconds; changed-file Ruff and Python compilation checks passed.
- 2026-08-05 build: `aegis.py test --impacted` selected 387 references but exited 127 before pytest because configured app-directory execution received repository-root selectors; direct focused tests were used and the full suite remains scheduled once for delivery.
- 2026-08-05 build: Advisory check reported zero errors; accepted the same 21 pre-existing ticket/layout warnings because the unrelated ticket reference and configured documentation/planning layout are outside this task, and the planning-analysis folder remains untouched.
- 2026-08-05 deliver: Updated AI Translation ownership/behavior knowledge, both user guides, and the Unreleased changelog entry without assigning a release version.
- 2026-08-05 deliver: `check --strict --run` exit 0; the configured full pytest suite passed in 1497.4 seconds and strict reported zero errors.
- 2026-08-05 deliver: Accepted the unrelated existing ticket-reference warning and 18 global uncovered-source warnings because none names a file changed by this task.
- 2026-08-05 deliver: Accepted outside-layout warnings for both required help files and `CHANGELOG.md`; the planning-analysis folder remains read-only/untracked, and unchanged `HowToTest.md` is outside configured source globs.
- 2026-08-05 deliver: The unticked-deliver warning is expected until semantic review, report generation, explicit no-commit close-out, and staging are complete.
- 2026-08-05 deliver: Semantic diff review found no unrequested changes, unsafe paths, secret exposure, portability regressions, or error-path gaps; one missing removed-profile fallback assertion was added and its focused test passed.
- 2026-08-05 deliver: Re-read all seven requirements and four specifications; statuses, prose, source ownership, and linked selectors match the implementation and tests.
- 2026-08-05 deliver: The initiating brief explicitly confirms a staged-only delivery with no commit or push, overriding the generic commit/PR checklist outcome for this task.
- 2026-08-05 deliver: Staged the exact 24 task-owned files with 1260 insertions and 38 deletions; the read-only planning-analysis directory is the only remaining unstaged worktree path.
- 2026-08-05 close-out: Task closed after the requested staged-only outcome; no commit or push was performed.

## Design

- Components: page owns editor-document preservation, debounce ordering, stable chunk identity, and button state (REQ-UX-7e8fb80a, REQ-UX-31620904, REQ-UX-1373b3b5, REQ-UX-3dae2eb0, REQ-FUNC-9a7e98c9).
- Components: main window captures the live profile, while the state service owns enabled/default/first fallback resolution (REQ-UX-eb55be5b).
- Components: the translation controller owns the defensive no-document retranslation precondition (REQ-FUNC-ee95beb7).
- Interface: add one optional selected-profile argument to `build_ai_translation_state`; page and controller signal signatures remain unchanged (REQ-UX-eb55be5b).
- Data: keep profile choice session-local and preserve the existing translation document/settings formats (REQ-UX-eb55be5b, REQ-FUNC-9a7e98c9).
- Editor decision: compare exact strings independently and call `setPlainText` only on real changes, with the translated loading guard scoped to that assignment (REQ-UX-7e8fb80a, REQ-UX-31620904).
- Ordering decision: flush synchronously at the start action before emitting worker intent; busy state only adds a defensive timer stop (REQ-FUNC-9a7e98c9).
- Boundary decision: reject retranslation when no started document exists before profile resolution, prompting, or worker dispatch (REQ-FUNC-ee95beb7).
- Rejected alternative: snapshotting/restoring cursors, undo stacks, and scroll bars after every `setPlainText` was rejected because Qt undo history is document-owned and identical content needs no mutation (REQ-UX-7e8fb80a).
- Test seams: page Qt tests cover refresh state, continued typing, stable IDs, signal order/timer state, and action gating (all page-owned requirements).
- Test seams: state-service and main-window tests cover live selection propagation and fallback; controller tests cover persisted-edit worker visibility and inert invalid retranslation (REQ-UX-eb55be5b, REQ-FUNC-9a7e98c9, REQ-FUNC-ee95beb7).
- Expected source files: `ai_translation_page.py`, `ai_translation_state_service.py`, `main_window.py`, and `ai_translation_ui_controller.py`; focused tests, contracts, knowledge, user help if wording is affected, changelog, and this journal complete delivery evidence.

## Delivery report (2026-08-05)

- stage: deliver; type: fix; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-9a7e98c9 - Flush pending translation edits before worker dispatch
  - REQ-UX-7e8fb80a - Preserve translation editor context on same-content refresh
  - REQ-UX-31620904 - Apply authoritative translation editor content when it changes
  - REQ-UX-1373b3b5 - Preserve selected translation chunk across state rebuilds
  - REQ-UX-eb55be5b - Preserve the selected enabled translation profile across refreshes
  - REQ-UX-3dae2eb0 - Gate selected-chunk retranslation on started translation state
  - REQ-FUNC-ee95beb7 - Reject selected-chunk retranslation before translation starts
- task-owned staged diff: 24 file(s) changed, 1260 insertion(s), 38 deletion(s)
- checks: errors=0 warnings=40 notes=0
- checklist: 7/8 done; open: close-out: `stage: done` set and committed only after the outcome
