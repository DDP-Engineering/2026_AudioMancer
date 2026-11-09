# TASK-a3c94d07 - Verify and publish AI Translation against canonical source

stage: done
type: change
path: full
interaction: autopilot
requirements: REQ-DATA-00dfaad5, REQ-DATA-ef2f9f01, REQ-FUNC-7298ddb1, REQ-FUNC-8701a2ee, REQ-REL-ed5bc963, REQ-FUNC-723fdb50, REQ-FUNC-5aa0c7f3, REQ-FUNC-c07fd83c, REQ-REL-061e8f66, REQ-FUNC-93999a8d, REQ-UX-a737a67e, REQ-UX-ea3d3aac
parent:
branch: master
base: 5ea3c7f12540c0e57d031279b1abe9e922dcd28c
opened: 2026-11-09

Edit Frame, Requirement coverage and Design directly. Write State, Log and
Rulings with `python .agentic/aegis.py` (advance, pause, log, ruling, verdict);
end each session with `advance` or `pause`.

## Done checklist (current stage)

- [x] diff reviewed against scope, requirements, design, error paths,
      portability, security and unrequested work
- [x] knowledge pages of changed components current with the reviewed code
- [x] project and environment context reconciled with the candidate
- [x] requirements re-read: status, prose, verification, paths and links true
- [x] manual or inspection verification recorded where applicable
- [x] explicit review approved, when enabled
- [x] final `check --strict --run` result logged truthfully after the last edit
- [x] remaining warnings and pre-existing failures explained
- [x] `report` appended

## Frame

Problem: OBSERVED translation matches by chunk ID only, consumers disagree on readiness, assembled requests can exceed their estimate, and publication spans UI and services.
Desired outcome: STATED implement the accepted AI Translation proposals, with verified approvals and common source first.
Actors: AudioMancer operator and downstream workflows consuming approved text.
Primary scenario: Translate, review, approve and hand off current canonical text, with safe continuation and replacement.
Examples: OBSERVED the analysis reproduced a stale approval, mixed source selection, and a 639-token estimate for a nominal 512-token segment.
Counterexamples: Current chunk ID alone cannot establish provenance. A failed retranslation cannot displace a published result.
In scope: STATED provenance, shared approved source, request validation and budget bounds, recoverable edit/approval/reset/publication, run identity and lifecycle, separated code, EN/RO help.
Out of scope: Existing provider APIs and source extraction, new dependencies, live model tests, package or commit.
Constraints: STATED current branch, autopilot, focused tests only, EN/RO help, no commit. Established single translation document and per-complete-chunk checkpoint remain.
Success signals: Focused tests demonstrate stale and legacy approval handling, shared downstream source, bounded request estimates, failure recovery and correct operator recovery controls.
Evidence: OBSERVED AI_Translation knowledge page, current service and consumers, synthetic read-only probes in the preceding analysis.
Assumptions: INFERRED an old translation without source identity remains available for review and requires new approval against current text.
Unknowns: Live provider fluency and exact tokenizer usage are outside structural verification.
Decision-blocking questions: None. Scope approved in the latest user request.
Proposed behaviors: Bind approval to source text; unify consumers; validate request and reply boundaries; publish translation mutations and their workflow effects recoverably.
Path and reason:

| Criterion | Holds? | Evidence |
|---|---|---|
| no new externally observable behavior | no | stale and unverified approvals become unavailable |
| no new interface or data format | no | source and request fingerprints |
| no new dependency | yes | stdlib and existing services |
| existing requirement covers behavior | no | new provenance and recovery behavior |
| no security or data-handling change | no | approval authority and selective invalidation |

## Requirement coverage

