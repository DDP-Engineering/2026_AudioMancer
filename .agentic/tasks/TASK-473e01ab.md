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

# TASK-473e01ab — Recover settings reads without data loss

stage: done
type: fix
path: full
requirements: REQ-PLAT-2a16daee, REQ-PLAT-b950f73c, REQ-REL-c822b662
branch: ddp/ps3-ps4-settings-recovery
opened: 2026-08-08

## Done checklist (current stage)

- [x] accepted delivery verification recorded: wrapper timeout documented, direct full suite green, and strict static audit green
- [x] diff reviewed against scope, requirements, design, error paths, portability, and security
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report inside the delivery commit; agreed outcome delivered
- [x] close-out: `stage: done` set and committed only after the outcome succeeded
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` Unreleased section written in user language
- [x] both help files updated in English and Romanian without a version change
- [x] no release version changes are present

## Log

- 2026-08-08 frame: Scope approved by the root coordinator from the user's explicit continue: accept valid UTF-8 BOM settings and recover malformed or undecodable active settings without silent data loss or startup failure.
- 2026-08-08 frame: Scope is limited to the settings read/recovery path, focused and neighboring tests, AEGIS artifacts, knowledge, changelog, and bilingual Help documentation.
- 2026-08-08 frame: Exclusions are UI prompts, PS-1, PS-5 through PS-9, general settings refactors, dependency or version changes, secret/history cleanup, `.gitattributes`, releases, planning-document edits, merge, push, and PR creation.
- 2026-08-08 frame: Full path selected because startup recovery changes externally observable persisted-data handling and must preserve operator-owned bytes.
- 2026-08-08 frame: Proposed requirements cover UTF-8 BOM acceptance, collision-safe exact-byte recovery before default replacement, and non-destructive safe defaults when settings access fails.
- 2026-08-08 specify: Created REQ-PLAT-2a16daee for optional UTF-8 BOM acceptance.
- 2026-08-08 specify: Created REQ-PLAT-b950f73c for exact-byte collision-safe corruption recovery.
- 2026-08-08 specify: Created REQ-REL-c822b662 for safe in-memory defaults and content-free warnings when recovery I/O fails.
- 2026-08-08 specify: No separate specification is needed because the requirements and the task design record fully define the file naming, ordering, and failure states.
- 2026-08-08 specify: Advisory check reported zero errors and 21 pre-existing repository/layout warnings unrelated to the new requirement formats.

## Design

- Component: Platform Settings UI retains the public `load_settings()` signature and existing validation/self-heal contract (REQ-PLAT-2a16daee, REQ-PLAT-b950f73c, REQ-REL-c822b662).
- Read path: read exact bytes once, decode with `utf-8-sig`, then parse JSON so an optional BOM is transparent (REQ-PLAT-2a16daee).
- Recovery data: reserve `settings.corrupt.json`, then `settings.corrupt.<n>.json`, using exclusive binary creation so an existing backup is never overwritten (REQ-PLAT-b950f73c).
- Recovery ordering: flush and sync the exact-byte backup before using the existing atomic settings writer to replace the active path with built-in defaults (REQ-PLAT-b950f73c).
- Failure state: read or backup `OSError` returns in-memory defaults without changing the active file; a later default-write `OSError` returns defaults with both the completed backup and atomic-writer-protected active bytes recoverable (REQ-REL-c822b662).
- Logging: recovery warnings identify paths and outcomes but never include persisted settings content or credential values (REQ-REL-c822b662).
- Rejected alternative: renaming the active file first would remove the active path before a replacement is durable and offers weaker cross-platform collision guarantees than exclusive backup creation (REQ-PLAT-b950f73c, REQ-REL-c822b662).
- Test seam for REQ-PLAT-2a16daee: `test_settings_service.py` loads a BOM fixture containing non-default validated values and asserts no backup.
- Test seam for REQ-PLAT-b950f73c: the same module exercises malformed JSON, invalid UTF-8, exact bytes, active defaults, and a pre-existing backup.
- Test seam for REQ-REL-c822b662: the same module injects read, backup, and post-backup write failures and inspects paths plus content-free warnings.
- Behavior files: `settings_service.py` and `test_settings_service.py`; delivery also updates the three requirements, task journal, Platform Settings knowledge, changelog, and both Help files.

## Log continuation

- 2026-08-08 design: Advisory check reported zero errors and the same 21 pre-existing repository/layout warnings, so the decision record is ready for build.
- 2026-08-08 build: `tests/test_settings_service.py::test_load_settings_accepts_utf8_bom_without_creating_backup` red as expected because the BOM payload was classified as invalid JSON and its non-default values were replaced.
- 2026-08-08 build: REQ-PLAT-b950f73c recovery tests red as expected because malformed JSON had no backup, invalid UTF-8 raised, and no distinct backup followed an existing one.
- 2026-08-08 build: `test --impacted` could not start its 661-selector legacy expansion and exited 127 on Windows, so direct focused and neighboring modules are the recorded inner-loop fallback.
- 2026-08-08 build: REQ-REL-c822b662 read, backup, and post-backup write failure tests red as expected because each simulated `PermissionError` escaped `load_settings()`.
- 2026-08-08 build: All seven new settings-read recovery regressions passed.
- 2026-08-08 build: Neighbor batch completed with 91 passed and two baseline failures caused only by the absent ignored app-local settings scaffold.
- 2026-08-08 build: Coordinator-authorized credential-free scaffold setup made the two exact baseline selectors pass, and the ignored scaffold was removed and verified absent immediately afterward.
- 2026-08-08 build: Focused settings service completed with 34 passed and one scaffold-only selector deselected after the exact scaffold rerun.
- 2026-08-08 build: Ruff and Python byte-compilation passed on both changed Python files.
- 2026-08-08 build: Accepted `ticket-ref` on existing REQ-UX-4753a4bf because it is unrelated baseline requirement content.
- 2026-08-08 build: Accepted `outside-layout` on established Help, planning, changelog, and HowToTest paths because they are repository-owned artifacts rather than stray task output.
- 2026-08-08 build: Advisory check completed with zero errors and 21 explained pre-existing repository/layout warnings.
- 2026-08-08 build: All three requirements are active with current source paths and linked red-to-green selectors.
- 2026-08-08 deliver: `check --strict --run` exited 1 only because its configured pytest command timed out with exit 124 after 1800.3 seconds at 52 percent, with no test failure reported before the timeout.
- 2026-08-08 deliver: The documented direct configured full-suite fallback passed with 1455 passed, 62 skipped, and 1 performance test deselected in 1989.48 seconds.
- 2026-08-08 deliver: The credential-free isolated-worktree scaffold used for full-suite validation was removed and verified absent without inspecting or referencing any primary-checkout settings.
- 2026-08-08 deliver: Full `ruff check src tests`, changed-file Python compilation, and `git diff --check` passed after the full suite.
- 2026-08-08 deliver: Task-scoped `check --strict` without command execution returned `strict: ok` with zero errors and 60 warnings.
- 2026-08-08 deliver: Accepted the inherited ticket-reference warning, branch-wide uncovered-source warnings from the baseline delta, and configured outside-layout warnings because this task neither introduced nor owns those findings.
- 2026-08-08 deliver: The remaining unticked-delivery warning is expected until the human checkpoint, delivery commit, and journal-only close-out commit are completed.
- 2026-08-08 deliver: Semantic review confirmed BOM transparency, exclusive collision-safe exact-byte backups, durable backup-before-atomic-replacement ordering, non-destructive I/O fallback, content-free warnings, and unchanged valid-settings validation interfaces.
- 2026-08-08 deliver: Updated Platform Settings knowledge, the Unreleased changelog, and English and Romanian Help while leaving project and Help versions unchanged because this task is not a release.
- 2026-08-08 deliver: Re-read all three active requirements and confirmed their prose, verification, affected source path, and linked green selectors match the implementation.
- 2026-08-08 deliver: Confirmed no planning, dependency, version, release, UI-prompt, secret-history, or real local-settings changes are present.
- 2026-08-08 deliver: Final strict static audit remained `strict: ok` with one inherited ticket reference, 38 branch-wide uncovered-source warnings, 20 configured outside-layout warnings, and one expected three-item open-delivery warning.
- 2026-08-08 deliver: Both Help files parsed successfully as HTML, all six Help/application version lines remain 2.0.0, and the temporary credential-free settings scaffold remains absent.
- 2026-08-08 deliver: Human approval accepted the staged ten-file recovery delivery, independent hunk review, green direct full suite and strict static audit, and authorized the delivery plus journal-only close-out commits without merge, push, or PR.
- 2026-08-08 close-out: Delivery commit `cbf5e383ab76f49850d478a373e9d7f77f2d05cb` succeeded and TASK-473e01ab was marked done without merge, push, or pull request.

## Delivery report (2026-08-08)

- stage: deliver; type: fix; path: full; branch: ddp/ps3-ps4-settings-recovery
- requirements:
  - REQ-PLAT-2a16daee - Accept UTF-8 BOM settings
  - REQ-PLAT-b950f73c - Preserve corrupt settings before replacement
  - REQ-REL-c822b662 - Degrade safely when settings recovery access fails
- diff vs merge base: 245 file(s) changed, 24804 line(s) added
- diff note: merge-base totals include inherited `bugfix/improvements` history; the checkpoint's staged stat and digest are the exact task-local delivery scope
- checks: errors=0 warnings=60 notes=0
- checklist: 10/11 done; open: close-out: `stage: done` set and committed only after the outcome succeeded
