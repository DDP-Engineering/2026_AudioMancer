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

# TASK-4ee8b9de — Reset owned Character Discovery logs and Character Voices samples

stage: done
type: fix
path: full
requirements: REQ-FUNC-fc51aea2, REQ-FUNC-de9cf536
branch: ddp/reset-artifact-integrity
opened: 2026-08-09

## Done checklist (current stage)

- [x] `check --strict --run` green or only explained pre-existing failures remain
- [x] diff reviewed against scope, requirements, design, error paths, portability, and security
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report inside the delivery commit; agreed outcome delivered
- [x] close-out: `stage: done` set and committed only after the outcome succeeded
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` Unreleased section written in user language without a version change

## Log

- 2026-08-09 frame: Scope is limited to owned Character Discovery AI-log deletion and metadata-owned Character Voices sample deletion before targets-document removal, with focused runtime tests and delivery records.
- 2026-08-09 frame: Excludes the dead Character Discovery log-reuse branch, blanket WAV globs, unrelated findings, UI, schemas, dependencies, versions, packaging, releases, planning documents, and AudioMancer_V2.
- 2026-08-09 frame: Full path chosen because safe persisted-path deletion is data-handling behavior and needs two independently verifiable ownership requirements plus a short design note.
- 2026-08-09 frame: Proposed requirement one covers Character Discovery AI-log ownership and preservation of unrelated operation logs.
- 2026-08-09 frame: Proposed requirement two covers Character Voices sample ownership, deletion ordering, preservation, and project-relative path safety.
- 2026-08-09 frame: The delegated implementation directive confirms the exact scope, requirements, verification cases, and pre-commit checkpoint, so work advances without an additional framing pause.
- 2026-08-09 specify: Created REQ-FUNC-fc51aea2 for current and historical Character Discovery AI-log ownership during reset.
- 2026-08-09 specify: Created REQ-FUNC-de9cf536 for metadata-proven Character Voices sample ownership, safe deletion ordering, and preservation boundaries.
- 2026-08-09 specify: No separate specs are needed because both requirements state the buildable trigger, ownership proof, deletion order, and preservation contract.
- 2026-08-09 specify: Advisory check reported zero errors and only pre-existing repository-layout and ticket-reference warnings.
- 2026-08-09 build: `test_operation_runtime_service.py::test_reset_operation_data_deletes_only_character_discovery_ai_logs` red as expected because the historical `log_ai_characters_*.log` family survived reset.
- 2026-08-09 build: Character Voices sample regressions red as expected because referenced character WAVs survived and the targets document was unlinked first, while preservation and unsafe-path controls were already inert.
- 2026-08-09 build: `test_character_voice_sample_reset_tolerates_non_utf8_targets_document` red as expected because `UnicodeDecodeError` escaped before the corrupt targets document could be deleted.
- 2026-08-09 build: All six new ownership regressions and the complete 24-test operation-runtime module pass with the shared interpreter and explicit worktree PYTHONPATH.
- 2026-08-09 build: AEGIS impacted selection expanded the shared runtime path to 808 historical references and exited 127 at command launch before pytest ran, so direct focused and complete-module runs provide the build evidence.
- 2026-08-09 build: Advisory check reports zero errors and retains the pre-existing repository-layout warnings because the configured source layout intentionally excludes documentation, planning, help, tool, and changelog files.
- 2026-08-09 build: Advisory check retains the pre-existing ticket-reference warning in REQ-UX-4753a4bf because that unrelated active requirement is outside this task.
- 2026-08-09 deliver: Task-scoped strict AEGIS check exited 0 with zero errors; pre-existing layout, ticket-reference, and repository-wide uncovered-source warnings remain accepted as out of scope, and unticked delivery items reflect this mandatory checkpoint.
- 2026-08-09 deliver: Per the task's exactly-one direct-suite constraint, verification separated the static strict AEGIS check from the direct full suite instead of invoking `check --strict --run` and duplicating pytest.
- 2026-08-09 deliver: Shared-interpreter preflight resolved application, runtime, test, and settings paths inside this worktree, generated settings matched built defaults, and one discovered credential field was empty.
- 2026-08-09 deliver: Direct full suite exited 0 with 1537 passed, 1 skipped, 1 deselected, and only the existing audioop deprecation warning in 1677.09 seconds.
- 2026-08-09 deliver: Removed only the task-generated ignored `04_Software/AudioMancer/settings.json` after the full suite.
- 2026-08-09 deliver: Compilation, Ruff, `git diff --check`, changed-file code-style audit, and changed-service logging coverage audit all passed.
- 2026-08-09 deliver: Revalidated the dead Character Discovery log-reuse branch is absent; `_resolve_log_path` derives a fresh current-token path, and its two existing start/resume tests pass.
- 2026-08-09 deliver: Semantic diff review confirms no blanket WAV glob, UI/schema/dependency/version/packaging/release/planning changes, and narrator, unrelated, unsafe, unreadable, and explicitly preserved artifacts retain their required behavior.
- 2026-08-09 deliver: Human checkpoint approved after independent staged-index review of exactly seven scoped files and an independent rerun of all six linked regressions with six passing.
- 2026-08-09 deliver: Approved outcome is one delivery commit followed by one journal-only closeout commit, with no push or merge.
- 2026-08-09 close-out: Delivery commit `917ba8e60ea049380f1b3091b3ad2c2fea19d4db` succeeded with seven scoped files after 1537 full-suite tests passed, and this journal-only commit closes the task without a push or merge.

## Design

- Component: change only the reset registry and helpers in `operation_runtime_service`, with focused seams in `test_operation_runtime_service.py` for both requirements.
- Interface: keep `reset_operation_data` and all persisted formats unchanged for REQ-FUNC-fc51aea2 and REQ-FUNC-de9cf536.
- AI logs: map Character Discovery reset to both `character_discovery` and `characters` tokens so current and historical owned logs are removed without changing log creation (REQ-FUNC-fc51aea2).
- Sample data: before deleting `characters_voice.json`, load its target list and consider only dictionary entries whose `target_kind` is exactly `character` and whose `sample_audio_path` safely resolves inside the project (REQ-FUNC-de9cf536).
- Sample safety: delete only resolved regular `.wav` files and skip narrator entries, malformed payloads, absent paths, unsafe or outside paths, symlinks, directories, and preserved `character_voices` operations (REQ-FUNC-de9cf536).
- Rejected alternative: do not add `audio_*.wav` to the glob registry because the name family cannot prove Character Voices ownership and overlaps preserved narrator or unrelated root audio (REQ-FUNC-de9cf536).
- Test seams: one reset test asserts exact AI-log families, and narrow reset tests assert multi-sample deletion order, narrator-preserving downstream reset, unsafe and unreferenced retention, and explicit Character Voices preservation.
- Expected modified files are the two requirements, journal, runtime service and tests, Operation Orchestration knowledge page, and `CHANGELOG.md`; planning documents remain read-only.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: full; branch: ddp/reset-artifact-integrity
- requirements:
  - REQ-FUNC-fc51aea2 - Reset Character Discovery owned AI logs
  - REQ-FUNC-de9cf536 - Reset only metadata-owned Character Voices samples
- staged delivery diff: 7 file(s) changed, 560 line(s) added, 1 line deleted
- checks: errors=0 warnings=77 notes=0
- checklist: 8/9 done; open: close-out: `stage: done` set and committed only after the outcome succeeded
