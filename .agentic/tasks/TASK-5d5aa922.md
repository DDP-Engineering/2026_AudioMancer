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

# TASK-5d5aa922 — Operation status popup replaces the per-page status pane

stage: done
type: change
path: full
requirements: REQ-UX-4e49f8f7, REQ-UX-2b482f01, REQ-UX-1829f58e, REQ-UX-2f024851, REQ-UX-54964a39, REQ-FUNC-07be158e, REQ-UX-f65f5ffa, REQ-UX-bd974d8e
branch: task/operation-status-popup
base: 7fe61c3af81f29cff3ef6989100a74357ad61860
opened: 2026-08-16

## Done checklist (current stage)

- [x] diff reviewed against scope, requirements, design, error paths,
      portability, security, and unrequested work
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, paths, and links true
- [x] manual or inspection verification completed and recorded where applicable
- [x] final evolution report refreshed after the last candidate edit
- [x] final `check --strict --run` result recorded truthfully after all edits - recorded as NOT run and not claimed, see the 2026-08-16 validate limitation
- [x] remaining warnings and pre-existing failures explained
- [x] `stage: deliver`

## Design

Components: App Shell (`ui/main_window.py`, new `ui/operation_status_dialog.py`), the nine
workflow pages under `ui/pages/`, and `services/ui_state_service.py` for the catalog and the
retired height helper. No state service and no controller changes.

Interface. Each page keeps composing exactly the status string it composes today and stores it
instead of painting it: the `self._status_edit.setPlainText(X)` call becomes
`self._set_operation_status_text(X)`, and the page gains one public reader
`operation_status_text() -> str` (`REQ-UX-1829f58e`). Nothing else about the pages' public API
changes, so the eight note-producing requirements keep prose, tests and behaviour untouched.
`OperationStatusDialog` is a new `QDialog`: non-modal, resizable, one read-only `QPlainTextEdit`
carrying the UI control font role (`REQ-UX-2f024851`), one Close button, and
`set_status_text()` / `apply_language()`. `MainWindow` replaces its single
`central_layout.addWidget(self._sidebar)` with a wrapper `QWidget` holding a zero-margin
`QVBoxLayout` of the sidebar (stretch 1) and the button (stretch 0, sidebar width)
(`REQ-UX-4e49f8f7`).

Data. One new module constant maps the nine page identifiers to their workflow operation kind;
`extraction` stays folded into the Text Cleanup page. Enablement reads the existing persisted
per-operation `status` through the manifest accessor already used by the Home summary and is
false for absent, empty and `not_started` and while no project is open (`REQ-UX-2b482f01`). No
new persisted state and no new file format. The button and the open dialog refresh from the
existing `_refresh_current_page_state` path, which already runs on page change and after every
operation, so a modeless dialog left open follows the page the operator navigates to.

Rejected alternative: let the dialog call the `*_state_service.build_*_state` functions itself
and drop the page readers. Rejected because the nine pages compose their status text nine
different ways - two of them interleave counter blocks, three filter blank lines, one appends a
validation line - so the dialog would have to reimplement all nine rules and the composition
would then live in two places that could disagree.

Test seams. `REQ-UX-4e49f8f7` and `REQ-UX-2b482f01`: `tests/test_main_window_lifecycle.py`,
against a real `MainWindow`, reading the left column children and the button state under a
manifest fixture. `REQ-UX-1829f58e`: new `tests/test_operation_status_dialog.py` for the dialog
in isolation plus one `MainWindow` test that presses the button and switches page.
`REQ-UX-2f024851`: `tests/test_operator_status_font_role.py`, repointed from the nine page
editors to the dialog editor. `REQ-UX-54964a39` and `REQ-FUNC-07be158e`: their existing page
tests, with the status-pane assertions removed.


## Log

