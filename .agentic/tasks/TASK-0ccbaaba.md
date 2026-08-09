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

# TASK-0ccbaaba — Speech Block identity and projection resolution

stage: done
type: fix
path: full
requirements: REQ-DATA-af08bfc5, REQ-REL-14f298bd, REQ-NFR-9c867783
branch: ddp/sb5-sb7-identity-projections
opened: 2026-08-09

## Done checklist (current stage)

- [x] repository proof completed with one finished direct full-suite run through the mandated shared interpreter plus task-scoped AEGIS static checking; the uv-backed `check --strict --run` substitution is explained in the log
- [x] diff reviewed against scope, requirements, design, error paths, portability, security — no unrequested changes
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report included in delivery commit `cec6cb7`; approved local integration succeeded
- [x] close-out: `stage: done` set after the delivery commit was integrated successfully
- [x] project delivery items satisfied: binding code style reviewed, `CHANGELOG.md` Unreleased updated, and no release/version/help-file workflow triggered

## Log

- 2026-08-09 frame: Scope covers SB-5 identity-contract correction, load-bearing downstream cleanup evidence, and SB-7 one-resolution projections across Speech Blocks public reads and mutations; persistence formats, unrelated findings, releases, and all 0_Planning files are excluded.
- 2026-08-09 frame: The full path is required because this task deliberately clarifies externally relevant identifier lifecycle behavior and changes performance-sensitive persistence orchestration.
- 2026-08-09 frame: The delegated scope is treated as confirmed and requires the next human checkpoint only after exact scoped staging, before any commit.
- 2026-08-09 frame: Proposed requirements cover current-document identifier uniqueness, deletion cleanup before identifier reuse, and at-most-once upstream source resolution per public operation.
- 2026-08-09 frame: Durable high-water persistence remains under evaluation against the fixed single-document contract and backward-compatible fallback requirements.
- 2026-08-09 specify: Created REQ-DATA-af08bfc5 for current-document identifier uniqueness, REQ-REL-14f298bd for load-bearing deleted-audio cleanup, and REQ-NFR-9c867783 for at-most-once source resolution per public operation.
- 2026-08-09 specify: No separate spec is needed because the design decision and helper threading can be captured directly in the task journal and tested through public contracts.
- 2026-08-09 specify: AEGIS check reported no errors and only pre-existing repository-layout and unrelated ticket-reference warnings.
- 2026-08-09 build: `test_speech_block_id_allocator_promises_current_document_uniqueness` was red as expected because the helper still promised historical non-reuse despite receiving only live identifiers.
- 2026-08-09 build: `test_speech_blocks_ui_controller_delete_confirms_and_resets_downstream` was red as expected because manifest synchronization ran before deleted-id Audio Blocks cleanup.
- 2026-08-09 build: `test_public_review_operations_resolve_source_chunks_at_most_once` was red as expected with three resolutions for approval and six for edit, insert, and delete while direct reads already resolved once.
- 2026-08-09 build: `test_build_speech_blocks_state_resolves_source_chunks_once` was red as expected because one page-state read resolved the same corpus three times across report, state, and source projections.
- 2026-08-09 build: Strengthened page-state corpus instrumentation was red with three chunking-document reads on completed translation, confirming a redundant prerequisite parse plus nested translation-summary reloads.
- 2026-08-09 build: Approved-translated page instrumentation was red until the gate's validated translation document was threaded into resolution; original-language and translated paths now each read chunking and translation documents once, while the unapproved path reads the translation gate once and deliberately skips source resolution.
- 2026-08-09 build: All nine affected Speech Blocks modules passed directly through the mandated shared interpreter with 187 tests passed.
- 2026-08-09 build: Ruff, Python compilation, and `git diff --check` passed on the scoped changes.
- 2026-08-09 build: The changed-file code-style audit retains six legacy `@brief` findings in pre-existing Speech Blocks document/projection callables, and the logging audit retains the pre-existing state-builder candidate whose prerequisite failures intentionally become page notes and fallback state; neither warning was introduced as a new callable or logging policy by this task.
- 2026-08-09 build: The uv-backed AEGIS impacted command was deliberately not run because the delegated runtime contract forbids uv; the linked and complete affected Speech Blocks set was run directly with the shared interpreter instead.
- 2026-08-09 deliver: Task-scoped AEGIS static checking reported zero errors and 76 advisory warnings consisting of repository-wide default-branch layout/coverage noise plus one unrelated requirement ticket reference.
- 2026-08-09 deliver: The first direct full-suite attempt was canceled by an interactive task steer after its monitor handle disappeared and no pytest process remained; it produced no result and was not duplicated while healthy.
- 2026-08-09 deliver: After revalidating the exact default settings payload and zero non-empty credentials, the sole completed direct full suite passed with 1551 passed, 1 skipped, and 1 deselected in 2035.60 seconds.
- 2026-08-09 deliver: The verified worktree-local generated `settings.json` still matched exact built defaults after the suite and was removed; no pre-existing settings file was overwritten or deleted.
- 2026-08-09 deliver: `check --strict --run` was not invoked because its configured command uses forbidden uv and would duplicate the completed full suite; direct full pytest plus task-scoped static AEGIS is the user-mandated equivalent evidence.
- 2026-08-09 deliver: Task-scoped `check --strict` exited 0 with zero errors and 77 advisory warnings; the additional warning is the three intentionally unticked approval, delivery, and close-out items at this pre-commit checkpoint.
- 2026-08-09 deliver: The human approved delivery and requested local integration into `AudioMancer_V2`; the unrelated dirty files already present in that worktree will be preserved and no push is authorized.
- 2026-08-09 deliver: Delivery decision is one scoped commit containing the twelve staged implementation, test, requirement, knowledge, changelog, and journal paths, followed by one journal-only closeout commit.
- 2026-08-09 deliver: Delivery commit `cec6cb7` succeeded and `AudioMancer_V2` fast-forwarded to it without modifying or staging the unrelated dirty delivery and planning files already present there.
- 2026-08-09 close-out: Local integration succeeded, every delivery checklist item is complete, and this journal-only closeout sets the task stage to done.

