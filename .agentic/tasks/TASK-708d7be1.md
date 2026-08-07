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

# TASK-708d7be1 — Enforce Cleanup fusion safety and truthful provenance

stage: done
type: fix
path: full
requirements: REQ-FUNC-e42171cc, REQ-FUNC-c30ccde3
branch: bugfix/improvements
opened: 2026-08-07

## Done checklist (current stage)

- [x] `check --strict --run` green or every environment/pre-existing limitation recorded truthfully
- [x] diff reviewed against scope, requirements, design, error paths, portability, security, and unrequested changes
- [x] knowledge pages updated for every materially changed component
- [x] requirements re-read: status, prose, verification, and links all true
- [x] requested delivery endpoint confirmed: stage only, no commit or push
- [x] journal and final report prepared without committing or pushing
- [x] close-out: `stage: done` set for the requested delivery-preparation endpoint before explicit staging
- [x] code follows `01_Documentation/Code_Style.md`
- [x] `CHANGELOG.md` Unreleased section written in user language
- [x] release version workflow skipped because this task is not a release

## Log

- 2026-08-07 frame: Scope is TC-5 rendered-span fusion enforcement and TC-8 conservative paragraph-local provenance after whitespace-only manual edits; other Cleanup findings, prompts, boundary policy, metadata schema, planning reports, unrelated lifecycle work, release/version work, commit, and push are excluded.
- 2026-08-07 frame: Full path chosen because a blocking output safety gate and persisted provenance semantics change across renderer, manual-edit, metadata-consumer, and downstream warning behavior.
- 2026-08-07 frame: Existing REQ-FUNC-e42171cc will be made independently testable for TC-5, while TC-8 receives a new requirement because existing whitespace-edit requirements cover role and diagnostic behavior but not truthful paragraph-local provenance.
- 2026-08-07 frame: The protected planning files began modified and unstaged with SHA-256 values 00_Executive_Summary.md=A7D71A4918F98CBB759CFD9AC2C3DFA1FEF56ADA0DFCF066315E310EE4865B02, 03_Text_Extraction_Cleanup.md=5797BF7A8B52EBA507EF847659DEC49C1D37F6D4D253ED560C942348FDB39E1B, and 05_AI_Runtime.md=82241F4C7070B4670935D00537BE11C8B54971B9326E5A38158C837DD3C13090.
- 2026-08-07 frame: Autopilot delivery preparation confirms the scope without a checkpoint pause on branch bugfix/improvements, retaining all three protected planning files as byte-for-byte read-only and unstaged.
- 2026-08-07 specify: Updated REQ-FUNC-e42171cc with a rendered-projection fusion contract and created REQ-FUNC-c30ccde3 for conservative unique paragraph provenance, each with a focused algorithm specification and no public API or schema change.
- 2026-08-07 specify: Task-scoped AEGIS check reported zero errors; all 46 warnings are the existing unrelated ticket reference, branch-wide uncovered source, and outside-layout planning, help, changelog, and test-guide findings.
- 2026-08-07 design: The design below uses transient rendered-boundary evidence for TC-5 and bidirectional normalized-content cardinality for TC-8 while retaining public APIs, persisted fields, role policy, and downstream projections.

## Design