| Behavior | Requirement | Design | Verification |
|---|---|---|---|
| Bind approval to current source | REQ-DATA-00dfaad5 | See Design | test_changed_source_disqualifies_only_its_translation |
| Preserve legacy translations for review | REQ-DATA-ef2f9f01 | See Design | test_legacy_translation_requires_explicit_reapproval |
| Resolve approved translation consistently | REQ-FUNC-7298ddb1 | See Design | test_consumers_agree_on_approved_source |
| Invalidate dependent work when effective text changes | REQ-FUNC-8701a2ee | See Design | test_approval_invalidates_speech_without_character_document |
| Recover translation publication | REQ-REL-ed5bc963 | See Design | test_translation_publication_restores_originals |
| Bound assembled translation requests | REQ-FUNC-723fdb50 | See Design | test_translation_planner_bounds_assembled_fragments |
| Keep empty source chunks out of translation | REQ-FUNC-5aa0c7f3 | See Design | test_blank_source_is_not_requested_or_counted |
| Reject invalid translation replies | REQ-FUNC-c07fd83c | See Design | test_invalid_reply_cannot_publish_chunk |
| Close failed translation runs | REQ-REL-061e8f66 | See Design | test_log_failure_records_terminal_status |
| Disclose translation request changes | REQ-FUNC-93999a8d | See Design | test_resume_discloses_changed_request_policy |
| Allow recovery from an invalid translation document | REQ-UX-a737a67e | See Design | test_invalid_translation_allows_reset |
| Retain unsaved translation edits after publication errors | REQ-UX-ea3d3aac | See Design | test_failed_autosave_blocks_approval_and_keeps_draft |


## Design

### Approach
OBSERVED current translation service combines validation, orchestration and provider calls. Extract the pure document policy and fragment planner plus the provider adapter. Keep service entry points and the single file. Implement approval and consumer changes first.
### Interfaces and data
REQ-DATA-00dfaad5 and REQ-DATA-ef2f9f01: per-row optional SHA-256 fingerprint of exact UTF-8 source text. Changed known source clears affected text/approval in the current projection. Legacy unbound text stays reviewable and explicit approval binds it; a read never silently grants approval.
REQ-FUNC-7298ddb1: one approved-source projection requires completed status, verified nonempty current chunks and full approval. Character Discovery, Speech Blocks, narrator readiness and workspace evidence use it; export review can still show unapproved text.
REQ-FUNC-8701a2ee and REQ-REL-ed5bc963: compare before/after effective text source at final publication or edit/approval/reset. Stage translation and manifest, retire dependent owned files only when source changes (or reset cannot establish the source); preserve narrator definition. Reuse the Chunking file replacement primitive with operation-specific recovery names. Batch checkpoints remain atomic document writes, with final state and workflow impact published together.
REQ-FUNC-723fdb50 and REQ-FUNC-5aa0c7f3: order paragraphs and smaller spans, count assembled text including separators, fail clearly when an unbreakable token exceeds budget, omit empty chunks from the translation plan.
REQ-FUNC-c07fd83c: optional provider JSON schema plus exact local validation; enforce paragraph count inside each response and rejoin continuations with a space.
REQ-REL-061e8f66: bracket setup and finalization with terminal checkpoint handling. Preserve the original failure if checkpoint writing also fails.
REQ-FUNC-93999a8d: store opaque hash of effective nonsecret request profile, prompts, budget and instructions; disclose a change before the next request, preserving prior completed translations.
REQ-UX-a737a67e and REQ-UX-ea3d3aac: allow confirmed Reset on invalid state. Keep and retry an unsaved draft on write failure, and gate actions requiring a successful flush.
### Files and test seams
New translation document/planning/provider/publication modules. Change current translation orchestration, UI state/controller/page, affected consumer gates, and shared persistence primitive. Use targeted fake-response and filesystem-injection tests, including actual consumer calls. Update both guides and Unreleased.
### Risks and open decisions
INFERRED legacy approvals require explicit re-review because provenance is unknown. Only caught file failures receive rollback; this is not a power-loss journal. Profile-specific token estimates do not prove provider tokenization. Existing workflow remains single-writer via the UI.
### Requirement map
The identifiers beside each decision above map to the named regression selectors in Requirement coverage.
Diagrams: [diagram_TASK-a3c94d07.md](diagram_TASK-a3c94d07.md)


