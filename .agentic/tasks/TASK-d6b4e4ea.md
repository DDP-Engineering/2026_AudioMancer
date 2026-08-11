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

# TASK-d6b4e4ea — Implement confirmed 2026-08-10 analysis fixes

stage: deliver
type: change
path: full
requirements: REQ-FUNC-4d5ece0f, REQ-FUNC-1a2d28bb, REQ-DATA-966afd2d, REQ-REL-484a0674, REQ-REL-8dc30a4b, REQ-REL-0f90f2a4, REQ-DATA-d5324480, REQ-FUNC-3199dbb1, REQ-FUNC-6f6e045f, REQ-REL-1a521d45, REQ-DATA-330b5d31, REQ-REL-557b0a5f, REQ-DATA-ca7c6c36, REQ-SEC-cdbd652c, REQ-PLAT-0ef29ded, REQ-REL-8a56ff1e, REQ-REL-50e2f540, REQ-REL-3b9c207e, REQ-UX-cc7bc507, REQ-DATA-5e59c157, REQ-UX-29c94862, REQ-UX-6ec7fe61, REQ-FUNC-f04f2515, REQ-UX-9a7fc380, REQ-PLAT-e1ca40ab, REQ-UX-a6c3e152, REQ-FUNC-2b7862b5, REQ-FUNC-efbb32a4, REQ-FUNC-90dd5691, REQ-FUNC-ff2e2c94, REQ-FUNC-085699ab, REQ-FUNC-efcaeeed, REQ-PLAT-2a16daee
branch: ddp/analysis-2026-08-10-fixes
opened: 2026-08-10

## Done checklist (current stage)

- [x] `check --strict --run` green, or every environmental deviation and remaining warning is explained in the log
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and unrequested changes
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, links all true
- [x] delivery confirmed by the human before the commit
- [ ] journal and report inside the delivery commit; approved local outcome delivered
- [ ] close-out: `stage: done` set and committed only after the approved outcome succeeded
- [x] project delivery additions and code style verified; no release version workflow required

## Log

- 2026-08-10 frame: Scope is the confirmed correctness, data-integrity, robustness, and safety defects in the Bugs sections of reports 01 through 05, the explicit unsupported ja/ko/zh target decision, and confirmed user-facing Narrator spelling, all implemented test-first in this isolated worktree.
- 2026-08-10 frame: Exclusions are the void CJK re-split claim, performance-only work, broad dead-code or duplicate-code cleanup, VoiceWeaver model-management endpoint removal, shared-runner/controller refactors, speculative abstractions, state-service base classes, subjective status/toast/sidebar/confirmation-fatigue UX, internal compatibility renames, releases, main-worktree edits before approval, pushes, and analysis-document edits.
- 2026-08-10 frame: The full path is required because language support changes externally observable behavior and the bug set spans persisted data, provider compatibility, filesystem safety, and UI state.
- 2026-08-10 frame: Expected requirements cover visible EPUB blocks, shared European chapter labels, Cleanup reset and online counts, provider repair/retry/fence handling, resumable character discovery and diagnostics, translation status preservation, prompt substitution, VoiceWeaver polling, Speech Blocks report/timestamps, voice-plan corruption, Narrator labels, export/settings/reset robustness, project activation/edit/progress/playback/page activation/runtime status/confirmation safety, and unsupported translation targets with retained Latin/Cyrillic source guarding.
- 2026-08-10 frame: Autopilot scope checkpoint was explicitly authorized by the user, so work continues without pausing at frame.
- 2026-08-10 specify: Added one independently verifiable draft requirement for each candidate behavior, linked exact existing requirements where they already govern the surface, retired the two compact-script TTS requirements invalidated by unsupported ja/ko/zh targets, and retained the CJK/Hangul source-rejection requirement.
- 2026-08-10 specify: Advisory check reported no errors; unrelated historical warnings remain for a ticket-like token in REQ-UX-4753a4bf and an open prior pytest-runtime delivery journal.
- 2026-08-10 triage: Rejected the online-fragment counter finding because the current durable contract explicitly counts submitted fragments including failed retry attempts.
- 2026-08-10 triage: Rejected the retranslate status finding because REQ-FUNC-a0ab9df4 explicitly requires status re-derivation from unchanged chunk review state after interruption.
- 2026-08-10 triage: Excluded extraction checkpoint throttling, whitespace-boundary indexing, and all other performance-only proposals by scope.
- 2026-08-10 test: test --impacted (747 test ref(s)) exit 127 (0.0s)

## Design

