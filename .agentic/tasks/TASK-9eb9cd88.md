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

# TASK-9eb9cd88 — Fail closed on corrupt stage documents and manifest language saves

stage: deliver
type: fix
path: full
requirements: REQ-FUNC-ac0451b0, REQ-FUNC-39146520, REQ-REL-c5b666e6, REQ-UX-7982f351, REQ-DATA-52fee282, REQ-UX-f80d35c2
branch: ddp/x5-x6-corrupt-state-boundaries
opened: 2026-08-09

## Done checklist (current stage)

- [x] user-directed scoped validation and strict static AEGIS completed — 392 passed and 1 skipped; the full suite was intentionally deferred and the evidence is in the log
- [x] diff reviewed against scope, requirements, design, error paths, portability, security — no unrequested changes
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report inside the delivery commit; agreed local fast-forward outcome authorized
- [ ] close-out: `stage: done` set and committed only after the outcome succeeded
- [x] the project items from `.agentic/PROJECT.md` ("Delivery checklist additions") — code style, and for a release the four-place version workflow

## Log

- 2026-08-09 frame: Scope is strict Speech Blocks and Audio Blocks document reads plus fail-closed Character Voices language persistence and their service, state, controller, and page boundaries; exclusions are the lenient Text Cleanup checkpoint, schema changes, unrelated workflows, `0_Planning`, settings bootstrap, full-suite execution, commits, integration, and push.
- 2026-08-09 frame: Full path is required because this changes externally observable recovery behavior and persisted-data failure handling across three workflow components.
- 2026-08-09 frame: Proposed requirements cover typed block-document rejection, reset-only block recovery UI, fail-closed manifest-backed language saves, and non-mutating Character Voices recovery presentation.
- 2026-08-09 frame: The delegated request explicitly directs uninterrupted implementation through one exact staged delivery checkpoint, so the normal frame conversation stop is satisfied by the recorded scope and terminal approval stop.
- 2026-08-09 specify: Existing Speech Blocks and Audio Blocks requirements were narrowed to preserve missing-document compatibility while the new reliability requirement owns rejection of every existing invalid document.
- 2026-08-09 specify: AEGIS check reported zero errors and only the repository's existing global coverage, layout, and historical ticket-reference warnings.
- 2026-08-09 design: Use existing stage error classes and exception chaining at strict loaders, recovery-only state payloads at read boundaries, and project-error warnings before generation or Character Voices activation.
- 2026-08-09 design: Preserve the persisted JSON schemas and public missing-file return values; the only data-order change is validating project.json before Character Voices may initialize or mutate characters_voice.json.
- 2026-08-09 design: Reject lenient logging-only handling because it would still let damaged authoritative files look absent and allow overwrite; text_cleanup_service remains unchanged because its checkpoint is optional.
- 2026-08-09 design: Test seams are the two single-document contract suites, Speech/Audio state and controller/page suites, and Character Voices service, state, controller, and workspace suites.
- 2026-08-09 deliver: The human approved cached fingerprint `d9b08dd4eb9ae212fd1e1985581c232f854c34f8` after independent root review and an additional 12-pass missing, null, and invalid boundary rerun.
- 2026-08-09 deliver: The user-directed validation override remains authoritative: 392 unique scoped tests passed and 1 skipped, the task-scoped strict static AEGIS check exited 0 with zero errors and 80 accepted warnings, and the full suite was intentionally deferred.
- 2026-08-09 deliver: The approved outcome is a delivery commit, a journal-only closeout commit, and guarded sequential local fast-forward into `F:\2026_AudioMancer` `AudioMancer_V2`, preserving every then-current dirty path byte-for-byte and never pushing.

## Design

