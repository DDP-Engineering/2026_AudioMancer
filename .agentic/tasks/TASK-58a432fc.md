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

  stage         frame | specify | design | build | validate | deliver | done
                (adoption journals: survey | components | close | done)
  type          feature | fix | change | adopt
  path          full | quick
  requirements  comma-separated requirement IDs, empty until specify
  branch        the branch this task is delivered on
  base          the commit this task started from, filled in at creation;
                the delivery report and `check --task` measure the diff
                against it, so leave it alone once it is written. Empty
                when the repository had no history yet.
  opened        YYYY-MM-DD

Header lines are edited in place; log lines are only ever appended.
Keep each log line to one sentence.
-->

# TASK-58a432fc — Keep AI Settings Apply and OK responsive

stage: done
type: fix
path: full
requirements: REQ-NFR-dfe9ab8a, REQ-FUNC-d335d502
branch: master
base: 31839aeac2dfefe03818fc8a5c8fafdcc1ad8c74
opened: 2026-08-18

## Done checklist (current stage)

- [x] validated candidate confirmed unchanged; otherwise returned to validate
- [x] validation evidence, diff, exclusions, and outcome presented
- [x] delivery confirmed by the human
- [x] journal and report included in the delivery commit
- [x] agreed outcome delivered — repository-local commit, staged for the operator, no push/PR
- [x] close-out committed after the outcome succeeded, or carried by the
      delivery commit where nothing could fail after it

## Log

- 2026-08-18 frame: scope is the AI Settings dialog Apply/OK persist path — `_persist_ai_settings_from_dialog` saves the settings file, reloads it, then calls `apply_current_ui_settings` (which reapplies the theme, font, palette, global scroll filter and re-translates every page and dialog app-wide) and `show_project_state` (which refreshes the current page a second time and rescans every Home export artifact), none of which an AI-profile-only change affects.
- 2026-08-18 frame: in scope is confining that save to a single page-scoped refresh of the current workflow page, since the AI Settings page owns only `llm_profiles` and the default-profile ids and no theme/font/language/scroll setting.
- 2026-08-18 frame: out of scope are the general Settings dialog persist path (it legitimately owns theme/font/language and must keep reapplying them app-wide), the `apply_theme`/`apply_ui_settings` internals, the backend-probe Connect path, and any change to what the AI Settings page itself edits or stores.
- 2026-08-18 frame: full path chosen because the fix adds a new public MainWindow method and changes how an existing requirement's behavior refreshes the window (page-scoped instead of app-wide), so a new requirement is owed and the existing one's linked test must change — this mirrors the just-delivered Audio Assembly fix (31839ae).
- 2026-08-18 frame: expected requirements are one new NFR for confining a non-appearance AI Settings save to the current page state (no app-wide theme/language reapply, no export rescan), plus updating REQ-FUNC-d335d502 (persist, reload, refresh) whose linked test currently pins the heavy `apply_current_ui_settings` and `show_project_state` calls.
- 2026-08-18 frame: branch stays `master` on operator instruction, so no task branch was created — the journal header records the checkout it is delivered on.
- 2026-08-18 specify: created REQ-NFR-dfe9ab8a for confining a non-appearance AI Settings save to the current page state, and updated REQ-FUNC-d335d502 prose from "refresh the window" to "refresh the current page" - persist and reload are unchanged, only the refresh scope narrows, so the requirement stays satisfied by a retargeted test.
- 2026-08-18 specify: no spec written; both requirements are buildable from their own prose.
- 2026-08-18 design: wrote the design note below - a public `refresh_current_page_state()` wrapper on MainWindow and the AI Settings save calling it instead of the app-wide reapply plus project refresh.
- 2026-08-18 build red: command=`uv run pytest -q tests/test_ai_settings_ui_controller.py::test_apply_ai_settings_persists_reloads_and_refreshes_window tests/test_ai_settings_ui_controller.py::test_apply_ai_settings_refreshes_only_the_current_page`; exit=1; expected missing behavior=the AI Settings save still calls the app-wide `apply_current_ui_settings` and `show_project_state` and never the page-scoped `refresh_current_page_state`, which does not yet exist on MainWindow (REQ-FUNC-d335d502, REQ-NFR-dfe9ab8a).
- 2026-08-18 test: test --impacted (20 test ref(s)) exit 0 (1125.9s)

## Design

Components touched: AI Settings (controller) and App Shell (main window).

Interface changes:

- `MainWindow` gains a public `refresh_current_page_state()` that refreshes the
  visible workflow page from the window's current project root, manifest and
  language - a thin wrapper over the existing private `_refresh_current_page_state`,
  parallel to `refresh_audio_assembly_page_state()` added in 31839ae
  (`REQ-NFR-dfe9ab8a`).
- `_persist_ai_settings_from_dialog` replaces its two heavy calls -
  `settings_ui_controller.apply_current_ui_settings(window)` and
  `window.show_project_state(...)` - with the single
  `window.refresh_current_page_state()`. Persist (`save_settings`) and reload
  (`load_settings`) are unchanged, so REQ-FUNC-d335d502 still holds; only the
  refresh scope narrows (`REQ-NFR-dfe9ab8a`).

Data and storage: none. No persisted format, settings field, or manifest change.
The general Settings dialog persist path keeps `apply_current_ui_settings`, which
it needs because it owns theme, font, and language.

Rejected alternative: early-out inside `apply_theme` when the resolved theme/font
signature is unchanged. That would also spare the AI Settings save the app-wide
work, but it changes a shared appearance primitive used by the general Settings
dialog and app startup, widening blast radius and risking a stale theme when a
signature comparison misses a field. Not calling the appearance reapply at all
from a path that changes no appearance setting is narrower and obviously correct.

