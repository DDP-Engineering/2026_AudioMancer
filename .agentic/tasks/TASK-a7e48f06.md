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

# TASK-a7e48f06 — Keep Audio Assembly settings edits responsive

stage: done
type: fix
path: full
requirements: REQ-UX-4cf55346, REQ-NFR-aed66768, REQ-NFR-01d90032
branch: master
base: c09a41501c7caa75c14769dd6e5dcd1179a22689
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

- 2026-08-18 frame: scope is the Audio Assembly Output Settings edit path — every spin-box tick currently emits a settings change that writes the manifest, may raise the outputs-reset confirmation, and runs the app-wide project refresh, which reloads Audio Blocks twice plus every Home export artifact on the GUI thread.
- 2026-08-18 frame: in scope are settled-value editing for the three numeric settings controls, a page-scoped refresh for a settings save that resets nothing, and building Audio Assembly page state from one Audio Blocks load.
- 2026-08-18 frame: out of scope are the Scene Mix preview identity contract (source WAV content digests stay as `REQ-NFR-b6ffe4e8` defines them), the generate/reset/playback paths, and any other workflow page's refresh cost.
- 2026-08-18 frame: full path chosen because the fix changes operator-visible behavior — the outputs-reset confirmation now appears once per settled value instead of once per typed digit — so new requirements are owed rather than an existing one covering it.
- 2026-08-18 frame: expected requirements are one UX requirement for committing a numeric Output Setting only once its value settles, and one NFR requirement for confining a settings save that resets nothing to the Audio Assembly page state built from a single Audio Blocks load.
- 2026-08-18 frame: branch stays `master` on operator instruction, so no task branch was created — the journal header records the checkout it is delivered on.
- 2026-08-18 specify: created REQ-UX-4cf55346 for reporting a numeric Output Setting only once its value settles, REQ-NFR-aed66768 for confining a settings save that discards nothing to the Audio Assembly page state, and REQ-NFR-01d90032 for building that page state from one Audio Blocks load.
- 2026-08-18 specify: reviewed the active requirements over the same files and none of them covers these three behaviors, so all three are new rather than updates - REQ-FUNC-6cc56487 states that a settings change resets assembly outputs but says nothing about how often the change is reported or how wide the refresh is.
- 2026-08-18 specify: no spec written, each requirement is buildable from its own prose.
- 2026-08-18 design: wrote the design note below - keyboard tracking on the page, a page-scoped window refresh for the non-resetting settings save, and an optional pre-loaded-blocks argument on the Scene Mix group listing.
- 2026-08-18 build red: command=`uv run pytest -q tests/test_audio_assembly_page.py::test_audio_assembly_page_reports_a_numeric_setting_once_its_value_settles`; exit=1; expected missing behavior=the numeric Output Settings controls still keep Qt keyboard tracking enabled, so each typed digit reports a settings change (REQ-UX-4cf55346).
- 2026-08-18 build red: command=`uv run pytest -q tests/test_audio_assembly_state_service.py::test_build_audio_assembly_state_loads_audio_blocks_once`; exit=1; expected missing behavior=building one page state loads the Audio Blocks document twice, once for readiness counting and once inside Scene Mix group listing (REQ-NFR-01d90032).
- 2026-08-18 build red: command=`uv run pytest -q tests/test_audio_assembly_ui_controller.py::test_audio_assembly_ui_controller_settings_change_without_reset_refreshes_only_the_page`; exit=1; expected missing behavior=a settings save that discards nothing still calls the app-wide `show_project_state` instead of refreshing only the Audio Assembly page (REQ-NFR-aed66768).
- 2026-08-18 build: implemented all three - `setKeyboardTracking(False)` on the three numeric Output Settings controls, a new public `MainWindow.refresh_audio_assembly_page_state()` that the controller calls instead of `show_project_state()` when a settings save discards nothing, and an optional pre-loaded `audio_blocks` argument on `list_scene_mix_groups()` that `build_audio_assembly_state()` now feeds from its single load.
- 2026-08-18 build: the first red run also exposed two faults in my own test rather than in the code - 250 ms is the default inter-block silence so typing it changed nothing, and typing into the spin box line edit fights its suffix validator - both corrected before the requirement was taken green.
- 2026-08-18 build: `anchor` recorded 332 files at c09a415 and `evolution` reported exactly the 8 files the design note named, 0 added and 0 removed, so nothing unrequested entered the change.
- 2026-08-18 build: targeted runs green - all four Audio Assembly modules (75 passed) and the main-window and workflow-controller modules that consume the new window method (51 passed).
- 2026-08-18 build: `check --task` reports errors=0 with the same 9 warnings and 1 note the repository already carried before this task - a ticket reference in another requirement and the untracked 0_Planning analysis folder - so none of them belongs to this change.
- 2026-08-18 build deviation: accepted two pre-existing audit findings inside files this task edited elsewhere - a missing docstring on `_fake_start_threaded_operation` in the controller tests and a LOG-COVERAGE candidate on `_write_scene_mix_group` - because fixing either is unrequested work; both are present at HEAD and the `--changed-only` audits stay non-empty for this delivery.
- 2026-08-18 validate: diff review found a flaw this task introduced - with keyboard tracking off a value typed and left unconfirmed is not interpreted, so Generate Audio would read the previous value - and the stage returned to build per the step-file protocol.
- 2026-08-18 build red: command=`uv run pytest -q tests/test_audio_assembly_page.py::test_audio_assembly_page_generates_with_a_typed_but_unconfirmed_setting`; exit=1; expected missing behavior=typing 480 into Inter-Block Silence and pressing Generate Audio emits the stale 250 because the pending edit is never interpreted (REQ-UX-4cf55346).
- 2026-08-18 build: fixed it by interpreting the three numeric controls before Generate Audio reads the settings payload, so a value still being typed settles through the usual reporting path first; REQ-UX-4cf55346 gained the regression and its verification now names this observation.
- 2026-08-18 build: `test --impacted --base HEAD` on the pre-fix candidate was exit 0 with 470 passed and 1 skipped in 25 minutes, and it was rerun after the fix because the candidate changed.
- 2026-08-18 test: test --impacted (27 test ref(s)) exit 0 (1310.6s)
- 2026-08-18 validate: diff reviewed hunk by hunk against scope/exclusions/design - no unrequested work, no new error paths, no portability or secret concerns; the settings-save branch still stops on the reset-confirmation `No` exactly as before.
- 2026-08-18 validate: updated Audio_Assembly.md and App_Shell.md knowledge pages to describe the single Audio Blocks load, the settled-value editing, and the new page-scoped `refresh_audio_assembly_page_state()` entry point.
- 2026-08-18 validate: re-read all three requirements - status active, prose matches the built behavior, verification matches what the tests observe, affected_paths and linked_tests current; REQ-UX-4cf55346 additionally links the Generate-with-unconfirmed-value regression and its verification names that observation.
- 2026-08-18 validate: no manual/inspection-verified requirement in this task.
- 2026-08-18 validate: `evolution --task TASK-a7e48f06` refreshed after the build-stage fix: 9 modified files (0 added, 0 removed) - the 5 source + 3 test files the design note named, plus `CHANGELOG.md` for the user-facing delivery entry; matches expectation.
- 2026-08-18 validate deviation: the operator instructed "do not run the full testsuite - only targeted tests", so step 8's `check --strict --run` was not used as written, because `[commands].test` in `aegis.toml` is the full suite and `--run` would execute it. Ran `check --task TASK-a7e48f06 --strict` (no `--run`): errors=0, warnings=10 (the same 9 pre-existing plus one new `outside-layout` note on `CHANGELOG.md`, which this task edited at the repository root exactly as `.agentic/PROJECT.md`'s changelog rule requires), notes=1, `strict: ok`, exit 0. Command=`python .agentic/aegis.py check --task TASK-a7e48f06 --strict`; exit=0.
- 2026-08-18 validate: in place of the full suite, ran the targeted regression set by hand on the final candidate: `uv run ruff check` on all 8 changed source+test files (all checks passed), the two `--changed-only` repository audits (same two pre-existing findings as build, both present at HEAD - accepted again for the same reason), and `uv run pytest -q tests/test_audio_assembly_service.py tests/test_audio_assembly_state_service.py tests/test_audio_assembly_page.py tests/test_audio_assembly_ui_controller.py` - 76 passed, exit 0.
- 2026-08-18 validate: also have `test --impacted --base HEAD` evidence on the final candidate from the build-stage rerun after the interpretText fix: 471 passed, 1 skipped, exit 0 in 1310.6s (27 test refs, covering every requirement whose affected_paths this task touched).
- 2026-08-18 validate: no pre-existing failures encountered; every command above exited 0.