- Components: Speech Blocks, TTS Audio Blocks, Character Voices, and Project Lifecycle manifest loading.
- Interface: existing `SpeechBlocksDocumentError` and `AudioBlocksDocumentError` become strict read errors for every present invalid document; missing files still return `None`.
- Interface: state builders convert expected typed persistence failures into complete reset-recovery page payloads, and generation/activation controllers use the existing localized project-error dialog.
- Data: no JSON fields or filenames change; loader messages name the exact reset action and retain `__cause__`.
- Data: `save_selected_voice_language` loads the manifest before `ensure_character_voices_files`, catches only `FileNotFoundError` for the established fallback, and otherwise propagates validation, filesystem, and unexpected failures.
- Alternative rejected: logging and returning `None`, because it preserves the overwrite path the task removes.
- Test seams: strict loader and no-overwrite generation tests; invalid state and disabled-control tests; controller no-start dialog tests; manifest byte-preservation, fallback, lock, propagation, and activation tests.
- Expected source files: both block services/state services/controllers, Character Voices service/state/controller, with no Text Cleanup, planning, settings, schema, or broad shell redesign.
- 2026-08-09 build: `test_existing_invalid_document_raises_typed_reset_recovery_error`, unreadable-read, and no-overwrite selectors were red as expected for both block stages because present-invalid documents returned `None` and generation proceeded.
- 2026-08-09 build: Follow-up present-JSON-null cases were red with 2 failed and 8 passed because both strict loaders still shared the optional reader's `None` result for missing and `null` documents.
- 2026-08-09 build: Speech/Audio corrupt state and controller selectors were red as expected because pages were built as ordinary work and generation reached confirmation or runtime probing; the two reset-only page contract tests already passed.
- 2026-08-09 build: Character Voices corrupt and injected manifest save selectors were red as expected because the broad catch reported success and initialized targets, while locked and genuinely missing compatibility controls already passed.
- 2026-08-09 build: Character Voices state and activation selectors were red as expected because manifest failures escaped the refresh and Qt activation boundaries instead of producing recovery state and a project-error warning.
- 2026-08-09 build: Direct linked green selectors passed with 16 strict block-document cases, 6 block recovery state/controller/page cases, and 8 Character Voices manifest cases under the mandated interpreter and explicit worktree PYTHONPATH.
- 2026-08-09 build: The complete affected-module run passed by non-duplicated composition with 384 passed and 1 skipped, followed by a 35 passed and 1 skipped complete workspace rerun after the final upstream-preflight ordering fix.
- 2026-08-09 build: The AEGIS impacted wrapper was not invoked because the delegated validation explicitly requires only the fixed external interpreter and forbids uv; all linked tests instead ran directly through that interpreter.
- 2026-08-09 build: A valid-WAV fixture correction was required by an existing Scene Ambience test whose literal RIFF bytes did not satisfy current WAV validation; production behavior was unchanged.
- 2026-08-09 build: AEGIS check reported zero errors and 79 repository-wide baseline warnings after implementation.
- 2026-08-09 build: Accepted ticket-ref on unrelated REQ-UX-4753a4bf because it predates and is outside this task.
- 2026-08-09 build: Accepted outside-layout warnings because they describe existing repository documentation and tool placement outside this task's changed paths.
- 2026-08-09 build: Accepted uncovered-source warnings because they are repository-wide historical requirement coverage debt and none names an uncovered source file changed by this task.
- 2026-08-09 deliver: The user-directed full-suite deferral is intentional; no full suite, settings bootstrap, uv command, install, or worktree virtual environment was used.
- 2026-08-09 deliver: Strict static AEGIS check exited 0 with zero errors and 80 warnings; the additional unticked-deliver warning truthfully reflects the requested approval checkpoint and deferred full-suite, commit, report, and closeout work.
- 2026-08-09 deliver: Six public Speech/Audio projection cases and both complete single-document contract modules passed after the final documentation audit; the two added present-null cases bring the unique scoped result to 392 passed and 1 skipped.
- 2026-08-09 deliver: The focused missing, invalid, unreadable, no-overwrite, and public-projection boundary rerun passed 22 cases across Speech Blocks and Audio Blocks after the null correction.
- 2026-08-09 deliver: An ignored default settings.json with empty credential fields appeared during scoped UI validation and was removed from the isolated worktree before checkpoint; no settings file is staged or retained.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: full; branch: ddp/x5-x6-corrupt-state-boundaries
- requirements:
  - REQ-FUNC-ac0451b0 - Treat a missing Speech Blocks document as not started
  - REQ-FUNC-39146520 - Treat a missing Audio Blocks document as not started
  - REQ-REL-c5b666e6 - Reject corrupt authoritative block documents
  - REQ-UX-7982f351 - Expose block-document reset recovery without generation
  - REQ-DATA-52fee282 - Fail closed when saving voice language against an unreadable manifest
  - REQ-UX-f80d35c2 - Expose Character Voices manifest save failures without mutation
- diff vs approved task base: 37 file(s) changed, 1401 line(s) added, 88 line(s) deleted
- checks: errors=0 warnings=80 notes=0
- checklist: 7/8 done; open: close-out: `stage: done` set and committed only after the outcome succeeded
