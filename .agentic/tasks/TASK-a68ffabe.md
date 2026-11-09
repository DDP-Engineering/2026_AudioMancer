# TASK-a68ffabe - Keep Character Discovery identities, overlap and evidence editable

stage: done
type: change
path: full
interaction: autopilot
requirements: REQ-FUNC-09974cdc, REQ-REL-50ad0471, REQ-FUNC-fb85b972, REQ-FUNC-2fa97648
parent:
branch: master
base: 5d69efb0269e283f75a0d5baec0f873bf920bb77
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

Problem: OBSERVED distinct candidates can share a slug and one is dropped. Resume skips the next window's overlap. The Evidence panel is a source preview and cannot save corrections.
Desired outcome: STATED unique IDs, retained overlap, editable evidence, and the existing text-source policy.
Actors: AudioMancer operator reviewing characters.
Primary scenario: Start, cancel and resume Discovery, then correct an evidence excerpt in Edit Character.
Examples: Li and Éli both survive synthesis. Resume after [1,2,3] starts at 3 when the next window overlaps by one.
Counterexamples: Established alias grouping and explicitly narration-only exclusions remain intact. A bad AI citation can leave an editable blank excerpt.
In scope: Unique ID allocation across persisted profiles and synthesis reservations, window cursor, permissive citation grounding and editable excerpts using the existing character draft and Save action.
Out of scope: STATED keep the simple variant and source rule. No downstream publication redesign, new AI calls or approval barriers, or commit.
Constraints: STATED AEGIS autopilot and focused tests. OBSERVED current default branch master. No document schema change or new dependencies.
Success signals: Distinct colliding names persist; resumed request keeps overlap; valid excerpts cite source, uncertain excerpts can be corrected or added; translation eligibility tests pass.
Evidence: Source and synthetic checks from previous analysis of character_discovery_service.py, CharactersPage._show_selected_evidence read-only.
Assumptions: Editable evidence means its excerpt is editable; canonical source text remains separate.
Unknowns: Model quality remains provider-dependent.
Decision-blocking questions: None.
Proposed behaviors: Reserve IDs, persist next window start, show an excerpt field inside Edit Character.
Path and reason: Full. Externally observable behavior: yes. New interface/data format: visible excerpt editor, unchanged JSON. New dependencies: no. Existing requirements alone: insufficient. Security/data handling: project-local evidence remains in the existing record.

## Requirement coverage

| Behavior | Requirement | Design |
|---|---|---|
| Allocate unique Character Discovery IDs | REQ-FUNC-09974cdc | Reuse slug suffix allocation and reserve IDs |
| Resume Character Discovery with window overlap | REQ-REL-50ad0471 | Persist the actual next window start |
| Keep uncertain character evidence reviewable and editable | REQ-FUNC-fb85b972 | Source-ground the AI excerpt where available and reuse draft save |
| Preserve the Character Discovery text source rule | REQ-FUNC-2fa97648 | Leave the shared resolver intact |

## Design

### Approach
Reuse suffix allocation for automated and manual IDs. Reserve stored inventory
and pending synthesis identities. Keep existing Unicode grouping and ordering.
Checkpoint the actual next planned window's start to preserve overlap.

### Interfaces and data
Retain the existing document fields, workflow states, and source resolver.
Resolve citations against the current window; keep a speaker claim reviewable
when the excerpt cannot be grounded. Synthesis uses but does not replace evidence.
The Characters page shows the source separately from the editable excerpt.
The existing draft/save flow stores a corrected excerpt, or a manual evidence
note when none exists. No extra confirmation or provider request.

### Files and test seams
Change character_discovery_service and Characters page/controller; add English
and Romanian labels. Exercise real mocked runs, page draft/save, and existing
source selection tests. Shared translation resolver remains reused.

### Risks and open decisions
A checkpoint already written by the old version resumes at its stored cursor.
New checkpoints store the next window start. No inventory migration.
Preserve checkpoint indices and durable character IDs when allocating new IDs.

### Requirement map
REQ-FUNC-09974cdc: unique allocation and reservations.
REQ-REL-50ad0471: actual next window start.
REQ-FUNC-fb85b972: source-grounded AI citations and user draft editing.
REQ-FUNC-2fa97648: unchanged shared source eligibility.

Diagrams: [diagram_TASK-a68ffabe.md](diagram_TASK-a68ffabe.md)

## Log

