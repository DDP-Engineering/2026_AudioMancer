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

# TASK-0607cbea — Converge VoiceWeaver cancellation on one cancelled outcome

stage: done
type: fix
path: quick
requirements: REQ-FUNC-a24e14cb, REQ-FUNC-1a06b572, REQ-NFR-5bda19fd
branch: master
base: ab952538007b48d7a3d39dea812407ef6665f439
opened: 2026-08-22

## Done checklist (current stage)

- [x] validated candidate confirmed unchanged; otherwise returned to validate
- [x] validation evidence, diff, exclusions, and outcome presented
- [x] delivery confirmed by the human
- [ ] journal and report included in the delivery commit
- [ ] agreed outcome delivered, normally a PR
- [ ] close-out committed after the outcome succeeded, or carried by the
      delivery commit where nothing could fail after it

## Log

- 2026-08-22 frame: scope is the VoiceWeaver cancellation model — `wait_for_terminal_operation` and `_cancel_last_observed_operation` in `voiceweaver_runtime_service.py`, and the busy gate `_runtime_operation_is_busy` in `audio_blocks_service.py` — so that a cancel, whether requested locally or reported by the runtime, ends on one cancelled outcome and leaves the run resumable.
- 2026-08-22 frame: out of scope are the six `!= "completed"` call sites, which the root-cause fix must leave untouched, the UI dialogs and controllers, the persisted document format, and the VoiceWeaver runtime itself.
- 2026-08-22 frame: quick path chosen at the operator's instruction — one behavioral model in two service modules, no new interface, data format, or dependency, and `REQ-FUNC-a24e14cb` and `REQ-NFR-5bda19fd` already govern the two files.
- 2026-08-22 frame: expected requirement work — widen `REQ-FUNC-a24e14cb` to cover a cancel that arrives before the first status read, add `REQ-FUNC-1a06b572` for the terminal-cancelled mapping the code has no requirement for, and relink `REQ-NFR-5bda19fd` to the corrected busy gate.
- 2026-08-22 frame: DEVIATION frame: no task branch and no commit — work stays on `master` and stops after validate at the operator's explicit instruction, which costs the usual per-task branch isolation and leaves delivery unfinished.
- 2026-08-22 build red: command=`uv run pytest -q tests/test_voiceweaver_runtime_service.py -k cancel tests/test_audio_blocks_service.py::test_audio_blocks_resumes_after_a_latched_cancelled_runtime_operation`; exit=1; expected missing behavior=four failures, one per defect — a cancel arriving before the first poll posts no `/cancel` (`assert 0 == 1`), a terminal `cancelled` status returns its payload instead of raising (`DID NOT RAISE OperationCancelledError`), a dropped connection during remote cancellation escapes as `ConnectionResetError` and supersedes the cancellation, and a latched `cancelled` status still reads as busy (`VoiceWeaver is still busy with a previous operation.`).
- 2026-08-22 build: the pinned assertion `status_reads["count"] == 0` in `test_wait_for_terminal_operation_stops_before_status_read_when_cancelled` was deliberately replaced, not quietly relaxed — it fixed the defect-4 behavior in place, so the test is renamed to `..._cancels_remotely_when_cancelled_before_the_first_poll` and now asserts exactly one status read and one `/cancel`.
- 2026-08-22 build: `test_audio_blocks_service.py`'s always-idle `read_status` stubs were left alone rather than rewritten; the latched-status gate is covered by one new dedicated test that drives `_ensure_clone_model_loaded` and `_ensure_sound_model_loaded` against a `cancelled` status, which exercises the gate without perturbing twenty unrelated generation fixtures.
- 2026-08-22 frame: DEVIATION frame: the working tree already carries TASK-9236a4f8's staged but uncommitted delivery, so `base: ab952538` makes every task-scoped diff and `check --task` report describe both tasks; this task's own diff is the unstaged one.
- 2026-08-22 build: the polling wait now raises `OperationCancelledError` on a terminal `cancelled` status, skips the remote `/cancel` in that one case because the runtime has already stopped, reads the operation once when a local cancel beats the first poll, and no longer lets an exception from `POST /cancel` supersede the cancellation; the busy gate accepts `cancelled` as one more latched terminal status.
- 2026-08-22 build: `evolution` reported exactly the two source files the design intended, the tests having been written before the anchor as the test-first order requires; `test --impacted --base HEAD` exit 0 (24 test files, 484 passed, 1 skipped) and `ruff check` clean on the changed files.
- 2026-08-22 build: DEVIATION build: `check` reports three warnings, none from this task — a `ticket-ref` in the unrelated `REQ-UX-4753a4bf`, `unticked-deliver` on TASK-9236a4f8's pending delivery, and `outside-layout` on `CHANGELOG.md`, which every delivery must touch; all accepted.
- 2026-08-22 validate: diff reviewed hunk by hunk — two source hunks in `voiceweaver_runtime_service.py`, one in `audio_blocks_service.py`, all inside the framed scope; none of the six `!= "completed"` call sites changed, no secrets, no path or portability surface touched, and the two broadened `except Exception` clauses each re-raise or log rather than swallow, with `OperationCancelledError` re-raised explicitly so a future cancel hook on the POST path cannot be trapped.
- 2026-08-22 validate: reviewed and rejected an extra guard for a stale latched `cancelled` seen on the first poll of a fresh run — every mutating endpoint returns the newly started operation in its own response, so the operation slot is already replaced before polling begins, and the existing `observed_active_operation` guard covers the separate registration-lag case where `/status` reads `idle`.
- 2026-08-22 validate: found but did not fix a pre-existing gap outside this scope — the mid-loop `_ensure_clone_model_loaded` call in `start_or_continue_generation` is the one runtime call site with no `except OperationCancelledError` handler, so a cancel during a mid-run model switch escapes without persisting cancelled state and leaves the document `running`; this predates the task and affects local cancels identically.
- 2026-08-22 validate: `TTS_Audio_Blocks.md` gained three key-behavior entries covering the single cancellation outcome, the pre-first-poll remote cancel, and the latched terminal busy gate; `REQ-FUNC-a24e14cb` prose and verification widened, `REQ-FUNC-1a06b572` written and `active`, `REQ-NFR-5bda19fd` relinked, all paths and links re-read and true.
- 2026-08-22 validate: DEVIATION validate: `REQ-FUNC-1a06b572` was written and `REQ-FUNC-a24e14cb` was reworded during build, which is specify work the quick path skips; the terminal-cancelled mapping had no requirement at all, so building it unrequiremented would have left the change unverifiable rather than merely unspecified.
- 2026-08-22 validate: `CHANGELOG.md` records the three operator-visible effects under `## [Unreleased]` in user language; no version was assigned, so this delivery is not a release.
- 2026-08-22 validate: after the last edit, targeted tests exit 0 (`uv run pytest -q tests/test_voiceweaver_runtime_service.py tests/test_audio_blocks_service.py tests/test_duplicate_model_activation_consolidation.py tests/test_tts_runtime_ui_support.py`, 79 passed), `ruff check` clean over the changed sources and all of `tests/`, `evolution` refreshed to the final three modified paths, and `check --task TASK-0607cbea --strict` exit 0 with `strict: ok` and the three accepted warnings.
- 2026-08-22 validate: DEVIATION validate: `check --run` was not executed — the operator excluded the full suite, so the repository-wide proof this stage owes rests on the 24-file impacted set run during build plus the targeted re-run above, and a regression outside those files would not have been caught here.
- 2026-08-22 validate: DEVIATION validate: delivery stops here — the operator asked for the diff and a proposed commit message instead of a commit, so the task stays at `deliver` unpublished.
- 2026-08-22 deliver: two blank lines were added between two test functions after the recorded strict check, so the candidate was re-proved before closing — targeted tests exit 0 (79 passed), `evolution` refreshed to the final four modified paths, and `check --task TASK-0607cbea --strict` exit 0 with `strict: ok`.
- 2026-08-22 deliver: the operator reviewed the presented evidence, diff, exclusions, and commit message and closed the task; the change is handed over as an uncommitted working tree, which is the agreed outcome here.
- 2026-08-22 deliver: DEVIATION deliver: the task closes with nothing committed, pushed, or published — the operator excluded commit and push, so the three delivery checklist items stay unticked and the working tree, not a commit, is the deliverable; the journal, the new `REQ-FUNC-1a06b572`, and both `TASK-0607cbea` sidecars are untracked and will be lost if the tree is cleaned.

