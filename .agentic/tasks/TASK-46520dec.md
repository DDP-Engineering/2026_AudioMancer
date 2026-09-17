<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the PolyForm Noncommercial License 1.0.0.
Commercial use requires a separate commercial license.
See the LICENSE.txt in the .agentic folder for full license details.
SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
-->


# TASK-46520dec - Skip Speech Block chunks the provider refuses and surface incomplete coverage

stage: deliver
type: feature
path: full
interaction: autopilot
requirements: REQ-REL-a54e058d, REQ-DATA-2caf6e05, REQ-FUNC-27de7656, REQ-UX-4260d6a4
parent:
branch: master
base: dd7d24509d04bd1a0e3a8d82e1a73bc066aa15bb
opened: 2026-09-17

## Done checklist (current stage)

- [x] diff reviewed semantically against scope, requirements, design and error paths
- [x] component knowledge and project context reconciled with the built candidate
- [x] every requirement re-read; status, prose, affected paths and linked tests current
- [x] manual and inspection verifications completed and recorded
- [x] two independent review verdicts recorded for the current candidate
- [x] `evolution` refreshed and every changed path reviewed
- [x] final proof run on the current candidate, with command and exit recorded
- [x] consolidated validation result logged
- [x] `stage: deliver`

## Frame

Problem: one provider refusal aborts the whole Speech Blocks run. On the
operator's Pride and Prejudice project the ChatGPT-subscription run completed 93
source chunks, failed on `chunk-0139`, and stopped; the remaining 49 chunks were
never attempted (OBSERVED: five `parsed_failure` records for `chunk-0139` and 93
distinct covered chunks in the project's `log_ai_speech_blocks_20260916T200314_0000.log`).

Desired outcome: the run skips a chunk the provider refuses, continues to the
last chunk, records which chunks were skipped, and never presents the stage as
fully split while chunks are missing.

Actors: the operator running Speech Blocks generation; the configured LLM
provider backend.

Primary scenario: operator starts or resumes generation -> the provider fails
for source chunk N -> the service leaves chunk N uncovered, records it as
skipped, and continues with chunk N+1 -> the run reaches the last chunk and
persists a document whose report and operation state name the skipped chunks and
whose stage status is not `completed`.

Examples: `chunk-0139` of the operator's project is refused on every attempt
(OBSERVED: five failures in the operation log, plus one reproduction outside the
application). STATED cause: the ChatGPT subscription backend ends the stream with
`response.incomplete` and `incomplete_details.reason = "content_filter"` when the
model reproduces long verbatim passages of a known published work.

Counterexamples: operator cancellation must still abort the run -
`OperationCancelledError` subclasses `RuntimeError` (OBSERVED:
`05_Software/AudioMancer/src/audiomancer/services/operation_runtime_service.py:131`),
so a broad `except RuntimeError` at the request seam would silently swallow it.
A `ValueError` from the provider facade keeps its existing deterministic
single-block fallback (OBSERVED:
`05_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py:2244`).

In scope:
- per-segment provider-failure handling inside `_generate_budgeted_chunk_blocks`
- generation loop continues past a failed chunk and leaves it uncovered
- skipped chunk identifiers persisted in the authoritative document
- report and operation-state projections expose skipped chunks
- Speech Blocks stage status reflects incomplete source coverage
- operator-visible surfacing of the skipped chunks

Out of scope: AI translation (same provider cause, separate operation);
changing the Speech Blocks prompt or response contract; classifying the provider
`content_filter` condition as its own error code; automatic local-model fallback
routing; retrying the refused chunk inside the same run.

Constraints:
- preserve `REQ-REL-63e230dd`: a compatible `review_pending`/`completed` document
  resumes from the first uncovered source chunk, regenerates each missing chunk
  exactly once, and leaves covered blocks and approvals untouched
- do not change `running`/`failed` checkpoint cursor semantics
- `01_Documentation/Code_Style.md` is binding
- work stays on `master`; no commit, no push

Success signals: a run over a book containing a refused chunk reaches the last
chunk; every other chunk is covered; the skipped chunks are named to the
operator; the stage does not read as completed; a later run regenerates exactly
the skipped chunks and nothing else.

Evidence:
- STATED: the operator wants most of the book converted with the ChatGPT model,
  the skipped chunks converted later with a local model or edited by hand, and
  the operator not misled that everything is split.
- OBSERVED: the generation loop aborts on an uncaught provider error -
  `speech_blocks_service.start_or_continue_generation` -> segment loop in
  `_generate_budgeted_chunk_blocks` -> `_generate_direct_block_response`, which
  catches only `ValueError`.
- OBSERVED: the run's terminal status is `review_pending`
  (`speech_blocks_service.py`, completion tail), and
  `_restore_next_speech_blocks_chunk_index` consults the stored cursor only while
  the status is `running` or `failed`; otherwise it returns the first source
  chunk with no persisted blocks.
- OBSERVED: `_persist_state` composes and writes the whole document, so a
  chunk's partially persisted segment rows disappear when the next persist
  excludes them.
- OBSERVED: the persisted document already carries a top-level `failure` field
  (`.agentic/knowledge/Speech_Blocks.md`, Data Contracts).
- OBSERVED: stage status is `completed` when approved blocks reach the total
  block count (`speech_blocks_report_state_service.py:68`); block coverage of
  source chunks is not part of that decision.
- INFERRED: because a partially covered chunk counts as covered for resume, a
  chunk whose later segment failed must be left wholly uncovered, or its missing
  segment would never be regenerated.

Assumptions: the operator recovers skipped chunks by re-running generation with a
different profile or by editing blocks manually; no in-run retry is wanted.

Unknowns: whether the operator-facing surface should be a dedicated page control
or a warning row plus operation-state field - resolved in `design`.

Decision-blocking questions: none. The user chose this approach explicitly and
gave the recovery workflow.

Proposed behaviors:
1. A provider failure for one source chunk ends that chunk's generation, leaves
   it without persisted blocks, and lets the run continue with the next chunk.
2. The authoritative document records the skipped chunk identifiers for the run.
3. Report and operation state expose the skipped chunks and the uncovered source
   chunk count.
4. Speech Blocks stage status is not `completed` while any current source chunk
   has no blocks.
5. Operator cancellation and the existing `ValueError` fallback keep their
   current behavior.

Path and reason: full.

| criterion | yes | no | evidence |
|---|---|---|---|
| no new externally observable behavior | | no | skipped chunks become visible and the stage stops reading completed |
| no new interface or data format | | no | new skipped-chunk field in the persisted document and its projections |
| no new dependency | yes | | no new package |
| an existing requirement already covers the behavior | | no | no requirement describes skipping a refused chunk |
| no security or data-handling behavior change | yes | | provider payloads and stored artifacts are unchanged in kind |

Any `no` selects the full path.

## Requirement coverage

Behavior inventory:

| Frame outcome | Actor/system | Trigger or state | Response | Positive case | Boundary or failure | Observable result |
|---|---|---|---|---|---|---|
| run survives a refusal | generation service | provider error for one source chunk | drop that chunk, continue | middle chunk refused, run reaches last chunk | refused chunk had a checkpointed earlier segment; operator cancels | every other chunk covered, refused chunk has no blocks |
| skipped chunks are durable | authoritative document | run skipped chunks | record their identifiers | two chunks refused | no chunk refused | reloaded document names exactly those chunks |
| stage is not falsely ready | stage-status projection | a current source chunk has no blocks | withhold completed | all blocks approved but one chunk uncovered | every chunk covered and approved | stage reads in progress, downstream stays gated |
| operator knows what is missing | state notes | document records skipped chunks | name count and identifiers | two skipped chunks | none skipped | notes carry the uncovered count and both identifiers |

Requirement mapping:

| Frame outcome | Atomic behavior | Requirement | Positive case | Boundary or failure | Verification | Design decision or no impact |
|---|---|---|---|---|---|---|
| run survives a refusal | skip the refused chunk and continue to the last chunk, leaving it wholly uncovered | REQ-REL-a54e058d | middle chunk refused, all others covered | partially checkpointed chunk must end uncovered; cancellation still aborts | service regression with a failing fake provider | failure caught at the per-segment request seam, not the chunk loop |
| skipped chunks are durable | persist the skipped source chunk identifiers | REQ-DATA-2caf6e05 | two refused chunks recorded | clean run records none | reload the persisted document | new field on the authoritative document |
| stage is not falsely ready | withhold completed while coverage is incomplete | REQ-FUNC-27de7656 | approved-but-incomplete reads in progress | fully covered and approved reads completed | state projection regression | coverage becomes an input to the stage-status decision |
| operator knows what is missing | name the uncovered chunks in the state notes | REQ-UX-4260d6a4 | notes list both identifiers | fully covered document adds no entry | state notes regression | reuses the existing notes channel, no new page control |

Preserved contracts: REQ-REL-63e230dd (first-uncovered-chunk resume, each missing
chunk regenerated exactly once) and REQ-FUNC-6f65b68e / REQ-FUNC-b355f8e6
(`running`/`failed` checkpoint cursor and segment semantics) are unchanged and
are what make a skipped chunk recoverable in a later run.

## Design

Requirements coverage: REQ-REL-a54e058d -> D1, D2. REQ-DATA-2caf6e05 -> D3.
REQ-FUNC-27de7656 -> D5, no production change. REQ-UX-4260d6a4 -> D4.

Component responsibilities are unchanged. `speech_blocks_service` keeps ownership
of generation, the authoritative document and its projections;
`speech_blocks_state_service` keeps ownership of operator notes; `ui_state_service`
keeps the translation tables. No architecture drawing is owed: this is a behavior
and data change inside existing seams.

**D1 - failure seam (REQ-REL-a54e058d).** The segment loop in
`_generate_budgeted_chunk_blocks` wraps only its `_generate_direct_block_response`
call. `OperationCancelledError` is re-raised before anything else, because it
subclasses `RuntimeError` and would otherwise be swallowed; any other
`RuntimeError` becomes a private `_ChunkGenerationRefusedError` carrying the chunk
identifier. `ValueError` keeps the existing deterministic single-block fallback
inside `_generate_direct_block_response`, untouched. Wrapping the provider call
alone, rather than the whole segment body, keeps a defect in normalization from
being reported as a provider refusal.

**D2 - chunk abandonment (REQ-REL-a54e058d).** The chunk loop in
`start_or_continue_generation` catches `_ChunkGenerationRefusedError`, drops every
in-memory block carrying that chunk identifier, discards it from
`covered_chunk_ids`, appends it to the run's skipped list, persists with
`next_chunk_index = chunk_index + 1` and no active chunk or segment cursor, and
continues with the next chunk. Dropping the blocks matters because
`_persist_segment_progress` may already have checkpointed rows for an earlier
segment of that chunk, and a partially covered chunk counts as covered for resume.
`_persist_state` rewrites the whole document, so those rows leave disk on that
same write.

**D3 - persistence (REQ-DATA-2caf6e05).** No new top-level document field.
`_validate_speech_blocks_document` compares `set(payload)` with
`_SPEECH_BLOCKS_DOCUMENT_FIELDS` for exact equality, so an added field would
reject every document written by an earlier release, including the operator's
in-flight project. The existing `failure` field is validated only as
`null | object` and is otherwise unused, so it carries the record as
`{"skipped_chunk_ids": [...]}`, and stays `None` when nothing was skipped. Round
trip: generation list -> `_build_operation_state_with_prompt_rules` ->
`metadata["skipped_chunk_ids"]` -> `_compose_speech_blocks_document` -> `failure`
-> `_project_operation_state` -> `metadata["skipped_chunk_ids"]`.

**D4 - operator notes (REQ-UX-4260d6a4).** `build_speech_blocks_notes` adds a
summary note carrying the uncovered chunk count
(`len(source_chunks) - report["processed_chunk_count"]`) followed by one entry note
per recorded skipped chunk identifier, mirroring the existing warning summary and
warning entry pattern. Two new keys in both the English and Romanian tables in
`ui_state_service`.

**D5 - stage status needs no production change (REQ-FUNC-27de7656).** Measured, not
assumed: `_project_speech_blocks_report` already derives `processed_chunk_count`
from the distinct chunk identifiers present in the blocks, and
`speech_blocks_report_state_service.rebuild_report` reports `completed` only when
`processed_chunk_count >= total_chunk_count`. A projected document with two of
three chunks covered and every block approved returns `in_progress`; the fully
covered equivalent returns `completed`. The behavior is currently incidental and
unowned by any requirement, so build adds the regression that locks it rather than
new production code.

**Data ownership and state transitions.** The run still ends `review_pending`.
That is deliberate: `_restore_next_speech_blocks_chunk_index` consults the stored
cursor only while the status is `running` or `failed`, so a `review_pending`
document with holes resumes at the first uncovered source chunk and regenerates
exactly the skipped chunks, once each - REQ-REL-63e230dd unchanged and doing the
recovery work.

**Failure recovery.** No in-run retry: the refusal is content-dependent and the
same chunk failed every attempt in the operator's project. Recovery is a later run,
optionally on a different profile, or manual block editing.

**Compatibility.** Documents written before this change carry `failure: null` and
project an empty skipped list; no migration. A document written after this change
remains loadable by an earlier release, which ignores the field content but
rewrites it to `null` on its next persist. Accepted: the record is advisory and
the coverage itself is the durable truth.

**Observability.** The operation log already writes a `failure` exchange row per
refused segment; the persisted skipped list is its durable operator-facing
counterpart.

**Test seams.**

- REQ-REL-a54e058d - `tests/test_speech_blocks_service.py`: a fake provider that
  raises for one middle chunk; a second case where that chunk already has
  checkpointed rows; a third where the seam raises `OperationCancelledError`.
- REQ-DATA-2caf6e05 - `tests/test_speech_blocks_service.py`: reload the persisted
  document and read back the identifiers; a clean run records none.
- REQ-FUNC-27de7656 - `tests/test_speech_blocks_service.py`: project an
  all-approved document with and without a hole.
- REQ-UX-4260d6a4 - `tests/test_speech_blocks_state_service.py`: notes built from
  a state carrying two skipped identifiers, and from a fully covered state.

**Expected files.**

- `05_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/speech_blocks_state_service.py`
- `05_Software/AudioMancer/src/audiomancer/services/ui_state_service.py`
- `05_Software/AudioMancer/tests/test_speech_blocks_service.py`
- `05_Software/AudioMancer/tests/test_speech_blocks_state_service.py`

**Alternatives and tradeoffs.**

- Write deterministic narrator blocks for the refused chunk instead of skipping it.
  Rejected by the user: it marks the chunk covered and hides the gap, and the
  operator wants to convert those passages with a different model or by hand.
- Add a dedicated top-level document field. Rejected: the strict root contract is
  an exact set comparison, so it would reject every existing project document.
- Retry the refused chunk inside the same run. Out of scope; measured as
  content-dependent and repeatedly unsuccessful for the same chunk.

**Risks.**

- R1 - a `RuntimeError` from a defect rather than the provider would be recorded as
  a refusal. Bounded by wrapping only the provider call.
- R2 - `sync_manifest_operation_summary` still advances the manifest summary at the
  end of a run containing skipped chunks. The stage status projection is the gate
  that keeps the plan visibly incomplete; the manifest summary is unchanged by this
  task. Accepted.

**Open decisions.** None.

## Log

- 2026-09-17 frame: scope accepted from the user's explicit choice - skip a refused chunk,
  keep the rest of the run, and never show the stage as fully split. Full path: the change
  adds observable behavior, a new persisted field and new projections. Autopilot recorded
  for this task on the user's instruction to implement it end to end; delivery stops before
  any commit. DEVIATION frame: working on `master` instead of a task branch, standing
  repository instruction from the user.
- 2026-09-17 specify: created 4 requirements (1 reliability, 1 data, 1 functional, 1 ux),
  revised 0, reused 0, retired 0. No spec written: the behaviors are carried by their own
  prose and the persisted-field shape is a single identifier list. Existing broad report and
  notes requirements were read and not reused - their semantics do not name coverage or
  skipped chunks. `check` reports errors=0.
- 2026-09-17 design: note recorded in `## Design`; no spec. Measured during design that the
  report projection already derives processed chunks from block coverage, so REQ-FUNC-27de7656
  is a regression-only requirement. The skipped-chunk record reuses the existing `failure`
  document field because the root contract is an exact field-set comparison.
- 2026-09-17 build red: REQ-REL-a54e058d, REQ-DATA-2caf6e05, REQ-UX-4260d6a4;
  command=`uv run pytest -q tests/test_speech_blocks_service.py tests/test_speech_blocks_state_service.py`
  limited to the seven new selectors; exit=1; 4 failed, 3 passed. Expected missing behavior: the
  provider RuntimeError propagates out of `start_or_continue_generation` instead of skipping the
  chunk, no skipped-chunk record reaches the document, and the notes carry no skipped entry. The
  three passing selectors are the guard cases - cancellation already aborts, and the coverage-derived
  projection already withholds `completed` (REQ-FUNC-27de7656, regression-only as designed).
- 2026-09-17 build green: REQ-REL-a54e058d, REQ-DATA-2caf6e05, REQ-FUNC-27de7656, REQ-UX-4260d6a4;
  command=`uv run pytest -q tests/test_speech_blocks_service.py tests/test_speech_blocks_state_service.py
  tests/test_speech_blocks_report_state_service.py tests/test_speech_blocks_single_document_contract.py
  tests/test_ui_state_service.py tests/test_localization_parity.py tests/test_ui_localization_coverage.py`;
  exit=0; 157 passed. `uv run ruff check` and `uv run python -m py_compile` on the five changed files
  both clean.
- 2026-09-17 build: the first green run exposed a real defect the design had not named - the completion
  report passed `len(source_chunks)` as the processed count, so a run with skipped chunks still returned
  a full-coverage report to its caller even though the reloaded projection was correct. Completion now
  reports the distinct covered chunk identifiers, matching the projection.
- 2026-09-17 build: DEVIATION recorded - verification narrowed to the targeted modules above instead of
  the 63-file impacted set, on the user's explicit instruction to avoid long runs and test the app by
  hand. The unrun impacted files are Qt page and controller suites that no changed file's requirement
  links to. `evolution` lists only the three source files because the anchor was taken after the tests
  were written, as the build step directs.
- 2026-09-17 validate: review round 1. spec_compliance=approved - scope, exclusions and all four
  requirements match the built candidate; AI translation, the prompt and response contract, provider
  error classification, fallback routing and in-run retry all stayed out. implementation_quality=
  approved after one in-stage fix.
- 2026-09-17 validate finding (fixed in stage): the diff review found `regenerate_chunk_speech_blocks`
  still writing `failure: None`, so regenerating any single chunk erased the skipped-chunk record - the
  erasure risk the design named. It now carries the record forward through
  `_uncovered_skipped_chunk_ids`, and a new regression covers the operator's real recovery path:
  regenerate a skipped chunk, see it covered and dropped from the record while the other skipped chunk
  remains.
- 2026-09-17 validate: `.agentic/knowledge/Speech_Blocks.md` Data Contracts reconciled with the built
  behavior; no architecture drawing owed, the change adds no structure.
- 2026-09-17 validate final: command=`uv run pytest -q tests/test_speech_blocks_service.py
  tests/test_speech_blocks_state_service.py tests/test_speech_blocks_report_state_service.py
  tests/test_speech_blocks_single_document_contract.py tests/test_ui_state_service.py
  tests/test_localization_parity.py tests/test_ui_localization_coverage.py`; exit=0; 158 passed.
  `uv run ruff check` and `uv run python -m py_compile` clean on every changed file.
  `python .agentic/aegis.py check --task TASK-46520dec --strict`: errors=0, strict: ok; the ten
  remaining warnings belong to other tasks and to the untracked `.agentic/rtm.*` files.
- 2026-09-17 validate: DEVIATION - `check --task ... --strict --run` was not used, because its
  configured full verification is the long suite the user ruled out. Substituted the targeted modules
  above plus the strict advisory catalog without `--run`. Cost: the Qt page and controller suites are
  unproven for this candidate; the user verifies the application by hand.
- 2026-09-17 validate: the round 1 verdicts were withdrawn on the user's challenge. They had been
  written from one combined diff-review pass rather than the two independent reviews the review
  contract requires, so they did not describe two reviews and are corrected here.
- 2026-09-17 validate: review round 1 re-run properly. spec_compliance=changes_required.
  REQ-REL-a54e058d requires generation to continue through the last chunk after a provider failure,
  but `_generate_scene_ambience_blocks` caught only `OperationCancelledError`, so a refusal during
  scene-ambience analysis still ended the run. Scene ambience is enabled on the operator's live
  project, so every chunk made a second unguarded provider call. The design and the single review
  pass shared the blind spot: both read the Frame's in-scope seam rather than the requirement.
  implementation_quality=approved with one minor finding - `skipped_chunk_ids` was seeded from
  `existing_state` unconditionally while blocks and cursor come from `_restore_resume_state`, which
  discards an incompatible snapshot, so a fresh run after re-chunking could start with stale ids.
- 2026-09-17 build: fixed only those two findings on the user's choice of the whole-chunk reading.
  `_generate_scene_ambience_blocks` now converts a provider `RuntimeError` into
  `_ChunkGenerationRefusedError`, and its request moved inside the chunk's own try so one handler
  owns both refusals and the chunk is skipped entire. The skipped-chunk seed now follows the same
  compatibility gate as the blocks it describes. REQ-REL-a54e058d prose and verification widened to
  name the scene-ambience request.
- 2026-09-17 build red/green: the new ambience regression passes with the guard and fails without it
  - the guard was removed temporarily and
  `uv run pytest -q tests/test_speech_blocks_service.py::test_scene_ambience_refusal_skips_the_chunk_without_ending_the_run`
  exited 1 with the provider `RuntimeError` escaping generation, then exited 0 once restored.
- 2026-09-17 validate: review round 2 on the fixed candidate, run as two separate passes.
  spec_compliance=approved - a systematic audit found exactly two `llm_provider_service.chat_json`
  call sites in the module, `_generate_direct_block_response` and `_generate_scene_ambience_blocks`,
  and both are now guarded; no excluded behavior was added. implementation_quality=approved - the
  minor seed finding is fixed and the two functions that now raise the refusal document it in their
  `@exception` contracts.
- 2026-09-17 validate final: command=`uv run pytest -q tests/test_speech_blocks_service.py
  tests/test_speech_blocks_state_service.py tests/test_speech_blocks_report_state_service.py
  tests/test_speech_blocks_single_document_contract.py tests/test_ui_state_service.py
  tests/test_localization_parity.py tests/test_ui_localization_coverage.py`; exit=0; 159 passed.
  `uv run ruff check` and `uv run python -m py_compile` clean on every changed file.
  The targeted-verification deviation recorded above still stands for this candidate.

## Rulings


## Handoff


current: deliver
status: ready
next: write the CHANGELOG Unreleased entry, run the delivery report, stage the files and hand back a commit message without committing
must_read: .agentic/steps/6_deliver.md, CHANGELOG.md, .agentic/PROJECT.md
blockers: none

## Stage report

stage: validate
result: completed
current: deliver
changed: 05_Software/AudioMancer/src/audiomancer/services/speech_blocks_service.py, 05_Software/AudioMancer/src/audiomancer/services/speech_blocks_state_service.py, 05_Software/AudioMancer/src/audiomancer/services/ui_state_service.py, 05_Software/AudioMancer/tests/test_speech_blocks_service.py, 05_Software/AudioMancer/tests/test_speech_blocks_state_service.py, CHANGELOG.md, .agentic/knowledge/Speech_Blocks.md, 4 requirement files, .agentic/tasks/TASK-46520dec.md
evidence: uv run pytest -q on the seven targeted modules, exit=0, 159 passed; the ambience regression proved red without its guard and green with it; ruff check and py_compile clean on all changed files; aegis check --task TASK-46520dec --strict, errors=0, strict: ok
issues: full impacted set (63 files) not run - the user limited verification to targeted tests and will exercise the application by hand
next: deliver - present the corrected candidate, stage the files and hand back a commit message without committing
needs_user: yes
spec_compliance: approved
implementation_quality: approved
review_round: 2
## Delivery report (2026-09-17)

- stage: deliver; type: feature; path: full; branch: master
- requirements:
  - REQ-REL-a54e058d - Continue Speech Blocks generation past a refused source chunk
  - REQ-DATA-2caf6e05 - Persist skipped Speech Block source chunks in the authoritative document
  - REQ-FUNC-27de7656 - Withhold Speech Blocks completion while source coverage is incomplete
  - REQ-UX-4260d6a4 - Name the skipped Speech Block source chunks to the operator
- deviations: 1 recorded
  - frame: working on `master` instead of a task branch, standing repository instruction from the user.
- explicit review: enabled; spec_compliance=approved; implementation_quality=approved; review_round=1
- diff vs task base dd7d245: 16 file(s) changed, 3045 line(s) added; 2 file(s) not content-scanned
- checks: errors=0 warnings=10 notes=1
- checklist: 9/9 done
