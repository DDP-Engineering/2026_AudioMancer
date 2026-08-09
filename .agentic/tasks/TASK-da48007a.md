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

# TASK-da48007a — Consolidate DUP-04 voice sample runtime flow

stage: deliver
type: change
path: full
requirements: REQ-FUNC-47809158, REQ-FUNC-7a68a78e
branch: ddp/dup-04-voice-runtime-consolidation
opened: 2026-08-09

## Done checklist (current stage)

- [x] focused runtime/controller suites and task-scoped static checks are green, with the user-requested full-suite exclusion recorded
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and monkeypatch seams
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] Unreleased changelog entry written in user language
- [x] journal and report included in the delivery commit
- [ ] close-out commit sets `stage: done` after delivery succeeds

## Log

- 2026-08-09 frame: Scope is DUP-04 only: validate and consolidate behavior-equivalent narrator and character VoiceWeaver sample runtime orchestration while preserving request construction, budgets, persistence ownership, stale-sample timing, UI refresh, messages, and monkeypatch seams.
- 2026-08-09 frame: Excludes DUP-03 and every other duplicate item, public API redesign, persisted-schema changes, planning-file edits, full-suite execution, push, merge, and parent-worktree edits.
- 2026-08-09 frame: Full path chosen because the refactor crosses runtime orchestration and caller-specific persistence boundaries, although it intentionally changes no external behavior.
- 2026-08-09 frame: Reuse REQ-FUNC-47809158 and REQ-FUNC-7a68a78e for narrator and character generation safety; the detailed user instruction confirms scope and authorizes reviewed delivery commits.
- 2026-08-09 specify: Existing narrator and character generation requirements fully cover the preserved behavior, so no new observable-behavior requirement or persisted-format spec is needed.

## Design

- REQ-FUNC-47809158 and REQ-FUNC-7a68a78e: add one function in `tts_runtime_ui_support.py` for the equivalent probe, capability, load, generation, terminal-result, progress, cancellation, timeout, and WAV-download flow.
- REQ-FUNC-47809158 and REQ-FUNC-7a68a78e: accept a narrow generation-request callback because narrator and character request construction use different services and inputs.
- REQ-FUNC-47809158: keep cached and discovered-model preview budget checks in the narrator adapter and keep narrator persistence in `store_profile_sample`.
- REQ-FUNC-7a68a78e: keep target/language request construction and character persistence in `store_target_sample`; batch sequencing stays in the character controller.
- Both requirements: return generation request, summary, and WAV bytes as ordinary data; do not create a framework, class hierarchy, schema, or persistence callback inside the shared runtime helper.
- Both requirements: preserve private controller entry points and progress/import-error wrappers as compatibility and monkeypatch seams while delegating their common bodies.
- Rejected: sharing completion/failure/cancellation UI handlers, stale deletion, or downstream invalidation, because narrator and character refresh and ownership behavior are not equivalent.
- Test seams: focused shared-support tests cover success, cancellation, and provider/runtime errors; focused controller tests cover caller-specific persistence and refresh behavior.
- Expected files: both controller modules, `tts_runtime_ui_support.py`, their three focused test modules, the two reused requirements, Voice Profiles and Character Voices knowledge, changelog, task journal, and generated report.
- 2026-08-09 build: six focused shared-flow and caller-ownership regressions red as expected because `tts_runtime_ui_support.run_voice_design_generation` did not exist.
- 2026-08-10 build: the six new regressions passed after the shared runtime helper and narrow narrator/character adapters were implemented.
- 2026-08-10 build: focused support and controller modules passed with 57 tests in 235.43 seconds.
- 2026-08-10 build: task-scoped Ruff passed and AEGIS strict static checking reported zero errors with 98 pre-existing repository-wide advisory warnings.
- 2026-08-10 build: `test --impacted` and the full delivery suite were intentionally not run because the user explicitly required focused tests and static checks only.
- 2026-08-10 deliver: semantic review retained narrator prepare-before-budget ordering through a narrow pre-probe callback and preserved each caller's explicit language fallback.
- 2026-08-10 deliver: final focused support and controller modules passed with 57 tests in 283.55 seconds after confirming the timed-out launcher left no orphaned worktree pytest process.
- 2026-08-10 deliver: Ruff and byte-compilation passed on every changed Python file, and AEGIS strict static checking reported zero errors with repository-wide advisory warnings accepted as unrelated baseline findings.
- 2026-08-10 deliver: reviewed 12 changed implementation, test, requirement, knowledge, and changelog files plus this journal against DUP-04; no planning files, schemas, releases, parent worktrees, remotes, or other duplicate items were changed.
- 2026-08-10 deliver: standing user approval authorizes the reviewed delivery commit and separate close-out commit without push or merge.

## Delivery report (2026-08-10)

- stage: deliver; type: change; path: full; branch: ddp/dup-04-voice-runtime-consolidation
- requirements:
  - REQ-FUNC-47809158 - The Narrator Voice controller shall manage sample generation with
  - REQ-FUNC-7a68a78e - The Character Voices controller shall preserve the existing sample on
- task diff vs `246bd55`: 13 file(s) changed, 933 line(s) added, 328 line(s) deleted
- checks: errors=0 warnings=99 notes=0
- checklist: 6/7 done; open: close-out commit sets `stage: done` after delivery succeeds
