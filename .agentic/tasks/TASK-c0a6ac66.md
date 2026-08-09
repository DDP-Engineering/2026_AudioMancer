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

# TASK-c0a6ac66 — Preserve Speech Blocks ordering contracts

stage: deliver
type: fix
path: full
requirements: REQ-REL-0e236c91, REQ-FUNC-10095db1, REQ-DATA-f0eb775c
branch: ddp/sb2-sb3-sb6-ordering-contracts
opened: 2026-08-09

## Done checklist (current stage)

- [x] `check --strict --run` green or all environment/baseline limitations recorded honestly
- [x] diff reviewed against scope, requirements, design, error paths, portability, and security
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] delivery confirmed by the human before the commit
- [x] journal and report included in the delivery commit
- [ ] close-out: `stage: done` set only after the delivery commit succeeds
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` updated under `Unreleased` in user language
- [x] no release version workflow applies to this non-release delivery

## Log

- 2026-08-09 frame: Scope is to preserve multi-segment checkpoint and resume order, same-narrator response contracts through operator updates, and scene-ambience references through renumbering; exclusions are unrelated Speech Blocks findings, persisted-format changes, and every file under `0_Planning`.
- 2026-08-09 frame: Full path selected because the task formalizes three persisted reliability and data-integrity behaviors with non-trivial resume and identifier semantics.
- 2026-08-09 frame: Live code revalidation confirmed SB-2, SB-3, and SB-6 remain present at the requested `AudioMancer_V2` head.
- 2026-08-09 frame: Proposed requirements cover deterministic multi-segment order, same-narrator response-contract preservation, and scene-ambience reference integrity.
- 2026-08-09 frame: The delegation requests uninterrupted implementation through the pre-commit delivery approval gate, so the scope checkpoint is recorded and work continues.
- 2026-08-09 specify: Created three self-contained requirements for segment order, response-contract preservation, and ambience-reference integrity; no separate specs are needed because the journal design records the small compatible algorithms.
- 2026-08-09 specify: AEGIS reported zero errors; its 31 warnings are unchanged repository-wide layout and historical ticket-reference advisories outside this task.
- 2026-08-09 build: `tests/test_speech_blocks_service.py::test_multi_segment_checkpoint_and_resume_preserve_block_order` red as expected because the durable checkpoint ordered A1, B1, A2, B2 instead of canonical segment order.
- 2026-08-09 build: `tests/test_speech_blocks_service.py::test_same_narrator_operator_updates_preserve_deterministic_response_contract` red as expected because a full-report edit rewrote the marker to `direct_blocks`.
- 2026-08-09 build: `tests/test_speech_blocks_service.py::test_scene_ambience_insertion_remaps_references_after_opener_renumbering` red as expected because after-block references resolved to the opener and wrong spoken row after renumbering.
- 2026-08-09 build: All three focused regressions passed with the shared interpreter and this worktree's explicit source path after the minimal implementation.
- 2026-08-09 build: The direct affected Speech Blocks set passed 176 tests with the shared interpreter; Ruff and Python compilation passed on both changed Python files.
- 2026-08-09 build: The task-scoped AEGIS check reported zero errors and 76 advisories caused by its default-branch diff including pre-existing AudioMancer_V2 work plus repository-wide layout debt, while the working diff contains only requested delivery artifacts and exactly two Python files.
- 2026-08-09 build: The AEGIS impacted-test wrapper was not used because it invokes worktree `uv`; equivalent linked and component tests were run directly through the owner-specified shared interpreter and explicit worktree source path.
- 2026-08-09 deliver: Settings preflight resolved imported source, package/source roots, runtime target, and settings inside this worktree; the public service generated exact built defaults with zero non-empty credentials.
- 2026-08-09 deliver: Exactly one direct full suite passed with 1540 tests, one skip, one deselection, and only the pre-existing Python `audioop` deprecation warning in 27 minutes 20 seconds.
- 2026-08-09 deliver: Removed only the generated ignored worktree `settings.json` after validating its exact path; the accidentally provisioned ignored worktree `.venv` remains unused and outside delivery because shell policy blocked its guarded cleanup.
- 2026-08-09 deliver: Accepted task-scoped AEGIS `uncovered-source` advisories because default-branch resolution includes pre-existing AudioMancer_V2 commits while the task branch itself has no committed divergence from `AudioMancer_V2`.
- 2026-08-09 deliver: Accepted task-scoped AEGIS `outside-layout` advisories because they are repository-wide baseline paths and the task's root changelog update is explicitly required by project delivery rules.
- 2026-08-09 deliver: Accepted the historical `ticket-ref` advisory in unrelated `REQ-UX-4753a4bf`; this task does not alter that requirement.
- 2026-08-09 deliver: Semantic diff review confirmed no public interface, persisted field set, version, dependency, credential, or planning-analysis change; error paths and Windows/Linux-compatible ordering logic remain scoped to the three requirements.
- 2026-08-09 deliver: Updated Speech Blocks knowledge and the Unreleased changelog, then re-read all three active requirements and verified their linked tests and affected paths.
- 2026-08-09 deliver: Final task-scoped static AEGIS check exited zero with the accepted baseline advisories plus the expected three pre-approval unticked items; unstaged diff whitespace validation also passed.
- 2026-08-09 deliver: Human delivery approval received after independent review of the eight staged files, cached diff check, requirements, journal, changelog, planning exclusion, settings cleanup, ignored environment, and three linked regressions.
- 2026-08-09 deliver: Approved outcome is two local commits with no push or merge; the AEGIS report was generated and its inflated merge-base statistic was corrected to the eight-file task diff.

## Design

- Component: Speech Blocks orchestration and its focused service regressions; no public function signature, command, dependency, or persisted field changes.
- REQ-REL-0e236c91: Renumber each cumulative generated segment snapshot in list order before checkpoint callbacks, then offset resumed rows after already persisted rows of the active chunk at checkpoint and final merge seams.
- REQ-REL-0e236c91: Test seam is a multi-block, multi-segment cancellation checkpoint followed by resume, compared with canonical source order and contiguous indices.
- REQ-FUNC-10095db1: Extend the existing persisted-contract allow-list with the deterministic narrator marker so all current full-report and compact-review callers retain it.
- REQ-FUNC-10095db1: Test seam seeds a same-narrator document and exercises representative mutations routed through both persistence helpers.
- REQ-DATA-f0eb775c: Track original spoken-row positions across chunk-local renumbering, build a direct old-ID to new-ID map, and rewrite only ambience reference fields from that map.
- REQ-DATA-f0eb775c: Test seam combines an opener with multiple after-block ambience rows and asserts each reference still resolves to the same spoken text.
- Rejected alternative: clearing ambience references would avoid dangling IDs but would discard the existing scene grouping and labeling relationship.
- Expected modified delivery files: the Speech Blocks service/test, these three requirements, task journal, Speech Blocks knowledge page, and root changelog.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: full; branch: ddp/sb2-sb3-sb6-ordering-contracts
- requirements:
  - REQ-REL-0e236c91 - Preserve multi-segment Speech Block order
  - REQ-FUNC-10095db1 - Preserve same-narrator Speech Block response contract
  - REQ-DATA-f0eb775c - Preserve scene-ambience Speech Block references
- scoped diff vs AudioMancer_V2 task base: 8 file(s) changed, 570 line(s) added, 5 line(s) deleted
- checks: errors=0 warnings=77 notes=0
- checklist: 9/10 done; open: close-out: `stage: done` set only after the delivery commit succeeds