## Delivery report (2026-08-22)

- stage: deliver; type: fix; path: quick; branch: master
- requirements:
  - REQ-FUNC-a24e14cb - Cancel cancellable VoiceWeaver operations remotely
  - REQ-FUNC-1a06b572 - A runtime-reported cancelled operation shall end the wait as a cancellation
  - REQ-NFR-5bda19fd - Shared audio model activation shall preserve runtime lifecycle
- deviations: 7 recorded
  - frame: no task branch and no commit — work stays on `master` and stops after validate at the operator's explicit instruction, which costs the usual per-task branch isolation and leaves delivery unfinished.
  - frame: the working tree already carries TASK-9236a4f8's staged but uncommitted delivery, so `base: ab952538` makes every task-scoped diff and `check --task` report describe both tasks; this task's own diff is the unstaged one.
  - build: `check` reports three warnings, none from this task — a `ticket-ref` in the unrelated `REQ-UX-4753a4bf`, `unticked-deliver` on TASK-9236a4f8's pending delivery, and `outside-layout` on `CHANGELOG.md`, which every delivery must touch; all accepted.
  - validate: `REQ-FUNC-1a06b572` was written and `REQ-FUNC-a24e14cb` was reworded during build, which is specify work the quick path skips; the terminal-cancelled mapping had no requirement at all, so building it unrequiremented would have left the change unverifiable rather than merely unspecified.
  - validate: `check --run` was not executed — the operator excluded the full suite, so the repository-wide proof this stage owes rests on the 24-file impacted set run during build plus the targeted re-run above, and a regression outside those files would not have been caught here.
  - validate: delivery stops here — the operator asked for the diff and a proposed commit message instead of a commit, so the task stays at `deliver` unpublished.
  - deliver: the task closes with nothing committed, pushed, or published — the operator excluded commit and push, so the three delivery checklist items stay unticked and the working tree, not a commit, is the deliverable; the journal, the new `REQ-FUNC-1a06b572`, and both `TASK-0607cbea` sidecars are untracked and will be lost if the tree is cleaned.
- diff vs task base ab95253: 18 file(s) changed, 3986 line(s) added
- checks: errors=0 warnings=4 notes=0
- checklist: 3/6 done; open: journal and report included in the delivery commit; agreed outcome delivered, normally a PR; close-out committed after the outcome succeeded, or carried by the delivery commit where nothing could fail after it
