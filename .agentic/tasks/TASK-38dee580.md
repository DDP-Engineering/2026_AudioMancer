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

# TASK-38dee580 — Fix Text Cleanup save exit and Home project activation

stage: deliver
type: fix
path: quick
requirements: REQ-UX-6fb5efc7
branch: ddp/fix-text-cleanup-home-activation
opened: 2026-08-09

## Done checklist (current stage)

- [x] task-scoped strict check has no errors or task-introduced failures, with the explicitly excluded full suite left to orchestration
- [x] diff reviewed against scope, requirements, error paths, portability, security, and code style
- [x] Text Cleanup knowledge page updated for the changed edit-session behavior
- [x] REQ-UX-6fb5efc7 re-read with active status, current prose, affected paths, and linked tests
- [x] delivery confirmed by the human before the commit
- [x] journal and report included in the approved delivery commit
- [ ] close-out performed only after the agreed outcome succeeds
- [x] CHANGELOG.md updated under Unreleased in user language; no release or version/help changes made

## Log

- 2026-08-09 frame: Scope is limited to ending successful Text Cleanup save edits before refresh and routing project activation through the existing Home page-switch flow; unrelated behavior, 0_Planning, releases, versions, help files, the full suite, commits, pushes, merges, and the parent checkout are excluded.
- 2026-08-09 frame: Quick path selected because both defects restore existing edit/save and Home project-activation requirements without adding interfaces, formats, dependencies, security behavior, or data-handling behavior.
- 2026-08-09 frame: Existing requirements REQ-UX-6fb5efc7 and REQ-FUNC-b27e4e87 cover the expected successful-save edit lifecycle and activated-project Home shell state.
- 2026-08-09 frame: Scope was explicitly confirmed by the delegated task, which directs execution through the delivery checkpoint.
- 2026-08-09 build: Verified BUG-01 because the success path refreshes while `_editing_cleaned_text` remains true, so `set_processing_state` preserves edit mode; the ValueError path returns before any proposed discard.
- 2026-08-09 build: Verified BUG-02 because `activate_project` passes the raw Home page to a stack populated with page containers, while `set_current_page("home")` selects the correct container and preserves the required state refresh.
- 2026-08-09 build: `uv run pytest tests/test_text_cleanup_ui_controller.py::test_successful_cleaned_text_save_exits_edit_mode_before_refresh tests/test_home_ui_controller.py::test_activate_project_selects_home_page_container -q` did not collect because the fresh environment lacked PySide6, so it is not red evidence.
- 2026-08-09 build: After `uv sync --extra dev`, the same two-selector command exited 1 with the Cleanup save assertion red as expected (`_editing_cleaned_text` remained true) while the Home activation assertion passed.
- 2026-08-09 build: BUG-02 is not reproducible because selecting Home in the sidebar emits `page_selected`, invokes `MainWindow.set_current_page("home")`, and selects `_page_containers["home"]`; a direct runtime spy observed the raw-page call followed by the container call, so no Home source change will be made.
- 2026-08-09 build: `uv run pytest tests/test_text_cleanup_ui_controller.py::test_successful_cleaned_text_save_exits_edit_mode_before_refresh tests/test_text_cleanup_ui_controller.py::test_failed_cleaned_text_save_keeps_editable_draft -q` exited 0 with 2 passed, proving successful save exits and failed save preserves the draft.
- 2026-08-09 build: `python .agentic/aegis.py test --impacted` expanded 1,084 selectors and exited 127 before pytest because it changed into the application directory while retaining repository-prefixed selector paths.
- 2026-08-09 build: `uv run pytest tests/test_text_cleanup_ui_controller.py tests/test_text_cleanup_page.py tests/test_home_ui_controller.py tests/test_main_window_project_flow.py -q` exited 0 with 56 passed in 170.29 seconds.
- 2026-08-09 build: `uv run ruff check src/audiomancer/ui/controllers/text_cleanup_ui_controller.py src/audiomancer/ui/pages/text_cleanup_page.py tests/test_text_cleanup_ui_controller.py` exited 0 with all checks passed.
- 2026-08-09 build: `python .agentic/aegis.py check --task TASK-38dee580 --strict` exited 0 with 0 errors and 90 warnings inherited from the broader branch-to-default merge-base diff, with no task scope-drift, requirement coverage, linked-test, parse, or source-without-test finding.
- 2026-08-09 deliver: The full pytest suite and `check --run` are excluded by the delegated task so orchestration can run the suite once after integrating all reviewed findings.
- 2026-08-09 deliver: Diff review found only the verified Text Cleanup defect relevant; BUG-02 remains unmodified because the requested visible-container behavior already passes through the sidebar navigation signal.
- 2026-08-09 deliver: Human approval received to commit the validated staged BUG-01 delivery and complete the AEGIS close-out without further approval stops.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: quick; branch: ddp/fix-text-cleanup-home-activation
- requirements:
  - REQ-UX-6fb5efc7 - Cleanup editing shall preserve drafts across same-project refreshes
- diff vs merge base: 405 file(s) changed, 38048 line(s) added
- checks: errors=0 warnings=91 notes=0
- checklist: 7/8 done; open: close-out performed only after the agreed outcome succeeds
- delivery scope note: inherited branch history causes the broad merge-base count; this approved delivery stages 7 files with 142 additions and 9 deletions.