- 2026-08-16 frame scope: remove the fixed three-line operator status pane (`_status_edit`, and `_status_group` on the eight pages that wrap it) from the nine workflow pages that carry it, let the freed vertical space fall to the existing content widget through the stretch factors already in place, and reach the same text through one modeless per-page status dialog opened by a new operation-status button placed under the navigation sidebar.
- 2026-08-16 frame scope: the button belongs to the shell, not to the sidebar list - `NavigationSidebar` is itself the `QListWidget` and `REQ-UX-23258764` fixes it at exactly ten icon-bearing page entries, so the button goes into a new wrapper `QWidget` with a vertical layout holding the sidebar (stretch 1) and the button (stretch 0), replacing the single `central_layout.addWidget(self._sidebar)` call; this also keeps the button outside the `PAGE_ORDER` loop in `set_project_active`, which would otherwise never see it.
- 2026-08-16 frame scope: the button is enabled from the manifest operation status of the page's own operation kind, `status not in {"", "not_started"}`, per the operator's decision; the pre-run guidance notes currently shown before an operation has run are deliberately dropped rather than relocated, because the operator asked for the operation result and not the guidance.
- 2026-08-16 frame scope: page-to-operation-kind mapping is one-to-one over the nine pages - text_cleanup/cleanup, text_chunking/chunking, ai_translation/translation, characters/character_discovery, narator_voice/narrator_definition, character_voices/character_voices, speech_blocks/speech_blocks, audio_blocks/audio_blocks, audio_assembly/audio_assembly - with extraction folded into the Text Cleanup page as it already is.
- 2026-08-16 frame scope: two pre-existing defects the operator asked to correct in the same task - `operator_status_pane_height()` is called only from constructors so nothing recomputes it after a UI font-scale change, and `text_chunking_page.py:169` seeds its status text from a hard-coded English literal instead of a translated catalog key, which contradicts `REQ-UX-aa109e16`.
- 2026-08-16 frame exclusions: no change to Home, Settings, AI Settings or TTS Settings, none of which has a status pane (Home keeps its own stage grid, which already serves as the pipeline-wide view); no change to the eight state services that produce the note text, so the note-content requirements keep both prose and tests; no change to `OperationProgressDialog` or its application-modal cancellation contract in `REQ-UX-afd2c37d`, which governs the in-run progress dialog and not this one; no sidebar list entries added; no splitter or preview geometry changes; no version bump, so the work stays under `## [Unreleased]`; no commit and no push per the operator's instruction.
- 2026-08-16 frame path: full, because this adds externally observable behaviour (a new shell control and a new dialog), adds a new UI interface, and amends four active requirements whose prose currently names the status pane as a page contract; the quick path is not available for any of those reasons.
- 2026-08-16 frame requirements to create: one UX requirement for the sidebar operation-status button (placement under the fixed-width sidebar, enablement from the current page's manifest operation status, disabled while no project is active); one UX requirement for the modeless per-page operation-status dialog (shows the current page's operation status text, is not application-modal, and coexists with an active progress dialog).
- 2026-08-16 frame requirements to amend: `REQ-UX-54964a39` (drop "and a status pane" from the Text Cleanup page contract); `REQ-FUNC-07be158e` (drop "status panel" from the Narrator Voice page contract); `REQ-UX-2f024851` (operator status font role moves from nine page editors to the dialog editor); `REQ-UX-f65f5ffa` (status pane height helper - decide at design whether it survives to size the dialog and gains the missing font-change recompute, or retires with the pane; the operator asked for the bug to be corrected, so retirement is only acceptable if the helper genuinely has no remaining caller).
- 2026-08-16 frame requirements to relink: `REQ-FUNC-0186546f`, `REQ-FUNC-3091aae8`, `REQ-FUNC-ef48abb5`, `REQ-FUNC-c94fb8a5`, `REQ-UX-7982f351`, `REQ-FUNC-db8b72d4` and `REQ-UX-aa109e16` keep their prose but their linked tests assert through `_status_edit`, so each needs its verification path pointed at the dialog; `REQ-UX-aa109e16` additionally gains the Text Chunking literal as a covered case.
- 2026-08-16 frame prior art: `TASK-6e7f4c7b` and `TASK-b84ca267` were both closed to `stage: done` before this task opened, on the operator's instruction and after confirming each one's work had reached `master` (`7db71ae` and `f9e55c9`); no open journal now competes for the Speech Blocks or shell layout surface.
- 2026-08-16 specify created: `REQ-UX-4e49f8f7` (the shell places one operation-status button directly below the fixed-width sidebar, outside the page list, so the list still holds exactly the workflow page entries); `REQ-UX-2b482f01` (the button is disabled while the current page's operation has no recorded run status - absent, empty, or not-started - and enabled for every other persisted status); `REQ-UX-1829f58e` (pressing the button shows a modeless dialog carrying the current page's operation status text). The frame proposed two requirements; three were written because placement, enablement, and presentation are each separately arrangeable and observable, and one "shall" belongs to each.
- 2026-08-16 specify amended: `REQ-UX-54964a39` lost "and a status pane" from the Text Cleanup page contract; `REQ-FUNC-07be158e` lost "status panel" from the Narrator Voice page contract and the one linked selector that asserted through it; `REQ-UX-2f024851` was rewritten from "operator status editors" plural to the single dialog editor, keeping the behaviour and moving only its location.
- 2026-08-16 specify retired: `REQ-UX-f65f5ffa` set to `status = "retired"` with the reason appended to its prose, on the operator's explicit decision to retire rather than repair `operator_status_pane_height()`; the pane whose height it computed no longer exists and the replacement dialog is operator-resizable, so the missing font-change recompute is resolved by removing the code rather than by fixing it, and this is recorded as removal and not as a fix.
- 2026-08-16 specify deferred to build: the seven relink requirements keep their prose and their current linked selectors until the tests they name are actually rewritten, because a link removed before its test changes would claim a coverage gap that does not yet exist; `REQ-UX-2f024851` likewise keeps its existing selector for that reason and build must repoint it.
- 2026-08-16 specify obligation: `test_narator_voice_page_status_panel_keeps_language_value_internal` was unlinked from `REQ-FUNC-07be158e` because the panel half of it is going away, but the test also asserts that the page keeps the language value internal, which is behaviour worth keeping; build must preserve that assertion under whatever name survives rather than deleting the test wholesale.
- 2026-08-16 specify check: `check` exit 0, errors=0; the `stale-paths` warnings on `REQ-UX-1829f58e` and `REQ-UX-2f024851` name `ui/operation_status_dialog.py`, which build creates, and the remaining warnings are the untracked `0_Planning/Analysis_2026-08-10/` notes and the pre-existing `ticket-ref` on `REQ-UX-4753a4bf`, none of them this task's.
- 2026-08-16 design finding: the second requested bug fix is resolved by deletion rather than by repair, exactly as the height helper was. The hard-coded English literal at `text_chunking_page.py:169` is the pane's *seed* text, and both of its lines are pre-run guidance ("Run cleanup before chunking." plus an unkeyed second sentence describing what generation will populate). The operator's enablement decision drops pre-run guidance, so the literal and its `text_chunking.initial_note` translated sibling both disappear with the pane; there is no surviving code path in which the literal could be corrected.
- 2026-08-16 design consequence: the same removal makes the `*.initial_note` catalog keys unreachable on the five pages that seed their pane through `apply_language` (`text_cleanup`, `text_chunking`, `ai_translation`, `speech_blocks`, `audio_blocks`), together with the `characters.summary` seed. Build removes those keys from both the English and Romanian catalogs and drops the matching assertions from `test_ui_localization_coverage.py`, because a catalog entry no surface reads is dead weight that the localization parity test would otherwise keep alive forever.
- 2026-08-16 design decision: pages retain their status composition and expose it through one reader rather than the dialog rebuilding it from the state services, so the nine distinct composition rules stay in one place each; recorded in `## Design` with the rejected alternative and its reason.
- 2026-08-16 build red: command=`uv run pytest -q tests/test_main_window_lifecycle.py::test_main_window_places_operation_status_button_under_the_sidebar`; exit=1; expected missing behavior=`AttributeError: 'MainWindow' object has no attribute '_operation_status_button'` because the shell still adds the sidebar straight into the central layout with no column wrapper and no status button.
- 2026-08-16 build green (REQ-UX-4e49f8f7): the shell wraps the sidebar and the new `operationStatusButton` in a zero-margin vertical column that replaces the sidebar in the central layout; `test_main_window_navigation_is_a_left_vertical_sidebar` was repointed from the sidebar to that column because it asserted the sidebar sat at central-layout index 0, which the wrapper changes while leaving the behaviour it guards - fixed left sidebar, stack taking the remaining width - true.
- 2026-08-16 build red: command=`uv run pytest -q tests/test_operation_status_button.py`; exit=1; expected missing behavior=`AssertionError: running` with the button still disabled after the manifest recorded a run status, because nothing yet read the per-operation status.
- 2026-08-16 build green (REQ-UX-2b482f01): `PAGE_OPERATION_KIND` maps the nine workflow pages to their operation kind, and `_refresh_operation_status_control` runs from `show_project_state`, which already fires on page change and after every operation; Home is deliberately absent from the map, so its button stays dead.
- 2026-08-16 build red: command=`uv run pytest -q tests/test_operation_status_dialog.py`; exit=1; expected missing behavior=`ModuleNotFoundError: No module named 'audiomancer.ui.operation_status_dialog'` because the dialog did not exist; and `uv run pytest -q tests/test_operation_status_button.py::test_operation_status_button_opens_the_dialog_and_follows_the_page`; exit=1; expected missing behavior=`AttributeError: 'MainWindow' object has no attribute '_operation_status_dialog'`.
- 2026-08-16 build green (REQ-UX-1829f58e, REQ-UX-2f024851): `OperationStatusDialog` is a resizable non-modal `QDialog` with one read-only editor carrying the UI control font role; each of the nine pages now stores the string it used to paint and exposes it through `operation_status_text()`, so the nine composition rules stay where they were and the dialog only renders.
- 2026-08-16 build removed: `operator_status_pane_height()` deleted from `ui_state_service` with its test, per the operator's decision to retire `REQ-UX-f65f5ffa` rather than repair it; `test_operator_status_font_role.py` deleted wholesale because its single parametrized test covered exactly the nine editors that no longer exist, and its behaviour is now asserted once against the dialog editor.
- 2026-08-16 build removed: `audio_assembly_page._apply_status_edit_font_role()` deleted as its only caller went with the pane. It is worth recording that this method was the one place in the codebase that re-polished the font role at runtime, so Audio Assembly alone did not suffer the font-scale staleness the other eight pages had; the dialog now carries that concern for every page.
- 2026-08-16 build corrected: `test_main_window_can_be_created` asserted the window owns exactly three `QDialog` children, which the status dialog makes four; the count was updated and the new dialog named, rather than loosened to an inequality that would stop catching an accidental fourth dialog.
- 2026-08-16 build corrected: `test_narator_voice_page_status_panel_keeps_language_value_internal` was renamed to `test_narator_voice_page_keeps_language_value_internal` and relinked to `REQ-FUNC-07be158e`, honouring the specify obligation to preserve its language-stays-internal assertion instead of deleting the test with the panel it was named after.
- 2026-08-16 build scope note: the second requested bug fix could not be performed as a fix. The Text Chunking hard-coded literal was the pane's pre-run seed, and the operator's own enablement decision removes pre-run guidance, so the literal, its `text_chunking.initial_note` sibling and four other now-unreachable `*.initial_note` / `characters.summary` catalog entries were deleted from both catalogs instead. Where a page's only Romanian assertion had been that seed, `test_ui_localization_coverage.py` was given a caption assertion for the same page rather than losing coverage of it.
- 2026-08-16 build targeted verification (the operator forbade the full suite, so these are module-level runs, not a full-suite proof): `tests/test_operation_status_button.py` and `tests/test_operation_status_dialog.py` 8 passed; `tests/test_main_window_lifecycle.py` 25 passed; `tests/test_ui_localization_coverage.py` 4 passed; the eleven touched page modules plus `tests/test_audio_blocks_main_window.py` and `tests/test_ui_state_service.py` 118 passed across two runs; `tests/test_ui_page_contract.py`, `tests/test_ai_translation_ui_controller.py`, `tests/test_workflow_impact_service.py` and `tests/test_navigation_sidebar.py` 24 passed; `ruff check src tests` clean.
- 2026-08-16 build tooling note (CORRECTED 2026-08-17): `aegis test --impacted --base HEAD` was recorded here as having produced no output and been abandoned. That was wrong and is retracted: the command buffered its output for its whole run and completed at exit 0 after 28m39s. See the 2026-08-17 entry for what it actually proved and what it did not.
- 2026-08-16 validate refactor: the mechanical rewrite had left seven pages assigning their status text through a one-line `_set_operation_status_text()` wrapper while two assigned the attribute directly; the wrapper was removed and all nine now assign directly, because `Code_Style.md` forbids unnecessary wrapper methods and the inconsistency had no reason to exist. All fourteen affected modules were re-run after the refactor: 130 passed.
- 2026-08-16 validate inspection (method: real `MainWindow` at 1400x860, shown, each page navigated to and its children measured): on Text Cleanup, Text Chunking and Speech Blocks the page widget is 809 px tall and the lowest visible child ends at 799 px, a 9 px gap that is the page layout's own bottom margin - the content now reaches the bottom of the scroll viewport instead of stopping above a fixed three-row pane. The button reads "Op Status", is 160 px wide against a 160 px sidebar, sits below it (sidebar bottom 776 px, button bottom 808 px), and is correctly disabled with no project open.
- 2026-08-16 validate diff review: the diff is confined to the shell, the nine pages, the UI catalog, the two help files and `CHANGELOG.md`; no state service, controller behaviour, persistence format or operation lifecycle was touched, so there are no new error paths, no security surface and no host-specific code. The one unrequested-looking removal, `audio_assembly_page._apply_status_edit_font_role()`, is a dead method whose only caller was the removed pane.
- 2026-08-16 validate correction: `git add -A` briefly staged the untracked `0_Planning/Analysis_2026-08-10/` notes, which belong to no task; they were reset out of the index immediately and remain untracked, matching how the previous task left them.
- 2026-08-16 validate requirements re-read: the three new requirements are active with prose, verification and links matching what was built; `REQ-UX-54964a39` and `REQ-FUNC-07be158e` no longer claim a status pane; `REQ-UX-2f024851` points at the dialog editor; `REQ-UX-f65f5ffa` is retired with its reason in the prose and its `linked_tests` emptied because the test it named was deleted with the helper.
- 2026-08-16 validate limitation: `check --strict --run` was NOT run. Its `--run` executes the full suite, which the operator forbade twice in this session. The strict-check proof is therefore owed and is not being claimed; what exists instead is `check --task` exit 0 with errors=0 notes=0, `ruff check src tests` clean, and the targeted module runs recorded above. The 12 remaining warnings are all pre-existing or by design: the untracked `0_Planning/` notes (8), the `ticket-ref` on `REQ-UX-4753a4bf` which this task never touched, and `outside-layout` on `CHANGELOG.md` and both help files, which are required deliverables that live outside the source and test globs by design.
- 2026-08-17 test: test --impacted (51 test ref(s)) exit 0 (1721.1s)

