<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->


# TASK-c6bc0143 - Preserve artifact-only pages during Cleanup

stage: deliver
type: fix
path: full
interaction: autopilot
requirements: REQ-FUNC-51ecd895
parent:
branch: ddp/fix-cleanup-artifact-only-pages
base: 1f7cb72c76b289b0fcf564dfeebe3b2b8e952158
opened: 2026-10-29

## Done checklist (current stage)

- [x] Local candidate reviewed; implementation and regression complete with verification limits recorded.
- [x] Unreleased changelog, both guides, component/spec and requirement updated; no release/version change requested.
- [x] New code follows binding style; all 65 whole-file audit findings verified identical to HEAD.
- [x] User explicitly approved commit and push after requesting rebuilt packages at the same version.
- [x] Journal and delivery report prepared for the approved commit.
- [ ] Approved publication outcome completed and close-out committed.

## Frame

Problem: STATED Cleanup fails on books such as Colossus; OBSERVED first PDF page contains only a recognized page number and the renderer rejects deleting its last text unit.
Desired outcome: STATED Fix Cleanup and add a regression test.
Actors: Operator, deterministic Cleanup analyzer, renderer, optional AI provider.
Primary scenario: Cleanup analyzes an artifact-only page -> retains its source units with artifact roles -> validates and publishes completed cleanup.
Examples: OBSERVED 09_Others/source_ledger.json page index 0 contains only u-000001, text 1; both supplied AI logs replay successfully until local rendering fails.
Counterexamples: Pages with body text still lose recognized page artifacts; manually supplied whole-page deletions remain rejected.
In scope: Deterministic artifact retention, synthetic integration regressions, real supplied-ledger replay, documentation and changelog.
Out of scope: Provider transport, credentials, extraction/OCR, changing user book files, release/version changes, publication.
Constraints: Preserve renderer whole-page deletion guard, source-only rendering, page_artifact roles and existing persistence format.
Success signals: Regression first reproduces current exception, then Cleanup completes and reloads; source narrative preserved; existing quality contract passes.
Evidence: STATED user fix request; OBSERVED cleanup_analysis_service.analyze_cleanup schedules every recognized artifact for deletion, cleanup_renderer_service.validate_operations rejects deleting all page units; INFERRED retain all recognized units on artifact-only pages conservatively; UNKNOWN live provider behavior outside supplied logs.
Assumptions: Existing whole-page safety rule remains authoritative; preserving artifact text is preferable to deleting the last extracted unit.
Unknowns: Other books may have unrelated failures.
Decision-blocking questions: None; the user authorized the diagnosed fix and regression.
Proposed behaviors: Keep artifact-only page units and their roles; remove recognized artifacts where other units survive.
Path and reason: full; clarify artifact-only-page behavior as a new explicit atomic requirement. No interface, dependency or security change. No delegated tasks.

## Requirement coverage

| Frame outcome | Atomic behavior | Requirement | Positive case | Boundary or failure | Verification | Design decision or no impact |
|---|---|---|---|---|---|---|
| Complete safe Cleanup | Retain recognized artifacts on pages consisting entirely of them | REQ-FUNC-51ecd895 | Number-only or header/footer-only page completes | Mixed pages still remove artifacts; explicit whole-page deletion rejected | Parameterized integration and guard tests | Compute protected artifact-only page set before building drop operations |

## Design

REQ-FUNC-51ecd895: Cleanup analysis owns deletion eligibility; renderer retains its independent safety check.
Identify located pages with at least one non-artifact unit. All other pages retain their recognized artifacts with page_artifact roles; schedule artifact drops only where another unit survives.
No public interface, persistence shape, provider, or architecture change. Invalid older checkpoints are already rejected as a whole and rebuilt; the analysis policy token identifies the updated deterministic policy.
Tests use synthetic layout ledgers (number-only page at beginning/middle/end and repeated header/footer pages), clean_text publication/reload and explicit rejection of whole-page deletion. The supplied ledger/logs are verified locally without network or committing copyrighted fixtures.
Tradeoff: Conservatively keep artifact text on otherwise text-empty pages. Chunking still receives the artifact roles. No unresolved decisions.
Expected paths: analyzer, test_cleanup_quality_contract.py, component knowledge/spec, both help files and CHANGELOG.md.

## Log

- 2026-10-29 frame: User authorized the diagnosed fix and regression. Full path selected; DEVIATION frame: flow through implementation/validation without intermediate checkpoints because the requested fix is already authorized; publication remains excluded.
- 2026-10-29 specify: One atomic requirement created; existing page safety and safe-gap contracts preserved.
- 2026-10-29 design: Local analyzer policy change defined in Design; no component or protocol changes. Advancing to build.

- 2026-10-29 build red: REQ-FUNC-51ecd895; command=`cd 05_Software/AudioMancer; uv run pytest -q tests/test_cleanup_quality_contract.py::test_cleanup_preserves_artifact_only_pages`; exit=1; all four cases fail with expected missing behavior: Cleanup may not remove every text unit on a page.

