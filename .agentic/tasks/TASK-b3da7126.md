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

# TASK-b3da7126 — Preserve custom theme selection in Settings

stage: deliver
type: fix
path: full
requirements: REQ-UX-8e33d3cf
branch: ddp/ps5-custom-theme-selection
opened: 2026-08-08

## Done checklist (current stage)

- [x] repository verification completed; timeout and pre-existing failures recorded and accepted at checkpoint
- [x] diff reviewed against scope, requirements, design, error paths, portability, and security
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report included in the delivery commit
- [ ] close-out: `stage: done` set and committed only after the outcome succeeded
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` updated under `Unreleased` in user language without a release version
- [x] both help files updated to match the user-visible Settings behavior without version changes

## Design

- Component: change only `SettingsPage`; keep `ui_theme_service` public APIs and the removed editing/import/export surface untouched (REQ-UX-8e33d3cf).
- Interface: `load_settings()` rebuilds the combo from `merged_theme_catalog(...)`; `build_settings()` retains its existing merge API (REQ-UX-8e33d3cf).
- Data: retain only the loaded normalized custom collection in page memory for preview and operator-authored labels; never write it back from this page (REQ-UX-8e33d3cf).
- Data: clear the combo before every rebuild so the latest normalized catalog cannot leave duplicates or stale items (REQ-UX-8e33d3cf).
- Rejected: preserving an unlisted custom id only in `build_settings()` would avoid the overwrite but still make selection, preview, localization, and reload incorrect (REQ-UX-8e33d3cf).
- Test seams: focused `SettingsPage` tests cover merged order/filtering, no-op payload preservation, custom stylesheet preview, relabeling, clean reload, and unchanged built-in selection (REQ-UX-8e33d3cf).
- Expected implementation files: `settings_page.py` and `test_settings_page.py`; delivery also updates the requirement, catalog spec, component knowledge, both help files, changelog, and this journal.

## Log

- 2026-08-08 frame: Scope confirmed by the delegated prompt: restore selection, preservation, preview, localization, and clean reload behavior for already persisted valid custom themes in Settings.
- 2026-08-08 frame: Exclusions are PS-1 and PS-6 through PS-9, theme editing/import/export UI, broad service refactors, analysis files, dependency/version/release work, push, merge, and unrelated changes.
- 2026-08-08 frame: The full path is required because custom-theme selection is externally observable behavior and the existing requirement must expand beyond built-ins.
- 2026-08-08 frame: Update REQ-UX-8e33d3cf so the normalized merged theme catalog is the Settings selector source of truth for loading, saving, preview, localization, and reload.
- 2026-08-08 specify: Expanded REQ-UX-8e33d3cf and reconciled the built-in catalog spec with a merged-catalog selector whose built-in prefix order remains stable.
- 2026-08-08 specify: AEGIS check reported no errors and 21 existing repository warnings for the color-like ticket pattern and known outside-layout files.
- 2026-08-08 design: Keep the persisted `ui_themes` payload caller-owned while the page uses a normalized in-memory custom collection for selector rendering and preview.
- 2026-08-08 build: Four focused Settings-page custom-theme regressions red as expected because custom IDs were absent, selection/preview fell back to `audiomancer_dark`, and reload/language handling had no custom entries.
- 2026-08-08 build: The focused Settings-page module passed 9 tests with changed-file Ruff and `py_compile` checks green.
- 2026-08-08 build: AEGIS impacted selection expanded one shared Settings-page path to 675 linked tests and exited 127 before pytest because the Windows command exceeded executable limits.
- 2026-08-08 build: The proportionate manual impacted set passed 87 tests with 20 deselected after seeding a credential-free ignored settings scaffold required by the repository tests.
- 2026-08-08 build: Accepted 21 AEGIS warnings because one color literal is a known ticket-pattern false positive and the remaining outside-layout files predate this task on the base improvement branch.
- 2026-08-08 deliver: `check --strict --run` exited 124 after 1800.3 seconds at 47 percent because the configured full-suite command exceeded the AEGIS timeout; no test failure had appeared before termination.
- 2026-08-08 deliver: The direct full suite completed with 1456 passed, 62 skipped, 1 deselected, and 3 failures outside the Settings component.
- 2026-08-08 deliver: Pre-existing failures `test_speech_blocks_page_header_uses_compact_buttons_and_wider_profile` and `test_speech_blocks_page_restores_selected_chunk_text_selection` reproduced identically on untouched `bugfix/improvements` and are out of scope.
- 2026-08-08 deliver: The full-suite-only `test_tts_settings_page_numeric_increment_arrows_change_values` failure is order-dependent shared-state debt; its complete six-test module passed on both this branch and untouched `bugfix/improvements`, and this task changes no TTS code.
- 2026-08-08 deliver: Task-scoped `check --strict` exited 0 with no errors and 61 warnings.
- 2026-08-08 deliver: Accepted `ticket-ref` for the pre-existing `#303648` color literal and `unticked-deliver` because this journal is intentionally paused at the mandatory pre-commit checkpoint.
- 2026-08-08 deliver: Accepted `uncovered-source` and unrelated `outside-layout` warnings because AEGIS diffs from the repository default branch while this task is based on the existing `bugfix/improvements` program; those reported files predate and are untouched by this task.
- 2026-08-08 deliver: Semantic review found the diff limited to REQ-UX-8e33d3cf, using existing normalization and fallback paths with no new I/O, dependency, platform assumption, secret, editing surface, release version, or analysis-file change.
- 2026-08-08 deliver: Final focused verification passed 9 tests with changed-file Ruff and `py_compile` green, and the ignored credential-free settings scaffold used only for repository tests was removed.
- 2026-08-08 deliver: Human checkpoint approved the exact nine-file staged diff and accepted the documented AEGIS timeout plus three unrelated full-suite failures for a commit-only delivery with journal closeout and no push, merge, or PR.

## Delivery report (2026-08-08)

- stage: deliver; type: fix; path: full; branch: ddp/ps5-custom-theme-selection
- requirements:
  - REQ-UX-8e33d3cf - The Settings page shall select themes from the merged catalog
- task diff vs `bugfix/improvements`: 9 files changed, 380 insertions, 76 deletions
- checks: errors=0 warnings=61 notes=0
- checklist: 9/10 done; open: close-out: `stage: done` set and committed only after the outcome succeeded