## Delivery report (2026-08-16)

- stage: deliver; type: change; path: full; branch: task/operation-status-popup
- requirements:
  - REQ-UX-4e49f8f7 - The shell shall expose an operation-status button under the navigation sidebar
  - REQ-UX-2b482f01 - The operation-status button shall be enabled only for an operation that has run
  - REQ-UX-1829f58e - Pressing the operation-status button shall open the modeless status dialog for the current page
  - REQ-UX-2f024851 - Operator status editors shall use the UI font role
  - REQ-UX-54964a39 - The Text Cleanup page shall expose a profile selector, Cleanup and
  - REQ-FUNC-07be158e - The Narrator Voice page shall lay out selection, editors, edit mode
  - REQ-UX-f65f5ffa - The operator status pane height shall scale with line count
- diff vs task base 7fe61c3: 52 file(s) changed, 3613 line(s) added
- checks: errors=0 warnings=13 notes=0
- checklist: 7/8 done; open: final `check --strict --run` result recorded truthfully after all edits
- 2026-08-16 frame (scope amended by the operator): while testing the delivered candidate the operator reported the Home Workflow Pipeline captions being cut off ("ext Cleanup", "Audio Assem"). Measured on a worktree at the task base `7fe61c3` and on this branch, the stepper is 790 px wide in both, the first caption starts at -20.1 px in both and the last ends at 810.1 px in both: the clipping is pre-existing and this task's shell change altered nothing about it (left column 160 px, page stack 856 px, exactly what the bare sidebar took). The operator chose to fix it inside this task rather than defer it, so the frame exclusion "no change to Home" is hereby withdrawn for this one defect; every other Home behaviour, and Settings, AI Settings and TTS Settings, stay excluded.
- 2026-08-16 frame root cause: `_paint_stepper` fixes the bead inset at `margin_x = 26.0` but draws each caption `gap / 2` wide either side of its bead, and with ten stages `gap / 2` is about 46 px, so the first and last captions are drawn outside the widget and clipped. The defect only became visible once the stage labels grew wide enough to fill their gap; the stage returns to specify because this is a new externally observable behaviour needing its own requirement.
- 2026-08-16 specify: created `REQ-UX-bd974d8e` for the Home stepper caption clipping; no design note was needed because the fix is one derived value in one existing painter with no new interface, data format or dependency.
- 2026-08-16 build red: command=`uv run pytest -q tests/test_home_page.py::test_workflow_stepper_keeps_end_captions_inside_its_width`; exit=1; expected missing behavior=`AttributeError: module 'audiomancer.ui.pages.home_page' has no attribute '_stepper_bead_layout'` across all twelve parametrized cases, because the bead inset was a literal inside the paint method with no seam to assert on.
- 2026-08-16 build green (REQ-UX-bd974d8e): `_stepper_bead_layout(width, count)` returns the inset and spacing, using `max(26.0, width / (2 * count))`; that is exactly the threshold at which half a caption fits, so the outer captions land on the edges rather than past them, and at widths where the old fixed 26 px was already large enough the value is unchanged. The paint method now takes both numbers from the helper instead of computing the spacing from a literal.
- 2026-08-16 build measured (real `MainWindow` at 1040x700, Home page shown): stepper 790 px, nine stages, inset 43.9 px, spacing 87.8 px; the first caption band starts at exactly 0.0 px and the last ends at exactly 790.0 px, against -20.1 px and 810.1 px before the fix. Every stage label's rendered text width (45-71 px) sits inside its 87.8 px band, so no caption wraps to a second line as a side effect.
- 2026-08-16 validate (second pass, after the Home stepper addition): `ruff check src tests` clean; the seventeen affected modules re-run together, 159 passed; `check --task` exit 0 with errors=0 notes=0; evolution refreshed after the last edit. `CHANGELOG.md` gained a `### Fixed` entry for the clipped step names in user language, still with no version assigned, so this remains a non-release delivery.
- 2026-08-16 validate limitation (unchanged): `check --strict --run` is still NOT run and still not claimed, because `--run` executes the full suite the operator forbade. Every other proof recorded in this journal is a targeted module run.
- 2026-08-17 build evidence (late-arriving): `aegis test --impacted --base HEAD` finished at exit 0 - 812 passed in 1719.58s across 51 test files, after the selector reduced 266 selectors to whole files because the command line was too long to launch. This is real regression evidence and materially wider than the targeted module runs: it includes every UI controller, the state services, the localization parity audit, the app entrypoint and the package import.
- 2026-08-17 build evidence limitation: that run was launched before two later code edits and therefore does NOT cover the delivered candidate. Not covered by it are the validate-stage removal of the `_set_operation_status_text` wrapper from seven pages with the parenthesis cleanup that followed, and the whole Home stepper fix (`_stepper_bead_layout`, `REQ-UX-bd974d8e`). Both are covered instead by the 159-passed targeted re-run over the seventeen affected modules, which was taken after the last code edit. The honest reading is: a wide sweep on a slightly earlier tree, plus a narrow sweep on the final tree, and no single run over the final tree at full width.
- 2026-08-17 close: delivered on `master` as commit 7442510, merged by pull request #57 (`1fda957`); the task is closed with `check --strict --run` still owed rather than done, exactly as the validate limitation above records.