- 2026-11-09 frame: journal opened
- 2026-11-09 frame: completed; next specify
- 2026-11-09 specify: completed; next design
- 2026-11-09 design: completed; next build
- 2026-11-09 build: red: five focused pytest cases fail as expected: only one ID survives, Romanian span absent, resume cursor misses overlap, and evidence editor is absent (REQ-FUNC-09974cdc, REQ-REL-50ad0471, REQ-FUNC-fb85b972).
- 2026-11-09 build: green: focused service, state, page, shared-source and two controller-save pytest selectors exit 0 (96 passed). Ruff and diff --check exit 0. Evolution reviewed; no source resolver or format changes. Advisory baseline warnings and expected docs paths remain.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Validate inspection: ten product paths match the design and docs cover the existing save flow. Source resolver and persisted schema remain intact. No new Ruff, style or logging audit issues across seven Python files. AEGIS advisories: 15 baseline and 3 expected bilingual help/changelog paths outside layout.
- 2026-11-09 validate: Review 1: a bare confidence token or null span in an unresolved citation could keep a narration-only candidate. Retain actual reported speaker clues without admitting confidence-only or null-span narration.
- 2026-11-09 validate: returned to build - Distinguish unresolved dialogue clues from confidence-only narration
- 2026-11-09 build: red review 1: evidence regression rejects neither confidence-only narration nor a null span before the fix; focused pytest exit 1.
- 2026-11-09 build: green review 1: 94 focused service/state/page/shared-source tests exit 0, including confidence-only and null-span narration controls; Ruff, diff and strict check exit 0. Original two controller-save cases remain green from unchanged controller/page implementation.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Reconciled validation after review fix: only the evidence predicate and its test changed. Existing manual draft behavior, persisted source rule and schema remain as documented.
- 2026-11-09 validate: Review 2: outside-window reason-only text saying no dialogue is misclassified by the old keyword heuristic. Limit ungrounded fallback to reported quotation or nonempty span, preserve the reason fallback for in-window evidence.
- 2026-11-09 validate: returned to build - Keep outside-window narration-only comments out of the speaker list
- 2026-11-09 build: red review 2: exact out-of-window no-dialogue assertion fails before correction; focused pytest exit 1.
- 2026-11-09 build: green review 2: 94 focused service/state/page/shared-source tests exit 0, including explicit outside-window no-dialogue control. Ruff, diff and strict AEGIS check exit 0. Only the evidence predicate and test changed.
- 2026-11-09 build: completed; next validate
- 2026-11-09 validate: Validate reconciliation after round 2: source rule, JSON format, editor, and all docs unchanged. Narration control now preserves the existing exclusion without a new language-specific gate.
- 2026-11-09 validate: DEVIATION validate: user requested only relevant tests, so omit full check --run. Prove with focused service/state/page/controller, common source and help version tests, Ruff, baseline-delta audits and strict AEGIS check.
- 2026-11-09 validate: final: uv run pytest on Character Discovery service/state, Characters page, shared approved-source and package metadata tests exit 0 (95 passed). Controller pytest -k save or edit or selection exit 0 (8 passed, 9 deselected). Ruff and baseline-delta audits on seven Python files exit 0 with no new findings; git diff --check and AEGIS check --strict exit 0. AEGIS warnings: 15 baseline plus intentional EN/RO guide and changelog paths. No live model calls. Existing discovery checkpoints use their stored cursor for first resume; new checkpoints preserve overlap.
- 2026-11-09 validate: completed; next done

## Rulings


## State

status: done
reported: validate - completed
next: implementation guidance complete; commit, push and integration belong to the developer
must_read: .agentic/tasks/TASK-a68ffabe.md
changed: Unique character IDs, overlapped resume, editable evidence, unchanged source rule.
evidence: 103 focused tests passed; Ruff, audit delta, diff and AEGIS strict checks passed.
issues: Full suite omitted as requested; provider replies simulated.
spec_compliance: approved
implementation_quality: approved
review_round: 3

## Delivery report (2026-11-09)

- stage: validate; type: change; path: full; branch: master
- requirements:
  - REQ-FUNC-09974cdc - Allocate unique Character Discovery IDs
  - REQ-REL-50ad0471 - Resume Character Discovery with window overlap
  - REQ-FUNC-fb85b972 - Keep uncertain character evidence reviewable and editable
  - REQ-FUNC-2fa97648 - Preserve the Character Discovery text source rule
- deviations: 1 recorded
  - validate: user requested only relevant tests, so omit full check --run. Prove with focused service/state/page/controller, common source and help version tests, Ruff, baseline-delta audits and strict AEGIS check.
- explicit review: enabled; spec_compliance=approved; implementation_quality=approved; review_round=3
- diff vs task base 5d69efb: 19 file(s) changed, 564 line(s) added
- checks: errors=0 warnings=18 notes=2
- checklist: 8/9 done; open: `report` appended