## Design

- Components: Speech Blocks service projections/persistence, Speech Blocks controller deletion cleanup, Audio Blocks artifact removal, and Speech Blocks knowledge/tests.
- Interface: public function signatures and persisted JSON stay unchanged; private persistence and log-path helpers receive one already-resolved source context or operation state (REQ-NFR-9c867783).
- Resolution: one private source-context helper loads upstream chunks once, derives count/language/kind, and falls back to persisted document identity plus processed-block count when upstream artifacts are unavailable (REQ-NFR-9c867783).
- Resolution: the page prerequisite gate reuses its validated approved translation document during source resolution, so original-language and translated page paths each parse the chunking and translation documents once while unapproved translation still prevents resolution (REQ-NFR-9c867783).
- Projection: report and operation-state views for one entry point are built from one loaded document and one shared source count, including generation and selected-chunk regeneration paths that already own resolved chunks (REQ-NFR-9c867783).
- Identity: the allocator contract is current-document uniqueness, matching the only durable information in the strict fixed-field document (REQ-DATA-af08bfc5).
- Cleanup: confirmed controller deletion remains the load-bearing boundary that removes the deleted Audio Blocks row/WAV before another controller action may reuse the identifier (REQ-REL-14f298bd).
- Storage: no field, sidecar, migration, or persisted-format change is introduced.
- Rejected: a monotonic high-water field was rejected because the strict document rejects extra top-level fields and retrofitting every full/compact composition path would create a schema change solely to preserve an unsupported docstring promise.
- Test seams: service tests assert current-ID allocation and instrument `resolve_source_chunks` across reads, approve, edit, insert, delete, generation, fallback, and count projections.
- Test seams: a controller integration test uses real Audio Blocks persistence/artifact cleanup across delete then identifier-reusing insert to prove stale audio cannot attach.
- Expected files: `speech_blocks_service.py`, `speech_blocks_state_service.py`, their service/state/controller tests, `Speech_Blocks.md`, three requirement files, this journal, and `CHANGELOG.md`.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: full; branch: ddp/sb5-sb7-identity-projections
- requirements:
  - REQ-DATA-af08bfc5 - Keep Speech Block identifiers unique in the current document
  - REQ-REL-14f298bd - Remove stale audio before a deleted Speech Block identifier can be reused
  - REQ-NFR-9c867783 - Resolve Speech Block source context once per operation
- diff vs configured default-branch merge base: 314 file(s) changed and 29378 line(s) added, including pre-existing `AudioMancer_V2` branch divergence; this task's working-tree scope is 12 files with 869 insertions and 87 deletions
- checks: errors=0 warnings=77 notes=0
- checklist: 5/8 done; open: delivery confirmed by the human before the commit; journal and report inside the delivery commit; agreed outcome delivered; close-out: `stage: done` set and committed only after the outcome succeeded
