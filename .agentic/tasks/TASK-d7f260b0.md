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

# TASK-d7f260b0 — Fix resumed ambience ordering and discovery window budgets

stage: deliver
type: fix
path: quick
requirements: REQ-FUNC-b355f8e6, REQ-FUNC-9f4389c9
branch: ddp/fix-speech-resume-ambience-character-window
opened: 2026-08-09

## Done checklist (current stage)

- [x] task-scoped `check --strict` green without `--run` as explicitly scoped;
      focused tests passed, no diff-introduced failures, and warnings explained
- [x] diff reviewed against scope, requirements, design, error paths,
      portability, security - no unrequested changes
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report inside the delivery commit; agreed outcome delivered
- [ ] close-out: `stage: done` set and committed only after the outcome succeeded
- [x] project additions: code style and Unreleased changelog complete; release-only
      version and help-file workflow not applicable

## Log

- 2026-08-09 frame: Validate BUG-03 resumed direct-segment ordering with Scene Ambience and BUG-04 production Character Discovery window parameters, then fix only reproduced defects with focused regressions.
- 2026-08-09 frame: Exclude full-suite testing, releases and version/help changes, planning files, refactors, unrelated cleanup or failures, push, merge, and parent-checkout edits.
- 2026-08-09 frame: Use the quick path because both corrections preserve existing interfaces and data formats while restoring behavior already covered by REQ-FUNC-b355f8e6 and REQ-FUNC-9f4389c9.
- 2026-08-09 frame: The task branch is ddp/fix-speech-resume-ambience-character-window and the delegation explicitly approves uninterrupted validation, commits, and close-out.
- 2026-08-09 frame: Update REQ-FUNC-b355f8e6 for resumed segment ordering across ambience insertion and REQ-FUNC-9f4389c9 for production use of profile-derived window budgets.
- 2026-08-09 build: tests/test_speech_blocks_service.py::test_speech_blocks_resume_with_scene_ambience_preserves_unfinished_direct_segment_order red as expected because ambience insertion reset resumed sequence order and persisted First A, Second, First B.
- 2026-08-09 build: tests/test_character_discovery_service.py::test_start_discovery_builds_windows_once_with_budget_metadata_parameters red as expected because production passed window size 8 and overlap 1 instead of metadata values 0 and 3.
- 2026-08-09 build: the default python launch failed before collection because PySide6 was unavailable, so red and green evidence uses the shared AudioMancer virtual-environment interpreter with this worktree's explicit PYTHONPATH.
- 2026-08-09 build: both focused regressions passed after moving resumed sequence continuation after ambience insertion and sourcing Character Discovery window arguments from budget metadata (2 passed).
- 2026-08-09 build: the first two-file focused run had 149 passed and one fixture KeyError because an existing resume test stub omitted max_window_chunks and window_overlap; adding its established default values keeps the test's original window plan.
- 2026-08-09 build: the repeated focused Speech Blocks and Character Discovery service files passed with 150 tests.
- 2026-08-09 build: AEGIS test --impacted expanded 1085 historical references and exited 127 before pytest, so the successful direct focused files are the test evidence and the wrapper was not retried.
- 2026-08-09 build: Ruff passed on the four changed Python source and test files.
- 2026-08-09 build: task-scoped strict AEGIS static check reported zero errors and strict ok; 90 repository-baseline ticket, layout, and uncovered-source warnings are accepted because none identifies this task's changed behavior.
- 2026-08-09 deliver: self-review confirmed the two one-line production corrections preserve interfaces, persisted IDs, checkpoint behavior, and existing profile-budget semantics with no refactor, planning, release, version, help, push, merge, or parent-checkout changes.
- 2026-08-09 deliver: REQ-FUNC-b355f8e6 maps to the resumed ambience order regression and REQ-FUNC-9f4389c9 maps to the production window-parameter regression; both remain active and their linked selectors exist.
- 2026-08-09 deliver: commit and journal close-out are already approved by the delegation after exact staging and report review; no PR, push, or merge is authorized.
- 2026-08-09 deliver: the generated report's 408-file merge-base statistic and 91 baseline warnings are repository-history artifacts; the HEAD-relative staged diff is the authoritative delivery scope.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: quick; branch: ddp/fix-speech-resume-ambience-character-window
- requirements:
  - REQ-FUNC-b355f8e6 - Speech-block generation shall resume from persisted progress across
  - REQ-FUNC-9f4389c9 - Character discovery shall construct bounded budgeted source windows
- diff vs merge base: 408 file(s) changed, 38206 line(s) added
- checks: errors=0 warnings=91 notes=0
- checklist: 7/8 done; open: close-out: `stage: done` set and committed only after the outcome succeeded
