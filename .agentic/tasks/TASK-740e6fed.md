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

# TASK-740e6fed — Correct Speech Blocks split coverage and provenance

stage: deliver
type: fix
path: full
requirements: REQ-FUNC-6292ab33, REQ-FUNC-c13373e7, REQ-FUNC-15a96219, REQ-FUNC-5e94d565
branch: ddp/sbu2-sbu4-sbu7-split-correctness
opened: 2026-08-09

## Done checklist (current stage)

- [x] strict static AEGIS and the mandated direct full suite are green with no diff-introduced failures, and repository warnings are explained in the log
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and code style with no unrequested changes
- [x] Speech Blocks knowledge updated for every materially changed behavior
- [x] requirements re-read: status, prose, verification, paths, and links are true
- [x] delivery confirmed by the human before the commit
- [x] journal and report inside the delivery commit
- [ ] close-out: `stage: done` set and committed only after the delivery commit succeeds
- [x] code follows `01_Documentation/Code_Style.md` and `CHANGELOG.md` Unreleased describes the user-visible fixes; this task is not a release

## Log

- 2026-08-09 frame: Correct dash-led coverage, German quotation closure, exact TTS-split provenance, and multilingual quote unwrapping; exclude planning-file edits, public or persisted format changes, unrelated Speech Blocks findings, releases, pushes, and pre-approval commits.
- 2026-08-09 frame: Use the full path because four externally observable multilingual and provenance behaviors span three services; the delegated request confirms this exact scope through the required pre-commit checkpoint.
- 2026-08-09 frame: Proposed REQ-FUNC-6292ab33 for dash coverage, REQ-FUNC-c13373e7 for German quote closure, REQ-FUNC-15a96219 for exact source provenance, and REQ-FUNC-5e94d565 for authoritative multilingual quote unwrapping.
- 2026-08-09 specify: Created four self-contained functional requirements with focused service-level verification and no separate specs because the design below defines the only cross-service choice.
- 2026-08-09 design: Use offset-preserving slices for all provenance and keep spoken normalization separate; share the splitter's quote-pair helper with normalization and use acceptable-closer stacks in narrator planning without changing public or persisted payload shapes.

## Design

- Components: Speech Blocks source splitting, narrator planning, and block normalization (all requirements).
- Interface: preserve all existing payloads and function signatures; add one read-only quote-pair helper for internal cross-service reuse (REQ-FUNC-5e94d565).
- Data: derive source slices only from the original source text; model audio text may guide spoken splitting but cannot become provenance (REQ-FUNC-15a96219).
- Dash parsing: make the first detected turn range begin at local offset zero after dash-led classification (REQ-FUNC-6292ab33).
- Quote tracking: store acceptable closer tuples and test a pending closer before treating the same glyph as another opener (REQ-FUNC-c13373e7).
- Rejected alternative: do not normalize and rejoin source fragments or copy another quote list, because either choice can drift from exact source/pair ownership (REQ-FUNC-15a96219, REQ-FUNC-5e94d565).
- Test seams: source/atomic coverage in `test_speech_blocks_text_split_service.py`, quote closure/planning in `test_speech_blocks_narrator_split_service.py`, and provenance/unwrapping in `test_speech_blocks_normalization_service.py`.
- Expected source files: the three corresponding Speech Blocks service modules; expected documentation files: this task, four requirements, Speech Blocks knowledge, and CHANGELOG.
- 2026-08-09 build: `test_unspaced_dash_opener_preserves_contiguous_span_and_atomic_coverage` red as expected because both first span offsets began after the unspaced opener instead of at zero.
- 2026-08-09 build: `test_low_quote_closers_end_nested_quotation_before_budget_splitting` red as expected because the German high closer left two pending quote-stack entries while the Romanian closer passed.
- 2026-08-09 build: both exact-provenance TTS split regressions red as expected because whitespace was normalized away and differing model audio replaced every source slice.
- 2026-08-09 build: `test_dialogue_normalization_unwraps_every_authoritative_quote_pair` red as expected because no authoritative pair helper exists for normalization to consume.
- 2026-08-09 build: seven focused regressions passed after the minimal implementation and the three complete affected service modules passed with 46 tests.
- 2026-08-09 build: the configured impacted wrapper was not invoked because this task explicitly forbids its `uv` runtime; all linked selectors and their complete modules ran directly with the mandated shared interpreter and explicit worktree PYTHONPATH.
- 2026-08-09 build: the broader Speech Blocks run exposed one obsolete expectation that discarded inter-sentence spaces, so its provenance assertion was updated to the new exact reconstruction contract.
- 2026-08-09 build: `test_tts_budget_split_preserves_whitespace_only_semantic_spans` red as expected for leading separators and a trailing tab because recursive blank spans returned an empty list and were discarded.
- 2026-08-09 build: the whitespace-only semantic-span regression passed for all three leading, adjacent, and trailing cases after preserving blank recursive slices; its hard-split reconstruction assertions also passed.
- 2026-08-09 deliver: focused regressions passed, the three affected split/normalization/narrator modules passed 49 tests, all Speech Blocks modules passed 197 tests, and 5,000 seeded randomized TTS-split inputs reconstructed exactly.
- 2026-08-09 deliver: Ruff and Python compilation passed for all changed Python files, `git diff --check` passed, and no file under `0_Planning` changed.
- 2026-08-09 deliver: strict static AEGIS passed with zero errors and 78 accepted repository-wide inventory warnings for pre-existing uncovered-source, outside-layout, and ticket-reference debt unrelated to this diff.
- 2026-08-09 deliver: `check --strict --run` was intentionally not invoked because its configured runtime uses forbidden `uv`; equivalent Ruff, compilation, focused, affected, randomized, and direct full-suite verification ran with the mandated shared interpreter and explicit worktree PYTHONPATH.
- 2026-08-09 deliver: runtime and source imports resolved to the requested shared interpreter and this worktree, and the missing worktree settings file was generated only through `ensure_settings_file`, matched all 33 built defaults with zero non-empty credentials, was reverified unchanged, and was removed.
- 2026-08-09 deliver: exactly one direct full suite passed with 1,561 passed, 1 skipped, 1 deselected, and the existing `audioop` deprecation warning in 37 minutes 51 seconds.
- 2026-08-09 deliver: semantic review confirmed exact dash coverage and attribution, closer-first nested quote handling, lossless source provenance with independent spoken splitting, authoritative quote unwrapping, preserved public and persisted payloads, and no unrelated finding or planning-file changes.
- 2026-08-09 deliver: human approval confirmed staged fingerprint `0666df4a61665d39cd9d11ac8972afa353964259`, the exact 14-file scope, and all recorded validation evidence before commit.

## Delivery report (2026-08-09)

- stage: deliver; type: fix; path: full; branch: ddp/sbu2-sbu4-sbu7-split-correctness
- requirements:
  - REQ-FUNC-6292ab33 - Preserve dash-led dialogue coverage
  - REQ-FUNC-c13373e7 - Close supported German quotations
  - REQ-FUNC-15a96219 - Preserve exact source provenance during TTS splitting
  - REQ-FUNC-5e94d565 - Unwrap every supported dialogue quote pair
- approved checkpoint diff: 14 file(s) changed, 714 line(s) added, 113 line(s) deleted; fingerprint `0666df4a61665d39cd9d11ac8972afa353964259`
- checks: errors=0 warnings=79 notes=0
- checklist: 5/8 done; open: delivery confirmed by the human before the commit; journal and report inside the delivery commit; close-out: `stage: done` set and committed only after the delivery commit succeeds
