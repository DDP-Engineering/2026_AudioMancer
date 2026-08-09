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

# TASK-ac1caa8b — Consolidate behavior-identical DUP-11 through DUP-14 helpers

stage: deliver
type: change
path: full
requirements: REQ-NFR-7fcf36ea, REQ-NFR-5bda19fd, REQ-NFR-6edd8483
branch: ddp/dup-11-14-consolidation
opened: 2026-08-10

## Done checklist (current stage)

- [x] user-scoped focused validation and task-scoped strict check recorded honestly
- [x] diff reviewed against scope, requirements, design, error paths, portability, security
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, links all true
- [x] delivery commit confirmed by the human through standing approval
- [x] journal and report inside the delivery commit
- [ ] close-out: `stage: done` set and committed after delivery succeeds
- [x] code follows project style, CHANGELOG updated, and no release/version change made

## Log

- 2026-08-10 frame: The user confirmed scope as independent validation of DUP-11 through DUP-14 at integrated HEAD 191979c, with only behavior-identical or narrow safely parameterized consolidation in this isolated branch.
- 2026-08-10 frame: Exclusions are duration formatting, DUP-15, DUP-03 and all other findings, schemas, releases and versions, planning-file edits, unrelated cleanup, parent-worktree mutation, push, and merge.
- 2026-08-10 frame: Full path chosen because this cross-component refactor introduces public canonical helpers and needs explicit edge-contract requirements and design evidence despite no intended user-visible behavior change.
- 2026-08-10 frame: The user supplied the scope and standing approval for delivery and close-out commits, so the frame checkpoint is satisfied without another pause.
- 2026-08-10 specify: Created REQ-NFR-7fcf36ea for service resolver equivalence, REQ-NFR-5bda19fd for Audio Blocks model activation, and REQ-NFR-6edd8483 for workflow-controller helper contracts.
- 2026-08-10 analysis: DUP-11 selected-text limit, voice-assignment mode, target-language resolver, token-note delegates, and safe-stem delegates are exact and accepted; duration formatters are excluded.
- 2026-08-10 analysis: DUP-11 runtime-token consolidation is rejected because Speech rejects null-like strings through valid_runtime_value while Audio Blocks and Audio Assembly accept their stripped string forms.
- 2026-08-10 analysis: DUP-12 is accepted only for the common status-evaluation and load-and-verify tail, leaving clone budget resolution and the runtime_effective early return explicit.
- 2026-08-10 analysis: DUP-13 paragraph offsets are rejected because metadata normalizes CRLF and CR before scanning while renderer offsets remain relative to its input text.
- 2026-08-10 analysis: DUP-13 page index is rejected because analysis returns None for non-mappings while renderer currently raises AttributeError.
- 2026-08-10 analysis: DUP-14 AI-profile resolution is split: Text Chunking matches the canonical helper, Character Discovery is already delegated, and Text Cleanup remains local because whitespace-id and invalid-settings behavior diverge.
- 2026-08-10 analysis: DUP-14 stage rank is accepted with an explicit unknown-rank parameter preserving Audio Assembly zero versus the other controllers minus one; the identical language helper is accepted.
- 2026-08-10 analysis: DUP-14 Cleanup refresh-and-notify is accepted with success assertions retained, manifest load before refresh, refresh before notification, and cancellation's None guard retained.
- 2026-08-10 analysis: DUP-14 synchronous progress is accepted with explicit create-only versus restart-existing behavior and controller-local named wrappers retained for patch seams.

## Design