## Log

- 2026-11-09 frame: journal opened
- 2026-11-09 frame: completed; next specify
- 2026-11-09 specify: completed; next design
- 2026-11-09 design: completed; next build
- 2026-11-09 build: red: focused pytest changed_source_disqualifies, legacy_translation_requires, consumers_agree exit 1, stale/legacy approvals counted and consumers disagreed (REQ-DATA-00dfaad5, REQ-DATA-ef2f9f01, REQ-FUNC-7298ddb1)
- 2026-11-09 build: green: three source identity and common source regressions passed (REQ-DATA-00dfaad5, REQ-DATA-ef2f9f01, REQ-FUNC-7298ddb1)
- 2026-11-09 build: red: focused pytest invalidates_speech_without and publication_restores_originals exit 1, Speech Blocks survived approval and final transaction was not used (REQ-FUNC-8701a2ee, REQ-REL-ed5bc963)
- 2026-11-09 build: green: 5 focused provenance/publication tests passed (REQ-FUNC-8701a2ee, REQ-REL-ed5bc963)
- 2026-11-09 build: red: six focused planner, blank-source, malformed-reply, log-failure and policy-change assertions failed for the expected reasons (REQ-FUNC-723fdb50, REQ-FUNC-5aa0c7f3, REQ-FUNC-c07fd83c, REQ-REL-061e8f66, REQ-FUNC-93999a8d)
- 2026-11-09 build: green: six new planning, reply, empty source, failure lifecycle and policy regressions passed; six old fixture assertions still require verified-source shape (REQ-FUNC-723fdb50, REQ-FUNC-5aa0c7f3, REQ-FUNC-c07fd83c, REQ-REL-061e8f66, REQ-FUNC-93999a8d)
- 2026-11-09 build: red: two focused Qt recovery tests fail because invalid Reset is disabled and an autosave OSError escapes while approval dispatches (REQ-UX-a737a67e, REQ-UX-ea3d3aac)
- 2026-11-09 build: green: Qt invalid-reset and failed-autosave regressions passed in the translation page module (REQ-UX-a737a67e, REQ-UX-ea3d3aac)
- 2026-11-09 build: red/green: valid Speech Blocks artifact survived a source-kind transition after a Chunking edit, then passed with checked staged invalidation (REQ-FUNC-8701a2ee). Scope seam includes the existing Chunking edit publication, Home option/project handoff, App Shell and Extraction pending-edit barriers.
- 2026-11-09 build: red/green: final selected-retranslation cancellation retained text but lost accrued usage. Added cancellation-boundary regression and retained usage without replacing text (REQ-REL-061e8f66 and existing REQ-FUNC-a0ab9df4).
- 2026-11-09 build: Focused build proof: 98 translation/UI/Chunking state tests, 29 relevant consumer and recovery tests, and 49 latest translation/state tests passed. Ruff and both audits found no new findings across 29 Python files. Existing 68 code-style and one logging audit findings are unchanged.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Review 1: narrator generation must check project target as well as voice language; translation worker failure must show named recovery error without requiring manifest reload; prevent stale translated Speech Blocks from being reused for a selected resplit or fresh audio/assembly generation. Preserve existing artifacts until reset.
- 2026-11-09 validate: returned to build - Round 1: common source gates for narrator, selected resplit and audio generation, plus recovery dialog
- 2026-11-09 build: RED review 1: 5 intended failures (narrator project-target mismatch, recovery popup attempts refresh, stale translated Speech Blocks reused by selected split / Audio Blocks / Audio Assembly), 2 language control cases pass.
- 2026-11-09 build: Review scope reconciliation: Audio Blocks and Audio Assembly knowledge inspected as downstream creation gates, using Speech Blocks source fingerprint. Existing playback and artifacts remain available.
- 2026-11-09 build: GREEN review 1 (REQ-FUNC-7298ddb1, REQ-REL-ed5bc963): uv run pytest on translation service/controller, narrator generation, selected Speech Blocks re-split, selected Audio Blocks regeneration and Audio Assembly composition exit 0 (87 passed). Verified stale rows cannot mutate outputs and a freshly generated verified source passes. Ruff, style/logging audit delta and strict AEGIS check passed. Evolution reviewed: extra downstream files are generation source guards, EN/RO help and changelog are intentional.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Validate inspection: reviewed source selection, failure and restore paths, guide parity, unchanged release version, the 12 requirement links and reconciled knowledge/context. Evolution confirms changes stay within translation and its consumers. Static warnings: 15 baseline AEGIS warnings plus the two required guide locations and changelog outside configured globs. Ruff and audits report zero newly introduced issues.
- 2026-11-09 validate: DEVIATION validate: full check --run test suite omitted by user request; prove with focused pytest covering AI Translation and affected consumers, plus AEGIS --strict without --run, Ruff and baseline-delta audits.
- 2026-11-09 validate: final: uv run pytest -q (AI Translation service/state/page/controller, Text Chunking state, package version smoke and two Home controller translation handoff tests) exit 0, 110 passed; uv run pytest -q with translation, translated, selective, publication, restore, atomic, selected resplit, skipped chunk regeneration, selected audio regeneration and composition selectors across downstream suites exit 0, 35 passed and 291 deselected. AEGIS check --task TASK-a3c94d07 --strict exit 0, no errors, 15 baseline warnings and 3 required guides/changelog outside configured globs. Ruff, baseline-delta code style and logging audits across 31 Python files, and git diff --check exit 0. No full suite or live provider requests.
- 2026-11-09 validate: completed; next done

