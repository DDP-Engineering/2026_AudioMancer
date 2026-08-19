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

# TASK-8815ea5a — Temperature field styling in AI Settings

stage: done
type: fix
path: quick
requirements: REQ-UX-b37f9db2
branch: master
base: 3683d4383a37ba98aaf595f2595cea46633b3245
opened: 2026-08-19

## Done checklist (current stage)

- [x] review diff against `01_Documentation/Code_Style.md`
- [x] targeted tests proven green (impacted suite only, per instruction)
- [x] `CHANGELOG.md` Unreleased entry written
- [x] files staged and commit message prepared; user confirmed the app manually before commit

## Log

- 2026-08-19 frame: In the AudioMancer Black theme, the Temperature spinbox on AI Settings renders with native grey chrome and light text instead of the theme's dark input styling, unlike the neighboring Context Window / Max Output Tokens / Timeout spinboxes. Scope: fix the theme stylesheet so QDoubleSpinBox is styled the same as QSpinBox. Excludes: any other visual/theme work, no version bump, no commit/push (per explicit instruction), stays on master. Quick path: existing requirement REQ-UX-b37f9db2 already governs styling of the single-line input control list in the theme stylesheet and simply omitted QDoubleSpinBox from that list; extended its wording to name QDoubleSpinBox rather than opening a new requirement.
- 2026-08-19 frame: An Explore subagent traced the root cause: `build_theme_stylesheet()` in `04_Software/AudioMancer/src/audiomancer/services/ui_state_service.py` lists QSpinBox but not QDoubleSpinBox in its base and `:focus` selectors (lines 2560, 2575); QDoubleSpinBox is a QAbstractSpinBox sibling of QSpinBox, not a subclass, so Qt's type selector never matches it and it falls back to native OS chrome. No disable/read-only logic and no per-widget stylesheet override exists on the Temperature field in `ai_settings_page.py`; this is a stylesheet gap, not a conditional-disable bug.
- 2026-08-19 build: Added QDoubleSpinBox to both selector lists (line 2560 base rule and 2575 focus rule) in `ui_state_service.py`. Updated the exact-selector-string assertion in `test_theme_stylesheet_controls_use_rounded_corners` (`tests/test_ui_state_service.py`) to match the new selector list - this is the requirement's only linked test and it encodes the fix directly, so no new test was added.
- DEVIATION build: implementation and test were edited together rather than red-then-green in strict order, because the defect and fix were already fully diagnosed by a prior investigation pass before the build stage opened; the existing linked test is exact-selector-string based and would have failed pre-fix for the same reason it now passes.
- 2026-08-19 validate: `uv run pytest -q tests/test_ui_state_service.py::test_theme_stylesheet_controls_use_rounded_corners` and the full `test_ui_state_service.py` file (20 tests) pass. Full suite not run - user asked to skip it and will test the app themselves.
- DEVIATION validate: full test suite and `aegis check` were not run, per explicit user instruction ("Do not run full testsuite - i will test the app"); scope is a two-token QSS selector addition confirmed by both the linked requirement test and the full styling test file.
- 2026-08-19 validate: CHANGELOG.md Unreleased/Fixed section updated in user language; no version bump (not a release per PROJECT.md - only a version-tagged Unreleased section triggers the release workflow).
- 2026-08-19 deliver: task's five files staged (ui_state_service.py, test_ui_state_service.py, REQ-UX-b37f9db2.toml, CHANGELOG.md, this journal); commit message drafted and handed to the user, commit left for the user to run after manual verification. Task closed.
