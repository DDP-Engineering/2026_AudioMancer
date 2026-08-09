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

# TASK-7c33dff5 — Validate and repair BUG-09 through BUG-14

stage: done
type: fix
path: quick
requirements: REQ-FUNC-f5c39900, REQ-UX-aa109e16, REQ-UX-08439166, REQ-FUNC-35098598, REQ-FUNC-5e008e3b
branch: ddp/bug09-bug14
opened: 2026-08-09

## Done checklist (current stage)

- [x] strict scoped static check has no errors or diff-introduced failures, with all warnings explained
- [x] diff reviewed against scope, requirements, error paths, portability, security, and exclusions
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, affected paths, and test links are true
- [x] delivery confirmed by standing human approval before commit
- [x] journal and report are inside the delivery commit and the delegated commit outcome is delivered
- [x] close-out: `stage: done` set and committed only after delivery succeeds
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` Unreleased section is written in user language
- [x] no release/version/help-version changes were made

## Log

- 2026-08-09 frame: Validate BUG-09 through BUG-14 independently and repair only findings proven by focused pre-fix regressions in Audio Blocks reconciliation, Character Voices and Narrator Voice error feedback, Speech Blocks failed-save projection, AI/TTS settings labels, and narrator export labels.
- 2026-08-09 frame: Exclude normal Audio Blocks generation changes, persisted `audio_narator` identities and `narator_voice` terminology, release/version/help updates, full-suite execution, planning files, unrelated cleanup, push, merge, and parent-checkout edits.
- 2026-08-09 frame: Use the quick path because the requested changes restore already-required voice identity, localized operator feedback, edit rollback, action labeling, and export presentation without adding interfaces, formats, dependencies, security behavior, or data-handling policy.
- 2026-08-09 frame: Reuse and update REQ-FUNC-f5c39900, REQ-UX-aa109e16, REQ-UX-08439166, REQ-FUNC-35098598, and REQ-FUNC-5e008e3b for the confirmed behaviors.
- 2026-08-09 frame: Standing approval in the delegated request authorizes uninterrupted validation, implementation, delivery commit, and AEGIS close-out.
- 2026-08-09 build: tests/test_audio_blocks_service.py::test_audio_blocks_service_reconcile_after_resplit_preserves_same_narrator_targets red as expected after a valid fixture because reconciliation never loads the TTS plan and retains character targets.
- 2026-08-09 build: Character Voices edit-failure and AI/TTS Apply-label regressions under REQ-UX-aa109e16 red as expected because edit errors produce no warning and both non-closing buttons display Save in English and Romanian.
- 2026-08-09 build: tests/test_narator_voice_ui_controller.py::test_narator_voice_delete_missing_profile_shows_localized_profile_error red as expected because delete ValueError returns without feedback.
- 2026-08-09 build: tests/test_speech_blocks_ui_controller.py::test_speech_blocks_ui_controller_failed_save_reprojects_persisted_block red as expected because the rejected editor projection remains untouched after edit mode ends.
- 2026-08-09 build: tests/test_project_export_service.py::test_project_export_service_narrator_default_filename_uses_user_facing_spelling red as expected because the public default filename contains `narator_voice`.
- 2026-08-09 build: BUG-11 readonly subclaim confirmed unreachable because the production edit service raises only `missing_profile`, state enables editing for every existing profile, and `readonly_profile` has no other producer or consumer beyond the controller arm and paired catalog entries.
- 2026-08-09 build: the eight failing finding regressions became 9 passing cases including both Character Voices error codes and localization parity.
- 2026-08-09 build: `test --impacted` expanded to 1107 selectors and exited 127 in 0.0 seconds before pytest launched, so it was not retried as a broad set.
- 2026-08-09 build: direct affected modules completed with 162 passed and one offscreen Qt spinbox click failure; the unchanged failing selector passed alone in 0.04 seconds and was classified as environment-sensitive outside this diff.
- 2026-08-09 build: final regression and wiring selectors passed 14 tests in 7.05 seconds after the last source correction.
- 2026-08-09 build: changed Python files passed Ruff and compilation; logging coverage reported no issues, while the changed-file code-style audit reported 13 pre-existing callable-doc findings only on legacy helpers outside the added code.
- 2026-08-09 build: task-scoped strict AEGIS static check reported zero errors and `strict: ok`; 75 repository-baseline advisory warnings remain outside this task.
- 2026-08-09 build: the ignored test-created settings file matched service defaults, contained zero non-empty credential fields, and was removed from this worktree.
- 2026-08-09 deliver: accepted the 75 strict AEGIS advisory warnings because they are repository-baseline layout, traceability, and ticket-reference findings outside the scoped diff.
- 2026-08-09 deliver: exact review mapped BUG-09 to REQ-FUNC-f5c39900, BUG-10 and BUG-13 to REQ-UX-aa109e16, BUG-11 to REQ-UX-08439166, BUG-12 to REQ-FUNC-35098598, and BUG-14 to REQ-FUNC-5e008e3b.
- 2026-08-09 deliver: all BUG-09 through BUG-14 findings were accepted; no finding was rejected, and the BUG-11 readonly edit arm and EN/RO entries were removed only after the unreachable-production-path proof.
- 2026-08-09 deliver: semantic diff review confirmed early failure exits, successful-save and invalidation flows, normal generation, persisted narrator identifiers and terminology, portability, security boundaries, versions, help files, planning files, parent checkout, push, and merge remain unchanged.
- 2026-08-09 deliver: standing approval confirms the exact reviewed delivery commit and delegated commit-only outcome.
- 2026-08-09 deliver: the generated report's 420-file merge-base count includes inherited branch divergence, while the exact task delta is 28 tracked files plus this new journal with no planning, version, or help-file changes.
- 2026-08-09 close: delivery commit f18ffb8caa2485f7c4d4bae0dabbd7febb47dbea succeeded; no push or merge was requested or performed.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: quick; branch: ddp/bug09-bug14
- requirements:
  - REQ-FUNC-f5c39900 - Audio-block exact-block operations shall detect and remove audio for an
  - REQ-UX-aa109e16 - Every app-owned operator-facing string on persistent windows, pages
  - REQ-UX-08439166 - Report unavailable narrator profiles during edit and delete
  - REQ-FUNC-35098598 - Persist Speech Block warning cleanup only on successful save
  - REQ-FUNC-5e008e3b - Project export shall detect readiness for TXT, Markdown, and ZIP export
- diff vs merge base: 420 file(s) changed, 39206 line(s) added
- checks: errors=0 warnings=76 notes=0
- checklist: 9/10 done; open: close-out: `stage: done` set and committed only after delivery succeeds
