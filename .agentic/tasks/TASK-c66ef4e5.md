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

# TASK-c66ef4e5 — Narrator voice script-aware preview budgets

stage: done
type: fix
path: full
requirements: REQ-FUNC-2b7862b5, REQ-FUNC-efbb32a4
branch: ddp/narrator-voice-budget-units
opened: 2026-08-07

## Done checklist (current stage)

- [x] strict AEGIS check and complete configured suite passed; inherited warnings are recorded
- [x] diff reviewed against scope, requirements, multilingual boundaries, runtime behavior, localization, portability, and security
- [x] Voice Profiles knowledge, English/Romanian help, and the Unreleased changelog are updated
- [x] requirements re-read: active status, prose, verification, paths, and linked tests are true
- [x] delivery report generated and read; exact task files are staged without commit or push by request
- [x] code follows `01_Documentation/Code_Style.md`
- [x] this is not a release, so the four-place version workflow does not apply
- [x] close-out after the user-approved commit and delivery outcome

## Log

- 2026-08-07 frame: From b224d95, replace narrator preview whitespace counts with existing script-aware budget units for generated-profile bounds, sample rejection, and every narrator operator budget projection; preserve the shared TTS budget service semantics.
- 2026-08-07 frame: Excludes NV-3 and later, character-limit-helper refactoring, changes under 0_Planning/Analysis_2026-08-02, commits, pushes, PRs, and task close-out.
- 2026-08-07 frame: Full path because this changes multilingual user-visible validation and adds two independently testable functional requirements.
- 2026-08-07 frame: The requested branch is attached to another worktree, so ddp/narrator-voice-budget-units was created at the exact requested b224d95 base.
- 2026-08-07 frame: Proposed requirements are script-aware AI narrator preview bounds and script-aware narrator sample budget enforcement with truthful counters.
- 2026-08-07 specify: Created REQ-FUNC-2b7862b5 for generated-profile duration-bound units and REQ-FUNC-efbb32a4 for runtime guard and operator budget-unit truth; no spec is needed because both reuse the documented shared helper directly.
- 2026-08-07 specify: `check --task` reported no errors; its 52 inherited warnings are repo-wide uncovered-source, layout, and an unrelated ticket-reference warning, while empty test links are expected before build.
- 2026-08-07 design: The dated analysis remains current at all four consumers; its one superseded detail is that `estimate_budget_units` now also counts Unicode word-like tokens, but it still takes the conservative maximum with per-script character units.
- 2026-08-07 design: REQ-FUNC-2b7862b5 changes only generated-profile bound counts; REQ-FUNC-efbb32a4 changes the worker, state, and page to the same helper while retaining the shared safe-budget helper and payload semantics.
- 2026-08-07 design: Local values and operator wording become budget units, while legacy safe-word helper names remain unchanged to avoid altering Speech Blocks and other TTS consumers.
- 2026-08-07 design: Tests attach to generated-profile validation, the pre-runtime sample worker, state status lines, and the live page label; rejected alternative is changing `tts_budget_service` names or formulas because that would expand scope and silently affect cross-consumers.
- 2026-08-07 build: test_narrator_profile_generation_service.py::test_narrator_profile_generation_accepts_default_compact_script_preview_at_minimum_budget red as expected because Chinese counted as 1 word and Korean as 12 words below the unchanged 15-unit minimum.
- 2026-08-07 build: test_narator_voice_ui_controller.py::test_narator_voice_generate_sample_rejects_compact_script_budget_before_runtime_work red as expected because a 15-unit Chinese preview reached VoiceWeaver status work under the whitespace count.
- 2026-08-07 build: narrator state and page compact-script budget-counter tests red as expected because both displayed 1 safe word instead of 15 safe budget units.
- 2026-08-08 build: Focused Narrator/TTS/UI and cross-consumer tests passed (159), followed by the configured full suite (1414 passed, 62 skipped, 1 deselected) and strict run (1383.4s test command, no errors, 52 inherited warnings).
- 2026-08-08 build: Independent multilingual and UI/runtime reviews both found that the first guard still probed VoiceWeaver; a cached-or-fallback preflight now rejects before probing while the post-probe guard retains the live limit.
- 2026-08-08 build: test_narator_voice_ui_controller.py::test_narator_voice_generate_sample_rejects_compact_script_budget_before_runtime_work red after the strengthened probe-failure seam and green after the preflight guard; related sample worker tests, Ruff, and compilation are green.
- 2026-08-08 build: Multilingual review requested explicit Latin boundary coverage; 15 and 30 unit previews now pass while 31 units are rejected, and the focused eight-test regression set is green.
- 2026-08-08 deliver: Final `check --task TASK-c66ef4e5 --strict --run` exit 0 after its complete configured test command (1441.6s); no errors and 52 accepted inherited warnings.
- 2026-08-08 deliver: Accepted warnings are one pre-existing requirement ticket reference, 31 repository-wide uncovered-source warnings, and 20 configuration layout warnings for documentation and read-only planning evidence outside configured source/test globs.
- 2026-08-08 deliver: Two independent reviews approved after resolving the pre-probe short-circuit finding; no out-of-scope changes, planning-file modifications, portability, security, or localization findings remain.
- 2026-08-08 deliver: Accepted the final `unticked-deliver` warning because the user explicitly requires stage `deliver` with only the post-commit close-out item open; the report's merge-base diff count includes predecessor-branch work, while staging is limited to this task's files.
- 2026-08-08 deliver: Close-out succeeded: delivery commit f9f8ed8 was pushed, merge commit a32bf88 was pushed to bugfix/improvements, and the close-out commit will now follow on this task branch.

## Design

- `narrator_profile_generation_service` will call `estimate_budget_units` for both established duration bounds (REQ-FUNC-2b7862b5).
- The worker, state status line, and page label will call that same helper; the safe numeric threshold remains from `estimated_safe_word_count` without a service-contract change (REQ-FUNC-efbb32a4).
- Local variables and English/Romanian wording will call the displayed measurement “units”; existing localization keys and compatibility payload names stay stable (REQ-FUNC-efbb32a4).
- Tests will prove compact Japanese acceptance, Korean-default relevance, a compact-script pre-runtime short circuit, and matching page/state counters (REQ-FUNC-2b7862b5, REQ-FUNC-efbb32a4).

## Delivery report (2026-08-08)

- stage: deliver; type: fix; path: full; branch: ddp/narrator-voice-budget-units
- requirements:
  - REQ-FUNC-2b7862b5 - AI narrator previews shall use script-aware duration units
  - REQ-FUNC-efbb32a4 - Narrator samples shall enforce script-aware safe TTS budgets
- diff vs merge base: 218 file(s) changed, 21602 line(s) added
- checks: errors=0 warnings=53 notes=0
- checklist: 7/8 done; open: close-out after the user-approved commit and delivery outcome
