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

# TASK-9c24d30c — Preserve Speech Block resume and chunk identity

stage: deliver
type: fix
path: full
requirements: REQ-REL-63e230dd, REQ-FUNC-31425199
branch: ddp/sb1-sbu1-speech-block-integrity
opened: 2026-08-09

## Done checklist (current stage)

- [x] direct full suite and task-scoped strict static check are green or any failure is accurately recorded
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and code style
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] `CHANGELOG.md` Unreleased section written in user language without a release version
- [x] delivery confirmed by the human before the commit
- [x] journal and report included in the delivery commit after approval
- [ ] close-out: `stage: done` set only in a journal-only commit after the delivery commit succeeds

## Log

- 2026-08-09 frame: Repair Speech Blocks review/completed resume so source-identity gaps regenerate exactly once without disturbing covered or approved rows, and parse complete numeric chunk tokens so ordering and ID namespaces remain distinct above 9999.
- 2026-08-09 frame: Exclude all planning-file edits, unrelated Speech Blocks findings, broad refactors, schema or document-version changes, unrelated migrations, dependencies, packaging, release/version work, `.gitattributes`, main-worktree changes, commits, pushes, merges, and pull requests before explicit approval.
- 2026-08-09 frame: Use the full path because both fixes strengthen externally observable persisted-plan integrity and require new independently verifiable behavior.
- 2026-08-09 frame: Create one reliability requirement for ordered source-identity resume and one functional requirement for complete numeric chunk ordering and identifier namespaces.
- 2026-08-09 frame: The delegated scope explicitly requests implementation through the mandatory pre-delivery checkpoint, so the frame proposal is treated as confirmed without an additional pause.
- 2026-08-09 specify: Created REQ-REL-63e230dd for gap-safe review/completed resume and REQ-FUNC-31425199 for complete numeric chunk ordering and identifier namespaces; neither behavior was fully covered by an existing requirement.
- 2026-08-09 specify: AEGIS check reported zero errors and 31 repository-baseline warnings, with no task-artifact format finding.
- 2026-08-09 design: Use a short journal design because resume selection and loop behavior must cooperate, while no external API or persisted schema changes.

## Design

- Components: Speech Blocks orchestration for REQ-REL-63e230dd; normalization and canonical sorting for REQ-FUNC-31425199.
- Interface: keep public functions and document shape unchanged; private resume helpers receive ordered source chunks and persisted blocks so they can compare identities.
- Resume data: running/failed checkpoints remain authoritative, including active-chunk segment cursors; review/completed state starts at the first uncovered source identity.
- Generation: skip already-covered chunks after the restored start, except the active partial checkpoint chunk, and add each generated chunk to the covered set.
- Identity data: parse all digits and retain `:04d` as a minimum width, so existing identifiers through 9999 remain byte-for-byte unchanged and larger prefixes expand naturally.
- Rejected alternative: converting the coverage count back into an index or discarding every row after the first gap would either retain ambiguity or destroy later approved operator work.
- Test seam REQ-REL-63e230dd: public generation with three realistic chunks, a deleted middle chunk, a later approved row, an all-covered no-op, and existing active segment-resume coverage.
- Test seam REQ-FUNC-31425199: normalization boundary assertions plus public canonical book sorting for chunks 0001, 10000, and 10001.
- Expected source/test files: `speech_blocks_service.py`, `speech_blocks_normalization_service.py`, `test_speech_blocks_service.py`, and `test_speech_blocks_normalization_service.py`.
- No spec is needed because these decisions make both narrow requirements directly buildable.
- 2026-08-09 design: AEGIS format findings remained at zero before entering build.
- 2026-08-09 build: `test_review_resume_restores_missing_middle_chunk_without_duplicate_covered_blocks` was red for both review-pending and completed states because resume regenerated chunk 0003 and left chunk 0002 absent.
- 2026-08-09 build: `test_chunk_identity_preserves_complete_numeric_token_above_four_digits` was red because chunk 10000 resolved to order 0 instead of 10000.
- 2026-08-09 build: `test_speech_block_book_sort_uses_complete_chunk_number` was red because chunk 10000 sorted before chunk 0001.
- 2026-08-09 build: The three new regressions and active direct-segment resume were green with eight parametrized cases passing.
- 2026-08-09 build: AEGIS `test --impacted` expanded this central service to 763 repository-wide references and exited 127 before running tests under its configured runner, so no green claim is made for that command.
- 2026-08-09 build: The nine focused Speech Blocks modules passed 173 tests with the shared interpreter and explicit worktree `PYTHONPATH`.
- 2026-08-09 build: Shared-interpreter `py_compile` and Ruff checks passed for both changed source files and both changed test files.
- 2026-08-09 build: Task-scoped strict AEGIS static check reported zero errors and only 72 repository-baseline ticket, layout, and uncovered-source warnings unrelated to this diff.
- 2026-08-09 deliver: Generated the ignored worktree `settings.json` only through `settings_service.ensure_settings_file()` after proving package and target paths were inside this worktree, then verified built-in defaults, an empty profile list, and zero non-empty credential fields.
- 2026-08-09 deliver: The one direct full suite passed 1526 tests with 1 skipped, 1 deselected, and 1 existing `audioop` deprecation warning in 1898.86 seconds; no duplicate suite was launched.
- 2026-08-09 deliver: Removed only the generated worktree `settings.json`, confirmed the diagnostic worktree `.venv` was absent, confirmed no pytest process remained, and confirmed the expected task-only Git status.
- 2026-08-09 deliver: Task-scoped static `check --strict` finished with zero errors and `strict: ok`; 73 warnings were repository-baseline traceability/layout findings plus this intentionally unticked delivery checkpoint.
- 2026-08-09 deliver: Accepted changed-only code-style findings on seven pre-existing callables at service lines 147-351 and one pre-existing logging candidate at normalization line 515 because none intersects this diff and fixing them would violate the bounded scope.
- 2026-08-09 deliver: Reviewed every hunk against both requirements, active checkpoint and segment semantics, boundary ordering, error paths, Windows/Linux portability, secrets, code style, and exclusions; `git diff --check` passed and no planning, schema, release, dependency, packaging, or unrelated file changed.
- 2026-08-09 deliver: Updated `.agentic/knowledge/Speech_Blocks.md` and the Unreleased changelog in user language without assigning a release version or changing either Help file.
- 2026-08-09 deliver: Human independently reviewed and approved the exact nine-file staged diff, requirements, evidence, knowledge, changelog, and exclusions for two local commits with no push, merge, or pull request.
- 2026-08-09 deliver: The generated report's 286-file merge-base statistic is an AEGIS base-selection artifact; the authoritative approved and cached delivery diff is nine files with 486 insertions and 39 deletions against HEAD 41e9f55.
- 2026-08-09 deliver: After adding the mandated report and approval record, the final delivery commit remains the same nine files and totals 498 insertions and 39 deletions; 486 insertions and 39 deletions was the approved pre-report checkpoint.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: full; branch: ddp/sb1-sbu1-speech-block-integrity
- requirements:
  - REQ-REL-63e230dd - Regenerate missing Speech Block source chunks without duplication
  - REQ-FUNC-31425199 - Preserve complete numeric Speech Block chunk identity
- diff vs merge base: 286 file(s) changed, 26600 line(s) added
- checks: errors=0 warnings=73 notes=0
- checklist: 6/8 done; open: journal and report included in the delivery commit after approval; close-out: `stage: done` set only in a journal-only commit after the delivery commit succeeds
