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

# TASK-85a6a1a7 — Harden source import errors and decoding

stage: done
type: fix
path: full
requirements: REQ-UX-da3b47c4, REQ-FUNC-c7960ee8, REQ-FUNC-379827ff
branch: bugfix/improvements
opened: 2026-08-03

## Done checklist (current stage)

- [x] full suite green and strict AEGIS check has no errors; warnings fixed or explained
- [x] diff reviewed against scope, requirements, design, error paths, portability, and security
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] delivery preparation confirmed by the requested autonomous mode
- [x] journal and report generated; only this task's files staged
- [x] close-out: `stage: done` set after successful requested staging outcome
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` Unreleased section written in user language
- [x] both help files updated for the changed behavior without a release version bump
- [x] release-version and `git grep` workflow skipped because this task is explicitly not a release

## Log

- 2026-08-03 frame: Scope contains Home-boundary create/import/confirmed-repair filesystem failures plus deterministic legacy TXT/RTF and declared EPUB decoding; PDF ordering, cleanup/editor behavior, other formats, global exception handling, and the read-only planning analysis are excluded.
- 2026-08-03 frame: Full path chosen because source decoding and its persisted encoding contract are externally observable data-handling behavior.
- 2026-08-03 frame: Autonomous delivery preparation was requested, so the scope checkpoint is logged and work continues without a pause on branch bugfix/improvements.
- 2026-08-03 frame: Proposed requirements are the focused existing Home project-error requirement REQ-UX-da3b47c4 plus new focused legacy-text and EPUB-encoding requirements.
- 2026-08-03 specify: Extended REQ-UX-da3b47c4 to the create/open/import/confirmed-repair Home boundary and created REQ-FUNC-c7960ee8 and REQ-FUNC-379827ff with encoding-selection specs.
- 2026-08-03 specify: Requirements are separate, self-contained behaviors for UI containment, undecorated legacy text selection, and EPUB content-document decoding.
- 2026-08-03 design: The controller will contain OSError and ValueError at each relevant service-call boundary without changing successful paths (REQ-UX-da3b47c4).
- 2026-08-03 design: Text decoding will prefer signatures/declarations and strict UTF-8, then score all successful Windows-code-page candidates by script coherence and text quality before the explicit Latin-1 terminal fallback (REQ-FUNC-c7960ee8).
- 2026-08-03 design: EPUB will decode every spine document independently, wrap declared-encoding errors with item identity, and report one uniform encoding or a sorted mixed-encoding token (REQ-FUNC-379827ff).
- 2026-08-03 design: No public function signature or persisted ledger schema changes; the existing optional encoding string carries the truthful uniform or mixed value.
- 2026-08-03 design: Rejected first-success codec ordering because permissive single-byte codecs silently accept bytes belonging to another language.
- 2026-08-03 design: Test seams are Home controller service-call monkeypatches and public Text Extraction runs with raw TXT/RTF and patched EPUB ZIP members.
- 2026-08-03 design: Expected implementation files are home_ui_controller.py and text_extraction_adapters.py, with focused tests, requirements/specs, knowledge, help, and changelog delivery artifacts.
- 2026-08-03 build: tests/test_home_ui_controller.py::test_home_ui_controller_contains_project_creation_filesystem_error red as expected because PermissionError escaped the create slot.
- 2026-08-03 build: tests/test_text_extraction_service.py::test_extract_text_selects_supported_text_encoding_without_mojibake red as expected because UTF-8 was mislabeled utf-8-sig and cp1251/cp1252 bytes were decoded by the first permissive codec.
- 2026-08-03 build: tests/test_text_extraction_service.py::test_extract_text_honors_uniform_epub_content_encoding red as expected because EPUB spine bytes were decoded unconditionally as strict UTF-8.
- 2026-08-03 build: Focused Home and Extraction files passed 49 tests in 47.43 seconds after implementation.
- 2026-08-03 build: `test --impacted` exited 127 because its branch-wide 313-selector command exceeded the Windows process launch limit; the exact changed test files passed and the final full suite remains the delivery gate.
- 2026-08-03 build: Ruff, compileall, and diff whitespace checks passed for every changed Python file.
- 2026-08-03 build: AEGIS check reported zero errors; accepted the pre-existing ticket-ref and unrelated branch-wide uncovered-source warnings, plus outside-layout warnings for user-owned analysis/README files and the repository-required changelog/help delivery files.
- 2026-08-03 deliver: Full suite passed 1256 tests with 1 skipped and 1 deselected in 1366.00 seconds; the AEGIS command completed in 1368.6 seconds.
- 2026-08-03 deliver: Static `check --task TASK-85a6a1a7 --strict` exited 0 with zero errors; the temporary unticked-deliver warning was resolved before close-out and all other accepted warning categories were already logged.
- 2026-08-03 deliver: Diff review found only the three requested behaviors plus their focused tests, requirements/specs, knowledge pages, bilingual help, changelog, and task journal; the planning analysis and unrelated README/test-guide changes remain untouched.
- 2026-08-03 deliver: No release version bump was performed as explicitly requested.
- 2026-08-03 deliver: Requested delivery outcome succeeded with exactly this task's 15 files staged and no commit or push performed.
- 2026-08-03 close-out: Task closed after report generation and successful review staging; the human retains commit authority.

## Delivery report (2026-08-03)

- stage: deliver; type: fix; path: full; branch: bugfix/improvements
- requirements:
  - REQ-UX-da3b47c4 - Contain expected project workspace failures at the Home UI boundary
  - REQ-FUNC-c7960ee8 - Select legacy text encodings deterministically
  - REQ-FUNC-379827ff - Honor EPUB content document encodings
- diff vs merge base: 84 file(s) changed, 7949 line(s) added
- checks: errors=0 warnings=36 notes=0
- checklist: 10/11 done; open: close-out: `stage: done` set after successful requested staging outcome
