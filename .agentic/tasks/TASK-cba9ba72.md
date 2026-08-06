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

# TASK-cba9ba72 — Fix EPUB hidden extraction and Cleanup language warnings

stage: done
type: fix
path: full
requirements: REQ-FUNC-fb96f028, REQ-FUNC-8f5415b0
branch: bugfix/improvements
opened: 2026-08-06

## Done checklist (current stage)

- [ ] `check --strict --run` green
- [x] diff reviewed against scope, requirements, design, error paths, portability, security — no unrequested changes
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, links all true
- [x] delivery preparation completed; user requested no commit or push
- [x] no release version assigned; changelog and both help files updated

## Log

- 2026-08-06 frame: Scope is TC-11 visible EPUB/HTML extraction and TC-13 non-blocking supported-source-language warning persistence; CSS/JavaScript, language detection changes, CJK/Hangul policy, other cleanup findings, releases, and the three pre-existing planning-document edits are excluded.
- 2026-08-06 frame: The full path is required because TC-11 changes extraction state-machine behavior and TC-13 adds a persisted user-visible warning contract; the current non-default branch bugfix/improvements is retained and matches this journal.
- 2026-08-06 frame: Starting SHA-256 values recorded for untouched user-owned planning edits are 00_Executive_Summary.md=94A4AC5A46B01A9CA3747FD0A21656F7E67143DD1E0504736EB2300F336F2DE1, 03_Text_Extraction_Cleanup.md=101D95834FB7F2463CAEFB1CADCDBD7AE959DFC2DAFF3CEB457DEB421D92B4CA, and 05_AI_Runtime.md=82241F4C7070B4670935D00537BE11C8B54971B9326E5A38158C837DD3C13090.
- 2026-08-06 frame: Proposed separate requirements are visible EPUB ignored-subtree extraction and persisted non-blocking warning for detected unsupported Cleanup source languages.
- 2026-08-06 frame: Autopilot scope, path, and requirements proposal are logged; continuing without a frame checkpoint.
- 2026-08-06 specify: Created REQ-FUNC-fb96f028 for balanced ignored-subtree EPUB extraction and REQ-FUNC-8f5415b0 for the persisted unsupported-language warning; both have focused specifications because their parser and persistence seams require exact behavior.
- 2026-08-06 specify: AEGIS check reported no errors; its 43 warnings are pre-existing ticket-reference, uncovered-source, and outside-layout findings, including the user-owned planning documents.
- 2026-08-06 design: REQ-FUNC-fb96f028 will replace the depth counter with a bounded ignored-tag stack that records only non-void starts, normalizes attribute values, and leaves the existing block/event interface unchanged.
- 2026-08-06 design: REQ-FUNC-8f5415b0 will append one warning at deterministic analysis after language detection, then use the existing persisted warnings projection for checkpoints, state notes, and manifest summary rather than rebuilding UI text.
- 2026-08-06 design: Test seams are public EPUB extraction with an actual container fixture and controlled cleanup_text_analysis_service.detect_language results for deterministic, resume, AI, finalization, state, and manifest paths; a counter-only parser and UI-local warning were rejected because each can lose state or duplicate behavior.
- 2026-08-06 build: tests/test_text_extraction_service.py hidden-subtree cases were red as expected because bare hidden attributes leaked and aria-hidden=false test confirmed the parser test seam before the fixture assertion was corrected to use a block element.
- 2026-08-06 build: tests/test_cleanup_quality_contract.py unsupported-language cases were red as expected because deterministic analysis did not read CLEANUP_SUPPORTED_SOURCE_LANGUAGES or persist a warning.
- 2026-08-06 build: Implemented a non-void ignored-tag stack, case-insensitive hidden and aria-hidden handling, and one deterministic unsupported-language warning; focused EPUB and Cleanup selectors each passed 11 tests.
- 2026-08-06 build: `aegis.py test --impacted` exited 127 because its configured command cannot find uv and uses repository-root selectors after changing directories; the equivalent direct Extraction/Cleanup modules passed 146 tests.
- 2026-08-06 deliver: The full virtual-environment suite passed with 1,405 passed, 1 skipped, and 1 deselected in 25:22; only the existing audioop deprecation warning was emitted.
- 2026-08-06 deliver: Ruff, py_compile, and git diff --check passed; strict AEGIS check has no errors and its 43 warnings are existing ticket-reference, uncovered-source, and outside-layout findings.
- 2026-08-06 deliver: `check --strict --run` cannot execute the configured uv command, while the direct full suite above passed; temporary pytest folders were removed before the final static check.
- 2026-08-06 deliver: The three user-owned planning files retain their starting SHA-256 values and remain unstaged; documentation, requirements, specs, knowledge, tests, and changelog were reviewed as task scope.
- 2026-08-06 close: Delivery preparation is complete and scoped files are staged at the user's request; no commit or push was requested, and the unavailable configured uv wrapper remains the documented check-run exception.

## Delivery report (2026-08-06)

- stage: deliver; type: fix; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-fb96f028 - Extract only visible EPUB HTML content
  - REQ-FUNC-8f5415b0 - Warn for unsupported Cleanup source languages
- diff vs merge base: 158 file(s) changed, 16138 line(s) added
- checks: errors=0 warnings=44 notes=0
- checklist: 5/6 done; open: `check --strict --run` green