## Design

Components touched: Audio Assembly (page, controller, state service, service)
and App Shell (main window).

Interface changes:

- `AudioAssemblyPage` disables keyboard tracking on the three numeric Output
  Settings controls, so `valueChanged` reaches `_handle_settings_changed` only
  for a settled value (`REQ-UX-4cf55346`). No signal, slot or payload changes.
- `MainWindow` gains a public `refresh_audio_assembly_page_state()` that
  refreshes that one page from the window's current project root, manifest and
  language. The Audio Assembly controller calls it instead of
  `show_project_state()` on the settings-save path that discards nothing
  (`REQ-NFR-aed66768`). `show_project_state()` is unchanged and still runs for
  generate, reset, failure, cancellation and a settings change that does reset.
- `audio_assembly_service.list_scene_mix_groups()` gains an optional
  `audio_blocks` keyword. Given the already-loaded blocks it skips its own load;
  omitted, it loads as before, so every existing caller keeps its behavior
  (`REQ-NFR-01d90032`). `build_audio_assembly_state()` loads once and passes
  them in.

Data and storage: none. No persisted format, path or manifest field changes,
and the Scene Mix preview identity contract is untouched.

Rejected alternative: debouncing the page's `settings_changed` signal behind a
`QTimer`. It would also collapse a burst of edits, but it makes the moment a
setting is persisted non-deterministic, leaves a pending timer to reconcile
when the page is left or an operation starts, and needs a fake clock in every
regression. Disabling keyboard tracking gets the same collapse from Qt's own
editing-finished semantics, with no new state to own.