Test seams:

- `REQ-FUNC-d335d502` - `tests/test_ai_settings_ui_controller.py`: retarget
  `test_apply_ai_settings_persists_reloads_and_refreshes_window` to assert
  `save_settings` ran, `_settings_payload` adopted the reloaded payload,
  `refresh_current_page_state` ran, and the dialog stayed open on Apply.
- `REQ-NFR-dfe9ab8a` - `tests/test_ai_settings_ui_controller.py`: a new test
  gives the window double counting `refresh_current_page_state`,
  `show_project_state`, and a monkeypatched `apply_current_ui_settings`, and
  asserts only the page refresh ran.

Files expected to change: `ai_settings_ui_controller.py`, `main_window.py`, and
`tests/test_ai_settings_ui_controller.py`.
- 2026-08-18 build: implemented the fix - added public `MainWindow.refresh_current_page_state()` wrapping the private per-page refresh, and pointed `_persist_ai_settings_from_dialog` at it instead of `apply_current_ui_settings` + `show_project_state`; the now-unused `settings_ui_controller` import was dropped from the AI settings controller.
- 2026-08-18 build: verified the red honestly - after removing a broken monkeypatch of the dropped import from the NFR test, stashed only the two source files and re-ran both tests against the pre-fix tree (exit 1, both fail on the behaviour assertions), then popped the stash; with the fix in place all three controller tests pass.
- 2026-08-18 build: activated REQ-NFR-dfe9ab8a with both controller tests linked; REQ-FUNC-d335d502 keeps its single retargeted test and stays active.
- 2026-08-18 build: `ruff check` and both `--changed-only` audits are clean on the three changed files after bringing the two edited tests up to the file's Doxygen docstring convention; `evolution` reports exactly the 3 files the design note named (0 added, 0 removed); `check --task` is errors=0 with only the 9 pre-existing `0_Planning/` untracked-doc warnings and 1 pre-existing note.
- 2026-08-18 build: the NFR test seam in the design note assumed monkeypatching `apply_current_ui_settings`, but removing its import made that patch target disappear, so the delivered NFR test instead asserts `show_project_state` is never called and `refresh_current_page_state` runs once - the same observable NFR, expressed on the window double.
- 2026-08-18 validate: diff reviewed hunk by hunk against scope/design - the controller drops the two heavy calls for one page-scoped refresh and sheds its now-unused `settings_ui_controller` import; the new MainWindow method is a thin wrapper; no new error paths, no portability or security concerns, no unrequested work. Confirmed the removed `apply_current_ui_settings` also carried an `install_global_scroll_step_filter` call, which is harmless to drop here because the filter is installed at startup and on the general Settings save and AI Settings changes no scroll setting.
- 2026-08-18 validate: updated App_Shell.md (page-scoped `refresh_current_page_state` entry point) and AI_Runtime.md (Apply/OK refresh only the current page, no app-wide reapply); both cite REQ-NFR-dfe9ab8a.
- 2026-08-18 validate: re-read both requirements - REQ-NFR-dfe9ab8a active with both controller tests linked, REQ-FUNC-d335d502 active with its single retargeted test; prose, verification, paths and links all true.
- 2026-08-18 validate: no manual/inspection verification owed.
- 2026-08-18 validate: `evolution` refreshed after the final docstring edits - 3 files (the two sources plus the one test module), 0 added, 0 removed, matching the design; knowledge pages live under `.agentic/` and are correctly outside the evolution set.
- 2026-08-18 validate deviation: per the operator's "no full testsuite - only targeted tests", step 8's `check --strict --run` was not run as written (its `[commands].test` is the full suite). Ran `check --task TASK-58a432fc --strict` (no `--run`): errors=0, warnings=9 (all the pre-existing untracked `0_Planning/` docs), notes=1, `strict: ok`, exit 0.
- 2026-08-18 validate: targeted proof on the final candidate - `ruff check` clean on all 3 changed files, both `--changed-only` audits clean, `uv run pytest -q tests/test_ai_settings_ui_controller.py tests/test_ai_settings_page.py` 21 passed. The impacted set (`test --impacted --base HEAD`, 20 test refs) ran 273 passed exit 0 in 1125.9s; it launched before the final docstring/line-length edits, which change no test logic, and the changed test module was re-run green afterwards.
- 2026-08-18 validate: no pre-existing failures encountered; every command above exited 0.

## Delivery report (2026-08-18)

- stage: deliver; type: fix; path: full; branch: master
- requirements:
  - REQ-NFR-dfe9ab8a - Confine a non-appearance AI Settings save to the current page state
  - REQ-FUNC-d335d502 - The AI Settings controller shall persist, reload, and refresh the
- diff vs task base 31839ae: 18 file(s) changed, 2722 line(s) added
- checks: errors=0 warnings=9 notes=1
- checklist: 6/6 done
- 2026-08-18 deliver: operator confirmed delivery ("i tested the app ... close the task, stage the files, give me a commit message").
- 2026-08-18 deliver: report appended above; diff vs base 31839ae reported as 18 files/2722 lines because it counts the untracked `0_Planning/` docs and journal artifacts - the task deliverable is 2 source files, 1 test module, 2 knowledge pages, 2 requirements, and the journal set; checks errors=0 warnings=9 notes=1, checklist 6/6.
- 2026-08-18 deliver: outcome is one repository-local commit on `master`, staged for the operator to commit, with no push and no PR per the operator's standing instruction for this task.
- 2026-08-18 done: closing out before the commit because the delivery commit is the whole outcome and nothing can fail after it - the operator's own commit carries this line.
