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

# TASK-cd9a8d20 — Reject output-length-limited provider responses

stage: done
type: feature
path: full
requirements: REQ-FUNC-3875ac3b
branch: bugfix/improvements
opened: 2026-08-03

## Done checklist (current stage)

- [x] `check --strict --run` green, with warnings fixed or explained and evidence in the log
- [x] diff reviewed against scope, requirements, design, error paths, portability, and security
- [x] knowledge page updated for the materially changed AI Runtime component
- [x] requirement re-read: status, prose, verification, and linked tests are true
- [x] delivery confirmation received; delivery commit authorized
- [x] journal report generated and read; it will remain uncommitted at the user's direction
- [x] close-out completed after the authorized delivery commit; push remains out of scope
- [x] changed Python follows `01_Documentation/Code_Style.md`
- [x] non-release task: no changelog, version, or bilingual help-file version workflow applies

## Log

- 2026-08-03 frame: Scope is rejecting first-choice OpenAI-compatible chat responses explicitly terminated by the provider output limit before parsing or repair; parsing and repair of non-truncated responses, provider compatibility retries, transport retries, domain schemas, prompts, budgets, and artifacts are excluded.
- 2026-08-03 frame: Full path selected because this is a new externally observable provider behavior with a distinct functional requirement and an AI runtime data-handling boundary.
- 2026-08-03 frame: Continuing autonomously through delivery on existing branch bugfix/improvements as requested, stopping before commit or push.
- 2026-08-03 frame: Proposed requirement: new functional requirement for rejection of provider responses explicitly stopped by the output-length limit before JSON parsing or repair.
- 2026-08-03 specify: Created REQ-FUNC-3875ac3b as the sole requirement; the provider boundary decision is direct and documented by the OpenAI-compatible length token, so no specification is necessary.
- 2026-08-03 specify: check reported no errors and 20 pre-existing warnings: one unrelated ticket-reference warning and 19 accepted outside-layout warnings for project help/changelog and the user-owned planning review files, all outside this task's scope.

## Design

- REQ-FUNC-3875ac3b: Validate the first choice's finish_reason inside `_extract_message_content`, after choice shape validation and before extracting message content, so neither local parsing nor the model-repair branch can observe a length-limited response.
- REQ-FUNC-3875ac3b: Treat only a normalized documented string token `length` as a hard failure; a missing field and every other value retain existing compatibility behavior without new storage or public parameters.
- REQ-FUNC-3875ac3b: Raise a fixed RuntimeError naming the provider output-token limit, avoiding prompt, content, credential, or provider-payload details; the existing `chat_json` failure logger records the failure and its normal non-retry classification ends the attempt.
- REQ-FUNC-3875ac3b: Reject adding retries or a wider protocol abstraction because the provider's explicit termination signal is sufficient and the requirement excludes changed retry behavior.
- REQ-FUNC-3875ac3b: Test seams are `test_llm_provider_service.py` mocked HTTP responses for malformed and valid length content, transaction logging, stop/omitted compatibility, and the existing non-truncated model-repair regression.
- REQ-FUNC-3875ac3b: Expected files are `llm_provider_service.py`, `test_llm_provider_service.py`, `REQ-FUNC-3875ac3b.toml`, `AI_Runtime.md`, and this journal.
- 2026-08-03 design: check again reported no errors and the same 20 pre-existing warnings previously recorded; the design is complete and the task advances to build.
- 2026-08-03 build: test_llm_provider_service length-response regressions were red as expected because valid JSON returned success and malformed JSON entered model repair before any finish_reason validation.
- 2026-08-03 build: focused provider tests passed (20), and direct provider-caller tests for Cleanup, Chunking, and Translation passed (77 total).
- 2026-08-03 build: `aegis test --impacted` could not launch because its existing 153-selector Windows command exceeds the command-line limit; the direct 77-test provider/caller selection passed instead.
- 2026-08-03 build: Ruff, py_compile, and git diff --check passed for the changed Python files; check --full reported no errors and the same 20 pre-existing warnings accepted at specify.
- 2026-08-03 build: full suite passed with 1224 passed, 1 skipped, 1 deselected, and one pre-existing audioop deprecation warning.
- 2026-08-03 deliver: `check --task TASK-cd9a8d20 --strict --run` exited 0 after 1224 passed, 1 skipped, and 1 deselected; accepted warnings are the unrelated ticket reference, intentional unticked pre-commit delivery items, eight inherited uncovered-source paths from existing branch history, and 19 pre-existing outside-layout paths.
- 2026-08-03 deliver: Reviewed the narrow five-file task diff against scope, REQ-FUNC-3875ac3b, the design, error handling, portability, security, and code style; it contains no unrequested behavior or sensitive-data exposure.
- 2026-08-03 deliver: Read the generated report; its 52-file merge-base comparison and inherited-source warnings describe prior branch work, while this task's working-tree change is limited to the provider guard, its tests, the requirement, the AI Runtime knowledge page, and this journal.
- 2026-08-03 deliver: User confirmed manual testing and authorized the delivery commit; push remains out of scope.
- 2026-08-03 deliver: Delivery commit 6a866da succeeded on bugfix/improvements; closing the task without push as requested.

## Delivery report (2026-08-03)

- stage: deliver; type: feature; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-3875ac3b - The provider client shall reject output-length-limited responses before JSON parsing or repair
- diff vs merge base: 52 file(s) changed, 5676 line(s) added
- checks: errors=0 warnings=29 notes=0
- checklist: 6/9 done; open: delivery confirmation and commit intentionally omitted at the user's direction; journal report generated and read; it will remain uncommitted at the user's direction; close-out intentionally deferred because no delivery commit or push is authorized

## Delivery report (2026-08-03)

- stage: deliver; type: feature; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-3875ac3b - The provider client shall reject output-length-limited responses before JSON parsing or repair
- diff vs merge base: 52 file(s) changed, 5686 line(s) added
- checks: errors=0 warnings=29 notes=0
- checklist: 7/9 done; open: delivery confirmation and commit intentionally omitted at the user's direction; close-out intentionally deferred because no delivery commit or push is authorized

## Delivery report (2026-08-03)

- stage: deliver; type: feature; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-3875ac3b - The provider client shall reject output-length-limited responses before JSON parsing or repair
- diff vs merge base: 52 file(s) changed, 5696 line(s) added
- checks: errors=0 warnings=29 notes=0
- checklist: 8/9 done; open: close-out intentionally deferred because no delivery commit or push is authorized