Test seams:

- `REQ-UX-4cf55346` - `tests/test_audio_assembly_page.py`: connect a counting
  slot to `AudioAssemblyPage.settings_changed`, type a multi-digit value into
  each numeric control with `qtbot.keyClicks`, and assert one payload carrying
  the final value.
- `REQ-NFR-aed66768` - `tests/test_audio_assembly_ui_controller.py`: give the
  window double counting `show_project_state` and
  `refresh_audio_assembly_page_state` callables and assert which one runs, with
  and without a persisted assembly.
- `REQ-NFR-01d90032` - `tests/test_audio_assembly_state_service.py`: wrap
  `audio_blocks_service.load_audio_blocks` with a counter through monkeypatch
  and assert one call per `build_audio_assembly_state()`.

Files expected to change: the four Audio Assembly source files, `main_window.py`,
and the three test modules above.

## Delivery report (2026-08-18)

- stage: deliver; type: fix; path: full; branch: master
- requirements:
  - REQ-UX-4cf55346 - Commit a numeric Audio Assembly output setting once its value settles
  - REQ-NFR-aed66768 - Confine a non-resetting Audio Assembly settings save to the page state
  - REQ-NFR-01d90032 - Build Audio Assembly page state from one Audio Blocks load
- diff vs task base c09a415: 25 file(s) changed, 3167 line(s) added
- checks: errors=0 warnings=10 notes=1
- checklist: 8/8 done
- 2026-08-18 deliver: presented candidate approved by the operator ("i tested, everything is ok, close task").
- 2026-08-18 deliver: report appended above; diff vs base c09a415 is 25 files changed, 3167 lines added, checks errors=0 warnings=10 notes=1, checklist 8/8.
- 2026-08-18 deliver: outcome is one repository-local commit on `master` with no push and no PR, per the operator's standing "do not commit or push" for this task; I staged every file this task touched (source, tests, requirements, journal, CHANGELOG, knowledge pages) and handed the operator the commit message, and the operator runs the actual `git commit`.
- 2026-08-18 done: close-out recorded now rather than in a second commit, because the delivery commit is the whole outcome and nothing can fail after it - the operator's own commit carries this line.