- Components: preserve existing service/controller boundaries and make only local fixes in Text Cleanup/Chunking, AI Runtime, Character Discovery, Speech/Voice runtime, Project Lifecycle/Settings, and App Shell UI.
- Interfaces: no public signature changes except removing obsolete optional script-name plumbing where ja/ko/zh-only budget behavior is retired (REQ-PLAT-e1ca40ab).
- Data: persisted schemas and stable internal IDs remain unchanged; fixes only preserve truthful values, reject unsafe destinations, tolerate malformed reads, and avoid fabricated timestamps (REQ-DATA-966afd2d, REQ-DATA-d5324480, REQ-DATA-330b5d31, REQ-DATA-ca7c6c36).
- Provider behavior: retain the active compatibility payload for repair and replace message-text retry guesses with a typed transient boundary (REQ-REL-484a0674, REQ-REL-8dc30a4b).
- UI behavior: use existing page, dialog, playback, and confirmation seams; do not introduce toast, status-bar, or shared-controller abstractions (REQ-UX-cc7bc507, REQ-DATA-5e59c157, REQ-UX-29c94862, REQ-UX-6ec7fe61, REQ-UX-9a7fc380).
- Language support: remove ja/ko/zh target-only options, labels, previews, compact-script TTS budgeting, and tests/help claims while retaining the minimal Latin/Cyrillic versus unsupported-script source guard (REQ-PLAT-e1ca40ab, REQ-FUNC-ff2e2c94).
- Rejected alternative: broad splitter, runner, controller, persistence, and naming refactors would exceed the confirmed behavior and risk compatibility; focused local patches are safer.
- Test seams: each requirement attaches to the smallest existing service or controller test module named in its verification; retired requirements are verified by absence/configuration coverage, and existing requirements retain their current selectors.
- 2026-08-10 design: Kept changes inside existing seams with no new shared architecture or persisted schema; advisory check again reported only the two unrelated historical warnings logged above.
- 2026-08-10 build red: Focused serial regressions failed before source edits for visible EPUB containers, shared European chapter labels, Cleanup provenance reset, one-pass prompt placeholders, typed provider retry classification, and single-line fenced JSON preservation.
- 2026-08-10 build red: Focused serial regressions failed before source edits for premature VoiceWeaver idle polling, empty Speech Blocks IDs, malformed voice-plan JSON, archive destinations inside the active project, BOM packaged settings, boolean integer settings, and removal of ja/ko/zh targets and previews.
- 2026-08-10 build red: Focused serial regressions failed before source edits for Character Discovery empty-synthesis resume and actual failure detail, stable Speech Blocks completion timestamps, best-effort reset deletion, destroyed viewport cleanup, Home container activation with translation-edit flush, token-usage retention, and exclusive audio playback.
- 2026-08-10 build red: Focused serial regressions failed before source edits for page refresh ordering, Narrator navigation and voice-target spelling, case-insensitive terminal TTS status, default-No narrator confirmations, provider compatibility retention during JSON repair, and preservation of original archive and snapshot failures when temporary cleanup also fails.
- 2026-08-10 triage: Rejected no-op status-message replacement, confirmation-fatigue restructuring, toast design, sidebar sizing, broad visual polish, and other subjective UX proposals because no existing requirement or help contract established them and no required red regression was available.
- 2026-08-10 triage: Rejected broad dead-code removal, unused VoiceWeaver model-management endpoint deletion, general deduplication, shared runner/controller refactors, speculative abstractions, and a state-service base class as explicitly excluded scope.
- 2026-08-10 build red: The existing strict structured-output regression was tightened before marker-conversion edits and failed because the private response-format compatibility exception escaped with the raw provider body instead of a clear public RuntimeError.
- 2026-08-10 build red: A focused AI Translation page regression failed before its page edit because state refresh stopped the debounce timer and discarded the pending edit without emitting it.
- 2026-08-10 build: The focused new regression set passed 35 tests, the affected text/AI/settings/language modules passed 365 tests, the affected speech/voice/project-lifecycle modules passed 184 tests, and the guide/configuration/localization selectors passed 64 tests.
- 2026-08-10 build: Four broader-module regressions exposed an invalid Cleanup provenance value and three obsolete message-text retry fixtures; the production value was corrected to the existing cleanup_roles contract, the fixtures were converted to the typed transient seam, and all five exact selectors passed.
- 2026-08-10 build: One serial UI module batch exceeded its 15-minute command-launcher bound with no buffered pytest output; the original healthy process was not duplicated or killed and exited shortly afterward, so no result is claimed for that batch and its coverage is deferred to the single direct full suite.
- 2026-08-10 build: AEGIS test --impacted exited 127 before pytest because its generated command changed into the application directory while retaining repository-prefixed selectors; exact linked focused selectors were run directly and are recorded above.
- 2026-08-10 build: Every delivered requirement is active with current affected paths and linked tests, the two removed compact-script requirements are retired with reasons, and the retained source-script guard remains active.
- 2026-08-10 build: Ruff passed for src and tests; task-scoped AEGIS strict check reported no errors and only the pre-existing ticket token, prior open delivery journal, and explicitly required guide/changelog outside-layout warnings.
- 2026-08-10 build: Transitioned to deliver after completing test-first implementation and recording the environmental impacted-run limitation honestly.
- 2026-08-11 deliver: The single direct serial full suite completed in 2252.09 seconds with 1703 passed, 62 skipped, 1 deselected, and 3 failed selectors.
- 2026-08-11 deliver: The three failures were reproduced serially and classified as the intended Narrator wording assertion plus two stale base assertions for a non-consuming report service and the already-established TTS Apply label; correcting only those tests produced 3 passed in 0.31 seconds.
- 2026-08-11 deliver: The full suite was not repeated after the focused corrections because the owner explicitly required exactly one full-suite invocation; the recorded full-suite exit remains non-zero and is not described as green.
- 2026-08-11 deliver: The generated ignored settings.json was verified to contain default language and empty API keys, then removed by its exact owned path; the ignored local virtual environment remains unstaged.
- 2026-08-11 deliver: AEGIS check --strict --run was intentionally not invoked because its configured test command would violate the owner's exactly-once direct full-suite instruction; Ruff, git diff --check, direct tests, and task-scoped check --strict were run separately.
- 2026-08-11 deliver: Accepted ticket-ref on REQ-UX-4753a4bf because it is pre-existing requirement prose outside this task.
- 2026-08-11 deliver: Accepted unticked-deliver on TASK-6e7f4c7b because it is a pre-existing open task outside this task.
- 2026-08-11 deliver: Accepted outside-layout on both offline user guides because the owner explicitly required English and Romanian help updates for changed language support and terminology.
- 2026-08-11 deliver: Accepted outside-layout on CHANGELOG.md because the project contract requires an Unreleased entry for every delivery.
- 2026-08-11 deliver: Reviewed the production, test, requirement, documentation, knowledge, and changelog diff against the confirmed findings and explicit exclusions; no analysis documents, release versions, broad refactors, compatibility identifiers, or unrelated user files are included.
- 2026-08-11 deliver: Re-read all task requirements; delivered requirements remain active, compact-script target-only requirements are retired with explicit reasons, and affected paths plus linked selectors match the implemented contracts.
- 2026-08-11 deliver: The human explicitly approved the staged delivery commit and safe local fast-forward merge into master; pushing remains forbidden.

