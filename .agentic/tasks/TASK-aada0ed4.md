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

# TASK-aada0ed4 — Resolve remaining Project Lifecycle findings

stage: done
type: fix
path: full
requirements: REQ-FUNC-3278aae6, REQ-UX-e4b0be69, REQ-FUNC-cfd0a750
branch: bugfix/improvements
opened: 2026-08-07

## Done checklist (current stage)

- [x] `check --strict --run` green or every environment/pre-existing limitation recorded truthfully
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and unrequested changes
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] requested delivery endpoint confirmed: stage only, no commit or push
- [x] journal and final report prepared without committing or pushing
- [x] close-out: `stage: done` set for the requested delivery-preparation endpoint before explicit staging
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` Unreleased section written in user language
- [x] release version workflow skipped because this task is not a release

## Log

- 2026-08-07 frame: Scope is the remaining Project Lifecycle defects in same-source re-selection, Home source-status translation, and dotted export and snapshot names; resolved findings, persisted-schema changes, general filesystem abstraction, planning documents, release/version work, commit, and push are excluded.
- 2026-08-07 frame: Full path chosen because the task changes operator-visible source lifecycle and export data-handling behavior across service and Home UI boundaries.
- 2026-08-07 frame: The completed TC-5/TC-8 Cleanup implementation is present as pre-existing staged work, so this task may proceed without building on the stale branch head.
- 2026-08-07 frame: The protected planning files began modified and unstaged with SHA-256 values 00_Executive_Summary.md=A7D71A4918F98CBB759CFD9AC2C3DFA1FEF56ADA0DFCF066315E310EE4865B02, 03_Text_Extraction_Cleanup.md=5797BF7A8B52EBA507EF847659DEC49C1D37F6D4D253ED560C942348FDB39E1B, and 05_AI_Runtime.md=82241F4C7070B4670935D00537BE11C8B54971B9326E5A38158C837DD3C13090.
- 2026-08-07 frame: Autopilot delivery preparation confirms full scope on branch bugfix/improvements while retaining the complete planning directory as byte-for-byte read-only and unstaged.
- 2026-08-07 frame: Proposed requirements are REQ-FUNC-3278aae6 for idempotent same-source import, REQ-UX-e4b0be69 for truthful translated source status, and REQ-FUNC-cfd0a750 for dotted destination extension normalization.
- 2026-08-07 specify: Created three self-contained requirements with focused verification and affected paths; a shared journal design is sufficient because no new schema or public API is needed.

## Design

- REQ-FUNC-3278aae6: make import resolve and validate the prior manifest path first, then return its unchanged payload when its resolved identity equals the selected file; the Home controller treats returned identity as a no-op before reset or manifest saving.
- REQ-UX-e4b0be69: retain `_refresh_summary_labels()` as the sole source-status derivation and remove the language-switch overwrite; the existing helper already distinguishes absent, selected-unlocked, and locked states.
- REQ-FUNC-cfd0a750: expose one small extension-appending helper from Project Lifecycle export code, compare complete filename endings case-insensitively, and use it at Home, archive, and snapshot boundaries before containment checks.
- No persisted field or public schema changes are needed; rejected alternatives are a persisted no-op flag and `Path.suffix`/`with_suffix`, because they respectively pollute source metadata and truncate dotted names.
- Test seams are `import_source` plus `handle_import_source_requested`, `HomeProjectPage.apply_language`, Home export routing, `create_archive_export`, and `create_project_snapshot`.
- Expected files are the three source service/UI files, four focused test modules, this journal, three requirements, Project Lifecycle knowledge, and CHANGELOG; user guides remain unchanged unless behavior text proves otherwise.
- 2026-08-07 build: REQ-FUNC-3278aae6 and REQ-FUNC-cfd0a750 focused tests red as expected because selecting the stored source created a numbered duplicate and reset the project, while extension replacement truncated dotted destination names.
- 2026-08-07 build: REQ-UX-e4b0be69 focused test red as expected because the language refresh overwrote selected-unlocked status with locked-source text.
- 2026-08-07 build: Implemented resolved-identity source no-ops at both service and Home boundaries, preserved the single Home status derivation, and centralized case-insensitive append-only extension normalization.
- 2026-08-07 build: Focused import, Home page/controller, export, and snapshot modules passed 77 tests; requirement paths and linked tests are current and every delivered requirement is active.
- 2026-08-07 build: `aegis.py test --impacted` exited 127 before pytest because it changes into the application directory before running root-relative selectors and requires unavailable `uv`; the directly impacted modules provide equivalent focused evidence.
- 2026-08-07 deliver: The full project-venv suite passed 1,425 tests with 1 skipped and 1 deselected in 1,787.65 seconds; the only warning was the existing Python audioop deprecation warning.
- 2026-08-07 deliver: Changed-file Ruff, py_compile, and `git diff --check` passed; static task-scoped AEGIS check reported zero errors and 45 accepted pre-existing ticket-reference, branch-wide uncovered-source, and outside-layout warnings.
- 2026-08-07 deliver: Updated Project Lifecycle and Operation Orchestration knowledge plus the Unreleased user-language changelog; both user guides remain accurate because their documented workflow did not change.
- 2026-08-07 deliver: `check --strict --run` did not complete within the 120-second local command timeout before producing findings; the direct project-venv full suite is the recorded authoritative verification, while static `check --full` reported zero errors and 22 warnings.
- 2026-08-07 deliver: Delivery staging is blocked because protected user-owned planning hashes changed after preflight for 00_Executive_Summary.md and 03_Text_Extraction_Cleanup.md; both remain modified and unstaged, and this task will not alter, stage, or discard them.
- 2026-08-07 close: User accepted the protected planning-file differences after testing, so the task is closed at the requested explicit-staging endpoint without a commit or push.

## Delivery report (2026-08-07)

- stage: deliver; type: fix; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-3278aae6 - Selecting the stored source is an idempotent no-op
  - REQ-UX-e4b0be69 - Language switching preserves truthful source status
  - REQ-FUNC-cfd0a750 - Export destinations preserve dotted requested names
- diff vs merge base: 174 file(s) changed, 17731 line(s) added
- checks: errors=0 warnings=46 notes=0
- checklist: 0/10 done; open: `check --strict --run` green or every environment/pre-existing limitation recorded truthfully; diff reviewed against scope, requirements, design, error paths, portability, security, and unrequested changes; knowledge pages updated for every materially changed component; requirements re-read: status, prose, verification, and links all true; requested delivery endpoint confirmed: stage only, no commit or push; journal and final report prepared without committing or pushing; close-out: `stage: done` set for the requested delivery-preparation endpoint before explicit staging; code follows `01_Documentation/Code_Style.md`; `CHANGELOG.md` Unreleased section written in user language; release version workflow skipped because this task is not a release

## Delivery report (2026-08-07)

- stage: done; type: fix; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-3278aae6 - Selecting the stored source is an idempotent no-op
  - REQ-UX-e4b0be69 - Language switching preserves truthful source status
  - REQ-FUNC-cfd0a750 - Export destinations preserve dotted requested names
- diff vs merge base: 174 file(s) changed, 17743 line(s) added
- checks: errors=0 warnings=45 notes=0
- checklist: 10/10 done