## Rulings


## State

status: done
reported: validate - completed
next: implementation guidance complete; commit, push and integration belong to the developer
must_read: .agentic/tasks/TASK-a3c94d07.md
changed: Verified translation approvals, shared narration source, recoverable publication, request validation, EN/RO guides
evidence: Focused pytest: 110 + 35 passed (exit 0); AEGIS strict check, Ruff, audits and git diff --check exit 0.
issues: Full suite omitted as requested; AI responses simulated in tests.
spec_compliance: approved
implementation_quality: approved
review_round: 2

## Delivery report (2026-11-09)

- stage: validate; type: change; path: full; branch: master
- requirements:
  - REQ-DATA-00dfaad5 - Bind approval to current source
  - REQ-DATA-ef2f9f01 - Preserve legacy translations for review
  - REQ-FUNC-7298ddb1 - Resolve approved translation consistently
  - REQ-FUNC-8701a2ee - Invalidate dependent work when effective text changes
  - REQ-REL-ed5bc963 - Recover translation publication
  - REQ-FUNC-723fdb50 - Bound assembled translation requests
  - REQ-FUNC-5aa0c7f3 - Keep empty source chunks out of translation
  - REQ-FUNC-c07fd83c - Reject invalid translation replies
  - REQ-REL-061e8f66 - Close failed translation runs
  - REQ-FUNC-93999a8d - Disclose translation request changes
  - REQ-UX-a737a67e - Allow recovery from an invalid translation document
  - REQ-UX-ea3d3aac - Retain unsaved translation edits after publication errors
- deviations: 1 recorded
  - validate: full check --run test suite omitted by user request; prove with focused pytest covering AI Translation and affected consumers, plus AEGIS --strict without --run, Ruff and baseline-delta audits.
- explicit review: enabled; spec_compliance=approved; implementation_quality=approved; review_round=2
- diff vs task base 5ea3c7f: 56 file(s) changed, 2346 line(s) added
- checks: errors=0 warnings=18 notes=2
- checklist: 8/9 done; open: `report` appended