- REQ-FUNC-e42171cc: after rendering, scan consecutive retained output spans and count only zero-width Unicode-alphanumeric joins across distinct source units; separators and non-alphanumeric endpoints are naturally excluded by the output projection.
- REQ-FUNC-e42171cc: mark a transient projected boundary as applied only when `dehyphenate` removes the previous retained span's terminal hyphen, and authorize only an adjacency at that projection whose left span has the same source unit ID.
- REQ-FUNC-e42171cc: keep `render_cleanup` and persisted metadata unchanged; a positive count still raises `CleanupRenderError` before metadata is returned or publication can occur.
- REQ-FUNC-c30ccde3: replace role-only one-sided grouping with one helper that indexes both prior and current normalized keys and realigns only keys occurring once on each side.
- REQ-FUNC-c30ccde3: unique truthful matches copy ordered deduplicated source IDs, page fields, transition flags, confidence, reason codes, and compatible role; unresolved or unavailable matches retain classifier roles with empty IDs, cleared page data, false transition flags, and unavailable provenance.
- REQ-FUNC-c30ccde3: append `user_whitespace_realign` once to every rebuilt whitespace record so existing reasons and warning projection survive without schema changes; lexical-edit reconstruction is untouched.
- Test seams: renderer quality-contract tests call the rendered-projection counter directly for controlled unsafe input and exercise integrated direct/dropped boundary chains; Cleanup service and quality-contract tests persist edits and inspect paragraph metadata, runtime warnings, roles, chunk output, and offsets.
- Rejected alternatives: source-string-only fusion checks cannot see dropped-chain output, and positional paragraph matching would create false provenance for duplicate content; general text diffing is outside scope and less conservative.
- Expected implementation files are `cleanup_renderer_service.py`, `text_cleanup_service.py`, focused Cleanup tests, both requirements/specs, this journal, `Text_Cleanup.md`, and `CHANGELOG.md`; user guides remain unchanged because no documented operator workflow changes.
- 2026-08-07 build: REQ-FUNC-e42171cc rendered-projection tests red as expected because an injected empty separator and a dehyphenation on a dropped left unit produced unreported fusion, while the existing counter exposed no rendered-span interface and remained effectively constant.
- 2026-08-07 build: REQ-FUNC-c30ccde3 paragraph-provenance tests red as expected because every rebuilt record received the document-wide source-ID union and available flag, including merged, split, and duplicate paragraphs, while unique matches lost their page, confidence, reason, and warning metadata.
- 2026-08-07 build: Implemented rendered-span fusion validation with exact applied-dehyphenation evidence and conservative unique paragraph metadata realignment; the directly affected quality-contract, Cleanup service, and metadata modules passed 89 tests.
- 2026-08-07 build: `aegis.py test --impacted` exited 127 before pytest because its branch-wide 454-selector command uses repository-root selectors after changing directories and requires unavailable `uv`; the directly affected modules above are the equivalent inner-loop evidence.
- 2026-08-07 build: Ruff and changed-file py_compile passed, and task-scoped AEGIS check reported zero errors with 46 accepted pre-existing ticket-reference, branch-wide uncovered-source, and outside-layout warnings after the workspace-local pytest temp was removed.
- 2026-08-07 deliver: The one delivery-candidate full suite passed 1,415 tests with 1 skipped and 1 deselected in 1,521.40 seconds; the only warning was the existing Python audioop deprecation notice.
- 2026-08-07 deliver: `check --strict --run` exited 1 before pytest because the configured command requires an unavailable `uv` executable; the direct project-venv full suite above is the authoritative test evidence.
- 2026-08-07 deliver: The strict-run findings were read in full and comprise the `uv` command error, the temporary unticked-deliver journal state, one unrelated ticket reference, pre-existing branch-wide uncovered sources, and outside-layout planning, help, changelog, and test-guide files.
- 2026-08-07 deliver: Full Ruff, changed-file py_compile, and `git diff --check` passed after the full suite, and semantic review confirmed rendered-output enforcement, exact dehyphenation scope, conservative one-to-one provenance, stable schema and APIs, and no prompt, policy, or unrelated lifecycle changes.
- 2026-08-07 deliver: Re-read both active requirements and focused specs against their linked tests, updated the Text Cleanup knowledge behavior and Files ownership plus the Unreleased changelog, and left both user guides unchanged because the operator workflow and documented UI behavior did not change.
- 2026-08-07 deliver: The three protected planning files retain their starting SHA-256 values and remain unstaged, and the release version workflow is intentionally skipped because no release version was assigned.
- 2026-08-07 close: Autonomous delivery preparation is complete at the requested explicit-staging endpoint with no commit or push; the closed journal and report are prepared before staging as requested.
- 2026-08-07 close: Final static `check --task TASK-708d7be1 --strict --full` exited 0 with zero errors and the same 46 accepted pre-existing branch-wide warnings.

## Delivery report (2026-08-07)

- stage: done; type: fix; path: full; branch: bugfix/improvements
- requirements:
  - REQ-FUNC-e42171cc - Cleanup shall reject newly introduced rendered alphanumeric fusion
  - REQ-FUNC-c30ccde3 - Whitespace-only Cleanup edits preserve only unambiguous paragraph provenance
- diff vs merge base: 164 file(s) changed, 16955 line(s) added
- checks: errors=0 warnings=46 notes=0
- checklist: 10/10 done
