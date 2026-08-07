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

# TASK-d79ec428 — Prevent invalid Character Discovery documents from blocking project open

stage: deliver
type: fix
path: full
requirements: REQ-FUNC-5ee17a17
branch: ddp/character-discovery-resume-profile-truth
opened: 2026-08-07

## Done checklist (current stage)

- [x] `check --strict --run` green, with inherited warnings explained in the log
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and code style
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and linked tests are true
- [x] delivery confirmed by the human before the commit
- [x] journal and report included in the delivery commit and the agreed branch push authorized
- [ ] close-out: `stage: done` set and committed only after the delivery push succeeds
- [x] project delivery additions satisfied; this task is not a versioned release

## Log

- 2026-08-07 frame: Keep strict Character Discovery document validation and reset-only recovery while preventing invalid persisted documents from blocking project-open export readiness.
- 2026-08-07 frame: Full path selected because the error recovery crosses a persisted-data boundary and export consumer, with one new functional requirement.
- 2026-08-07 frame: User explicitly requested this implementation after the traced project-open failure, satisfying the frame checkpoint.
- 2026-08-07 specify: Created REQ-FUNC-5ee17a17 for resilient Characters export readiness without document repair or compatibility acceptance.
- 2026-08-07 design: REQ-FUNC-5ee17a17 catches only CharacterDocumentError at the Characters export readiness seam and returns not-ready; strict reader behavior, stored data, and all other export errors remain unchanged.
- 2026-08-07 design: The failing seam is build_export_states with a valid project whose characters.json lacks the current required root field.
- 2026-08-07 build: tests/test_project_export_service.py::test_project_export_service_invalid_character_document_is_unavailable red as expected because CharacterDocumentError escaped Characters export readiness.
- 2026-08-07 build: Added narrow CharacterDocumentError handling only to Characters export readiness, preserving strict reader errors and persisted content.
- 2026-08-07 build: Direct export and MainWindow project-open regressions passed with 16 passed in 1.31 seconds.
- 2026-08-07 build: `aegis.py test --impacted` exited 127 before execution because its configured command changes into the application directory then passes root-relative test paths.
- 2026-08-07 build: Ruff, py_compile, and staged/unstaged diff checks passed; AEGIS check reported zero errors and the pre-existing ticket/layout warnings.
- 2026-08-07 build: The configured full suite timed out after 1800.4 seconds at 49 percent with exit 124 and no reported test failure, so it is not claimed as green.
- 2026-08-07 deliver: The combined delivery full suite later passed with 1395 passed, 62 skipped, and 1 deselected in 1564.10 seconds.
- 2026-08-07 deliver: `aegis.py check --full` returned zero errors and only the documented inherited ticket and outside-layout warnings.
- 2026-08-07 deliver: The supervisor reviewed the narrow strict-document recovery change and the human authorized commit and push.

## Design

- REQ-FUNC-5ee17a17: handle the expected strict CharacterDocumentError only in the Characters branch of `_artifact_ready`, returning false so project-open can render its established Reset-only state.
- Do not repair or loosen characters.json validation; that would violate the hard-break contract and could expose incompatible inventory data to exports.
- Expected files: project export service, export service test, requirement, Character Discovery knowledge page, and task journal.

## Delivery report (2026-08-07)

- stage: deliver; type: fix; path: full; branch: ddp/character-discovery-resume-profile-truth
- requirements:
  - REQ-FUNC-5ee17a17 - Invalid Character Discovery document shall not block project open
- diff vs merge base: 202 file(s) changed, 20927 line(s) added
- checks: errors=0 warnings=54 notes=0
- checklist: 7/8 done; open: close-out: `stage: done` set and committed only after the delivery push succeeds
