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

# TASK-bd433c60 — Validate and consolidate DUP-01 and DUP-02

stage: deliver
type: change
path: full
requirements: REQ-NFR-d559facc, REQ-NFR-0eae9411
branch: ddp/dup-01-02-consolidation
opened: 2026-08-09

## Done checklist (current stage)

- [x] task-scoped strict static check and user-requested focused tests completed with limitations logged
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and exclusions
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links are true
- [x] delivery confirmed by the standing approval in the delegated request
- [x] journal and report inside the delivery commit; agreed commit outcome delivered
- [ ] close-out: stage done set and committed only after the delivery commit succeeds
- [x] code follows project style and the Unreleased changelog is updated without release/version changes

## Log

- 2026-08-09 frame: Validate DUP-01 profile-selector and DUP-02 confirmation duplication, consolidate only exact behavioral matches, and exclude planning edits, releases, schemas, unrelated duplication items, full-suite work, push, and merge.
- 2026-08-09 frame: Chose the full path because two new internal shared interfaces span state services and UI controllers even though externally observable behavior must remain unchanged.
- 2026-08-09 frame: Standing approval in the delegated request suppresses the frame and pre-commit conversation stops while retaining staged review evidence.
- 2026-08-09 specify: Added REQ-NFR-d559facc for exact selector-state preservation and REQ-NFR-0eae9411 for exact confirmation-dialog preservation.
- 2026-08-09 specify: Advisory check reported no errors and 177 baseline-selection warnings unrelated to the uncommitted task files.

## Design

- REQ-NFR-d559facc: add `build_llm_profile_selector_state` to the existing `ai_state_note_service` and delegate the five strip-normalizing selector wrappers to it.
- REQ-NFR-d559facc: retain `build_ai_cleanup_profile_state` locally because it deliberately preserves non-empty whitespace in labels rather than stripping it.
- REQ-NFR-d559facc: keep every wrapper signature and narrator `can_generate_profiles` augmentation unchanged; no data, persistence, or schema changes occur.
- REQ-NFR-d559facc test seam: exercise the shared helper's invalid/default/selection rules, all five wrapper mappings, narrator augmentation, and Cleanup's rejected whitespace-label subcase.
- REQ-NFR-0eae9411: add `confirm_question` to `misc_ui_controller` with the exact translated title/body, parent, Yes-or-No buttons, default No, and `decision == Yes` result.
- REQ-NFR-0eae9411: delegate only the 26 exact explicit-button/default-No calls across eight calling controllers; preserve wrapper names and inline flow boundaries.
- REQ-NFR-0eae9411: retain Home repair, Text Cleanup pretranslated text, Character Voices and Narator Voice three-argument overloads, formatted messages, and the Text Chunking page-local confirmation.
- REQ-NFR-0eae9411 test seam: patch the existing controller `QMessageBox.question` and `ui_state_service.translate` objects, which are shared identities with the helper imports, then verify exact arguments, decisions, and translation exceptions.
- Both requirements reject configurable mega-helpers because mode flags would hide the distinct contracts this consolidation must preserve.
- 2026-08-09 build: REQ-NFR-d559facc tests red as expected with two missing `build_llm_profile_selector_state` failures while 43 other focused cases passed or remained pending behind the second requirement.
- 2026-08-09 build: REQ-NFR-0eae9411 tests red as expected with two missing `confirm_question` failures; the corrected focused run totaled 4 failed and 41 passed before source edits.
- 2026-08-09 build: The same focused selector and confirmation set passed after implementation with 45 passed.
- 2026-08-09 build: AEGIS `test --impacted` expanded to 1,160 historical references and exited 127 before pytest produced results, so direct task selectors were used instead.
- 2026-08-09 build: One 17-module aggregate focused run timed out after 604 seconds without result output and was excluded from pass counts rather than retried wholesale.
- 2026-08-09 build: Final non-overlapping direct focused validation passed 110 tests: 77 selector/state tests, 30 shared and per-wrapper confirmation tests, and 3 inline-handler confirmation tests.
- 2026-08-09 build: Ruff and Python compilation passed for every changed Python file.
- 2026-08-09 build: Strict task-scoped AEGIS static check completed with zero errors and 86 merge-base/baseline warnings; strict result was ok.
- 2026-08-09 build: Changed-only code-style audit retains three pre-existing callable-doc findings outside changed functions, and logging coverage retains two pre-existing principal-state-builder candidates outside the consolidation behavior.
- 2026-08-09 build: Correction to the earlier Ruff line: the first enumeration omitted the untracked confirmation test, explicit checking found only line-length formatting there, and the final explicit Ruff plus compilation run passed all changed Python files.
- 2026-08-09 deliver: Per user direction, no full suite or `check --run` was executed; only focused tests and task-scoped static checks are delivery evidence.
- 2026-08-09 deliver: Semantic diff review confirmed five selector delegates, 26 exact default-No confirmation delegates, preserved public wrapper names and patch seams, and no changes to distinct dialog or Cleanup label behavior.
- 2026-08-09 deliver: Standing approval authorizes the reviewed delivery commit and a separate close-out commit without another conversational checkpoint.

## Delivery report (2026-08-09)

- stage: deliver; type: change; path: full; branch: ddp/dup-01-02-consolidation
- requirements:
  - REQ-NFR-d559facc - Shared LLM selector construction shall preserve caller contracts
  - REQ-NFR-0eae9411 - Shared confirmation construction shall preserve dialog contracts
- staged delivery diff: 25 file(s) changed, 995 line(s) added, 339 line(s) deleted
- checks: errors=0 warnings=87 notes=0
- checklist: 7/8 done; open: close-out: stage done set and committed only after the delivery commit succeeds
