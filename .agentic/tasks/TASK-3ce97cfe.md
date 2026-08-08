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

# TASK-3ce97cfe — Fix platform settings startup, localization, and example contract

stage: done
type: fix
path: full
requirements: REQ-UX-f9cbdc8c, REQ-UX-ade084a1, REQ-PLAT-dd51f8cd
branch: ddp/ps7-ps9-platform-settings
opened: 2026-08-09

## Done checklist (current stage)

- [x] `check --strict --run` green where no diff-introduced failures remain
- [x] diff reviewed against scope, requirements, design, error paths,
      portability, security, and requested exclusions
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report inside the delivery commit; agreed outcome delivered
- [x] close-out: `stage: done` set and committed only after the outcome succeeded
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` Unreleased section written in user language
- [x] no release version assigned and no version or help-file changes made

## Log

- 2026-08-09 frame: Scope is limited to persisted startup font steps, localized stable-code interface-language selection, and the two optional-string values in the committed settings example.
- 2026-08-09 frame: Exclusions are all planning-file edits, every other finding, unrelated refactors or normalization, dependency and release changes, packaging artifacts, `.gitattributes`, ignored settings or secrets, and main-worktree changes.
- 2026-08-09 frame: Full path selected because the language selector changes an externally visible UI and persistence contract; the prompt confirms scope and directs continuous work through the pre-delivery checkpoint.
- 2026-08-09 frame: Proposed three narrow requirements cover pre-construction font-step application, localized language labels with stable stored codes, and loader-compatible optional strings in the committed example.
- 2026-08-09 specify: Created REQ-UX-f9cbdc8c, REQ-UX-ade084a1, and REQ-PLAT-dd51f8cd; no separate specs are needed because each contract and verification is directly buildable.
- 2026-08-09 specify: Advisory check reported zero errors and 30 repository-wide baseline or layout warnings.

## Design

- Component: Platform Settings UI bootstrap, settings page, and committed settings scaffold.
- Interface: keep all public signatures and startup order unchanged; pass the two validated persisted step values through the existing `apply_theme` keyword parameters before `MainWindow` construction (REQ-UX-f9cbdc8c).
- Data: populate each interface-language item from `config.SUPPORTED_LANGUAGES` with translated text and its code as item data, then load and persist by item data while in-place relabeling retains the selected code (REQ-UX-ade084a1).
- Storage: replace only the two existing `discovered_model_name` null values with empty strings; make no other scaffold normalization (REQ-PLAT-dd51f8cd).
- Rejected: persisting `currentText()` after relabeling because translated labels are locale-dependent and fail the validated stable-code contract (REQ-UX-ade084a1).
- Test seam: extend the lightweight app entrypoint fake to capture both font-step arguments and prove theme application precedes window construction (REQ-UX-f9cbdc8c).
- Test seam: adapt Settings-page tests to assert localized item text plus stable data, code selection across relabeling, and code-based load/build behavior (REQ-UX-ade084a1).
- Test seam: extend the committed-example regression to assert every optional discovered model name is a string (REQ-PLAT-dd51f8cd).
- Expected implementation files: `app.py`, `settings_page.py`, and `settings.example.json`; expected focused tests: `test_app_entrypoint.py`, `test_settings_page.py`, and `test_settings_service.py`.

- 2026-08-09 build: `tests/test_app_entrypoint.py::test_main_creates_application_and_shows_window` red as expected because startup passed `None` for both persisted font-size steps.
- 2026-08-09 build: `tests/test_settings_page.py::test_settings_page_offers_exactly_supported_ui_languages` red as expected because both language items had no stable item data.
- 2026-08-09 build: `tests/test_settings_service.py::test_committed_settings_example_uses_strings_for_optional_discovered_model_names` red as expected because both committed example profiles used null.
- 2026-08-09 build: All seven linked regressions passed, and changed Python files passed `py_compile` and Ruff.
- 2026-08-09 build: The AEGIS impacted runner exited 127 before pytest launched, so the linked set was run directly through the approved shared interpreter instead.
- 2026-08-09 build: The broader focused module run passed 74 tests and hit one environment-only failure because ignored `settings.json` was intentionally absent from this fresh worktree.
- 2026-08-09 build: Advisory check reported zero errors and the same 30 accepted repository-wide ticket-reference or outside-layout warnings; none concerns this task's changed Python files.
- 2026-08-09 deliver: Generated only the ignored worktree-local `settings.json` through `ensure_settings_file`, confirmed it matched built-in defaults, validated cleanly, and contained no non-empty credential fields.
- 2026-08-09 deliver: Direct full suite exited 0 with 1524 passed, 1 skipped, 1 deselected, and one existing `audioop` deprecation warning in 2087.97 seconds.
- 2026-08-09 deliver: Removed only the generated worktree-local `settings.json` after the full suite and confirmed it no longer appears in status.
- 2026-08-09 deliver: Task-scoped static strict check exited 0 with zero errors, 70 warnings, and `strict: ok`; the warnings are the expected unticked checkpoint, pre-existing ticket reference, repository layout, and repository-wide uncovered-source advisories.
- 2026-08-09 deliver: Accepted three pre-existing code-style audit warnings for unrelated nested helpers in `test_settings_service.py` because this diff does not touch those callables; changed files otherwise pass Ruff, compilation, and logging coverage.
- 2026-08-09 deliver: Reviewed every hunk against all three requirements, startup ordering, settings validation, portability, secrets, and exclusions; planning files, versions, help files, dependencies, packaging, and ignored operator data remain untouched.
- 2026-08-09 deliver: Updated the Platform Settings UI knowledge page and the Unreleased changelog entry in user language without assigning a release version.
- 2026-08-09 deliver: Human approved the exact staged 14-file PS-7, PS-8, and PS-9 delivery diff and authorized the delivery and journal-only closeout commits.
- 2026-08-09 deliver: Delivery commit `bb94074` succeeded locally; no push, merge, or pull request was requested or performed.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: full; branch: ddp/ps7-ps9-platform-settings
- requirements:
  - REQ-UX-f9cbdc8c - Apply persisted font-size steps before main-window construction
  - REQ-UX-ade084a1 - Localize interface-language labels while preserving stable codes
  - REQ-PLAT-dd51f8cd - Keep optional discovered model names string-typed in the settings example
- approved staged delivery diff: 14 file(s) changed, 413 line(s) added, 18 line(s) removed
- checks: errors=0 warnings=70 notes=0
- checklist: 9/10 done; open: close-out: `stage: done` set and committed only after the outcome succeeded