- REQ-NFR-7fcf36ea: add canonical public resolvers only in existing owner modules and replace private delegates directly; no storage, schema, or call-result changes.
- REQ-NFR-5bda19fd: share only Audio Blocks' busy/active/load/wait/verify sequence after each wrapper performs its existing progress, cancellation, status read, and clone-budget work.
- REQ-NFR-6edd8483: place generic workflow rank/language functions in workflow_controller_service and synchronous dialog mechanics in misc_ui_controller, while named controller handlers and divergent defaults stay explicit.
- REQ-NFR-7fcf36ea test seams: public helper edge tables plus monkeypatched canonical owner calls from former state-service delegates.
- REQ-NFR-5bda19fd test seam: direct private wrapper calls with patched VoiceWeaver status/load/wait functions and exact call/result assertions.
- REQ-NFR-6edd8483 test seams: workflow helper edge tables, ordered Cleanup callbacks, and existing-dialog progress lifecycle assertions through controller module references.
- Rejected alternative: a generic resolver or controller base abstraction would require behavior flags for divergent runtime tokens, Cleanup profile IDs, paragraph normalization, and page errors, obscuring rather than removing behavior.
- Expected source files are exactly the affected_paths listed by the three requirements; focused tests and AEGIS artifacts are the only additional files.
- 2026-08-10 build: REQ-NFR-7fcf36ea service-consolidation regressions red as expected with missing canonical resolvers and retained private delegates.
- 2026-08-10 build: REQ-NFR-5bda19fd model-activation regressions red as expected because the shared load-and-verify helper does not exist.
- 2026-08-10 build: REQ-NFR-6edd8483 controller-consolidation regressions red as expected with missing workflow, refresh, and dialog helpers plus retained local copies.
- 2026-08-10 build: the first uv launch exited before pytest because the fresh minimal environment omitted PySide6; rerunning through the declared dev extra produced the recorded red evidence.
- 2026-08-10 build: the three new regression files passed 18 tests after implementation.
- 2026-08-10 build: the 401-selector affected-module run outlived its ten-minute launcher, completed with six cached Speech Blocks failures, and all six passed after correcting missed resolved-mode references.
- 2026-08-10 build: the final combined consolidation and corrected Speech Blocks regression set passed 24 tests in 0.32 seconds.
- 2026-08-10 build: AEGIS impacted expanded to 1199 historical test references and exited 127 before pytest because app-relative selectors were prefixed after changing into the application directory, so no duplicate expanded run was launched.
- 2026-08-10 build: focused Ruff reported All checks passed on every changed Python source and test file.
- 2026-08-10 build: task-scoped AEGIS strict check reported zero errors and strict ok; 85 repository-wide ticket, layout, and coverage warnings are pre-existing or expected for the changelog and planning layout.
- 2026-08-10 deliver: full-suite execution is intentionally omitted because the user explicitly limited validation to focused tests and task-scoped static checks.
- 2026-08-10 deliver: semantic review found Text Chunking treats falsey non-string profile IDs as missing while the canonical helper can match their string form, so that consolidation was reverted and rejected.
- 2026-08-10 deliver: after reverting the divergent profile resolver, the three consolidation files plus the Text Chunking controller module passed 26 tests and focused Ruff remained clean.
- 2026-08-10 deliver: final task-scoped strict check reported zero errors and strict ok; the 87 warnings are the three expected unticked delivery items plus the same repository-wide ticket, layout, and uncovered-source warnings.
- 2026-08-10 deliver: reviewed every source and test hunk against the four findings, public and monkeypatch seams, exact fallbacks, cancellation and error order, Windows paths, and the hard exclusions with no planning, schema, version, or unrelated change.
- 2026-08-10 deliver: standing approval authorizes the local delivery and close-out commits; push, merge, parent-worktree edits, and pull-request publication remain excluded.

## Delivery report (2026-08-10)

- stage: deliver; type: change; path: full; branch: ddp/dup-11-14-consolidation
- requirements:
  - REQ-NFR-7fcf36ea - Shared service resolvers shall preserve caller edge behavior
  - REQ-NFR-5bda19fd - Shared audio model activation shall preserve runtime lifecycle
  - REQ-NFR-6edd8483 - Shared controller helpers shall preserve caller UI contracts
- staged task candidate: 31 file(s) changed, 1049 line(s) added, 410 line(s) deleted
- checks: errors=0 warnings=87 notes=0
- checklist: 7/8 done; open: close-out: `stage: done` set and committed after delivery succeeds