- 2026-10-29 build green: REQ-FUNC-51ecd895; `cd 05_Software/AudioMancer; uv run pytest -q tests/test_cleanup_quality_contract.py tests/test_cleanup_service.py tests/test_cleanup_adjudication_contract.py tests/test_cleanup_acceptance_corpus.py tests/test_cleanup_chunking_contract.py`; exit=0, 149 passed. Focused Ruff and py_compile exit=0. Four regression cases cover publication, roles, mixed-page removals, whole-page guard and old-checkpoint recovery.
- 2026-10-29 build: Anchor and evolution recorded; five non-.agentic paths match expected scope. Advisory check exit=0, errors=0, warnings=12, notes=1: nine pre-existing requirement/journal/sidecar warnings and three outside-layout warnings for required guides/changelog (configured layout declares only source/tests). No accepted product or verification deviation.
- 2026-10-29 validate manual replay: Temporary copies of supplied Colossus extraction, ledger, manifest and invalid checkpoint completed deterministic cleanup (0 requests, 150 paragraphs), GPT log replay (20 requests, 160 paragraphs) and LM Studio replay (37 requests, 181 paragraphs). All removed 21 artifacts, kept the cover number, had zero failed batches, reloaded strictly and reused completed state. No network or original-book edits.
- 2026-10-29 validate review round 1: Specification compliance approved independently against requirement and preserved contracts; implementation quality approved against hunk review, localized analyzer ownership, unchanged renderer guard, synthetic integration/recovery coverage and real-ledger replay. No findings. Documentation, both guides and Unreleased changelog match candidate; no release requested.

- 2026-10-29 validate final full check: `python .agentic/aegis.py check --task TASK-c6bc0143 --strict --run`; exit=1. Full pytest aborted after 2111.8s on its configured 120s per-test timeout in unchanged `tests/test_main_window_lifecycle.py::test_main_window_applies_settings_without_closing`, stack in `ui_state_service.apply_theme` / QApplication.setStyleSheet / ui_scroll_service.eventFilter. Windows COM/Qt diagnostic 0x8001010d appeared during earlier UI teardown; execution continued past it. Full-suite success is not claimed. Logging-coverage command passed. Code-style command exit=1; a direct audit_file comparison against HEAD proves source 22/22 and test 43/43 existing findings, with zero introduced findings. Catalog: 2 command errors, 11 warnings (existing records/sidecars and expected guides/changelog outside configured layout), 1 existing manual-verification note.
- 2026-10-29 DEVIATION validate: Required full check is not green because of timeout in an unchanged UI path and existing style findings; accepted as an explicit repository-wide verification limit for this local fix. No UI, audit policy, test timeout or unrelated documentation debt changed.
- 2026-10-29 validate supplemental verification: `cd 05_Software/AudioMancer; uv run pytest -q -m service`; exit=0, 1543 passed, 4 skipped, 498 deselected, one existing audioop deprecation warning, 191.86s. This completes the service tier, including tests beyond where the full run stopped; it does not replace full UI verification. Earlier focused proof: 149 passed; Ruff and compilation passed; real Colossus deterministic and both saved-provider replays completed/reloaded with zero failed batches.
- 2026-10-29 validate close: Candidate unchanged after full-check attempt. Both review verdicts remain approved for the scoped fix, with the recorded verification limit. Final diff reviewed: nine intended files including new requirement/journal; original 09_Others artifacts unchanged. Local patch ready for review on ddp/fix-cleanup-artifact-only-pages; no commit, push, PR, release or package requested or performed.

- 2026-10-29 deliver authorization: User requested rebuilding delivery packages while preserving 2.2.0, then explicitly approved commit followed by push. Agreed outcome: commit the scoped source/docs and already-tracked rebuilt Windows ZIP, Linux ZIP/AppImage and checksum manifest to ddp/fix-cleanup-artifact-only-pages; push to the existing private origin. Public GitHub publication and PR creation are outside this requested outcome. The Public GitHub Delivery Notes apply to that separate executable-only repository; this internal repository already tracks these archives, including prior commit be8b8a7.
- 2026-10-29 deliver packaging evidence: Existing Windows and WSL Ubuntu scripts rebuilt all three archives. Embedded bytecode in both ZIPs contains the new cleanup policy and artifact-only-page logic; packaged version 2.2.0, current guides/changelog and sanitized settings verified. Windows startup loads packaged settings unchanged and initializes Qt; existing Linux validator passed ZIP integrity, AppImage shared-library resolution and offscreen startup. All three SHA256SUMS entries verified again before commit. Version metadata unchanged. Source candidate unchanged since prior scoped verification; full-check limits remain recorded above.

## Rulings


- RULING-001 | date=2026-10-29 | decision=Commit the reviewed fix and rebuilt version-2.2.0 packages, then push the task branch to private origin | reason=Explicit user instruction after review and package verification | source=user | supersedes=none

## Handoff

current: deliver
status: ready
next: Commit reviewed files and push ddp/fix-cleanup-artifact-only-pages to origin.
must_read: .agentic/tasks/TASK-c6bc0143.md
blockers: none for approved push; full-suite limitations remain recorded.

## Stage report

stage: deliver
result: in_progress
current: deliver
changed: Approved fix, regression, docs and rebuilt packages at version 2.2.0.
evidence: 1543 service tests pass; package startup/integrity and all SHA256 checks pass.
issues: Full check limited by unchanged UI timeout and existing style findings.
next: Commit and push the reviewed task branch to private origin.
needs_user: no
spec_compliance: approved
implementation_quality: approved
review_round: 1

## Delivery report (2026-10-29)

- stage: deliver; type: fix; path: full; branch: ddp/fix-cleanup-artifact-only-pages
- requirements:
  - REQ-FUNC-51ecd895 - Preserve text on artifact-only pages during Cleanup
- deviations: 2 recorded
  - frame: flow through implementation/validation without intermediate checkpoints because the requested fix is already authorized; publication remains excluded.
  - validate: Required full check is not green because of timeout in an unchanged UI path and existing style findings; accepted as an explicit repository-wide verification limit for this local fix. No UI, audit policy, test timeout or unrelated documentation debt changed.
- explicit review: enabled; spec_compliance=approved; implementation_quality=approved; review_round=1
- diff vs task base 1f7cb72: 13 file(s) changed, 286 line(s) added
- checks: errors=0 warnings=16 notes=1
- checklist: 5/6 done; open: Approved publication outcome completed and close-out committed.
