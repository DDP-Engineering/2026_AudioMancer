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

# TASK-eb50102e — Harden Audio Assembly inputs and classic WAV outputs

stage: deliver
type: fix
path: full
requirements: REQ-FUNC-7c32fd5e, REQ-REL-607c7bfb, REQ-REL-f3f965de
branch: ddp/as1-as2-assembly-output-safety
opened: 2026-08-09

## Done checklist (current stage)

- [x] directed scoped validation and strict static AEGIS are green, with the user-directed full-suite deferral recorded
- [x] diff reviewed against scope, requirements, design, error paths, portability, security — no unrequested changes
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report prepared for the delivery commit; approved outcome is guarded local integration without push
- [ ] close-out: `stage: done` set and committed only after the outcome succeeded
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` Unreleased section written in user language; this task is not a release

## Log

- 2026-08-09 frame: Scope is Audio Assembly composition-source preflight, exact classic-WAV output-size preflight, and failed-temp cleanup, with public APIs and persisted formats unchanged.
- 2026-08-09 frame: Excludes Audio Blocks behavior, unrelated review findings, settings bootstrap, full-suite execution, schemas, dependencies, versions, releases, every planning document, push, and main-worktree mutation before approved guarded integration.
- 2026-08-09 frame: Full path is required because operator-visible validation and reliability behavior changes across planning, composition, resume, and failure boundaries.
- 2026-08-09 frame: The delegated scope confirms proceeding through the requested pre-commit checkpoint without a separate frame pause.
- 2026-08-09 frame: Proposed requirements cover exact opened-source validation, per-output classic-WAV size rejection before publish-state mutation, and failed temporary-output cleanup.
- 2026-08-09 specify: Created REQ-FUNC-7c32fd5e, REQ-REL-607c7bfb, and REQ-REL-f3f965de, with an exact integer-frame classic-WAV sizing spec for REQ-REL-607c7bfb.
- 2026-08-09 specify: Static AEGIS reported zero errors; its 86 repository-baseline warnings are unrelated to the new artifacts and remain for strict delivery accounting.

## Design

- Component: change only Audio Assembly service behavior and its focused service tests; keep controller, page, public APIs, persisted schemas, and Audio Blocks ownership unchanged (REQ-FUNC-7c32fd5e, REQ-REL-607c7bfb, REQ-REL-f3f965de).
- Input boundary: derive the exact non-pause composition set through `_is_assembly_block`, resolve with the existing containment helper, require a regular file, and translate unreadable/invalid WAV input into the existing preflight validation family (REQ-FUNC-7c32fd5e).
- Output boundary: validate pending output-plan items after resume reconciliation but before running report/state persistence, using the selected reference format, exact direct/silence frames, and conservative integer rate-conversion bounds (REQ-REL-607c7bfb).
- Scene Mix sizing: inspect its source headers and use the existing target-frame rule without materializing mix output; then bound any final-rate conversion (REQ-REL-607c7bfb).
- Cleanup: wrap only final temporary composition/publication so any write or close exception unlinks the temp while the published output remains untouched; successful replace and cooperative cancellation propagation remain unchanged (REQ-REL-f3f965de).
- Test seams: public composition tests inject legacy ambience rows and observe preflight behavior; private integer sizing helpers exercise the legal/overflow boundary without large allocation; the public start path proves no output work or persistence; `_compose_output_file` simulates write and close failures (all requirements).
- Rejected: duration-only float estimation can undercount conversions, and catching `struct.error` after writing is too late to prevent multi-gigabyte work (REQ-REL-607c7bfb).
- Expected files: the three requirements and size spec, this journal, `audio_assembly_service.py`, `test_audio_assembly_service.py`, Audio Assembly knowledge, and `CHANGELOG.md`.
- 2026-08-09 build: REQ-FUNC-7c32fd5e red as expected because missing, unsafe, directory, and invalid-WAV legacy Scene Ambience sources reached duration or mix work instead of the approved-source ValueError.
- 2026-08-09 build: REQ-REL-607c7bfb red as expected because the exact classic-WAV byte boundary and preflight helper do not exist.
- 2026-08-09 build: REQ-REL-f3f965de red as expected because simulated write and close failures left `audiobook.wav.tmp` while preserving the published output.
- 2026-08-09 build: The focused AS-1/AS-2 selectors passed 13 tests after composition-source preflight, integer-frame size validation, and final temp cleanup were implemented.
- 2026-08-09 build: The complete Audio Assembly service module passed 38 tests.
- 2026-08-09 build: The direct requirement-linked impacted equivalent passed 14 tests with the mandated interpreter and explicit worktree PYTHONPATH; the AEGIS test wrapper was not invoked because it is configured through user-forbidden `uv`.
- 2026-08-09 build: Ruff and py_compile passed on the changed service and test files.
- 2026-08-09 build: Static AEGIS reported zero errors and the same 86 repository-baseline warnings; none refers to a task-created requirement, spec, journal, source edit, or test edit.
- 2026-08-09 deliver: Complete non-duplicated scoped module coverage passed 188 tests across Audio Assembly service/state/controller/page/sample-width, operation runtime, PCM codec, and VoiceWeaver runtime, with one existing `audioop` deprecation warning.
- 2026-08-09 deliver: Strict static AEGIS exited zero with errors=0, warnings=87, and strict ok; one warning is the expected pre-approval unticked-deliver state and the other 86 are repository-baseline findings.
- 2026-08-09 deliver: The full pytest suite and `check --run` are intentionally deferred to the root integration task exactly as directed, and no settings file was bootstrapped.
- 2026-08-09 deliver: Semantic diff review confirms exact non-pause composition-source validation, per-pending-output integer size guards, writer-temp cleanup, unchanged public and persisted contracts, and unchanged atomic success/cancellation propagation.
- 2026-08-09 deliver: Requirements, linked selectors, code style, knowledge, and Changelog Unreleased are current; planning, Audio Blocks, controllers/pages, schemas, dependencies, versions, help, packaging, settings, ZIP artifacts, and the main worktree remain untouched.
- 2026-08-09 deliver: Human approved staged diff fingerprint `28d8869634e8a6076917defb5602aa346d883d2f` after independently reviewing the exact nine-file patch, cached cleanliness, residue state, and planning exclusion.
- 2026-08-09 deliver: Human reran 12 key selectors successfully and differentially verified that representative actual resampling outputs never exceed the conservative planned-frame bound.
- 2026-08-09 deliver: Approved outcome is one delivery commit, one journal-only closeout commit, and guarded local fast-forward integration into `AudioMancer_V2` with all six user-owned dirty paths preserved and no push.
- 2026-08-09 deliver: Corrected generated report accounting to task base `a500bf5` because the configured repository merge base includes unrelated historical changes.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: full; branch: ddp/as1-as2-assembly-output-safety
- requirements:
  - REQ-FUNC-7c32fd5e - Validate every opened Audio Assembly source
  - REQ-REL-607c7bfb - Reject oversized classic WAV outputs before composition
  - REQ-REL-f3f965de - Remove failed Audio Assembly temporary outputs
- diff vs task base a500bf5: 9 file(s) changed, 941 line(s) added, 36 line(s) removed
- checks: errors=0 warnings=87 notes=0
- checklist: 8/9 done; open: close-out: `stage: done` set and committed only after the outcome succeeded