## Delivery report (2026-08-11)

- stage: deliver; type: change; path: full; branch: ddp/analysis-2026-08-10-fixes
- requirements:
  - REQ-FUNC-4d5ece0f - Extract visible EPUB container text
  - REQ-FUNC-1a2d28bb - Use canonical European chapter labels
  - REQ-DATA-966afd2d - Reset Cleanup manual-edit provenance on reanalysis
  - REQ-REL-484a0674 - Preserve provider compatibility during JSON repair
  - REQ-REL-8dc30a4b - Classify transient provider failures by type
  - REQ-REL-0f90f2a4 - Resume empty Character Discovery synthesis
  - REQ-DATA-d5324480 - Persist Character Discovery failure details
  - REQ-FUNC-3199dbb1 - Substitute prompt placeholders in one pass
  - REQ-FUNC-6f6e045f - Parse single-line fenced JSON responses
  - REQ-REL-1a521d45 - Ignore premature VoiceWeaver idle polls
  - REQ-DATA-330b5d31 - Exclude empty chunk identifiers from progress
  - REQ-REL-557b0a5f - Treat malformed character voice plans as unavailable
  - REQ-DATA-ca7c6c36 - Keep projected Speech Blocks completion timestamps stable
  - REQ-SEC-cdbd652c - Reject archive exports inside the project
  - REQ-PLAT-0ef29ded - Reject booleans for positive integer settings
  - REQ-REL-8a56ff1e - Attempt all owned artifact removals during reset
  - REQ-REL-50e2f540 - Release destroyed scroll viewport state
  - REQ-REL-3b9c207e - Preserve the original project snapshot failure
  - REQ-UX-cc7bc507 - Show Home after project activation
  - REQ-DATA-5e59c157 - Flush translation edits before project activation
  - REQ-UX-29c94862 - Preserve displayed token usage across progress ticks
  - REQ-UX-6ec7fe61 - Keep audio playback mutually exclusive
  - REQ-FUNC-f04f2515 - Normalize VoiceWeaver terminal status case
  - REQ-UX-9a7fc380 - Default narrator confirmations to No
  - REQ-PLAT-e1ca40ab - Limit translation targets to supported scripts
  - REQ-UX-a6c3e152 - Spell Narrator correctly in user-facing text
  - REQ-FUNC-2b7862b5 - AI narrator previews shall use script-aware duration units
  - REQ-FUNC-efbb32a4 - Narrator samples shall enforce script-aware safe TTS budgets
  - REQ-FUNC-90dd5691 - Character voice preview text shall cover supported TTS languages and
  - REQ-FUNC-ff2e2c94 - Cleanup shall reject predominantly CJK or Hangul source text before
  - REQ-FUNC-085699ab - The Character Voices controller shall, on page activation, warn on a
  - REQ-FUNC-efcaeeed - Project export shall atomically create voice and audio archives
  - REQ-PLAT-2a16daee - Accept UTF-8 BOM settings
- diff vs merge base: 105 file(s) changed, 2744 line(s) added
- checks: errors=0 warnings=6 notes=0
- checklist: 6/8 done; open: journal and report inside the delivery commit; approved local outcome delivered; close-out: `stage: done` set and committed only after the approved outcome succeeded
