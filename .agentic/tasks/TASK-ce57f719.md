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

# TASK-ce57f719 — Character Discovery recovery and truthful summary

stage: done
type: fix
path: full
requirements: REQ-FUNC-f878c579, REQ-FUNC-5cd8727a
branch: bugfix/improvements
opened: 2026-08-07

## Done checklist (current stage)

- [x] full suite and `check --full` results are logged with every warning explained
- [x] diff reviewed against scope, requirements, design, error paths, portability, and security with no unrequested changes
- [x] Character Discovery knowledge updated, including its Files section
- [x] requirements re-read with status, prose, verification, and links all true
- [x] staged-only delivery outcome confirmed by the supplied request, with commit and push excluded
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` Unreleased section is written in user language
- [x] protected planning inputs remain byte-for-byte unchanged and unstaged
- [x] release-only version and bilingual help workflow recorded as not applicable
- [x] task closed before report generation and explicit-path staging as requested

## Log

- 2026-08-07 frame: Scope is safe Characters-page recovery from a strict-invalid authoritative document and completed summaries that state only the persisted character count.
- 2026-08-07 frame: Direct loading remains strict, refresh remains read-only, reset follows the established downstream policy, and valid or missing document states remain unchanged.
- 2026-08-07 frame: Tolerant parsing, automatic repair or deletion, broad exception handling, schema expansion, fabricated progress counts, CD-7 through CD-10, narrator and downstream behavior, planning documents, releases, commits, and pushes are excluded.
- 2026-08-07 frame: The full path is required because the separate page-recovery and completed-summary behaviors are user-visible and cross persistence, page state, localization, controller, and reset boundaries.
- 2026-08-07 frame: Preflight confirmed committed Unicode task TASK-9a15893d at 519b642, the shared Unicode identity normalizer, a clean index, and no open AEGIS journals.
- 2026-08-07 frame: The protected planning files began modified and unstaged with SHA-256 values 85BB1400855126281BE95EA913EBFE56BB849CD756D9ED7381B282F15427A8C0, 36FB759DF7D415D421B6CDEFBCB4FCFD5A02B4740276C026B3DCAF7BD4843013, A6497D58E601461010642E1894C893BCE213E12761B366566BE2E47E48080EEC, 82241F4C7070B4670935D00537BE11C8B54971B9326E5A38158C837DD3C13090, and E93EF77DDA423890B0E4A365B5BF2EEC3DA18FBAD37622F23FB8A0917892A987 respectively.
- 2026-08-07 frame: Autopilot scope was accepted from the supplied request without a frame checkpoint, with one new requirement for invalid-document page recovery and one new requirement for truthful completed summaries.
- 2026-08-07 specify: Created REQ-FUNC-f878c579 for the isolated strict-read page-state boundary and REQ-FUNC-5cd8727a for completed summaries limited to persisted facts.
- 2026-08-07 specify: AEGIS check reported zero errors and 21 pre-existing warnings: one ticket reference and layout warnings for existing help, changelog, test-guide, and planning documents.

## Design

- Components: Character Discovery state projection, UI localization, Characters page, controller, MainWindow refresh, and their focused tests implement REQ-FUNC-f878c579; the state projection and localization implement REQ-FUNC-5cd8727a.
- Interface: `build_character_discovery_state` preserves its complete payload contract and catches only `CharacterDocumentError` around authoritative reads for REQ-FUNC-f878c579; direct service loaders and reset-controller interfaces stay unchanged.
- Data: recovery contains no profile or edit state but retains a valid chunk map and resolved AI profile; its failed status and disabled actions prevent mutation until the existing reset removes the invalid artifact for REQ-FUNC-f878c579.
- Data: completed notes format only `character_count`; no schema field, derived window count, running progress note, token note, warning, or rerun notice changes for REQ-FUNC-5cd8727a.
- Alternative rejected: tolerant document parsing or synthesizing a window count was rejected because neither is authoritative persisted data and both conceal the documented error boundary.
- Test seams: direct loaders demonstrate strict failures, state fixtures prove recovery and bilingual notes, page/MainWindow tests prove rendered controls, and the reset controller proves the existing recovery path and manifest policy for REQ-FUNC-f878c579; completed state fixtures prove summary and retained notes for REQ-FUNC-5cd8727a.
- Expected files: `character_discovery_state_service.py`, `ui_state_service.py`, the four focused Character Discovery UI/state test modules, both requirements, the recovery specification, this journal, Character Discovery knowledge, and CHANGELOG.
- 2026-08-07 design: The detailed recovery specification records the non-obvious strict-loader versus safe-page-boundary contract; completed summary behavior is buildable from its requirement alone.
- 2026-08-07 build: The new malformed, invalid-root, and invalid-nested document recovery regressions were red because strict CharacterDocumentError escaped page-state construction; summary and reset regressions were red because the summary invented a zero window count and activation could not render the recovery page.
- 2026-08-07 build: Recovery now catches only CharacterDocumentError at the state boundary, leaves the invalid artifact untouched, retains valid source chunks and the resolved AI profile, and enables only Reset; completed summaries now format only the persisted character count in both languages.
- 2026-08-07 build: Direct service, state, page, controller, MainWindow-refresh, and localization modules passed 114 tests.
- 2026-08-07 build: Ruff and Python compilation passed on all changed Python files.
- 2026-08-07 build: The AEGIS impacted wrapper selected 539 tests but exited 127 before pytest because the managed Windows command retains repository-root selectors after changing into the application directory; direct affected modules were run and the managed payload remains unchanged.
- 2026-08-07 build: AEGIS check reported zero errors and 21 pre-existing warnings: one ticket reference and layout warnings for existing help, changelog, test-guide, and planning documents.
- 2026-08-07 build: Both existing Characters user-guide sections now describe Reset Discovery recovery; this is not a release, so help and project version fields remain unchanged.
- 2026-08-07 deliver: The configured full suite exited 0 with 1444 passed, 1 skipped, 1 deselected, and the pre-existing Python audioop deprecation warning in 1646.5 seconds.
- 2026-08-07 deliver: Requested check --full exited 0 with zero errors and 22 warnings: the pre-existing REQ-UX-4753a4bf ticket reference, expected unticked-deliver warning before journal closure, and 20 outside-layout warnings for existing help, changelog, test-guide, and protected planning documents.
- 2026-08-07 deliver: Reviewed the final diff against both requirements, strict direct-loader behavior, recovery error paths, Windows portability, localization, reset policy, security, and code style; no unrequested changes or sensitive document details are exposed.
- 2026-08-07 deliver: Re-read REQ-FUNC-f878c579 and REQ-FUNC-5cd8727a and confirmed their active status, prose, verification, paths, specification, and linked selectors match the implementation.
- 2026-08-07 deliver: The Character Discovery knowledge page and its Files section are current; CHANGELOG is user-language complete; this is not a release, so no project or help version fields changed.
- 2026-08-07 deliver: The five protected planning files retain their recorded SHA-256 values, remain unstaged, and were not modified by this task.
- 2026-08-07 close-out: The supplied request authorizes an explicit-path staged handoff only, so no commit or push was made and the journal is closed before report generation.

## Delivery report (2026-08-07)

- stage: done; type: fix; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-f878c579 - Characters page shall recover from invalid discovery documents
  - REQ-FUNC-5cd8727a - Completed character summary shall report persisted facts
- diff vs merge base: 194 file(s) changed, 19848 line(s) added
- checks: errors=0 warnings=51 notes=0
- checklist: 10/10 done
